#!/usr/bin/env python
"""Run the LoRA-tuned audio-LLM on one audio clip + transcript and print its CoT + label.

Run on the H100 only, after train_lora.py has produced an adapter checkpoint:

    python scripts/infer.py \
        --adapter outputs/meld_lora/final \
        --audio path/to/clip.wav \
        --transcript "transcript text here"
"""

import argparse
import sys
from pathlib import Path

import librosa
import torch
from peft import PeftModel
from transformers import AutoProcessor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.model_loading import load_base_model  # noqa: E402
from data.prompts import build_conversation  # noqa: E402

ANSWER_KEY = "Emotion"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2-Audio-7B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=200)
    args = parser.parse_args()

    processor = AutoProcessor.from_pretrained(args.base_model)
    model = load_base_model(args.base_model)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    conversation = build_conversation(args.audio, args.transcript, ANSWER_KEY)
    prompt_text = processor.apply_chat_template(
        conversation, add_generation_prompt=True, tokenize=False
    )
    audio_array = librosa.load(args.audio, sr=processor.feature_extractor.sampling_rate)[0]
    inputs = processor(
        text=prompt_text,
        audio=[audio_array],
        sampling_rate=processor.feature_extractor.sampling_rate,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        # Greedy decoding for reproducible review output (the base model's default
        # generation_config.json has do_sample=True, meant for varied chit-chat).
        generated = model.generate(
            **inputs, max_new_tokens=args.max_new_tokens, do_sample=False, num_beams=1
        )

    completion = processor.tokenizer.decode(
        generated[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
    )
    print(completion)


if __name__ == "__main__":
    main()
