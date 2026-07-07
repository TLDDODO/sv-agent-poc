#!/usr/bin/env python
"""Exact binomial significance for donor-swap tracking numbers (stdlib only, no scipy).

Every tracking claim in RP.md is reported with an exact one-sided binomial test against the
chance null (the probability that a swapped prediction matches the donor label by luck alone:
1/7 for MELD/LIME's 7 emotion classes, 1/5 for ESD's 5). This script makes that computation
mechanical and identical everywhere, instead of re-derived by hand in prose each time.

    python scripts/significance.py --k 9 --n 15              # MELD-style cell, null 1/7
    python scripts/significance.py --k 100 --n 100 --null 1/5  # ESD-style cell
    python scripts/significance.py --self-test               # verify against RP.md's published values

--self-test doubles as the regression guard run in CI: if this code ever disagrees with the
numbers already published in RP.md's Core Finding, the build fails.
"""

import argparse
import sys
from fractions import Fraction
from math import comb


def binom_tail(n: int, k: int, p: float) -> float:
    """One-sided exact P(X >= k) for X ~ Binomial(n, p)."""
    if not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got k={k} n={n}")
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def parse_prob(s: str) -> float:
    """Accept '1/7' or '0.1428…' — fractions read exactly as written in RP.md."""
    return float(Fraction(s))


# (n, k, null, published) — the values as they appear in RP.md's Core Finding paragraphs.
# Tolerance is loose (2%) because RP.md rounds for prose; the point is agreement, not digits.
PUBLISHED = [
    (15, 7, "1/7", 0.0027),     # supervision-fixed MELD rerun (grounded CoT + text_mask 0.3)
    (15, 9, "1/7", 5.45e-05),   # meld textmask1 / textmask1_acoustic
    (15, 13, "1/7", 8.2e-10),   # LIME Part B
]


def self_test() -> int:
    failures = 0
    for n, k, null, published in PUBLISHED:
        got = binom_tail(n, k, parse_prob(null))
        ok = abs(got - published) <= 0.02 * published
        print(f"P(X>={k} | n={n}, p={null}) = {got:.4g}  (RP.md: {published:g})  {'OK' if ok else 'MISMATCH'}")
        failures += 0 if ok else 1
    if failures:
        print(f"SELF-TEST FAILED: {failures} value(s) disagree with RP.md", file=sys.stderr)
    return failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, help="observed successes (e.g. donor-label matches)")
    ap.add_argument("--n", type=int, default=15, help="trials (rows on the ruler; default 15)")
    ap.add_argument("--null", default="1/7", help="chance probability, e.g. 1/7 (MELD/LIME) or 1/5 (ESD)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(1 if self_test() else 0)
    if args.k is None:
        ap.error("--k is required unless --self-test")
    p = parse_prob(args.null)
    tail = binom_tail(args.n, args.k, p)
    print(f"tracking {args.k}/{args.n} vs chance null p={args.null}:")
    print(f"  exact one-sided P(X>={args.k}) = {tail:.4g}")


if __name__ == "__main__":
    main()
