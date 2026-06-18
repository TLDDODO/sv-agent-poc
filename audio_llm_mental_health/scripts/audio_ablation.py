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
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration

sys.path.append(str(Path(__file__).resolve().parent.parent))
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


def pick_swap_donor(target: dict, rows: list[dict]) -> dict | None:
    """First row whose gold emotion differs from the target's (a contrasting clip)."""
    target_emotion = (target.get("emotion") or "").lower()
    for cand in rows:
        if (cand.get("emotion") or "").lower() != target_emotion:
            return cand
    return None


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
    args = parser.parse_args()

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    all_rows = load_manifest(args.manifest)
    if args.indices is not None:
        wanted = [int(i) for i in args.indices.split(",")]
        target_rows = [all_rows[i] for i in wanted]
    else:
        target_rows = all_rows

    processor = AutoProcessor.from_pretrained(args.base_model)
    sr = processor.feature_extractor.sampling_rate
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        args.base_model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
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
            generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
        return processor.tokenizer.decode(
            generated[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_audio_sensitive = 0
    n_evaluable = 0
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
                swap_donor = pick_swap_donor(row, all_rows)
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
            varied = [c for c in ("silence", "swap") if c in per_condition]
            changed = None
            if base_label is not None and varied:
                n_evaluable += 1
                changed = any(per_condition[c]["label"] != base_label for c in varied)
                if changed:
                    n_audio_sensitive += 1

            result = {
                "audio_path": row["audio_path"],
                "transcript": row["transcript"],
                "gold_emotion": row.get("emotion"),
                "swap_donor_emotion": (swap_donor or {}).get("emotion"),
                "conditions": per_condition,
                "label_changed_when_audio_varied": changed,
            }
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")

            labels_str = "  ".join(f"{c}={per_condition[c]['label']!r}" for c in per_condition)
            verdict = "" if changed is None else ("  <- AUDIO-SENSITIVE" if changed else "  (label unchanged)")
            print(f"[{i + 1}/{len(target_rows)}] {Path(row['audio_path']).name}: {labels_str}{verdict}")

    print(f"\nWrote {len(target_rows)} rows to {out_path}")
    if n_evaluable:
        print(
            f"{n_audio_sensitive}/{n_evaluable} rows changed their label when the audio was "
            f"removed/swapped (transcript held fixed)."
        )
        if n_audio_sensitive == 0:
            print(
                "  -> 0 means the label is invariant to the audio on this sample: the model is "
                "reading the transcript, not listening. The CoT's acoustic cues are post-hoc."
            )
        else:
            print(
                "  -> non-zero means the label tracks the audio on at least some rows: evidence "
                "the model is using the waveform, not just the transcript."
            )
    else:
        print("No evaluable rows (need the 'original' condition plus 'silence' and/or 'swap').")


if __name__ == "__main__":
    main()
