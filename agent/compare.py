"""Weak-vs-strong model comparison for the adjudication (decision) step.

Evidence is gathered ONCE (deterministically, via the same tools the agent uses),
then the identical evidence is handed to a weak model and a strong model. Only the
interpretation/decision varies, so 'where the weak model breaks' becomes visible.
This also works with models that lack tool-calling (e.g. deepseek-reasoner).
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

from .llm_client import make_client
from .tools import _predictions, validate_residues, fetch_structures, map_residues

# Per-tool caveats attached to the evidence bundle (kept here to keep the agent
# package self-contained). Only tools with real per-residue scores appear.
_CAVEATS = {
    "AlphaFold-Multimer":
        "AF-Multimer interface confidence is model-derived, not experimental, and "
        "can be overconfident on shallow or transient interfaces.",
    "HADDOCK":
        "HADDOCK scores depend on the input restraints and sampling; they reflect "
        "docking energetics, not direct observation.",
    "PISA-contacts":
        "PISA contacts come from a single static pose; they are sensitive to which "
        "docked model was chosen.",
}


def gather_evidence(uniprot: str, domain=(1, 80)) -> tuple[list, dict]:
    preds = _predictions()
    residues = sorted({r for scores in preds.values() for r in scores},
                      key=lambda x: int(re.sub(r"\D", "", x) or 0))
    evidence = {
        "uniprot": uniprot,
        "tools": {t: {"scores": preds[t], "caveat": _CAVEATS.get(t, "")} for t in preds},
        "residue_validation_vs_uniprot": validate_residues(uniprot, residues),
        "canonical_mapping": map_residues(residues, uniprot, domain[0], domain[1]),
        "pdbe_structures": fetch_structures(uniprot),
    }
    return residues, evidence


_PROMPT = """You are adjudicating which residues of a protein form its interface,
by comparing several prediction tools. Use ONLY the evidence below; never invent
residues or scores.

EVIDENCE (JSON):
{evidence}

Decide:
- consensus_interface: residues all tools score high (>= 0.6)
- disputed: residues where tools strongly disagree (score spread > 0.3)
- weak: ambiguous; no tool is decisive
- confidence: 0..1; lower it if disputes are unresolved OR if
  residue_validation_vs_uniprot shows mismatches (data may not match the real protein)
- flags: anything needing human / MD / experimental confirmation
- reasoning: short, grounded in the evidence

Respond with ONLY a JSON object with keys:
consensus_interface, disputed, weak, confidence, flags, reasoning."""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"error": "no JSON in response", "raw": (text or "")[:500]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return {"error": f"json parse: {exc}", "raw": (text or "")[:500]}


def _reasoning_of(msg) -> str | None:
    val = getattr(msg, "reasoning_content", None)
    if val:
        return val
    extra = getattr(msg, "model_extra", None) or {}
    return extra.get("reasoning_content")


def adjudicate(model: str, evidence: dict) -> dict:
    client = make_client()
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": _PROMPT.format(
            evidence=json.dumps(evidence, indent=2))}])
    msg = resp.choices[0].message
    return {"model": model, "adjudication": _extract_json(msg.content),
            "chain_of_thought": _reasoning_of(msg), "raw": msg.content}


def diff(weak: dict, strong: dict) -> dict:
    def field(x, k):
        return set((x.get("adjudication") or {}).get(k, []) or [])
    wc, sc = field(weak, "consensus_interface"), field(strong, "consensus_interface")
    wd, sd = field(weak, "disputed"), field(strong, "disputed")
    wconf = (weak.get("adjudication") or {}).get("confidence")
    sconf = (strong.get("adjudication") or {}).get("confidence")
    return {
        "consensus_shared": sorted(wc & sc),
        "consensus_only_weak": sorted(wc - sc),     # weak over-claims interface here
        "consensus_only_strong": sorted(sc - wc),   # weak misses interface here
        "disputed_only_weak": sorted(wd - sd),
        "disputed_only_strong": sorted(sd - wd),
        "confidence_weak": wconf,
        "confidence_strong": sconf,
        "agreement": wc == sc and wd == sd,
    }


def render(goal, weak, strong, d) -> str:
    def block(r):
        a = r.get("adjudication") or {}
        cot = ("\n\n_chain-of-thought:_ " + r["chain_of_thought"]) if r.get("chain_of_thought") else ""
        return (f"- consensus: {', '.join(a.get('consensus_interface', []) or []) or '-'}\n"
                f"- disputed: {', '.join(a.get('disputed', []) or []) or '-'}\n"
                f"- weak: {', '.join(a.get('weak', []) or []) or '-'}\n"
                f"- confidence: {a.get('confidence', '-')}\n"
                f"- reasoning: {a.get('reasoning', '-')}{cot}")
    where = []
    if d["consensus_only_weak"]:
        where.append(f"- Called interface by the weak model but NOT the strong one "
                     f"(disagreement → flag): {', '.join(d['consensus_only_weak'])}")
    if d["consensus_only_strong"]:
        where.append(f"- Called interface by the strong model but NOT the weak one "
                     f"(disagreement → flag): {', '.join(d['consensus_only_strong'])}")
    if d["disputed_only_weak"] or d["disputed_only_strong"]:
        where.append(f"- Disputed-set differs: weak-only {d['disputed_only_weak'] or '-'}, "
                     f"strong-only {d['disputed_only_strong'] or '-'}")
    if d["confidence_weak"] != d["confidence_strong"]:
        where.append(f"- Confidence differs: weak={d['confidence_weak']} vs "
                     f"strong={d['confidence_strong']} (which is correct is unknown)")
    if not where:
        where.append("- The two models agree on this case.")

    return f"""# Weak-vs-Strong Adjudication Comparison

**Goal:** {goal}

Same evidence, two interpreters. There is NO ground truth here, so neither model
is declared correct. Where the two models DISAGREE, that residue is treated as
low-confidence and flagged for a human / MD / experiment — disagreement is the
signal, not a verdict on which model is right.

## Weak model (`{weak['model']}`)
{block(weak)}

## Strong model (`{strong['model']}`)
{block(strong)}

## Where the two models disagree (= low-confidence flags)
{chr(10).join(where)}

---
*Evidence (tool scores, UniProt validation, mapping, structures) was gathered once
and shared; only the decision step differs between models.*
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Weak-vs-strong adjudication comparison")
    ap.add_argument("--uniprot", default="O15205")
    ap.add_argument("--weak-model", default="deepseek-chat")
    ap.add_argument("--strong-model", default="deepseek-reasoner")
    ap.add_argument("--goal", default="Adjudicate the FAT10 (O15205) N-terminal ubl interface with MAD2.")
    args = ap.parse_args()

    _, evidence = gather_evidence(args.uniprot)
    print(f"Gathering done. Adjudicating with weak={args.weak_model} ...")
    weak = adjudicate(args.weak_model, evidence)
    print(f"Adjudicating with strong={args.strong_model} ...")
    strong = adjudicate(args.strong_model, evidence)
    d = diff(weak, strong)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / "agent_compare.json").write_text(
        json.dumps({"goal": args.goal, "evidence": evidence,
                    "weak": weak, "strong": strong, "diff": d}, indent=2),
        encoding="utf-8")
    (out / "agent_compare.md").write_text(render(args.goal, weak, strong, d), encoding="utf-8")

    print("\nWROTE outputs/agent_compare.json")
    print("WROTE outputs/agent_compare.md")
    print(json.dumps(d, indent=2))


if __name__ == "__main__":
    main()
