#!/usr/bin/env python
"""Donor-swap / silence ruler for a DUAL-ENCODER adapter (scripts/train_dual_encoder.py output).

Same fixed ruler as scripts/audio_ablation.py -- hold the prompt fixed, vary only the audio
(original / silence / swap), and read whether the predicted emotion follows the audio -- but for a
model whose audio path includes the injected emotion token. So generation must reproduce the
training-time injection: forward #1 (no_grad) lets the base model do its own audio merge and we take
hidden_states[0] (the audio-merged inputs_embeds); we prepend the emotion tower's projected token;
then generate from those inputs_embeds. The varied audio_array is fed to BOTH the semantic processor
(input_features) and the emotion tower, so silence/swap perturb both towers exactly as intended.

The headline number is the same tracking ratio the data-level cells report (swap label == donor
emotion / N on the fixed 15-row set), so a dual-encoder MELD run drops straight into RP.md's
gradient table next to baseline 3/15, textmask1 9/15, LIME 13/15, ESD 15/15 -- the apples-to-apples
comparison of objective-level vs data-level decoupling.

    python scripts/eval_dual_encoder.py --adapter outputs/dual_meld/final \
        --manifest data/meld_dev_manifest.jsonl --audio-only \
        --indices 228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034 \
        --out outputs/ablation_dual_meld.jsonl

The emotion projection is loaded from <adapter>/emotion_proj.pt (saved beside the LoRA adapter by
train_dual_encoder.py). --encoder must match what the run trained with (default hubert-base-ls960).
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
from data.emotion_tower import EmotionTower  # noqa: E402
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
    matches = re.findall(rf"{re.escape(answer_key)}\s*:\s*(.+)", completion)
    if not matches:
        return None
    return matches[-1].strip().split("\n")[0].strip().lower()


def pick_swap_donor(target: dict, rows: list[dict], rng: random.Random) -> dict | None:
    target_emotion = (target.get("emotion") or "").lower()
    candidates = [c for c in rows if (c.get("emotion") or "").lower() != target_emotion]
    return rng.choice(candidates) if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2-Audio-7B-Instruct")
    parser.add_argument("--adapter", required=True, help="Dir with the LoRA adapter + emotion_proj.pt")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--indices", default=None, help="Comma-separated 0-based row indices.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--conditions", default="original,silence,swap")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--audio-only", action="store_true")
    parser.add_argument("--encoder", default="facebook/hubert-base-ls960",
                        help="Must match the emotion_encoder the adapter trained with.")
    args = parser.parse_args()

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    rng = random.Random(args.seed)
    all_rows = load_manifest(args.manifest)
    target_rows = ([all_rows[int(i)] for i in args.indices.split(",")]
                   if args.indices is not None else all_rows)

    processor = AutoProcessor.from_pretrained(args.base_model)
    sr = processor.feature_extractor.sampling_rate
    model = load_base_model(args.base_model)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    base = model.get_base_model()

    # Emotion tower: same architecture as training, with the trained projection weights restored.
    emotion_tower = EmotionTower(
        llm_hidden=base.config.text_config.hidden_size, encoder_name=args.encoder
    ).to(model.device)
    proj_path = Path(args.adapter) / "emotion_proj.pt"
    if not proj_path.exists():
        raise FileNotFoundError(f"{proj_path} not found -- dual-encoder eval needs the emotion "
                                f"projection saved beside the adapter by train_dual_encoder.py.")
    emotion_tower.proj.load_state_dict(torch.load(proj_path, map_location=model.device))
    emotion_tower.eval()

    def run(conversation: list[dict], audio_array: np.ndarray) -> str:
        prompt_text = processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False)
        inputs = processor(text=prompt_text, audio=[audio_array], sampling_rate=sr,
                           return_tensors="pt").to(model.device)
        with torch.no_grad():
            # forward #1: base model's own audio merge -> hidden_states[0] is the merged embeds.
            out1 = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"],
                         input_features=inputs["input_features"],
                         feature_attention_mask=inputs["feature_attention_mask"],
                         output_hidden_states=True, use_cache=False)
            merged = out1.hidden_states[0]                          # (1, S, D)
            emo = emotion_tower([audio_array]).to(merged.dtype)     # (1, D)
            inputs_embeds = torch.cat([emo.unsqueeze(1), merged], dim=1)  # (1, S+1, D)
            attn = inputs["attention_mask"].new_ones((1, inputs_embeds.shape[1]))
            generated = model.generate(inputs_embeds=inputs_embeds, attention_mask=attn,
                                       max_new_tokens=args.max_new_tokens, do_sample=False,
                                       num_beams=1)
        # With inputs_embeds, generate() returns ONLY the newly generated token ids (no prompt
        # prefix to strip), unlike the input_ids path in audio_ablation.py.
        return processor.tokenizer.decode(generated[0], skip_special_tokens=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_silence_changed = n_silence_eval = 0
    n_swap_changed = n_swap_eval = 0
    n_swap_followed = n_swap_follow_eval = 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for i, row in enumerate(target_rows):
            conversation = build_conversation(
                row["audio_path"], row["transcript"], ANSWER_KEY,
                include_transcript=not args.audio_only)
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
                per_condition[cond] = {"completion": completion, "label": parse_label(completion)}

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

            out_f.write(json.dumps({
                "audio_path": row["audio_path"], "transcript": row["transcript"],
                "gold_emotion": row.get("emotion"),
                "swap_donor_emotion": (swap_donor or {}).get("emotion"),
                "conditions": per_condition,
                "silence_changed_label": silence_changed,
                "swap_changed_label": swap_changed,
                "swap_label_followed_donor_emotion": swap_followed,
            }, ensure_ascii=False) + "\n")
            labels_str = "  ".join(f"{c}={per_condition[c]['label']!r}" for c in per_condition)
            donor = f" (donor={swap_donor['emotion']})" if swap_donor else ""
            print(f"[{i + 1}/{len(target_rows)}] {Path(row['audio_path']).name}: {labels_str}{donor}",
                  flush=True)

    print(f"\nWrote {len(target_rows)} rows to {out_path}")
    if n_silence_eval:
        print(f"silence:  {n_silence_changed}/{n_silence_eval} rows changed label when audio REMOVED.")
    if n_swap_eval:
        print(f"swap:     {n_swap_changed}/{n_swap_eval} rows changed label when audio SUBSTITUTED.")
    if n_swap_follow_eval:
        print(f"tracking: {n_swap_followed}/{n_swap_follow_eval} swap labels MATCHED the donor "
              f"emotion -- the gradient-table number (compare to baseline 3/15, textmask1 9/15, "
              f"LIME 13/15, ESD 15/15).")


if __name__ == "__main__":
    main()
