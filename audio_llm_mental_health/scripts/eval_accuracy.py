#!/usr/bin/env python
"""Measure the trained model's emotion accuracy vs MELD gold labels (a de-risking check).

Before spending GPU on a retrain, this answers: does the model capture the right emotion at
all? Run on a REPRESENTATIVE random sample (not the conflict candidates, which are adversarial
by construction and would understate accuracy).

Read the result against the majority-class baseline, not in isolation: MELD is neutral-heavy,
so a model that always says "neutral" already scores well above zero. Only accuracy clearly
above that baseline -- and non-trivial per-class recall -- means the model is actually
discriminating emotions.

    python scripts/eval_accuracy.py --adapter outputs/meld_lora/final \
        --manifest data/meld_dev_manifest.jsonl --sample 200
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
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
    matches = re.findall(rf"{re.escape(answer_key)}\s*:\s*(.+)", completion)
    if not matches:
        return None
    return matches[-1].strip().split("\n")[0].strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2-Audio-7B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sample", type=int, default=200, help="Random sample size (0 = all rows).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--out", default=None, help="Optional JSONL dump of per-row predictions.")
    parser.add_argument(
        "--silence", action="store_true",
        help="Replace the loaded audio with equal-length silence (keep the transcript). Run "
        "twice with the same --seed/--sample, with and without this flag, then diff the two "
        "--out dumps with compare_audio_contribution.py to isolate audio's contribution to "
        "accuracy from the transcript's.",
    )
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    if args.sample and args.sample < len(rows):
        rng = random.Random(args.seed)
        rows = rng.sample(rows, args.sample)

    processor = AutoProcessor.from_pretrained(args.base_model)
    sr = processor.feature_extractor.sampling_rate
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        args.base_model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    out_f = open(args.out, "w", encoding="utf-8") if args.out else None
    gold_counts: Counter[str] = Counter()
    correct_by_gold: Counter[str] = Counter()
    pred_counts: Counter[str] = Counter()
    correct = evaluable = 0

    for i, row in enumerate(rows):
        gold = (row.get("emotion") or "").lower()
        conversation = build_conversation(row["audio_path"], row["transcript"], ANSWER_KEY)
        prompt_text = processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False
        )
        audio_array = librosa.load(row["audio_path"], sr=sr)[0]
        if args.silence:
            audio_array = np.zeros_like(audio_array)
        inputs = processor(
            text=prompt_text, audio=[audio_array], sampling_rate=sr, return_tensors="pt"
        ).to(model.device)
        with torch.no_grad():
            generated = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens, do_sample=False, num_beams=1
            )
        completion = processor.tokenizer.decode(
            generated[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )
        pred = parse_label(completion)

        if gold:
            gold_counts[gold] += 1
        if pred:
            pred_counts[pred] += 1
        if gold and pred:
            evaluable += 1
            if pred == gold:
                correct += 1
                correct_by_gold[gold] += 1

        if out_f:
            out_f.write(json.dumps(
                {"audio_path": row["audio_path"], "gold": gold, "pred": pred,
                 "correct": (pred == gold) if (gold and pred) else None}, ensure_ascii=False
            ) + "\n")
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(rows)} done")

    if out_f:
        out_f.close()

    print(f"\nEvaluated {evaluable} rows (parsed both gold and prediction).")
    if not evaluable:
        print("No evaluable rows.")
        return

    acc = correct / evaluable
    majority_emotion, majority_n = gold_counts.most_common(1)[0]
    baseline = majority_n / sum(gold_counts.values())

    print(f"\nAccuracy (model vs gold):   {acc:.3f}  ({correct}/{evaluable})")
    print(f"Majority-class baseline:    {baseline:.3f}  (always predict '{majority_emotion}')")
    delta = acc - baseline
    print(f"Above baseline:             {delta:+.3f}")

    print("\nPer-gold-class recall (does it discriminate, or just push one class?):")
    for emo, n in gold_counts.most_common():
        rec = correct_by_gold[emo] / n if n else 0.0
        print(f"  {emo:<10} n={n:<4} recall={rec:.3f}")

    print("\nPrediction distribution (collapsed to a few classes => not really listening):")
    for emo, n in pred_counts.most_common():
        print(f"  {emo:<10} {n}")

    print("\nRead it:")
    print("  * acc near baseline / predictions collapsed to 1-2 classes => audio emotion not")
    print("    captured; retraining on MELD as-is is unlikely to help.")
    print("  * acc clearly above baseline with spread-out per-class recall => the signal is")
    print("    there; since the ablation showed it's text-driven, the audio-only retrain is")
    print("    the path most likely to convert that into genuine grounding.")


if __name__ == "__main__":
    main()
