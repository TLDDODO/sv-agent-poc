#!/usr/bin/env python
"""LoRA SFT for Qwen2-Audio-7B-Instruct on the MELD pipeline-validation task.

Run on the H100 only -- this repo's sandbox has no GPU. See ../README.md for setup.
Run from the `audio_llm_mental_health/` project root so the relative paths in
configs/train_config.yaml resolve correctly:

    python scripts/train_lora.py --config configs/train_config.yaml

To resume an interrupted run from the last checkpoint (e.g. a long run killed by an SSH drop
or a reclaimed GPU slot -- see RP.md "Environment"):

    python scripts/train_lora.py --config configs/train_config.yaml \
        --resume-from outputs/meld_lora/checkpoint-200
"""

import argparse
import sys
from pathlib import Path

import librosa
import torch
import yaml
from peft import LoraConfig, PeftModel, get_peft_model
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import AutoProcessor, get_linear_schedule_with_warmup

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.meld_dataset import MELDDataset  # noqa: E402
from data.model_loading import load_base_model, prepare_for_qlora_training  # noqa: E402


def build_batch(processor, examples):
    """Tokenize a list of dataset examples into one padded batch with masked labels.

    Each example's prompt portion is masked out (-100) so loss is computed only over the
    CoT + final-answer target tokens, not the instruction itself.
    """
    texts, audio_arrays, raw_prompt_lens = [], [], []
    for ex in examples:
        prompt_text = processor.apply_chat_template(
            ex["conversation"], add_generation_prompt=True, tokenize=False
        )
        texts.append(prompt_text + ex["target"] + processor.tokenizer.eos_token)
        audio_arrays.append(
            librosa.load(ex["audio_path"], sr=processor.feature_extractor.sampling_rate)[0]
        )
        # Counts the literal, un-expanded "<|AUDIO|>" placeholder in prompt_text as a single
        # token; Qwen2AudioProcessor expands it below into `num_audio_tokens` placeholder
        # tokens (a function of the audio length), so this raw count is corrected afterwards.
        raw_prompt_lens.append(len(processor.tokenizer(prompt_text)["input_ids"]))

    batch = processor(
        text=texts,
        audio=audio_arrays,
        sampling_rate=processor.feature_extractor.sampling_rate,
        return_tensors="pt",
        padding=True,
    )

    # Mirror Qwen2AudioProcessor's own placeholder-count formula (processing_qwen2_audio.py)
    # to find how many tokens each audio was expanded to. Without this correction the labels
    # mask boundary is off by (num_audio_tokens - 1) per example -- audio clips a few seconds
    # long expand to dozens of placeholder tokens, so this left a large block of audio
    # placeholder / trailing-prompt tokens unmasked and supervised as if they were the CoT
    # target, diluting the actual reasoning/answer loss with unlearnable boilerplate.
    audio_lengths = batch["feature_attention_mask"].sum(-1)
    input_lengths = (audio_lengths - 1) // 2 + 1
    num_audio_tokens = (input_lengths - 2) // 2 + 1
    prompt_lens = [raw + (int(n) - 1) for raw, n in zip(raw_prompt_lens, num_audio_tokens)]

    labels = batch["input_ids"].clone()
    for i, plen in enumerate(prompt_lens):
        labels[i, :plen] = -100
    labels[batch["attention_mask"] == 0] = -100
    batch["labels"] = labels
    return batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--resume-from", default=None,
        help="Checkpoint dir to resume from, e.g. outputs/meld_lora/checkpoint-200. Loads the "
        "adapter plus the optimizer/scheduler/progress state saved alongside it.",
    )
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    lora_cfg_dict = yaml.safe_load(Path(config["lora_config_path"]).read_text())

    torch.manual_seed(config["seed"])

    processor = AutoProcessor.from_pretrained(config["model_name_or_path"])
    model = load_base_model(config["model_name_or_path"])
    model = prepare_for_qlora_training(model)
    if args.resume_from:
        model = PeftModel.from_pretrained(model, args.resume_from, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(**lora_cfg_dict))
    model.print_trainable_parameters()

    train_dataset = MELDDataset(
        config["train_manifest"],
        text_mask_prob=config.get("text_mask_prob", 0.0),
        seed=config["seed"],
    )

    def make_loader(epoch: int) -> DataLoader:
        # Seeded per-epoch (rather than relying on the global RNG's call history) so the shuffle
        # order for a given epoch is identical whether this is the original run or a --resume-from
        # restart -- otherwise the resumed epoch's data wouldn't line up with the within-epoch
        # `step` position saved in training_state.pt, and the skip-already-seen-batches logic
        # below would skip/duplicate the wrong rows.
        generator = torch.Generator().manual_seed(config["seed"] + epoch)
        return DataLoader(
            train_dataset,
            batch_size=config["per_device_train_batch_size"],
            shuffle=True,
            generator=generator,
            collate_fn=lambda batch: build_batch(processor, batch),
        )

    optimizer = AdamW(model.parameters(), lr=config["learning_rate"])
    steps_per_epoch = max(len(make_loader(0)) // config["gradient_accumulation_steps"], 1)
    total_steps = steps_per_epoch * config["num_train_epochs"]
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * config["warmup_ratio"]),
        num_training_steps=total_steps,
    )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    global_step, start_epoch, resume_step = 0, 0, -1
    if args.resume_from:
        state = torch.load(Path(args.resume_from) / "training_state.pt", map_location="cpu")
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        global_step, start_epoch, resume_step = state["global_step"], state["epoch"], state["step"]
        print(f"Resumed from {args.resume_from}: global_step={global_step}, epoch={start_epoch}")

    model.train()
    for epoch in range(start_epoch, config["num_train_epochs"]):
        for step, batch in enumerate(make_loader(epoch)):
            # Replays (audio-load + tokenize, no forward/backward) up to the exact raw batch the
            # resumed checkpoint last completed an optimizer step on, so the rest of that epoch's
            # data isn't silently skipped -- the only state a checkpoint doesn't capture is "how
            # far into this epoch's shuffled order had we gotten."
            if epoch == start_epoch and step <= resume_step:
                continue

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
                    ckpt_dir = output_dir / f"checkpoint-{global_step}"
                    model.save_pretrained(ckpt_dir)
                    torch.save(
                        {
                            "optimizer": optimizer.state_dict(),
                            "scheduler": scheduler.state_dict(),
                            "global_step": global_step,
                            "epoch": epoch,
                            "step": step,
                        },
                        ckpt_dir / "training_state.pt",
                    )
        resume_step = -1  # only the resumed epoch needs the within-epoch skip

    model.save_pretrained(output_dir / "final")
    processor.save_pretrained(output_dir / "final")


if __name__ == "__main__":
    main()
