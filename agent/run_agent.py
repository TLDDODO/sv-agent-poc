from __future__ import annotations
import argparse
import json
from pathlib import Path

from .llm_client import make_client, MODEL
from .tools import TOOLS, DISPATCH

SYSTEM_PROMPT = """You are an interface-adjudication agent. You do not predict
interfaces yourself; several prediction tools do that, and you compare and
adjudicate them.

Drive the whole task by calling tools, in whatever order you judge best:
- list the available interface-prediction tools,
- get each tool's per-residue scores,
- fetch the PDB structures to confirm the system,
- map the predicted residues to canonical UniProt numbering and check they fall
  inside the binding domain,
- then REASON over the per-residue scores: residues all tools score high are the
  consensus interface; residues where tools strongly disagree are disputed and
  must be flagged for MD/experiment; lower your confidence when disputes are
  unresolved.

Rules: use ONLY values returned by tools - never invent residues or scores. When
done, call submit_adjudication exactly once."""


def run(user_goal: str, max_steps: int = 16, verbose: bool = True):
    client = make_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_goal},
    ]
    trace = []
    result = None

    for step in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS,
            tool_choice="auto", temperature=0)
        msg = resp.choices[0].message
        messages.append(msg.model_dump())

        if not msg.tool_calls:
            result = {"final_text": msg.content}
            if verbose:
                print(f"[step {step}] AGENT (no tool) -> {msg.content[:200]}")
            break

        done = False
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            trace.append({"step": step, "tool": name, "args": args})
            if verbose:
                print(f"[step {step}] AGENT calls {name}({json.dumps(args)[:160]})")

            if name == "submit_adjudication":
                result = args
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "ok"})
                done = True
                break

            out = DISPATCH[name](**args) if name in DISPATCH else {"error": f"unknown tool {name}"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})

        if done:
            break

    return result, trace


def render(goal: str, result: dict, trace: list) -> str:
    steps = "\n".join(
        f"{i+1}. **{t['tool']}**({json.dumps(t['args'])[:120]})" for i, t in enumerate(trace))
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

_The DeepSeek agent drove this end to end: it chose which tools to call, observed
the results, and reasoned its way to the verdict below. The numeric data comes
from tools; the decisions are the model's._

## Agent loop (tool calls, in order)
{steps}

## Adjudication
{body}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="DeepSeek-driven interface adjudication agent")
    ap.add_argument("--goal", default=(
        "Adjudicate the FAT10 (UniProt O15205) N-terminal ubiquitin-like domain "
        "(residues 1-80) interface with MAD2 (UniProt Q13257): compare the available "
        "prediction tools and decide the consensus interface vs disputed residues."))
    ap.add_argument("--max-steps", type=int, default=16)
    args = ap.parse_args()

    result, trace = run(args.goal, max_steps=args.max_steps)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / "agent_trace.json").write_text(
        json.dumps({"goal": args.goal, "trace": trace, "result": result}, indent=2),
        encoding="utf-8")
    (out / "agent_report.md").write_text(render(args.goal, result, trace), encoding="utf-8")

    print("\nWROTE outputs/agent_trace.json")
    print("WROTE outputs/agent_report.md")
    print(json.dumps(result, indent=2)[:800])


if __name__ == "__main__":
    main()
