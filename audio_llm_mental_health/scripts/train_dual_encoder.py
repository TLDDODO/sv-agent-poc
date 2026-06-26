#!/usr/bin/env python
"""Dual-encoder + disentanglement training -- the architecture/objective-level intervention.

This is the mechanistically-distinct counterpart to the data-level decoupling already measured in
RP.md ("Approach" point 1, "The controlled comparison"). Beside Qwen2-Audio's frozen semantic
(Whisper-style) tower it adds a frozen paralinguistic EMOTION tower (data/emotion_tower.py) whose
trainable projection emits one extra token, injected into the prompt, and decorrelated from the
semantic audio features by data/disentangle.py's loss. The LLM gets a LoRA adapter as usual. The
question this run feeds: does counteracting collapse at the objective level (a dedicated emotion
path forced to carry non-semantic signal) move the fixed donor-swap / silence-vs-audio ruler by the
SAME amount as removing the transcript shortcut at the data level did?

What trains: the LLM LoRA adapter + the emotion tower's projection head. What's frozen: the 4-bit
LLM base, the semantic audio tower, and the emotion encoder. So the disentanglement loss pushes ONLY
the emotion projection to be orthogonal to the (frozen) semantic features -- exactly the intended
"emotion path carries what the semantic path doesn't" objective.

Injection (the smoke-test-critical part, kept in one function build_dual_embeds):
  forward #1 (no_grad): run the base model so it does its OWN audio merge; take hidden_states[0]
    (the audio-merged inputs_embeds fed to decoder layer 0) and, via a hook on
    multi_modal_projector, the pooled semantic features. Using the model's own merge avoids
    replicating Qwen2-Audio's version-specific scatter logic.
  then: prepend the emotion token's projected embedding at position 0; extend attention_mask (1)
    and labels (-100, so it is never a prediction target).
  forward #2 (grad): model(inputs_embeds=..., labels=...) with NO input_features, so the model
    runs the LLM on our pre-merged embeds and does not re-merge audio.

    python scripts/train_dual_encoder.py --config configs/train_config_dual_smoke.yaml

Run the smoke config first (a handful of steps) and confirm loss is finite and falls before
committing a full run to a MIG slice. See RP.md "Approach" point 1.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import librosa
import torch
import yaml
from peft import LoraConfig, get_peft_model
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import AutoProcessor, get_linear_schedule_with_warmup

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.disentangle import cosine_orthogonality_loss, decorrelation_loss  # noqa: E402
from data.emotion_tower import EmotionTower  # noqa: E402
from data.meld_dataset import MELDDataset  # noqa: E402
from data.model_loading import load_base_model, prepare_for_qlora_training  # noqa: E402
from train_lora import build_batch  # noqa: E402  -- reuse the verified tokenize+label-mask path

DIS_LOSSES = {"cosine": cosine_orthogonality_loss, "decorrelation": decorrelation_loss}


def dual_collate(processor, examples):
    """build_batch (tokenized inputs + masked labels) plus the raw 16 kHz waveforms the emotion
    tower needs. Audio is loaded twice (once inside build_batch for the Qwen processor, once here);
    acceptable for v0 -- fold into one load if it shows up in profiling."""
    batch = build_batch(processor, examples)
    sr = processor.feature_extractor.sampling_rate
    waveforms = [librosa.load(ex["audio_path"], sr=sr)[0] for ex in examples]
    return batch, waveforms


def build_dual_embeds(model, base, emotion_tower, batch, waveforms):
    """Returns (inputs_embeds, attention_mask, labels, sem, emo) for the grad forward.

    sem/emo are the (B, D) pooled semantic / emotion vectors for the disentanglement loss. sem is
    detached (the semantic tower is frozen); emo carries grad through the projection head.
    """
    captured = {}

    def hook(_m, inp, out):
        captured["post_proj"] = out.detach()  # (B_audio_tokens-flattened? per-sample) projected feats

    handle = base.model.multi_modal_projector.register_forward_hook(hook)
    try:
        with torch.no_grad():
            out1 = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                input_features=batch["input_features"],
                feature_attention_mask=batch["feature_attention_mask"],
                output_hidden_states=True,
                use_cache=False,
            )
    finally:
        handle.remove()

    if out1.hidden_states is None:
        raise RuntimeError("no hidden_states -- output_hidden_states did not reach the LLM; check "
                           "the transformers/PEFT kwarg plumbing (same check as extract_hidden_states).")
    merged = out1.hidden_states[0]  # (B, S, D): audio-merged inputs_embeds fed to layer 0, no grad

    # Pooled semantic features per sample: mean the projected audio features over that row's audio
    # token positions. The hook's post_proj is per audio-token-frame; recover per-sample pooling
    # from the audio-token mask, mirroring extract_hidden_states.py's projector_vec.
    audio_id = base.config.audio_token_id
    post_proj = captured["post_proj"]
    sem_rows = []
    flat = post_proj.reshape(-1, post_proj.shape[-1]) if post_proj.dim() == 3 else post_proj
    cursor = 0
    for b in range(batch["input_ids"].shape[0]):
        n = int((batch["input_ids"][b] == audio_id).sum())
        if n == 0:  # no audio tokens for this row -> fall back to a zero vector
            sem_rows.append(merged.new_zeros(merged.shape[-1]))
            continue
        sem_rows.append(flat[cursor:cursor + n].float().mean(dim=0))
        cursor += n
    sem = torch.stack(sem_rows)  # (B, D), detached

    emo = emotion_tower(waveforms).to(merged.dtype)  # (B, D), grad through projection head

    # Prepend the emotion token at position 0.
    emo_tok = emo.unsqueeze(1)                                   # (B, 1, D)
    inputs_embeds = torch.cat([emo_tok, merged], dim=1)         # (B, S+1, D)
    ones = batch["attention_mask"].new_ones((batch["attention_mask"].shape[0], 1))
    attention_mask = torch.cat([ones, batch["attention_mask"]], dim=1)
    neg = batch["labels"].new_full((batch["labels"].shape[0], 1), -100)
    labels = torch.cat([neg, batch["labels"]], dim=1)
    return inputs_embeds, attention_mask, labels, sem, emo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    lora_cfg_dict = yaml.safe_load(Path(config["lora_config_path"]).read_text())
    dis_name = config.get("disentangle_loss", "cosine")
    dis_fn = DIS_LOSSES[dis_name]
    lam = float(config.get("disentangle_lambda", 1.0))
    max_steps = int(config.get("max_steps", 0))  # 0 = full run; >0 = smoke

    torch.manual_seed(config["seed"])

    processor = AutoProcessor.from_pretrained(config["model_name_or_path"])
    model = load_base_model(config["model_name_or_path"])
    model = prepare_for_qlora_training(model)
    model = get_peft_model(model, LoraConfig(**lora_cfg_dict))
    base = model.get_base_model()
    model.print_trainable_parameters()

    llm_hidden = base.config.text_config.hidden_size
    emotion_tower = EmotionTower(
        llm_hidden=llm_hidden,
        encoder_name=config.get("emotion_encoder", "facebook/hubert-base-ls960"),
    ).to(model.device)
    emotion_tower.encoder.eval()

    train_dataset = MELDDataset(
        config["train_manifest"],
        text_mask_prob=config.get("text_mask_prob", 0.0),
        seed=config["seed"],
    )

    def make_loader(epoch: int) -> DataLoader:
        generator = torch.Generator().manual_seed(config["seed"] + epoch)
        return DataLoader(
            train_dataset,
            batch_size=config["per_device_train_batch_size"],
            shuffle=True,
            generator=generator,
            collate_fn=lambda b: dual_collate(processor, b),
        )

    # Both trainable groups: the LLM LoRA adapter AND the emotion projection head.
    trainable = [p for p in model.parameters() if p.requires_grad] + \
                [p for p in emotion_tower.parameters() if p.requires_grad]
    optimizer = AdamW(trainable, lr=config["learning_rate"])
    steps_per_epoch = max(len(make_loader(0)) // config["gradient_accumulation_steps"], 1)
    total_steps = steps_per_epoch * config["num_train_epochs"]
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * config["warmup_ratio"]),
        num_training_steps=total_steps,
    )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "run_metadata.jsonl", "a") as f:
        f.write(json.dumps({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "config_path": args.config, "config": config, "lora_config": lora_cfg_dict,
            "disentangle_loss": dis_name, "disentangle_lambda": lam,
        }) + "\n")
    metrics_path = output_dir / "metrics.jsonl"

    model.train()
    emotion_tower.train()  # encoder stays in eval via its own .eval() in forward; proj head trains
    run_start = time.time()
    global_step = 0
    stop = False
    for epoch in range(config["num_train_epochs"]):
        if stop:
            break
        for step, (batch, waveforms) in enumerate(make_loader(epoch)):
            batch = {k: v.to(model.device) for k, v in batch.items()}
            inputs_embeds, attn, labels, sem, emo = build_dual_embeds(
                model, base, emotion_tower, batch, waveforms)

            out = model(inputs_embeds=inputs_embeds, attention_mask=attn, labels=labels,
                        use_cache=False)
            lm_loss = out.loss
            dis_loss = dis_fn(sem, emo)
            loss = (lm_loss + lam * dis_loss) / config["gradient_accumulation_steps"]
            loss.backward()

            if (step + 1) % config["gradient_accumulation_steps"] == 0:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                if global_step % config["logging_steps"] == 0:
                    print(f"epoch {epoch} step {global_step} loss {loss.item() * config['gradient_accumulation_steps']:.4f} "
                          f"(lm {lm_loss.item():.4f} dis {dis_loss.item():.4f})", flush=True)
                    with open(metrics_path, "a") as f:
                        f.write(json.dumps({
                            "global_step": global_step, "epoch": epoch,
                            "loss": (lm_loss + lam * dis_loss).item(),
                            "lm_loss": lm_loss.item(), "dis_loss": dis_loss.item(),
                            "lr": scheduler.get_last_lr()[0],
                            "elapsed_s": round(time.time() - run_start, 1),
                        }) + "\n")

                if config.get("save_steps") and global_step % config["save_steps"] == 0:
                    ckpt = output_dir / f"checkpoint-{global_step}"
                    model.save_pretrained(ckpt)
                    torch.save(emotion_tower.proj.state_dict(), ckpt / "emotion_proj.pt")

                if max_steps and global_step >= max_steps:
                    print(f"reached max_steps={max_steps} (smoke), stopping.", flush=True)
                    stop = True
                    break

    model.save_pretrained(output_dir / "final")
    processor.save_pretrained(output_dir / "final")
    torch.save(emotion_tower.proj.state_dict(), output_dir / "final" / "emotion_proj.pt")
    print(f"saved adapter + emotion projection to {output_dir/'final'}", flush=True)


if __name__ == "__main__":
    main()
