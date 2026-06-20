#!/usr/bin/env python
"""Build a JSONL training manifest from ESD (Emotional Speech Dataset; Zhou et al., NUS/SUTD),
the parallel-text data-level decoupling corpus (RP.md "Data-level" intervention).

Real repo layout, confirmed by direct `ls`/`head` reads on the extracted release (see RP.md
"Open premises") -- NOT the train/evaluation/test three-way split some documentation describes;
this release ships flat per-emotion folders --

    <root>/000X/                  one dir per speaker: 0001-0010 Mandarin, 0011-0020 English.
    <root>/000X/000X.txt           tab-separated: utt_id \t text \t EmotionLabel, e.g.
                                   "0011_000351\tThe nine the eggs, I keep.\tAngry" -- all
                                   1750 (= 350 x 5) of that speaker's utterances in one file,
                                   not split per emotion.
    <root>/000X/<EmotionLabel>/    one .wav per record (e.g. 0011/Angry/0011_000351.wav).
                                   EmotionLabel matches the .txt field exactly: Neutral, Angry,
                                   Happy, Sad, Surprise.

Confirmed by direct read (not just the paper's "350 parallel utterances" prose): the SAME
sentence text recurs across all 5 emotions for a given speaker, at utt-id offsets of exactly
350 from each other (e.g. for speaker 0011, utt 000001/000351/000701/001051/001401 are all
"The nine the eggs, I keep." under Neutral/Angry/Happy/Sad/Surprise respectively). This is
genuinely lexically-identical text with multiple emotion labels -- the property LIME Part B's
public release claims in its paper but doesn't deliver in practice (its `text` field is null for
100% of records; see RP.md "Open premises" and scripts/build_lime_manifest.py). Here the
transcript is real and present, but carries zero label signal by construction, so this corpus
exercises a different decoupling mechanism (same-but-uninformative text) than LIME Part B's
(no text at all) -- both are kept as data-level conditions.

Audio is confirmed 16kHz mono PCM_16 already (no resample needed in practice for this release),
but this script still re-encodes through --sr/soundfile like extract_meld_audio.py and
build_lime_manifest.py do, so the manifest's audio_path is decoupled from wherever the raw
extracted release happens to sit (it can be moved or deleted later without invalidating the
manifest), and a future release at a different sample rate doesn't silently break training.

ESD's label set (neutral/angry/happy/sad/surprise) is a strict subset of MELD's 7-class set --
no fear/disgust. EMOTION_REMAP maps the ones that don't already match MELD's names
(angry->anger, happy->joy, sad->sadness) so MELD + ESD manifests can be combined later; fear/
disgust rows simply never occur in an ESD-only run, reported in the run summary rather than
silently padded.

English speakers only by default (0011-0020, per RP.md's "both English" premise for the
coupled-vs-decoupled comparison); --speakers overrides if the Mandarin set is ever wanted.

Splits by (speaker, sentence-index) GROUP, not by row: the same canonical sentence recurs 5x
per speaker, once per emotion. Splitting at the row level could put some of a sentence's five
emotion-variants in train and the rest in dev -- this doesn't leak a *label* (the whole point of
this corpus is that text is uninformative about the label), but it does leak the literal text
string itself across the split, the same reason build_lime_manifest.py splits by group rather
than by row.

Usage:
    # Smoke test first (small slice, no group split):
    python scripts/build_esd_manifest.py --root "/data/.../Emotion Speech Dataset" --limit 100 \
        --audio-out-dir data/esd_audio_smoke --out data/esd_manifest_smoke.jsonl

    # Full run (English speakers only):
    python scripts/build_esd_manifest.py --root "/data/.../Emotion Speech Dataset" \
        --audio-out-dir data/esd_audio --train-out data/esd_train_manifest.jsonl \
        --dev-out data/esd_dev_manifest.jsonl --dev-frac 0.1
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import librosa
import soundfile as sf

ENGLISH_SPEAKERS = [f"{i:04d}" for i in range(11, 21)]  # 0011-0020, per dataset card + direct read.

EMOTION_REMAP = {
    "angry": "anger",
    "happy": "joy",
    "sad": "sadness",
}
# Known MELD label set, for a sanity-check print only -- not used to remap ESD's labels.
KNOWN_EMOTIONS = {"neutral", "anger", "joy", "sadness", "fear", "disgust", "surprise"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help='Path to the extracted "Emotion Speech Dataset" directory.')
    parser.add_argument(
        "--speakers", nargs="+", default=ENGLISH_SPEAKERS,
        help="Speaker ids to include (default: the 10 English speakers, 0011-0020).",
    )
    parser.add_argument("--audio-out-dir", required=True, help="Directory to write resampled .wav files.")
    parser.add_argument("--out", default=None, help="Single manifest output (no group split).")
    parser.add_argument("--train-out", default=None, help="Train manifest output (use with --dev-out).")
    parser.add_argument("--dev-out", default=None, help="Dev manifest output (use with --train-out).")
    parser.add_argument("--dev-frac", type=float, default=0.1, help="Fraction of (speaker, sentence) GROUPS sent to dev.")
    parser.add_argument("--sr", type=int, default=16000)
    parser.add_argument("--block-size", type=int, default=350, help="Utterances per emotion block in the source numbering.")
    parser.add_argument("--limit", type=int, default=None, help="Cap records scanned (omit to scan every record).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if bool(args.train_out) != bool(args.dev_out):
        raise SystemExit("--train-out and --dev-out must be given together (or neither, with --out).")
    if not args.out and not args.train_out:
        raise SystemExit("Pass either --out, or --train-out together with --dev-out.")

    root = Path(args.root)
    if not root.is_dir():
        raise SystemExit(f"--root {root} doesn't exist.")
    audio_out_dir = Path(args.audio_out_dir)
    audio_out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    seen_emotions: set[str] = set()
    n_scanned = n_bad_line = n_missing_audio = n_decode_failed = 0
    done = False
    for speaker_id in args.speakers:
        if done:
            break
        speaker_dir = root / speaker_id
        txt_path = speaker_dir / f"{speaker_id}.txt"
        if not txt_path.is_file():
            raise SystemExit(f"Missing transcript file {txt_path} -- check --root and --speakers.")

        with open(txt_path, encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]

        for line in lines:
            if args.limit and n_scanned >= args.limit:
                done = True
                break

            parts = line.split("\t")
            if len(parts) != 3:
                n_bad_line += 1
                continue
            utt_id, text, emotion_label = parts

            src_path = speaker_dir / emotion_label / f"{utt_id}.wav"
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
            except Exception as e:  # noqa: BLE001 -- one bad row shouldn't kill a 17.5k-row run.
                n_decode_failed += 1
                print(f"  [skip] {utt_id}: failed to decode audio ({e})")
                continue

            emotion = emotion_label.lower()
            emotion = EMOTION_REMAP.get(emotion, emotion)
            seen_emotions.add(emotion)

            seq = int(utt_id[len(speaker_id) + 1:])
            sentence_idx = ((seq - 1) % args.block_size) + 1
            group = f"{speaker_id}_{sentence_idx:04d}"

            rows.append({
                "audio_path": str(out_path),
                "transcript": text,
                "emotion": emotion,
                "group": group,
                "id": utt_id,
            })
            n_scanned += 1
            if n_scanned % 2000 == 0:
                print(f"  ...{n_scanned} records processed")

    print(
        f"\nScanned {n_scanned} usable records "
        f"(bad lines: {n_bad_line}, missing audio: {n_missing_audio}, decode failures: {n_decode_failed})."
    )
    unknown = seen_emotions - KNOWN_EMOTIONS
    print(f"Distinct emotion labels seen: {sorted(seen_emotions)}")
    if unknown:
        print(
            f"NOTE: {sorted(unknown)} are not in the MELD 7-class set {sorted(KNOWN_EMOTIONS)} -- "
            f"extend EMOTION_REMAP before training on MELD + ESD together."
        )
    missing_classes = KNOWN_EMOTIONS - seen_emotions
    if missing_classes:
        print(f"NOTE: ESD has no examples of {sorted(missing_classes)} -- expected (5-class corpus), not a bug.")

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
