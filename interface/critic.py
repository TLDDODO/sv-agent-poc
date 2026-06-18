from __future__ import annotations
from .schemas import ToolVerdict, AggregateInterface


def audit(verdicts: list[ToolVerdict], agg: AggregateInterface) -> list[str]:
    """Reliability audit over the interface adjudication. The critic never
    proposes interface residues; it checks the evidence chain and flags what
    must not be trusted before MD / experimental confirmation."""
    findings: list[str] = []

    for v in verdicts:
        if not v.source_id or v.source_id == "none":
            findings.append(f"{v.tool}: prediction not bound to a real source_id.")
        if not v.called_interface:
            findings.append(f"{v.tool}: called no interface residues - check the run.")

    if agg.disputed and agg.confidence > 0.7:
        findings.append(
            f"Overconfident: {len(agg.disputed)} disputed residue(s) but aggregate "
            f"confidence {agg.confidence} > 0.7.")
    if not agg.evidence_ids:
        findings.append("Aggregate interface cites no evidence ids.")
    if not agg.consensus_interface:
        findings.append("No consensus interface residues - tools do not converge; "
                        "do not pick an MD interface model yet.")

    for r in agg.disputed:
        findings.append(f"Flag for MD / experimental check: {r} (tools disagree).")
    for r in agg.weak:
        findings.append(f"Weak/ambiguous (no tool decisive): {r} - treat as tentative.")

    if not findings:
        findings.append("No reliability issues detected.")
    return findings
