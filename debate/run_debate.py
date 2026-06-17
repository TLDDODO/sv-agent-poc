from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .data import mock_profiles
from .experts import expert_md, expert_nma
from .aggregator import aggregate
from .critic import audit
from .llm import LLM


def _vtab(v) -> str:
    return "\n".join(
        f"| {rv.region} | {rv.value:.2f} | {rv.stance} |" for rv in v.region_verdicts)


def render(system, md, nma, exchanges, judgment, findings) -> str:
    region_table = "\n".join(
        f"| {t.region} | {t.md_value:.2f} | {t.nma_value:.2f} | {t.delta:.2f} | {t.status} |"
        for t in judgment.region_table)
    debate = "\n".join(
        f"- **{e.speaker} -> {e.responds_to}** on *{e.region}* [{e.agreement}]: {e.comment}"
        for e in exchanges)
    audit_block = "\n".join(f"- {x}" for x in findings)
    return f"""# Multi-Agent Method-Comparison Brief - {system}

**Question:** Do MD and NMA agree on the dynamics of {system}, and where should we trust which?

## 1. Expert Verdicts

### MD-view - source `{md.source_id}` - confidence {md.confidence}
{md.rationale}

| Region | MD flex | stance |
| --- | --- | --- |
{_vtab(md)}

### NMA-view - source `{nma.source_id}` - confidence {nma.confidence}
{nma.rationale}

| Region | NMA flex | stance |
| --- | --- | --- |
{_vtab(nma)}

## 2. Debate (who agrees with whom)
{debate}

## 3. Aggregate Judgment
**Verdict:** {judgment.verdict}

- Agreement (Pearson r): **{judgment.agreement_score}**
- Confidence: **{judgment.confidence}**
- Consensus regions: {', '.join(judgment.consensus_regions) or '-'}
- Conflict regions: {', '.join(judgment.conflict_regions) or '-'}

| Region | MD | NMA | delta | status |
| --- | --- | --- | --- | --- |
{region_table}

## 4. Reliability Audit (critic)
{audit_block}

---
*MD = molecular dynamics (the real engine). NMA = normal-mode analysis. The agents
interpret and reconcile both methods; they do not generate the dynamics. Current run
uses demo profiles - swap in real MDAnalysis RMSF + ENM fluctuations on HPC.*
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="MD-vs-NMA multi-agent decision PoC")
    ap.add_argument("--system", default="EGFR T790M")
    ap.add_argument("--llm", choices=["mock", "real"], default="mock")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    llm = LLM(args.llm, args.model)
    md_profile, nma_profile = mock_profiles()
    md = expert_md(md_profile, llm)
    nma = expert_nma(nma_profile, llm)
    exchanges, judgment = aggregate(md, nma, llm)
    findings = audit([md, nma], judgment)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    evidence = {
        "system": args.system,
        "llm_mode": args.llm,
        "expert_verdicts": [asdict(md), asdict(nma)],
        "debate": [asdict(e) for e in exchanges],
        "aggregate_judgment": asdict(judgment),
        "reliability_audit": findings,
    }
    (out / "debate_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out / "debate_report.md").write_text(
        render(args.system, md, nma, exchanges, judgment, findings), encoding="utf-8")

    print("WROTE outputs/debate_evidence.json")
    print("WROTE outputs/debate_report.md")
    print(json.dumps({
        "system": args.system,
        "agreement_r": judgment.agreement_score,
        "confidence": judgment.confidence,
        "conflict_regions": judgment.conflict_regions,
        "audit": findings,
    }, indent=2))


if __name__ == "__main__":
    main()
