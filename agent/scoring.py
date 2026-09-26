"""Benchmark scoring rule (approved in docs/benchmark_design.md section 4).

For each protein of a pair, the prediction R is the union of the residue ranges the
agent (or the baseline) submitted for that UniProt accession; T is the true interface
residue set. A protein is a HIT when
  * recall = |R & T| / |T| >= RECALL_MIN, and
  * |R| <= MAX_SPAN_RATIO * span(T), span(T) = max(T) - min(T) + 1
    (so predicting the whole chain does not count).
Case score = mean of the two protein hits (0, 0.5 or 1). F1 / Jaccard are auxiliary.
A missing or malformed prediction for a protein is a miss.
"""
from __future__ import annotations

RECALL_MIN = 0.5
MAX_SPAN_RATIO = 2.0


def _residues(regions, uniprot) -> set[int]:
    out: set[int] = set()
    for r in regions or []:
        try:
            if r["uniprot"] != uniprot:
                continue
            lo, hi = int(r["start"]), int(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo >= 1 and hi >= lo:
            out |= set(range(lo, hi + 1))
    return out


def score_protein(regions, uniprot: str, truth) -> dict:
    T = set(truth)
    R = _residues(regions, uniprot)
    span = max(T) - min(T) + 1
    inter = len(R & T)
    recall = inter / len(T)
    precision = inter / len(R) if R else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    jaccard = inter / len(R | T) if R | T else 0.0
    hit = bool(R) and recall >= RECALL_MIN and len(R) <= MAX_SPAN_RATIO * span
    return {"hit": hit, "recall": recall, "predicted_length": len(R),
            "true_span": span, "f1": f1, "jaccard": jaccard}


def score_case(regions, truth_by_uniprot: dict) -> dict:
    per = {acc: score_protein(regions, acc, t) for acc, t in truth_by_uniprot.items()}
    return {"score": sum(p["hit"] for p in per.values()) / len(per), "per_protein": per}
