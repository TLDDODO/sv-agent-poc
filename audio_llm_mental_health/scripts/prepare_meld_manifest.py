#!/usr/bin/env python
"""Build a JSONL training manifest from a MELD split (run on the H100, needs pandas).

MELD (https://affective-meld.github.io/) ships a CSV per split with one row per utterance
(Utterance, Emotion, Sentiment, Dialogue_ID, Utterance_ID, ...) plus raw video that must be
extracted to per-utterance audio (commonly named "dia{Dialogue_ID}_utt{Utterance_ID}.wav") by
MELD's own extraction scripts before this runs.

Usage:
    python prepare_meld_manifest.py \
        --csv MELD.Raw/train_sent_emo.csv \
        --audio-dir MELD.Raw/train_splits_audio \
        --out ../data/meld_train_manifest.jsonl
"""

import argparse
import json
from pathlib import Path

import pandas as pd

# Generic placeholder cue phrases per emotion, used only to seed the synthetic CoT target
# (see data/prompts.py). These are not derived from the audio itself.
EMOTION_CUES = {
    "joy": ["an upbeat tone", "brisk pacing"],
    "anger": ["a raised, tense tone", "sharper word choice"],
    "sadness": ["a low, slow tone", "subdued pacing"],
    "fear": ["a shaky, hesitant tone"],
    "disgust": ["a sharp, clipped tone"],
    "surprise": ["a sudden rise in pitch"],
    "neutral": ["an even, flat tone"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to a MELD split CSV.")
    parser.add_argument(
        "--audio-dir", required=True, help="Directory of per-utterance audio extracted from MELD."
    )
    parser.add_argument("--out", required=True, help="Output JSONL manifest path.")
    parser.add_argument(
        "--filename-template",
        default="dia{Dialogue_ID}_utt{Utterance_ID}.wav",
        help="Audio filename pattern, formatted against each CSV row.",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    audio_dir = Path(args.audio_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written, skipped = 0, 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for _, row in df.iterrows():
            filename = args.filename_template.format(**row.to_dict())
            audio_path = audio_dir / filename
            if not audio_path.exists():
                skipped += 1
                continue
            emotion = str(row["Emotion"]).lower()
            example = {
                "audio_path": str(audio_path),
                "transcript": str(row["Utterance"]),
                "emotion": emotion,
                "sentiment": str(row["Sentiment"]).lower(),
                "cues": EMOTION_CUES.get(emotion, []),
            }
            out_f.write(json.dumps(example, ensure_ascii=False) + "\n")
            written += 1

    print(f"Wrote {written} examples to {out_path} ({skipped} rows skipped, audio not found).")


if __name__ == "__main__":
    main()
