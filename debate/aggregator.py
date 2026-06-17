from __future__ import annotations
from .schemas import ExpertVerdict, DebateExchange, AggregateJudgment, RegionConsensus
from .llm import LLM

_CONFLICT = 0.25   # |MD - NMA| above this is a method conflict


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(cov / (vx * vy), 2) if vx and vy else 0.0


def aggregate(md: ExpertVerdict, nma: ExpertVerdict, llm: LLM):
    md_map = {rv.region: rv.value for rv in md.region_verdicts}
    nma_map = {rv.region: rv.value for rv in nma.region_verdicts}
    regions = list(md_map)

    table: list[RegionConsensus] = []
    consensus: list[str] = []
    conflict: list[str] = []
    exchanges: list[DebateExchange] = []

    for r in regions:
        d = round(abs(md_map[r] - nma_map[r]), 2)
        status = "conflict" if d > _CONFLICT else "consensus"
        table.append(RegionConsensus(r, md_map[r], nma_map[r], d, status))
        if status == "consensus":
            consensus.append(r)
            exchanges.append(DebateExchange(
                "NMA-view", "MD-view", r, "agree",
                f"{r}: both ~{(md_map[r] + nma_map[r]) / 2:.2f}; methods concur."))
        else:
            conflict.append(r)
            md_higher = md_map[r] > nma_map[r]
            why = ("anharmonic loop motion that MD captures but harmonic NMA flattens"
                   if md_higher else
                   "a slow collective mode NMA resolves but the trajectory under-samples")
            exchanges.append(DebateExchange(
                "MD-view", "NMA-view", r, "disagree",
                f"{r}: MD={md_map[r]:.2f} vs NMA={nma_map[r]:.2f}; "
                f"{'MD' if md_higher else 'NMA'} sees more motion, likely {why}."))

    agreement = _pearson([md_map[r] for r in regions], [nma_map[r] for r in regions])
    frac_consensus = 1 - len(conflict) / len(regions) if regions else 0.0
    # Confidence rewards agreement and is penalised when conflicts are unresolved.
    confidence = round(
        max(0.2, min(0.9, 0.4 + 0.5 * frac_consensus)) * (0.8 if conflict else 1.0), 2)

    if conflict:
        verdict = (f"MD and NMA agree on the rigid core and shared flexible regions, "
                   f"but DISAGREE on [{', '.join(conflict)}] — treat those as "
                   f"method-dependent, not settled.")
    else:
        verdict = ("MD and NMA agree across all analyzed regions; the dynamic picture "
                   "is method-robust.")

    delta_of = {t.region: t.delta for t in table}
    dissent = [f"{r}: unresolved MD/NMA conflict (delta={delta_of[r]:.2f})" for r in conflict]
    judgment = AggregateJudgment(
        verdict, confidence, agreement, consensus, conflict, table,
        [md.source_id, nma.source_id], dissent)
    return exchanges, judgment
