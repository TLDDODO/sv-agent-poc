#!/usr/bin/env python
"""Build a JSONL training manifest from LIME-440K Part B (RP.md "Data-level" intervention).

Field names below (group/text/emotion/audio/id) are EDUCATED GUESSES, not confirmed -- run
probe_lime_partB.py --dump-schema first and pass the real names via the matching --*-field
flag if they differ. Auto-detection here exists so this script can be drafted and reviewed
before that real schema is in hand, not as a substitute for it.

Unlike probe_lime_partB.py (read-only, drops audio), this script materializes audio to local
.wav files, so it actually pulls the dataset rather than just streaming column names -- run it
on the H100's login/transfer node (compute nodes offline, per RP.md "Environment").

Splits by GROUP, not by row: LIME's whole design is multiple rows per group sharing identical
text with different emotions (see RP.md "Open premises"). Splitting at the row level could put
near-duplicate-text rows from the same group on both sides of train/dev, leaking the transcript
across the split. Group-level split keeps that contamination out.

Usage:
    # Smoke test first (small slice, no group split):
    python scripts/build_lime_manifest.py \
        --dataset zhaoxiaoxian/LIME-440K_CogAudio-LLM --limit 50 \
        --audio-out-dir data/lime_audio_smoke --out data/lime_manifest_smoke.jsonl

    # Full run, once the real field names are confirmed:
    python scripts/build_lime_manifest.py \
        --dataset zhaoxiaoxian/LIME-440K_CogAudio-LLM \
        --group-field <real_name> --text-field <real_name> --emotion-field <real_name> \
        --audio-out-dir data/lime_audio --train-out data/lime_train_manifest.jsonl \
        --dev-out data/lime_dev_manifest.jsonl --dev-frac 0.1
"""

import argparse
import io
import random
from collections import defaultdict
import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from datasets import load_dataset

TEXT_FIELD_CANDIDATES = ["text", "transcript", "sentence", "content", "utterance"]
EMOTION_FIELD_CANDIDATES = ["emotion", "label", "emotion_label", "emo"]
GROUP_FIELD_CANDIDATES = ["group", "group_id", "text_id", "sentence_id", "cluster_id", "pair_id"]
AUDIO_FIELD_CANDIDATES = ["audio", "audio_path", "wav", "speech"]
ID_FIELD_CANDIDATES = ["id", "utterance_id", "uid", "sample_id"]

# Known MELD label set, for a sanity-check print only -- not used to remap LIME's labels.
KNOWN_EMOTIONS = {"neutral", "anger", "joy", "sadness", "fear", "disgust", "surprise"}


def pick_field(columns: list[str], candidates: list[str], kind: str) -> str:
    for c in candidates:
        if c in columns:
            return c
    raise SystemExit(
        f"Could not auto-detect the {kind} field among columns {columns}. "
        f"Pass --{kind}-field explicitly (run probe_lime_partB.py --dump-schema first)."
    )


def pick_field_optional(columns: list[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


def extract_audio_array(value, target_sr: int) -> np.ndarray:
    """Handle the few shapes a HF `Audio` feature value can take. Defensive because the real
    schema isn't confirmed yet (see module docstring)."""
    if isinstance(value, dict) and value.get("array") is not None:
        y, sr = np.asarray(value["array"], dtype=np.float32), value.get("sampling_rate", target_sr)
    elif isinstance(value, dict) and value.get("bytes"):
        y, sr = sf.read(io.BytesIO(value["bytes"]), dtype="float32")
    elif isinstance(value, str):
        y, sr = librosa.load(value, sr=None)
    else:
        raise ValueError(f"Unrecognized audio field value type: {type(value)}")
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
    return y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="zhaoxiaoxian/LIME-440K_CogAudio-LLM")
    parser.add_argument("--config", default=None, help="HF dataset config name, if Part A/B are separate configs")
    parser.add_argument("--split", default="train")
    parser.add_argument("--language-field", default=None, help="Column to filter on, if Part A/B share one split")
    parser.add_argument("--language-value", default="English")
    parser.add_argument("--group-field", default=None)
    parser.add_argument("--text-field", default=None)
    parser.add_argument("--emotion-field", default=None)
    parser.add_argument("--audio-field", default=None)
    parser.add_argument("--id-field", default=None, help="Optional; falls back to a running index.")
    parser.add_argument("--audio-out-dir", required=True, help="Directory to write extracted .wav files.")
    parser.add_argument("--out", default=None, help="Single manifest output (no group split).")
    parser.add_argument("--train-out", default=None, help="Train manifest output (use with --dev-out).")
    parser.add_argument("--dev-out", default=None, help="Dev manifest output (use with --train-out).")
    parser.add_argument("--dev-frac", type=float, default=0.1, help="Fraction of GROUPS sent to dev.")
    parser.add_argument("--sr", type=int, default=16000)
    parser.add_argument("--limit", type=int, default=None, help="Cap rows scanned (omit to scan the full split).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if bool(args.train_out) != bool(args.dev_out):
        raise SystemExit("--train-out and --dev-out must be given together (or neither, with --out).")
    if not args.out and not args.train_out:
        raise SystemExit("Pass either --out, or --train-out together with --dev-out.")

    ds = load_dataset(args.dataset, name=args.config, split=args.split, streaming=True)
    sample = next(iter(ds.take(1)))
    columns = list(sample.keys())

    group_field = args.group_field or pick_field(columns, GROUP_FIELD_CANDIDATES, "group")
    text_field = args.text_field or pick_field(columns, TEXT_FIELD_CANDIDATES, "text")
    emotion_field = args.emotion_field or pick_field(columns, EMOTION_FIELD_CANDIDATES, "emotion")
    audio_field = args.audio_field or pick_field(columns, AUDIO_FIELD_CANDIDATES, "audio")
    id_field = args.id_field or pick_field_optional(columns, ID_FIELD_CANDIDATES)
    print(
        f"Using fields: group={group_field!r} text={text_field!r} emotion={emotion_field!r} "
        f"audio={audio_field!r} id={id_field!r}"
    )

    audio_out_dir = Path(args.audio_out_dir)
    audio_out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    seen_emotions: set[str] = set()
    n_scanned = n_filtered_out = n_failed = 0
    for row in ds:
        if args.language_field and row.get(args.language_field) != args.language_value:
            n_filtered_out += 1
            continue
        idx = n_scanned
        n_scanned += 1
        if args.limit and n_scanned > args.limit:
            break

        stem = str(row[id_field]) if id_field else f"row{idx:06d}"
        wav_path = audio_out_dir / f"{stem}.wav"
        try:
            y = extract_audio_array(row[audio_field], target_sr=args.sr)
        except Exception as e:  # noqa: BLE001 -- one bad row shouldn't kill a 96k-row run.
            n_failed += 1
            print(f"  [skip] {stem}: failed to decode audio ({e})")
            continue
        sf.write(wav_path, y, args.sr)

        emotion = str(row[emotion_field]).lower()
        seen_emotions.add(emotion)
        rows.append({
            "audio_path": str(wav_path),
            "transcript": row[text_field],
            "emotion": emotion,
            "group": row[group_field],
        })
        if n_scanned % 500 == 0:
            print(f"  ...{n_scanned} rows processed")

    print(f"\nScanned {n_scanned} rows (filtered out {n_filtered_out}, decode failures {n_failed}).")
    unknown = seen_emotions - KNOWN_EMOTIONS
    print(f"Distinct emotion labels seen: {sorted(seen_emotions)}")
    if unknown:
        print(
            f"NOTE: {sorted(unknown)} are not in the MELD 7-class set {sorted(KNOWN_EMOTIONS)} -- "
            f"check whether these need remapping before training on MELD + LIME together."
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(rows)} rows to {out_path}")
        return

    groups: dict = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    group_ids = list(groups.keys())
    random.Random(args.seed).shuffle(group_ids)
    n_dev_groups = max(1, round(len(group_ids) * args.dev_frac))
    dev_group_ids = set(group_ids[:n_dev_groups])

    train_path, dev_path = Path(args.train_out), Path(args.dev_out)
    train_path.parent.mkdir(parents=True, exist_ok=True)
    dev_path.parent.mkdir(parents=True, exist_ok=True)
    n_train = n_dev = 0
    with open(train_path, "w", encoding="utf-8") as train_f, open(dev_path, "w", encoding="utf-8") as dev_f:
        for gid, group_rows in groups.items():
            target_f, counter = (dev_f, "dev") if gid in dev_group_ids else (train_f, "train")
            for row in group_rows:
                target_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if counter == "dev":
                n_dev += len(group_rows)
            else:
                n_train += len(group_rows)
    print(
        f"Wrote {n_train} rows ({len(group_ids) - n_dev_groups} groups) to {train_path}\n"
        f"Wrote {n_dev} rows ({n_dev_groups} groups) to {dev_path}"
    )


if __name__ == "__main__":
    main()
