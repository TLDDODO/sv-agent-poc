#!/usr/bin/env python
"""Extract real acoustic features from each clip and bucket them against corpus percentiles.

This is the data-side fix for the text-dominance result in RP.md "Preliminary Result": the
Phase-1 CoT target was a deterministic function of the gold label, so the model never had to
listen. Here we measure actual acoustic quantities (pitch variability, loudness dynamics, pace)
straight from the waveform with librosa, then bucket each into low/mid/high by the corpus's own
tertiles -- so the thresholds come from the data, not hand-picked magic numbers.

data/prompts.py:build_decoupled_cot_target turns these buckets into the CoT's "acoustic
evidence" clause. Because those facts can only be known by listening, silencing or hiding the
audio makes the target unreachable, which forces gradient descent to route through the audio
encoder instead of shortcutting from the transcript.

Run on the H100 (needs the raw audio), once per split, BEFORE train_lora.py:

    python scripts/extract_acoustic_priors.py \
        --in data/meld_train_manifest.jsonl --out data/meld_train_manifest_acoustic.jsonl
"""

import argparse
import json
from pathlib import Path

import librosa
import numpy as np

FEATURES = ("pitch_var", "loudness_var", "pace")


def raw_features(audio_path: str, sr: int = 16000) -> dict[str, float]:
    """Crude but real, listen-only acoustic descriptors. Exactness matters less than that they
    vary across clips and cannot be recovered from the transcript."""
    y, sr = librosa.load(audio_path, sr=sr)
    duration = max(len(y) / sr, 1e-6)
    rms = librosa.feature.rms(y=y)[0]

    # Energy-gate pitch tracking so unvoiced/silent frames don't dominate the variability.
    f0 = librosa.yin(y, fmin=65, fmax=400, sr=sr)
    if rms.size and f0.size:
        gate = rms[: f0.size] > (0.5 * np.median(rms) + 1e-8)
        voiced = f0[: gate.size][gate] if gate.any() else f0
    else:
        voiced = f0
    pitch_var = float(np.std(voiced)) if voiced.size else 0.0

    loudness_var = float(np.std(rms)) if rms.size else 0.0
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    pace = float(len(onsets) / duration)  # onsets per second, a speech-rate proxy

    return {"pitch_var": pitch_var, "loudness_var": loudness_var, "pace": pace}


def tertiles(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    return float(np.percentile(arr, 33.3)), float(np.percentile(arr, 66.7))


def bucket(value: float, lo: float, hi: float) -> str:
    if value <= lo:
        return "low"
    if value >= hi:
        return "high"
    return "mid"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", required=True, help="Input JSONL manifest.")
    parser.add_argument("--out", required=True, help="Output JSONL with an added 'acoustic' field.")
    parser.add_argument("--sr", type=int, default=16000)
    args = parser.parse_args()

    rows = []
    with open(args.inp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Pass 1: measure raw features (the expensive, audio-reading pass).
    raw: list[dict[str, float]] = []
    for i, row in enumerate(rows):
        raw.append(raw_features(row["audio_path"], sr=args.sr))
        if (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{len(rows)} clips measured")

    # Corpus tertiles per feature => data-driven thresholds, not magic numbers.
    thresholds = {feat: tertiles([r[feat] for r in raw]) for feat in FEATURES}
    print("Corpus tertile thresholds (low<=t33, high>=t67):")
    for feat, (lo, hi) in thresholds.items():
        print(f"  {feat:<12} t33={lo:.3f}  t67={hi:.3f}")

    # Pass 2: bucket and write.
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out_f:
        for row, r in zip(rows, raw):
            acoustic = {feat: bucket(r[feat], *thresholds[feat]) for feat in FEATURES}
            acoustic["_raw"] = {feat: round(r[feat], 4) for feat in FEATURES}
            row["acoustic"] = acoustic
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(rows)} rows with acoustic priors to {out_path}")


if __name__ == "__main__":
    main()
