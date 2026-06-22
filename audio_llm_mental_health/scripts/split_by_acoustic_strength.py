#!/usr/bin/env python
"""Split an acoustic-tagged manifest into high- vs low-acoustic-strength subsets.

Companion to scripts/extract_acoustic_priors.py, reused here for diagnosis rather than CoT
target construction (see RP.md "Environment", the text_mask_prob=1.0 confound discussion): does
the silence-vs-audio delta on the *already-trained* MELD baseline already differ between
acoustically loud and acoustically quiet clips? If it doesn't, ESD's full-grounding result can't
be attributed to its acted, loud acoustics -- it has to be the data-level decoupling itself, and
a text_mask_prob=1.0 training run becomes confirmation rather than the only way to settle this.

Acoustic strength is read off the per-feature low/mid/high tertile buckets that
extract_acoustic_priors.py already wrote (not re-thresholded here, so both scripts agree on what
"high" means). A row counts as high-acoustic if more of its {pitch_var, loudness_var, pace}
buckets are "high" than "low" (and vice versa for low); ties and all-mid rows are dropped, so
the two output subsets are unambiguous.

CAUTION (read before trusting a delta comparison built on this split): acoustic strength is not
independent of emotion category -- anger/surprise are spoken with naturally larger pitch and
loudness swings than neutral/sadness, so a "high-acoustic" subset will skew toward those
classes. This script prints each subset's emotion composition so that skew is visible rather
than hidden; if the two subsets differ mostly in emotion mix, a delta difference between them
may reflect class difficulty, not acoustic strength.

Run on the dev manifest, after extract_acoustic_priors.py:

    python scripts/extract_acoustic_priors.py \
        --in data/meld_dev_manifest.jsonl --out data/meld_dev_manifest_acoustic.jsonl
    python scripts/split_by_acoustic_strength.py \
        --in data/meld_dev_manifest_acoustic.jsonl \
        --out-high data/meld_dev_acoustic_high.jsonl \
        --out-low data/meld_dev_acoustic_low.jsonl

Then run scripts/eval_accuracy.py (with and without --silence) on each subset file and compare
the two silence-vs-audio deltas.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

FEATURES = ("pitch_var", "loudness_var", "pace")


def load_manifest(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def composite_score(row: dict, features: tuple[str, ...]) -> int:
    """+1 per 'high' bucket, -1 per 'low' bucket, 0 for 'mid', summed across features."""
    acoustic = row["acoustic"]
    score = 0
    for feat in features:
        bucket = acoustic[feat]
        if bucket == "high":
            score += 1
        elif bucket == "low":
            score -= 1
    return score


def print_composition(name: str, rows: list[dict]) -> None:
    counts = Counter(row["emotion"] for row in rows)
    total = len(rows)
    print(f"{name}: {total} rows")
    for emotion, n in counts.most_common():
        print(f"    {emotion:<10} {n:>4}  ({100 * n / total:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", required=True, help="Acoustic-tagged JSONL manifest.")
    parser.add_argument("--out-high", required=True)
    parser.add_argument("--out-low", required=True)
    parser.add_argument(
        "--feature",
        choices=[*FEATURES, "composite"],
        default="composite",
        help="Single acoustic feature to split on, or 'composite' (sum across all three).",
    )
    args = parser.parse_args()

    rows = load_manifest(args.inp)
    features = FEATURES if args.feature == "composite" else (args.feature,)

    high, low = [], []
    for row in rows:
        score = composite_score(row, features)
        if score > 0:
            high.append(row)
        elif score < 0:
            low.append(row)
        # score == 0 (all-mid, or high/low features cancelling out): dropped, ambiguous.

    dropped = len(rows) - len(high) - len(low)
    print(
        f"Split {len(rows)} rows on '{args.feature}': {len(high)} high, {len(low)} low, "
        f"{dropped} dropped (mid / tied).\n"
    )
    print_composition("High-acoustic subset", high)
    print()
    print_composition("Low-acoustic subset", low)

    for path, subset in ((args.out_high, high), (args.out_low, low)):
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for row in subset:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(high)} rows to {args.out_high}")
    print(f"Wrote {len(low)} rows to {args.out_low}")


if __name__ == "__main__":
    main()
