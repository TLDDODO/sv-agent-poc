#!/usr/bin/env python
"""Extract per-utterance .wav audio from MELD's raw .mp4 video clips (run on the H100).

MELD.Raw.tar.gz ships train/dev/test video clips named "dia{Dialogue_ID}_utt{Utterance_ID}.mp4"
inside split-specific subfolders (e.g. "train_splits/", "dev_splits_complete/"). This script
flattens any one of those folders into a directory of same-named .wav files, which is what
prepare_meld_manifest.py's default --filename-template ("dia{Dialogue_ID}_utt{Utterance_ID}.wav")
expects via --audio-dir. Requires ffmpeg on PATH.

Usage (run once per split):
    python extract_meld_audio.py --video-dir MELD.Raw/train_splits --out-dir MELD.Raw/train_audio
    python extract_meld_audio.py --video-dir MELD.Raw/dev_splits_complete --out-dir MELD.Raw/dev_audio
"""

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", required=True, help="Directory of MELD .mp4 clips.")
    parser.add_argument("--out-dir", required=True, help="Output directory for .wav files.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    args = parser.parse_args()

    video_dir = Path(args.video_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(video_dir.glob("*.mp4"))
    converted, skipped, failed = 0, 0, 0
    for video_path in videos:
        wav_path = out_dir / (video_path.stem + ".wav")
        if wav_path.exists():
            skipped += 1
            continue
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-ar", str(args.sample_rate), "-ac", "1",
                str(wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            failed += 1
            print(f"ffmpeg failed on {video_path.name}: {result.stderr.decode(errors='replace')[-300:]}")
            continue
        converted += 1

    print(f"Converted {converted}, skipped {skipped} (already existed), failed {failed}.")


if __name__ == "__main__":
    main()
