#!/usr/bin/env python
"""LoRA SFT for Qwen2-Audio-7B-Instruct on the MELD pipeline-validation task.

Run on the H100 only -- this repo's sandbox has no GPU. See ../README.md for setup.
Run from the `audio_llm_mental_health/` project root so the relative paths in
configs/train_config.yaml resolve correctly:

    python scripts/train_lora.py --config configs/train_config.yaml
"""

import argparse
import sys
from pathlib import Path

import librosa
import torch
import yaml
from peft import LoraConfig, get_peft_model
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration, get_linear_schedule_with_warmup

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.meld_dataset import MELDDataset  # noqa: E402


def build_batch(processor, examples):
    """Tokenize a list of dataset examples into one padded batch with masked labels.

    Each example's prompt portion is masked out (-100) so loss is computed only over the
    CoT + final-answer target tokens, not the instruction itself.
    """
    texts, audio_arrays, prompt_lens = [], [], []
    for ex in examples:
        prompt_text = processor.apply_chat_template(
            ex["conversation"], add_generation_prompt=True, tokenize=False
        )
        texts.append(prompt_text + ex["target"] + processor.tokenizer.eos_token)
        audio_arrays.append(
            librosa.load(ex["audio_path"], sr=processor.feature_extractor.sampling_rate)[0]
        )
        prompt_lens.append(len(processor.tokenizer(prompt_text)["input_ids"]))

    batch = processor(
        text=texts,
        audio=audio_arrays,
        sampling_rate=processor.feature_extractor.sampling_rate,
        return_tensors="pt",
        padding=True,
    )
    labels = batch["input_ids"].clone()
    for i, plen in enumerate(prompt_lens):
        labels[i, :plen] = -100
    labels[batch["attention_mask"] == 0] = -100
    batch["labels"] = labels
    return batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    lora_cfg_dict = yaml.safe_load(Path(config["lora_config_path"]).read_text())

    torch.manual_seed(config["seed"])

    processor = AutoProcessor.from_pretrained(config["model_name_or_path"])
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        config["model_name_or_path"], torch_dtype=torch.bfloat16, device_map="cuda"
    )
    model = get_peft_model(model, LoraConfig(**lora_cfg_dict))
    model.print_trainable_parameters()

    train_dataset = MELDDataset(
        config["train_manifest"],
        text_mask_prob=config.get("text_mask_prob", 0.0),
        seed=config["seed"],
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=config["per_device_train_batch_size"],
        shuffle=True,
        collate_fn=lambda batch: build_batch(processor, batch),
    )

    optimizer = AdamW(model.parameters(), lr=config["learning_rate"])
    steps_per_epoch = max(len(train_loader) // config["gradient_accumulation_steps"], 1)
    total_steps = steps_per_epoch * config["num_train_epochs"]
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * config["warmup_ratio"]),
        num_training_steps=total_steps,
    )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    model.train()
    global_step = 0
    for epoch in range(config["num_train_epochs"]):
        for step, batch in enumerate(train_loader):
            batch = {k: v.to(model.device) for k, v in batch.items()}
            loss = model(**batch).loss / config["gradient_accumulation_steps"]
            loss.backward()

            if (step + 1) % config["gradient_accumulation_steps"] == 0:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                if global_step % config["logging_steps"] == 0:
                    print(f"epoch {epoch} step {global_step} loss {loss.item():.4f}")

                if global_step % config["save_steps"] == 0:
                    model.save_pretrained(output_dir / f"checkpoint-{global_step}")

    model.save_pretrained(output_dir / "final")
    processor.save_pretrained(output_dir / "final")


if __name__ == "__main__":
    main()
