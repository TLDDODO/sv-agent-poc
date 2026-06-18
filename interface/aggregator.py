from __future__ import annotations
from .schemas import (
    ToolPrediction, ToolVerdict, DebateExchange, ResidueConsensus, AggregateInterface,
)
from debate.llm import LLM

_HI = 0.60          # consensus mean at/above -> interface
_LO = 0.40          # consensus mean at/below -> non-interface
_DISPUTE = 0.30     # spread across tools above this -> tools disagree


def aggregate(predictions: list[ToolPrediction], verdicts: list[ToolVerdict], llm: LLM):
    tools = [p.tool for p in predictions]
    residues = [s.residue for s in predictions[0].scores]
    score_of = {p.tool: {s.residue: s.score for s in p.scores} for p in predictions}

    table: list[ResidueConsensus] = []
    consensus_iface: list[str] = []
    consensus_non: list[str] = []
    disputed: list[str] = []
    weak: list[str] = []
    exchanges: list[DebateExchange] = []
    spreads: list[float] = []

    for r in residues:
        vals = {t: score_of[t][r] for t in tools}
        lo, hi = min(vals.values()), max(vals.values())
        mean = round(sum(vals.values()) / len(vals), 2)
        spread = round(hi - lo, 2)
        spreads.append(spread)

        if spread > _DISPUTE:
            status = "disputed"
            disputed.append(r)
            leans_iface = [t for t in tools if vals[t] > _LO]
            leans_against = [t for t in tools if vals[t] <= _LO]
            exchanges.append(DebateExchange(
                speaker=", ".join(leans_iface) or "none", responds_to=", ".join(leans_against) or "none",
                residue=r, agreement="disagree",
                comment=(f"{r}: {', '.join(f'{t}={vals[t]:.2f}' for t in tools)}. "
                         f"[{', '.join(leans_iface) or 'none'}] lean interface; "
                         f"[{', '.join(leans_against) or 'none'}] lean against.")))
        elif mean >= _HI:
            status = "consensus-interface"
            consensus_iface.append(r)
            exchanges.append(DebateExchange(
                ", ".join(tools), "all", r, "agree",
                f"{r}: all tools ~{mean:.2f}; agreed interface residue."))
        elif mean <= _LO:
            status = "consensus-noninterface"
            consensus_non.append(r)
        else:
            status = "weak"
            weak.append(r)

        table.append(ResidueConsensus(r, vals, mean, spread, status))

    n = len(residues)
    agreement = round(1 - sum(spreads) / n, 2) if n else 0.0
    frac_clean = (len(consensus_iface) + len(consensus_non)) / n if n else 0.0
    confidence = round(
        max(0.2, min(0.9, 0.4 + 0.5 * frac_clean)) * (0.8 if disputed else 1.0), 2)

    aggregate_iface = AggregateInterface(
        consensus_interface=consensus_iface,
        consensus_noninterface=consensus_non,
        disputed=disputed,
        weak=weak,
        agreement_score=agreement,
        confidence=confidence,
        table=table,
        evidence_ids=[v.source_id for v in verdicts],
    )
    return exchanges, aggregate_iface
