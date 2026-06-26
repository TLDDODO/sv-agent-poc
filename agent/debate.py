"""Multi-agent debate over a REAL conflict: MD interface vs NMR expectation.

This is not theater. There is a genuine disagreement in the evidence:
  - the 100 ns MD (on the AF3 starting model) puts the FAT10-MAD2 interface on
    FAT10's C-terminal region (UBL2 + tail),
  - the literature/NMR says MAD2 binds the N-terminal first ubl domain (UBL1).
Two advocate agents argue each side from the SAME real facts; a judge weighs them.
Every number handed to the agents is real (MD occupancies, UniProt-verified domain
boundaries); the agents may only interpret, not invent.

    export DEEPSEEK_API_KEY=...
    python -m agent.debate
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from .llm_client import make_client, MODEL
from .tools import get_expected_interface_region
from .skills import load_skill

DOMAINS = [
    ("Ubiquitin-like 1 (N-term)", 6, 81),
    ("linker", 82, 89),
    ("Ubiquitin-like 2 (C-term)", 90, 163),
    ("C-terminal tail", 164, 165),
]
INTERFACE_CUTOFF = 0.5


def _resnum(label):
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) if m else 0


def _domain_of(n):
    for name, lo, hi in DOMAINS:
        if lo <= n <= hi:
            return name
    return "outside annotated domains"


def evidence_bundle(scores_path="analysis/md_interface_scores.json") -> dict:
    data = json.loads(Path(scores_path).read_text())
    method, occ = next(iter(data.items()))
    core = {k: v for k, v in occ.items() if v >= INTERFACE_CUTOFF}
    return {
        "md_method": method,
        "persistent_interface_occupancy": core,
        "domain_of_each_interface_residue": {k: _domain_of(_resnum(k)) for k in core},
        "all_occupancies": occ,
        "nmr_expected": get_expected_interface_region(),
        "fat10_domains": {name: [lo, hi] for name, lo, hi in DOMAINS},
        "model_provenance": "starting complex = AlphaFold3 multimer; 100 ns explicit-solvent MD",
    }


def _ask(client, system, facts, extra=""):
    msg = client.chat.completions.create(
        model=MODEL, temperature=0,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": f"FACTS (JSON):\n{json.dumps(facts, indent=2)}\n{extra}"}])
    return msg.choices[0].message.content


# Role prompts are defined in skills/*.md (the real source); inline text is fallback.
ADVOCATE_MD = load_skill("md_advocate",
    "You are the MD advocate. Argue as strongly as you legitimately can that the "
    "C-terminal interface should not be dismissed. Use only the given facts; do not "
    "invent numbers. 4-6 sentences.")

ADVOCATE_NMR = load_skill("nmr_advocate",
    "You are the NMR/literature advocate. Argue why the model's interface is suspect "
    "and where MAD2 is expected to bind (note the AlphaFold Gly-Gly tail-docking "
    "artifact). Use only the given facts. 4-6 sentences.")

JUDGE = load_skill("judge",
    "You are the JUDGE. Separate whether the model CONTRADICTS the literature (factual) "
    "from which side is actually right (unknown — no experimental complex). Do not "
    "declare a winner; recommend an experiment. Respond ONLY as JSON with keys: "
    "interface_shown_by_data, contradicts_literature_expectation, "
    "true_interface_experimentally_known, confidence_in_contradiction, "
    "confidence_in_which_side_is_right, flags, recommendation, reasoning.")


def _extract_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"error": "no JSON", "raw": (text or "")[:400]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"error": str(e), "raw": (text or "")[:400]}


def run():
    client = make_client()
    facts = evidence_bundle()

    print("Round 1: MD advocate ...")
    arg_md = _ask(client, ADVOCATE_MD, facts)
    print("Round 1: NMR advocate ...")
    arg_nmr = _ask(client, ADVOCATE_NMR, facts)
    print("Round 2: judge ...")
    verdict = _extract_json(_ask(
        client, JUDGE, facts,
        extra=f"\nMD ADVOCATE said:\n{arg_md}\n\nNMR ADVOCATE said:\n{arg_nmr}"))

    report = f"""# Multi-Agent Debate — FAT10–MAD2 Interface

**The conflict (real):** MD (on the AF3 model) shows a C-terminal interface; the
literature/NMR expects binding via the N-terminal UBL1. Two agents argue; a judge weighs.

**Facts handed to all agents (all real):**
- MD persistent interface: {', '.join(f"{k} ({v:.2f})" for k, v in facts['persistent_interface_occupancy'].items())}
- Their domains: {', '.join(f"{k}→{d}" for k, d in facts['domain_of_each_interface_residue'].items())}
- NMR-expected region: {facts['nmr_expected']['expected_region']} (residues {facts['nmr_expected']['residue_range']})

## 🧬 MD / structural advocate
{arg_md}

## 📚 Literature / NMR advocate
{arg_nmr}

## ⚖️ Judge's verdict
```json
{json.dumps(verdict, indent=2, ensure_ascii=False)}
```
"""
    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / "debate_report.md").write_text(report, encoding="utf-8")
    print("\nWROTE outputs/debate_report.md")
    print(json.dumps(verdict, indent=2, ensure_ascii=False)[:600])
    return verdict


if __name__ == "__main__":
    run()
