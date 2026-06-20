#!/usr/bin/env python
"""Build a JSONL training manifest from LIME-440K Part B (RP.md "Data-level" intervention).

Real repo layout and field names, confirmed by a direct `HfApi.list_repo_files` + `json.load()`
read (see RP.md "Open premises" and probe_lime_partB.py's docstring) --

    PartB_json_EN/*.json   English Part B annotations: a dict of {utt_id: {text, emotion,
                           scenario, group, wav_path}} per file, NOT JSON-Lines, so
                           `datasets.load_dataset(...)` cannot read it directly. `text` is
                           `null` in 100% of records in this public release (confirmed by an
                           exhaustive scan of all 32 files, 96,000/96,000 records -- see RP.md
                           "Open premises"), so every row here is written out with an empty
                           transcript and trained/evaluated audio-only by construction, not via
                           the probabilistic text_mask_prob masking used for MELD.
    PartB_wav_en.tar.gz    The actual audio, as ONE archive -- not fetched per-row from the
                           Hub. Download and extract it yourself first (per the dataset card):

                               python -c "from huggingface_hub import hf_hub_download as d; \\
                                   print(d('zhaoxiaoxian/LIME-440K_CogAudio-LLM', \\
                                   'PartB_wav_en.tar.gz', repo_type='dataset'))"
                               mkdir -p PartB_wav_en && tar -xzvf <path printed above> -C PartB_wav_en/

                           then pass that directory via --audio-root. Each record's wav_path
                           (e.g. "/4/strong/4_5_surprise.wav") is relative to that root.

This script re-encodes each extracted .wav to --sr (16 kHz mono, matching extract_meld_audio.py's
convention for MELD) and writes the normalized copy to --audio-out-dir, so the manifest's
audio_path always points to a known-good, already-resampled file rather than whatever sample
rate the TTS happened to render at.

emotion labels in the source data are upper-case English words (SURPRISE, HAPPY, SAD, ...).
EMOTION_REMAP lowercases them and maps the ones that don't already match MELD's 7-class names
(HAPPY->joy, SAD->sadness, ANGRY->anger) so MELD + LIME manifests can be combined later. The
full LIME label set hasn't been enumerated yet, so unmapped labels are passed through lowercased
and flagged in the run summary rather than silently guessed at.

Splits by GROUP, not by row: LIME's whole design is multiple rows per group sharing one
scenario/cluster with different emotions (the paper frames this as lexically-identical text per
group; Part B's `text` being null means there's nothing to leak lexically, but the group-level
split is kept anyway for consistency with Part A and in case a future release backfills text).

Usage:
    # Smoke test first (small slice, no group split):
    python scripts/build_lime_manifest.py --audio-root PartB_wav_en/ --limit 50 \
        --audio-out-dir data/lime_audio_smoke --out data/lime_manifest_smoke.jsonl

    # Full run:
    python scripts/build_lime_manifest.py --audio-root PartB_wav_en/ \
        --audio-out-dir data/lime_audio --train-out data/lime_train_manifest.jsonl \
        --dev-out data/lime_dev_manifest.jsonl --dev-frac 0.1
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import librosa
import soundfile as sf
from huggingface_hub import HfApi, hf_hub_download

DEFAULT_DATASET = "zhaoxiaoxian/LIME-440K_CogAudio-LLM"
DEFAULT_PREFIX = "PartB_json_EN/"

EMOTION_REMAP = {
    "happy": "joy",
    "sad": "sadness",
    "angry": "anger",
}
# Known MELD label set, for a sanity-check print only -- not used to remap LIME's labels.
KNOWN_EMOTIONS = {"neutral", "anger", "joy", "sadness", "fear", "disgust", "surprise"}


def list_json_files(api: HfApi, dataset: str, prefix: str) -> list[str]:
    files = api.list_repo_files(dataset, repo_type="dataset")
    matches = sorted(f for f in files if f.startswith(prefix) and f.endswith(".json"))
    if not matches:
        raise SystemExit(f"No .json files under prefix {prefix!r} in {dataset}.")
    return matches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Repo path prefix to scan, e.g. PartB_json_EN/")
    parser.add_argument("--audio-root", required=True, help="Local dir where PartB_wav_en.tar.gz was extracted.")
    parser.add_argument("--audio-out-dir", required=True, help="Directory to write resampled .wav files.")
    parser.add_argument("--text-field", default="text")
    parser.add_argument("--emotion-field", default="emotion")
    parser.add_argument("--group-field", default="group")
    parser.add_argument("--wav-field", default="wav_path")
    parser.add_argument("--out", default=None, help="Single manifest output (no group split).")
    parser.add_argument("--train-out", default=None, help="Train manifest output (use with --dev-out).")
    parser.add_argument("--dev-out", default=None, help="Dev manifest output (use with --train-out).")
    parser.add_argument("--dev-frac", type=float, default=0.1, help="Fraction of GROUPS sent to dev.")
    parser.add_argument("--sr", type=int, default=16000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records scanned (omit to scan every matching file).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if bool(args.train_out) != bool(args.dev_out):
        raise SystemExit("--train-out and --dev-out must be given together (or neither, with --out).")
    if not args.out and not args.train_out:
        raise SystemExit("Pass either --out, or --train-out together with --dev-out.")

    audio_root = Path(args.audio_root)
    if not audio_root.is_dir():
        raise SystemExit(
            f"--audio-root {audio_root} doesn't exist. Extract PartB_wav_en.tar.gz there first "
            f"(see module docstring)."
        )
    audio_out_dir = Path(args.audio_out_dir)
    audio_out_dir.mkdir(parents=True, exist_ok=True)

    api = HfApi()
    json_files = list_json_files(api, args.dataset, args.prefix)
    print(f"{len(json_files)} json files under prefix {args.prefix!r}")

    rows: list[dict] = []
    seen_emotions: set[str] = set()
    n_scanned = n_missing_field = n_missing_audio = n_decode_failed = n_empty_text = 0
    done = False
    for rel_path in json_files:
        if done:
            break
        local_path = hf_hub_download(args.dataset, rel_path, repo_type="dataset")
        with open(local_path, encoding="utf-8") as f:
            data = json.load(f)
        for utt_id, record in data.items():
            if args.limit and n_scanned >= args.limit:
                done = True
                break

            text = record.get(args.text_field)
            raw_emotion = record.get(args.emotion_field)
            group = record.get(args.group_field)
            wav_path = record.get(args.wav_field)
            if raw_emotion is None or group is None or wav_path is None:
                n_missing_field += 1
                continue

            src_path = audio_root / wav_path.lstrip("/")
            if not src_path.is_file():
                n_missing_audio += 1
                print(f"  [skip] {utt_id}: audio not found at {src_path}")
                continue

            out_path = audio_out_dir / f"{utt_id}.wav"
            try:
                y, sr = librosa.load(src_path, sr=None)
                if sr != args.sr:
                    y = librosa.resample(y, orig_sr=sr, target_sr=args.sr)
                sf.write(out_path, y, args.sr)
            except Exception as e:  # noqa: BLE001 -- one bad row shouldn't kill a 96k-row run.
                n_decode_failed += 1
                print(f"  [skip] {utt_id}: failed to decode audio ({e})")
                continue

            emotion = str(raw_emotion).lower()
            emotion = EMOTION_REMAP.get(emotion, emotion)
            seen_emotions.add(emotion)
            if not text:
                n_empty_text += 1
            rows.append({
                "audio_path": str(out_path),
                "transcript": text or "",
                "emotion": emotion,
                "group": group,
                "id": utt_id,
            })
            n_scanned += 1
            if n_scanned % 2000 == 0:
                print(f"  ...{n_scanned} records processed")

    print(
        f"\nScanned {n_scanned} usable records "
        f"(missing fields: {n_missing_field}, missing audio: {n_missing_audio}, decode failures: {n_decode_failed})."
    )
    if n_scanned:
        print(
            f"{n_empty_text}/{n_scanned} rows ({n_empty_text / n_scanned:.1%}) have an empty/null "
            f"transcript -- those rows train/eval audio-only regardless of text_mask_prob "
            f"(see RP.md \"Open premises\")."
        )
    unknown = seen_emotions - KNOWN_EMOTIONS
    print(f"Distinct emotion labels seen: {sorted(seen_emotions)}")
    if unknown:
        print(
            f"NOTE: {sorted(unknown)} are not in the MELD 7-class set {sorted(KNOWN_EMOTIONS)} -- "
            f"extend EMOTION_REMAP before training on MELD + LIME together."
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
            target_f, bucket = (dev_f, "dev") if gid in dev_group_ids else (train_f, "train")
            for row in group_rows:
                target_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if bucket == "dev":
                n_dev += len(group_rows)
            else:
                n_train += len(group_rows)
    print(
        f"Wrote {n_train} rows ({len(group_ids) - n_dev_groups} groups) to {train_path}\n"
        f"Wrote {n_dev} rows ({n_dev_groups} groups) to {dev_path}"
    )


if __name__ == "__main__":
    main()
