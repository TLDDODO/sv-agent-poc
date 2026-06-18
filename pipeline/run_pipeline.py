from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .structures import (
    SearchSpec, offline_structures, mcp_structures, build_mappings, MUTATION_POSITION,
)
from debate.data import mock_profiles
from debate.experts import expert_md, expert_nma
from debate.aggregator import aggregate
from debate.critic import audit as debate_audit
from debate.llm import LLM


def structure_critic(structures, mappings) -> list[str]:
    """Audit the static structure evidence before the dynamics is interpreted."""
    findings = []
    if not structures:
        findings.append("Retrieval returned no structures.")
        return findings
    if not any(m.observed and m.canonical_uniprot_position == MUTATION_POSITION for m in mappings):
        findings.append(f"No structure observes canonical residue {MUTATION_POSITION} as the mutation.")
    non_mut = [s.pdb_id for s in structures if s.mutation_status != "T790M"]
    if non_mut:
        findings.append("Non-T790M titles among hits: " + ", ".join(non_mut))
    unknown_state = [s.pdb_id for s in structures if s.apo_or_bound == "unknown"]
    if unknown_state:
        findings.append("Apo/bound state unknown for: " + ", ".join(unknown_state))
    return findings


def render(system, source, structures, mappings, md, nma, exchanges, judgment, audit) -> str:
    struct_rows = "\n".join(
        f"| {s.pdb_id.upper()} | {s.resolution} | {s.experimental_method} | "
        f"{s.mutation_status} | {s.apo_or_bound} | {s.title} |" for s in structures)
    map_rows = "\n".join(
        f"| {m.pdb_id.upper()} | {m.chain_id} | {m.auth_seq_id} | "
        f"{m.canonical_uniprot_accession}:{m.canonical_uniprot_position} | "
        f"{m.canonical_residue_name}->{m.pdb_residue_name} | {m.observed} |" for m in mappings)
    debate = "\n".join(
        f"- **{e.speaker} -> {e.responds_to}** on *{e.region}* [{e.agreement}]: {e.comment}"
        for e in exchanges)
    region_table = "\n".join(
        f"| {t.region} | {t.md_value:.2f} | {t.nma_value:.2f} | {t.delta:.2f} | {t.status} |"
        for t in judgment.region_table)
    audit_block = "\n".join(f"- {x}" for x in audit)
    pdb_ids = ", ".join(s.pdb_id.upper() for s in structures[:5])
    return f"""# End-to-End Mutation Brief - {system}

**Pipeline:** PDBe retrieval ({source}) -> canonical residue {MUTATION_POSITION} mapping
-> MD-vs-NMA multi-agent debate -> combined reliability audit.

## 1. Structure Retrieval
| PDB | Resolution | Method | Mutation | State | Title |
| --- | --- | --- | --- | --- | --- |
{struct_rows}

## 2. Canonical Residue Mapping (EGFR / UniProt {mappings[0].canonical_uniprot_accession})
| PDB | Chain | auth_seq | canonical | residue | observed |
| --- | --- | --- | --- | --- | --- |
{map_rows}

## 3. Dynamics: MD-vs-NMA Debate
The mapped system is interpreted by two method-bound experts over canonical regions.

**MD-view** (`{md.source_id}`, conf {md.confidence}): {md.overall}
**NMA-view** (`{nma.source_id}`, conf {nma.confidence}): {nma.overall}

{debate}

### Aggregate judgment
**{judgment.verdict}**

- Agreement (Pearson r): **{judgment.agreement_score}** | Confidence: **{judgment.confidence}**
- Consensus: {', '.join(judgment.consensus_regions) or '-'}
- Conflict: {', '.join(judgment.conflict_regions) or '-'}

| Region | MD | NMA | delta | status |
| --- | --- | --- | --- | --- |
{region_table}

## 4. Combined Reliability Audit
Evidence: structures [{pdb_ids}]; dynamics [{', '.join(judgment.evidence_ids)}].

{audit_block}

---
*Static structure evidence (PDBe) anchors the system and canonical numbering; the agents
interpret and reconcile the dynamics (MD vs NMA) but never generate it. MD stays the engine.
Dynamics use demo profiles - swap in real MDAnalysis RMSF + ENM fluctuations on HPC.*
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="PDBe -> mapping -> MD-vs-NMA debate, one shot")
    ap.add_argument("--system", default="EGFR T790M")
    ap.add_argument("--source", choices=["offline", "mcp"], default="offline",
                    help="offline = verified snapshot (runs anywhere); mcp = live PDBe on HPC")
    ap.add_argument("--llm", choices=["mock", "real"], default="mock")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    spec = SearchSpec(query="title:*EGFR* AND title:*T790M*")
    structures = (mcp_structures(spec) if args.source == "mcp"
                  else offline_structures(spec))
    mappings = build_mappings(structures)

    llm = LLM(args.llm, args.model)
    md_profile, nma_profile = mock_profiles()
    md = expert_md(md_profile, llm)
    nma = expert_nma(nma_profile, llm)
    exchanges, judgment = aggregate(md, nma, llm)

    # Combined audit: structure-side checks first, then the dynamics audit.
    audit = structure_critic(structures, mappings) + debate_audit([md, nma], judgment)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    evidence = {
        "system": args.system,
        "source": args.source,
        "llm_mode": args.llm,
        "structures": [asdict(s) for s in structures],
        "residue_mappings": [asdict(m) for m in mappings],
        "expert_verdicts": [asdict(md), asdict(nma)],
        "debate": [asdict(e) for e in exchanges],
        "aggregate_judgment": asdict(judgment),
        "combined_audit": audit,
    }
    (out / "pipeline_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out / "pipeline_report.md").write_text(
        render(args.system, args.source, structures, mappings, md, nma, exchanges, judgment, audit),
        encoding="utf-8")

    print("WROTE outputs/pipeline_evidence.json")
    print("WROTE outputs/pipeline_report.md")
    print(json.dumps({
        "system": args.system,
        "source": args.source,
        "n_structures": len(structures),
        "top_pdbs": [s.pdb_id.upper() for s in structures[:5]],
        "agreement_r": judgment.agreement_score,
        "confidence": judgment.confidence,
        "conflict_regions": judgment.conflict_regions,
        "audit": audit,
    }, indent=2))


if __name__ == "__main__":
    main()
