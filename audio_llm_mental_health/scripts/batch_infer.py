#!/usr/bin/env python
"""Run a LoRA-tuned checkpoint over several manifest rows and dump a review report.

For manual CoT-quality checks (acoustic-text congruence, conflict robustness -- see
README.md "Evaluation"): loads the model once instead of once per clip, so it's cheap to
run over a handful of hand-picked rows.

    python scripts/batch_infer.py --adapter outputs/meld_lora/final \
        --manifest data/meld_dev_manifest.jsonl --indices 0,5,12 \
        --out outputs/review_conflict.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

import librosa
import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.prompts import build_conversation  # noqa: E402

ANSWER_KEY = "Emotion"


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
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.manifest).read_text().splitlines() if line.strip()]
    if args.indices is not None:
        wanted = [int(i) for i in args.indices.split(",")]
        rows = [rows[i] for i in wanted]

    processor = AutoProcessor.from_pretrained(args.base_model)
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        args.base_model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out_f:
        for i, row in enumerate(rows):
            conversation = build_conversation(row["audio_path"], row["transcript"], ANSWER_KEY)
            prompt_text = processor.apply_chat_template(
                conversation, add_generation_prompt=True, tokenize=False
            )
            audio_array = librosa.load(row["audio_path"], sr=processor.feature_extractor.sampling_rate)[0]
            inputs = processor(
                text=prompt_text,
                audio=[audio_array],
                sampling_rate=processor.feature_extractor.sampling_rate,
                return_tensors="pt",
            ).to(model.device)

            with torch.no_grad():
                generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
            completion = processor.tokenizer.decode(
                generated[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
            )

            result = {
                "audio_path": row["audio_path"],
                "transcript": row["transcript"],
                "gold_emotion": row.get("emotion"),
                "gold_sentiment": row.get("sentiment"),
                "completion": completion,
            }
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(f"[{i + 1}/{len(rows)}] {row['audio_path']} -> {completion!r}")

    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
