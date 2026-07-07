#!/usr/bin/env python
"""Surface MELD rows where the bare transcript wording and the gold label disagree.

MELD's Sentiment/Emotion labels were assigned by watching the actual scene (audio + video),
so a row where the literal words read as negative/aggressive but the gold label is positive
(or vice versa) is a good candidate for a conflict-robustness check: does the model's CoT
notice the acoustic cues override the surface wording, or does it just parrot the words
(see README.md "Evaluation")? This is a keyword heuristic, not ground truth -- always confirm
candidates by listening to the audio before using them as a test case.

    python scripts/find_conflict_candidates.py --manifest data/meld_dev_manifest.jsonl
"""

import argparse
import json
from pathlib import Path

NEGATIVE_WORDS = [
    "get out", "shut up", "hate", "stupid", "idiot", "kill", "damn", "hell",
    "ugh", "worst", "screw", "shoot you", "sick of",
]
POSITIVE_WORDS = [
    "love", "great", "wonderful", "thank", "happy", "awesome", "amazing", "glad",
]


def naive_sentiment(transcript: str) -> str | None:
    text = transcript.lower()
    if any(w in text for w in NEGATIVE_WORDS):
        return "negative"
    if any(w in text for w in POSITIVE_WORDS):
        return "positive"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = []
    with open(args.manifest, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    found = 0
    for i, row in enumerate(rows):
        guess = naive_sentiment(row["transcript"])
        gold = row.get("sentiment")
        if guess is not None and gold is not None and guess != gold:
            print(f"index={i} gold_sentiment={gold} gold_emotion={row.get('emotion')} (wording reads {guess})")
            print(f"  transcript: {row['transcript']!r}")
            print(f"  audio_path: {row['audio_path']}")
            found += 1
            if found >= args.limit:
                break

    print(f"\n{found} candidate(s) found (keyword heuristic -- confirm by listening before using).")


if __name__ == "__main__":
    main()
