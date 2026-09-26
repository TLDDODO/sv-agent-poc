from __future__ import annotations
import argparse
import json
from pathlib import Path

from .llm_client import make_client, MODEL
from .cases import Case, default_case, find_case, reset_active_case, set_active_case
from . import events, leakage
from .tools import TOOLS, DISPATCH, tools_for
from .skills import load_skill
from .runlog import RunRecorder

# Defined in skills/investigator.md (the real source); inline text is fallback.
SYSTEM_PROMPT = load_skill("investigator",
    "You are an autonomous interface-investigation agent. Decide which tools to call "
    "and in what order. Never invent residues or scores — every number comes from a "
    "tool. There is no experimental FAT10-MAD2 complex, so nothing is ground truth: "
    "report contradictions as fact, do not declare a winner, recommend an experiment. "
    "Think step by step before each tool call. When done, call submit_adjudication once.")


def _reasoning_of(msg) -> str | None:
    """DeepSeek-R1 returns the chain-of-thought in `reasoning_content`."""
    val = getattr(msg, "reasoning_content", None)
    if val:
        return val
    extra = getattr(msg, "model_extra", None) or {}
    return extra.get("reasoning_content")


# Benchmark pairs: same loop, a generic prompt (skills/pair_investigator.md).
PAIR_PROMPT = load_skill("pair_investigator",
    "You are an autonomous interface-investigation agent. Predict, for each of two "
    "proteins, the sequence region that forms their interface. Every fact comes from a "
    "tool; tools with no data report 'pending'. Submit once with submit_adjudication.")


def run(user_goal: str, model: str = MODEL, max_steps: int = 16, verbose: bool = True,
        case: Case | None = None):
    case = case or default_case()
    token = set_active_case(case)               # the tools act on this protein pair, for this run only
    leakage.clear_cache()                       # the leak filter's live PDBe lookups are per run
    try:
        return _loop(user_goal, model, max_steps, verbose, case)
    finally:
        reset_active_case(token)


MAX_EMPTY_RESUBMITS = 2      # times an empty residue list is sent back before it is marked as missing


def _md_seen(transcript: list) -> bool:
    """True once a get_md_interface_scores result with real occupancy values is in the transcript."""
    return any(a["tool"] == "get_md_interface_scores" and isinstance(a.get("result"), dict)
               and a["result"].get("occupancy") for e in transcript for a in e["actions"])


def _loop(user_goal: str, model: str, max_steps: int, verbose: bool, case: Case):
    tools = tools_for(case)
    client = make_client()
    messages = [
        {"role": "system", "content": PAIR_PROMPT if case.generic else SYSTEM_PROMPT},
        {"role": "user", "content": user_goal},
    ]
    transcript = []   # rich per-step record incl. the agent's reasoning
    result = None
    rec = RunRecorder("agent", model, user_goal, case.id)
    empty_resubmits = 0

    for step in range(max_steps):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools,
            tool_choice="auto", temperature=0)
        rec.llm(resp)
        msg = resp.choices[0].message
        messages.append(msg.model_dump())

        entry = {
            "step": step,
            "reasoning": _reasoning_of(msg),       # R1 chain-of-thought, if any
            "thought": msg.content,                # the model's own written reasoning
            "actions": [],
        }
        if verbose and (msg.content or entry["reasoning"]):
            print(f"[step {step}] THINK: {(entry['reasoning'] or msg.content or '')[:200]}")

        if not msg.tool_calls:
            result = {"final_text": msg.content}
            transcript.append(entry)
            break

        done = False
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if verbose:
                print(f"[step {step}] CALL {name}({json.dumps(args)[:160]})")
            rec.tool(name)
            events.emit("tool_call", tool=name, args=args)

            if name == "submit_adjudication":
                # MD data was retrieved but no residues were submitted: send it back (twice at most),
                # then keep the submission and mark it, never fill the list in ourselves.
                if (not case.generic and not args.get("consensus_interface")
                        and _md_seen(transcript + [entry])):
                    if empty_resubmits < MAX_EMPTY_RESUBMITS:
                        empty_resubmits += 1
                        entry["actions"].append({"tool": name, "args": args, "rejected": "empty consensus_interface"})
                        events.emit("resubmit_requested", attempt=empty_resubmits)
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({
                            "error": "rejected: consensus_interface is empty although MD contact data was "
                                     "retrieved. Submit again with the residues you conclude form the "
                                     "interface (list the disputed ones in `disputed`)."})})
                        continue
                    args = dict(args, residues_missing=True)
                result = args
                entry["actions"].append({"tool": name, "args": args})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "ok"})
                done = True
                break

            if case.generic:
                # only schema arguments: no off-schema path arguments (e.g. scores_path)
                allowed = next((t["function"]["parameters"]["properties"] for t in tools
                                if t["function"]["name"] == name), {})
                args = {k: v for k, v in args.items() if k in allowed}
            out = DISPATCH[name](**args) if name in DISPATCH else {"error": f"unknown tool {name}"}
            if case.generic and name == "map_residues" and not {"domain_lo", "domain_hi"} <= args.keys():
                out = {"error": "domain_lo and domain_hi are required for this protein pair"}
            if case.benchmark:
                out = leakage.guard(out, case)  # never show a held-out complex to the agent
            entry["actions"].append({"tool": name, "args": args, "result": out})
            events.emit("tool_result", tool=name, args=args, result=out)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})

        transcript.append(entry)
        if done:
            break

    rec.finish(result)
    return result, transcript


def render(goal: str, model: str, result: dict, transcript: list) -> str:
    steps = []
    for e in transcript:
        line = [f"### Step {e['step']}"]
        if e.get("reasoning"):
            line.append(f"_chain-of-thought:_ {e['reasoning']}")
        elif e.get("thought"):
            line.append(f"_reasoning:_ {e['thought']}")
        for a in e["actions"]:
            line.append(f"- **{a['tool']}**({json.dumps(a['args'])[:140]})")
        steps.append("\n\n".join(line))
    steps_md = "\n\n".join(steps)

    if result and "consensus_interface" in result:
        body = f"""**Consensus interface:** {', '.join(result.get('consensus_interface', [])) or '-'}
**Disputed (flag for MD / experiment):** {', '.join(result.get('disputed', [])) or '-'}
**Weak / ambiguous:** {', '.join(result.get('weak', []) or []) or '-'}
**Confidence:** {result.get('confidence', '-')}

**Flags:**
{chr(10).join('- ' + f for f in result.get('flags', []) or []) or '- none'}

**Agent reasoning:**
{result.get('reasoning', '-')}"""
    else:
        body = "**Agent final message:**\n\n" + (result or {}).get("final_text", "(no result)")

    return f"""# Agentic Interface Adjudication

**Goal:** {goal}
**Model:** `{model}`

_The agent drove this end to end: it chose which tools to call, recorded its
reasoning at each step, and reached the verdict below. Numeric data comes from
tools; the decisions are the model's._

## Agent loop (reasoning + tool calls, in order)
{steps_md}

## Adjudication
{body}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="DeepSeek-driven interface adjudication agent")
    ap.add_argument("--goal", default=(
        "Investigate where MAD2 (UniProt Q13257) binds FAT10 (UniProt O15205): find "
        "where the literature expects the interface, get the real MD contact evidence, "
        "and determine whether the current model's interface is consistent with the "
        "literature. If they conflict, convene the debate and reach a calibrated verdict."))
    ap.add_argument("--case", default=None, help="case id in cases/ or benchmark/ (default: FAT10-MAD2)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-steps", type=int, default=16)
    args = ap.parse_args()

    case = find_case(args.case) if args.case else None
    if case and args.goal == ap.get_default("goal"):
        args.goal = case.goal
    result, transcript = run(args.goal, model=args.model, max_steps=args.max_steps, case=case)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / "agent_trace.json").write_text(
        json.dumps({"goal": args.goal, "model": args.model,
                    "transcript": transcript, "result": result}, indent=2),
        encoding="utf-8")
    (out / "agent_report.md").write_text(
        render(args.goal, args.model, result, transcript), encoding="utf-8")

    print("\nWROTE outputs/agent_trace.json")
    print("WROTE outputs/agent_report.md")
    print(json.dumps(result, indent=2)[:800])


if __name__ == "__main__":
    main()
