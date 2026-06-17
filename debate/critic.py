from __future__ import annotations
from .schemas import ExpertVerdict, AggregateJudgment


def audit(verdicts: list[ExpertVerdict], judgment: AggregateJudgment) -> list[str]:
    """Reliability audit. The critic never generates a verdict; it checks the
    evidence chain and flags anything that should not be trusted at face value."""
    findings: list[str] = []

    for v in verdicts:
        if not v.source_id or v.source_id == "none":
            findings.append(f"{v.expert}: verdict not bound to a real source_id.")
        if v.evidence_type == "inference" and v.confidence > 0.3:
            findings.append(
                f"{v.expert}: inference-only verdict with confidence {v.confidence} > 0.3.")

    if judgment.conflict_regions and judgment.confidence > 0.7:
        findings.append(
            f"Overconfident: {len(judgment.conflict_regions)} unresolved conflict(s) "
            f"but aggregate confidence {judgment.confidence} > 0.7.")
    if not judgment.evidence_ids:
        findings.append("Aggregate judgment cites no evidence ids.")

    for r in judgment.conflict_regions:
        findings.append(f"Flag for human / experimental check: {r} (MD vs NMA disagree).")

    if not findings:
        findings.append("No reliability issues detected.")
    return findings
