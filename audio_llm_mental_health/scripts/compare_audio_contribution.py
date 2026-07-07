#!/usr/bin/env python
"""Diff two eval_accuracy.py JSONL dumps to isolate audio's marginal contribution to accuracy.

Run eval_accuracy.py twice on the SAME --seed/--sample (once normally, once with --silence),
each with --out pointing at a different file, then:

    python scripts/compare_audio_contribution.py \
        --with-audio outputs/eval_accuracy.jsonl \
        --silenced outputs/eval_accuracy_silence.jsonl

Overall accuracy with vs. without audio answers a different question than the swap/tracking
test in audio_ablation.py: that test asked "does the label follow an arbitrary substituted
clip's emotion" (it doesn't, ~chance). This asks "does having the real matching audio at all
help get the gold label right, compared to no audio" -- a weaker but more direct test of
whether the audio channel is contributing anything beyond what the transcript already gives.
"""

import argparse
import json
from pathlib import Path


def load(path: str) -> dict[str, dict]:
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[row["audio_path"]] = row
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-audio", required=True, help="eval_accuracy.py --out, real audio.")
    parser.add_argument("--silenced", required=True, help="eval_accuracy.py --out, --silence run.")
    args = parser.parse_args()

    with_audio = load(args.with_audio)
    silenced = load(args.silenced)
    shared = sorted(set(with_audio) & set(silenced))
    if not shared:
        raise SystemExit("No overlapping audio_path between the two dumps -- same --seed/--sample?")

    n = audio_correct = silence_correct = audio_helped = audio_hurt = both_wrong_diff = 0
    for path in shared:
        a, s = with_audio[path], silenced[path]
        if a["correct"] is None or s["correct"] is None:
            continue
        n += 1
        audio_correct += bool(a["correct"])
        silence_correct += bool(s["correct"])
        if a["correct"] and not s["correct"]:
            audio_helped += 1  # right with real audio, wrong when silenced
        elif s["correct"] and not a["correct"]:
            audio_hurt += 1    # wrong with real audio, right when silenced (suspicious)
        elif not a["correct"] and not s["correct"] and a["pred"] != s["pred"]:
            both_wrong_diff += 1  # wrong either way, but the guess itself changed

    print(f"Compared {n} rows present in both dumps.\n")
    print(f"Accuracy with real audio: {audio_correct / n:.3f} ({audio_correct}/{n})")
    print(f"Accuracy with silence:    {silence_correct / n:.3f} ({silence_correct}/{n})")
    print(f"Delta (audio - silence):  {(audio_correct - silence_correct) / n:+.3f}\n")
    print(f"Rows where real audio was needed to get it right (correct->wrong when silenced): {audio_helped}/{n}")
    print(f"Rows where silence was *better* than real audio (wrong->right when silenced):    {audio_hurt}/{n}")
    print(f"Rows wrong both ways but the guess itself changed:                               {both_wrong_diff}/{n}")

    print("\nRead it:")
    print("  * delta near 0 and audio_helped near 0 => the transcript alone explains the")
    print("    original accuracy; the audio channel isn't contributing to correctness, only")
    print("    adding noise (consistent with the ablation's near-chance tracking rate). An")
    print("    audio-only retrain has nothing to build on for THIS data/model pairing.")
    print("  * delta clearly positive with non-trivial audio_helped => real audio measurably")
    print("    helps accuracy even though it doesn't track arbitrary swapped emotions -- the")
    print("    audio-only retrain (remove the transcript at train+eval time) is the most")
    print("    promising next step to convert that into genuine, inspectable grounding.")


if __name__ == "__main__":
    main()
