#!/usr/bin/env python
"""Test whether the fine-tuned model actually USES the audio, or just reads the transcript.

The Phase 1 CoT targets are templated from the gold label (see data/prompts.py
build_synthetic_cot_target), so a model can score well while ignoring the waveform entirely
and reading the transcript alone. The CoT text cannot reveal this on its own, because its
"acoustic cue" is a deterministic per-emotion placeholder keyed on the predicted label.

This script settles the question by intervention: hold the transcript fixed and vary ONLY the
audio fed to the model, then compare the final label across conditions.

    original : the real, matched clip for the transcript
    silence  : an equal-length silent waveform (audio information removed)
    swap     : audio borrowed from another row with a DIFFERENT gold emotion

If the label is invariant when the audio is removed/swapped, the model is not using the audio
-- the rationale is post-hoc justification of a transcript-only decision. If the label tracks
the audio, that is real evidence of audio grounding.

    python scripts/audio_ablation.py --adapter outputs/meld_lora/final \
        --manifest data/meld_dev_manifest.jsonl --indices 0,5,12 \
        --out outputs/ablation.jsonl
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import torch
from peft import PeftModel
from transformers import AutoProcessor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.model_loading import load_base_model  # noqa: E402
from data.prompts import build_conversation  # noqa: E402

ANSWER_KEY = "Emotion"


def load_manifest(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_label(completion: str, answer_key: str = ANSWER_KEY) -> str | None:
    """Pull the final '<answer_key>: <value>' label out of a completion, lowercased."""
    matches = re.findall(rf"{re.escape(answer_key)}\s*:\s*(.+)", completion)
    if not matches:
        return None
    return matches[-1].strip().split("\n")[0].strip().lower()


def pick_swap_donor(target: dict, rows: list[dict], rng: random.Random) -> dict | None:
    """A RANDOM row whose gold emotion differs from the target's (a contrasting clip).

    Random (seeded) rather than "first match" so different targets borrow different donor
    clips -- otherwise every swap reuses the same clip and the test collapses to a single
    audio sample biased toward one emotion.
    """
    target_emotion = (target.get("emotion") or "").lower()
    candidates = [c for c in rows if (c.get("emotion") or "").lower() != target_emotion]
    return rng.choice(candidates) if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2-Audio-7B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--manifest", required=True, help="JSONL manifest to draw rows from.")
    parser.add_argument(
        "--indices", default=None,
        help="Comma-separated 0-based row indices to run (default: all rows in the manifest).",
    )
    parser.add_argument("--out", required=True, help="Output JSONL report path.")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument(
        "--conditions", default="original,silence,swap",
        help="Comma-separated subset of: original, silence, swap.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed for random swap-donor choice.")
    args = parser.parse_args()

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    rng = random.Random(args.seed)
    all_rows = load_manifest(args.manifest)
    if args.indices is not None:
        wanted = [int(i) for i in args.indices.split(",")]
        target_rows = [all_rows[i] for i in wanted]
    else:
        target_rows = all_rows

    processor = AutoProcessor.from_pretrained(args.base_model)
    sr = processor.feature_extractor.sampling_rate
    model = load_base_model(args.base_model)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    def run(conversation: list[dict], audio_array: np.ndarray) -> str:
        prompt_text = processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False
        )
        inputs = processor(
            text=prompt_text, audio=[audio_array], sampling_rate=sr, return_tensors="pt"
        ).to(model.device)
        with torch.no_grad():
            # Greedy decoding: any label difference between conditions must come from the
            # audio change, not from the base model's default sampling (do_sample=True in its
            # generation_config.json, intended for varied chit-chat, not a controlled ablation).
            generated = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens, do_sample=False, num_beams=1
            )
        return processor.tokenizer.decode(
            generated[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Three distinct signals, reported separately (a single "audio-sensitive" count conflates them):
    n_silence_changed = 0   # label changed when audio was REMOVED (silence)
    n_silence_eval = 0
    n_swap_changed = 0      # label changed when audio was SUBSTITUTED (swap)
    n_swap_eval = 0
    n_swap_followed = 0     # swap label == donor's gold emotion (does the label TRACK the audio)
    n_swap_follow_eval = 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for i, row in enumerate(target_rows):
            # Transcript is held FIXED across conditions -- only the audio changes.
            conversation = build_conversation(row["audio_path"], row["transcript"], ANSWER_KEY)
            original_audio = librosa.load(row["audio_path"], sr=sr)[0]

            audio_variants: dict[str, np.ndarray] = {}
            if "original" in conditions:
                audio_variants["original"] = original_audio
            if "silence" in conditions:
                audio_variants["silence"] = np.zeros_like(original_audio)
            swap_donor = None
            if "swap" in conditions:
                swap_donor = pick_swap_donor(row, all_rows, rng)
                if swap_donor is not None:
                    audio_variants["swap"] = librosa.load(swap_donor["audio_path"], sr=sr)[0]

            per_condition = {}
            for cond, audio_array in audio_variants.items():
                completion = run(conversation, audio_array)
                per_condition[cond] = {
                    "completion": completion,
                    "label": parse_label(completion),
                }

            base_label = per_condition.get("original", {}).get("label")
            silence_changed = swap_changed = swap_followed = None
            if base_label is not None and "silence" in per_condition:
                n_silence_eval += 1
                silence_changed = per_condition["silence"]["label"] != base_label
                n_silence_changed += int(silence_changed)
            if base_label is not None and "swap" in per_condition:
                n_swap_eval += 1
                swap_changed = per_condition["swap"]["label"] != base_label
                n_swap_changed += int(swap_changed)
            if swap_donor is not None and "swap" in per_condition:
                donor_emotion = (swap_donor.get("emotion") or "").lower()
                if donor_emotion:
                    n_swap_follow_eval += 1
                    swap_followed = per_condition["swap"]["label"] == donor_emotion
                    n_swap_followed += int(swap_followed)

            result = {
                "audio_path": row["audio_path"],
                "transcript": row["transcript"],
                "gold_emotion": row.get("emotion"),
                "swap_donor_emotion": (swap_donor or {}).get("emotion"),
                "conditions": per_condition,
                "silence_changed_label": silence_changed,
                "swap_changed_label": swap_changed,
                "swap_label_followed_donor_emotion": swap_followed,
            }
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")

            labels_str = "  ".join(f"{c}={per_condition[c]['label']!r}" for c in per_condition)
            donor = f" (donor={swap_donor['emotion']})" if swap_donor else ""
            print(f"[{i + 1}/{len(target_rows)}] {Path(row['audio_path']).name}: {labels_str}{donor}")

    print(f"\nWrote {len(target_rows)} rows to {out_path}")
    if n_silence_eval:
        print(
            f"silence:  {n_silence_changed}/{n_silence_eval} rows changed label when audio was "
            f"REMOVED. 0 => the model falls back to a transcript-driven answer; high => the "
            f"original prediction leaned on the audio."
        )
    if n_swap_eval:
        print(
            f"swap:     {n_swap_changed}/{n_swap_eval} rows changed label when audio was "
            f"SUBSTITUTED with a contrasting clip."
        )
    if n_swap_follow_eval:
        print(
            f"tracking: {n_swap_followed}/{n_swap_follow_eval} swap labels MATCHED the donor "
            f"clip's emotion. This is the strongest grounding signal: high => the label follows "
            f"whatever the audio says, low => the audio only nudges and the transcript dominates."
        )
    if not (n_silence_eval or n_swap_eval):
        print("No evaluable rows (need the 'original' condition plus 'silence' and/or 'swap').")


if __name__ == "__main__":
    main()
