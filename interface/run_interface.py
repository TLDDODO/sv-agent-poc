from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .data import mock_predictions, SYSTEM, FAT10_UNIPROT, MAD2_UNIPROT
from .experts import tool_expert
from .aggregator import aggregate
from .critic import audit
from .structures import (
    offline_structures, mcp_structures, canonical_map, mapping_critic, NTERM_UBL_RANGE,
)
from debate.llm import LLM


def render(predictions, structures, mappings, verdicts, exchanges, agg, findings) -> str:
    tools = [p.tool for p in predictions]

    if structures:
        struct_rows = "\n".join(
            f"| {s.pdb_id.upper()} | {s.resolution if s.resolution is not None else '-'} "
            f"| {s.experimental_method} | {s.title} |"
            for s in structures)
        struct_block = ("| PDB | Resolution | Method | Title |\n| --- | --- | --- | --- |\n"
                        + struct_rows)
    else:
        struct_block = ("_No PDB structures pulled in offline mode. Run `--source mcp` on HPC "
                        "for a live PDBe query. System identity is fixed by UniProt accessions "
                        "above; the canonical mapping below anchors the tools' residue numbers._")

    map_rows = "\n".join(
        f"| {m.residue_label} | {m.residue_name} | "
        f"{m.canonical_uniprot_accession}:{m.canonical_uniprot_position} | {m.in_nterm_ubl} |"
        for m in mappings)

    verdict_rows = "\n".join(
        f"### {v.tool}  -  source `{v.source_id}`  -  confidence {v.confidence}\n"
        f"{v.rationale}\n\nCalled interface: **{', '.join(v.called_interface) or 'none'}**\n"
        for v in verdicts)

    header = "| Residue | " + " | ".join(tools) + " | mean | spread | status |"
    sep = "| --- | " + " | ".join("---" for _ in tools) + " | --- | --- | --- |"
    body = "\n".join(
        f"| {t.residue} | " + " | ".join(f"{t.scores[tool]:.2f}" for tool in tools)
        + f" | {t.mean:.2f} | {t.spread:.2f} | {t.status} |"
        for t in agg.table)
    table = "\n".join([header, sep, body])

    debate = "\n".join(
        f"- **{e.speaker}** vs **{e.responds_to}** on *{e.residue}* [{e.agreement}]: {e.comment}"
        for e in exchanges)
    audit_block = "\n".join(f"- {x}" for x in findings)

    return f"""# Interface-Tool Adjudication - {SYSTEM}

**System:** FAT10 (UniProt {FAT10_UNIPROT}) N-terminal ubl domain : MAD2 (UniProt {MAD2_UNIPROT})
**Question:** Which FAT10 residues form the MAD2 interface, where do the prediction tools
agree, and which residues are too disputed to commit to an MD interface model?

## 1. Structure Retrieval (PDBe)
{struct_block}

## 2. Canonical Residue Mapping (FAT10 / UniProt {FAT10_UNIPROT})
Every predicted interface residue is anchored to canonical numbering and checked
against the MAD2-binding N-terminal ubl domain (residues {NTERM_UBL_RANGE[0]}-{NTERM_UBL_RANGE[1]}),
so all tools refer to the same positions.

| Residue | Name | Canonical | In N-term ubl |
| --- | --- | --- | --- |
{map_rows}

## 3. Tool Verdicts (each agent interprets one tool)
{verdict_rows}
## 4. Per-Residue Comparison
{table}

## 5. Disagreements (who calls what)
{debate}

## 6. Adjudicated Interface
- **Consensus interface residues (use for the MD interface model):** {', '.join(agg.consensus_interface) or '-'}
- **Consensus non-interface:** {', '.join(agg.consensus_noninterface) or '-'}
- **Disputed (need MD / experimental check):** {', '.join(agg.disputed) or '-'}
- **Weak / ambiguous:** {', '.join(agg.weak) or '-'}
- Agreement (1 - mean spread): **{agg.agreement_score}** | Confidence: **{agg.confidence}**

## 7. Reliability Audit
Evidence: {', '.join(agg.evidence_ids)}

{audit_block}

---
*The agents do not predict the interface; they compare the tools, surface disagreement
instead of hiding it, and audit the result. The consensus residues feed the team's
"pick one interface model for MD" step; disputed residues are flagged for MD /
experimental confirmation. Demo uses mock tool scores - swap in real
AF-Multimer / HADDOCK / PISA per-residue output on HPC.*
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="FAT10:MAD2 interface-tool adjudication PoC")
    ap.add_argument("--source", choices=["offline", "mcp"], default="offline",
                    help="offline = no PDB IDs (mapping only); mcp = live PDBe query on HPC")
    ap.add_argument("--llm", choices=["mock", "real"], default="mock")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    llm = LLM(args.llm, args.model)
    predictions = mock_predictions()

    # PDBe retrieval -> canonical residue mapping (anchors all tools to UniProt numbering).
    structures = mcp_structures() if args.source == "mcp" else offline_structures()
    residue_labels = [s.residue for s in predictions[0].scores]
    mappings = canonical_map(residue_labels)

    verdicts = [tool_expert(p, llm) for p in predictions]
    exchanges, agg = aggregate(predictions, verdicts, llm)
    # Combined audit: residue-mapping checks first, then the interface adjudication audit.
    findings = mapping_critic(mappings) + audit(verdicts, agg)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    evidence = {
        "system": SYSTEM,
        "fat10_uniprot": FAT10_UNIPROT,
        "mad2_uniprot": MAD2_UNIPROT,
        "source": args.source,
        "llm_mode": args.llm,
        "structures": [asdict(s) for s in structures],
        "residue_mappings": [asdict(m) for m in mappings],
        "tool_verdicts": [asdict(v) for v in verdicts],
        "debate": [asdict(e) for e in exchanges],
        "aggregate_interface": asdict(agg),
        "reliability_audit": findings,
    }
    (out / "interface_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out / "interface_report.md").write_text(
        render(predictions, structures, mappings, verdicts, exchanges, agg, findings),
        encoding="utf-8")

    print("WROTE outputs/interface_evidence.json")
    print("WROTE outputs/interface_report.md")
    print(json.dumps({
        "system": SYSTEM,
        "consensus_interface": agg.consensus_interface,
        "disputed": agg.disputed,
        "agreement": agg.agreement_score,
        "confidence": agg.confidence,
        "audit": findings,
    }, indent=2))


if __name__ == "__main__":
    main()
