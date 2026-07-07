#!/usr/bin/env python
"""GPU half of the Accessibility-Delta Probe: cache pooled audio-channel representations.

The reprioritized RQ (see chat with the user, not yet in RP.md pending a result): this
project's unique asset is not "does modality dominance exist" -- LISTEN (arXiv 2510.10444)
and Billa (arXiv 2602.23136) already answered that on fixed, off-the-shelf models. The unique
asset is a series of ACTUALLY TRAINED adapters spanning a controlled grounding gradient
(collapsed baseline 2-3/15 donor-swap tracking -> supervision-fix 7/15 -> MELD-textmask1
9/15 -> LIME-plain 13/15 -> ESD-plain 15/15, all in RP.md "Core Finding"). The question this
script feeds: as a DATA-LEVEL training intervention moves behavior up that gradient, does the
underlying representation change (probe AUC rises with tracking -- "re-representation"), or
does it stay constant while only the model's USE of it changes (probe AUC flat, behavior
moves anyway -- "re-arbitration")? Billa showed re-arbitration on one static model; this
gradient is the only thing that can show whether training-driven grounding gains are
representational or purely a decision-time effect, across FOUR(+) checkpoints, not one.

Run this once per adapter on the H100 (needs the 4-bit model + real audio), then run
scripts/probe_accessibility.py (CPU-only, no GPU/model needed) on the resulting .npz dumps.

Three probe locations per clip, all pooled (mean) over time/audio-token positions:
  audio_tower : Qwen2-Audio's Whisper-style encoder output, BEFORE the LLM projector. The
                purely acoustic representation, never touched by the LoRA adapter (frozen,
                4-bit base) or by anything LLM-side.
  projector   : the same features AFTER the multi_modal_projector linear layer, i.e. in the
                LLM's embedding space -- this is exactly what gets scattered into inputs_embeds
                at the audio-token positions. Also untouched by LoRA (the projector itself
                isn't a LoRA target_module per configs/lora_config.yaml: q/k/v/o_proj only).
  llm_layers  : every Qwen2 decoder layer's hidden state (output_hidden_states=True), POOLED
                ONLY OVER AUDIO-TOKEN POSITIONS (input_ids == audio_token_id) -- not the whole
                sequence, which would just measure whether the prompt template's text tokens
                are linearly readable (trivially yes) rather than what the audio channel itself
                carries at each depth. This is the layer-resolved, LoRA-affected location: the
                one that can show *where* (if anywhere) a trained intervention changes what's
                encoded vs. just how much downstream layers attend to it.

Both audio_tower and projector outputs are extracted via a forward hook on
multi_modal_projector (its input = audio_tower's last_hidden_state, its output = the projected
features) rather than re-deriving Qwen2AudioEncoder's internal feature-length masking by hand
-- the hook fires during the SAME single forward pass used for llm_layers, so this is one
forward per clip, not three.

Why every adapter is probed under the SAME audio-only prompt (USER_PROMPT_AUDIO_ONLY),
regardless of whether that adapter was itself trained with or without a transcript: the audio
block is the FIRST content in build_conversation's user turn (audio, then text), and decoding
is causal, so the hidden state AT an audio-token position depends only on the system prompt +
the audio itself -- never on whatever text follows (transcript present, absent, or replaced).
Pooling strictly over audio-token positions therefore gives the identical vectors whether or
not a transcript follows in the prompt, which means this script does not need a per-adapter
in-distribution prompt choice (audio-only vs. with-transcript) to stay comparable across the
gradient -- one prompt template, four(+) adapters, genuinely apples-to-apples.

    python scripts/extract_hidden_states.py \
        --adapter outputs/meld_lora_4bit/final --manifest data/meld_dev_manifest.jsonl \
        --out outputs/probe_meld_baseline.npz
    python scripts/extract_hidden_states.py \
        --adapter outputs/meld_lora_textmask1/final --manifest data/meld_dev_manifest.jsonl \
        --out outputs/probe_meld_textmask1.npz
    python scripts/extract_hidden_states.py \
        --adapter outputs/lime_lora_plain/final --manifest data/lime_dev_manifest.jsonl \
        --out outputs/probe_lime_plain.npz
    python scripts/extract_hidden_states.py \
        --adapter outputs/esd_lora_plain/final --manifest data/esd_dev_manifest.jsonl \
        --out outputs/probe_esd_plain.npz

Then: python scripts/probe_accessibility.py --in outputs/probe_meld_baseline.npz:3 \
    --in outputs/probe_meld_textmask1.npz:9 --in outputs/probe_lime_plain.npz:13 \
    --in outputs/probe_esd_plain.npz:15 --out outputs/accessibility_probe_results.csv
(the ':N' suffix is each adapter's RP.md donor-swap tracking score out of 15, printed
alongside the probe AUC for the read-out -- entirely optional, omit it to just see AUCs.)
"""

import argparse
import json
import random
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


def extract_one(model, base, processor, sr: int, audio_path: str):
    """One forward pass -> (audio_tower_vec, projector_vec, llm_layer_vecs) or None if the
    processor produced no audio tokens for this row (bad/unreadable audio)."""
    conversation = build_conversation(audio_path, "", ANSWER_KEY, include_transcript=False)
    prompt_text = processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
    audio_array = librosa.load(audio_path, sr=sr)[0]
    inputs = processor(
        text=prompt_text, audio=[audio_array], sampling_rate=sr, return_tensors="pt"
    ).to(model.device)

    captured = {}

    def hook(_module, inp, out):
        captured["pre_proj"] = inp[0].detach()
        captured["post_proj"] = out.detach()

    handle = base.model.multi_modal_projector.register_forward_hook(hook)
    try:
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True, use_cache=False)
    finally:
        handle.remove()

    if outputs.hidden_states is None:
        raise RuntimeError(
            "model(...) returned no hidden_states -- output_hidden_states=True did not reach "
            "the language model. Check the PEFT/transformers version's kwarg plumbing."
        )

    audio_mask = inputs["input_ids"][0] == base.config.audio_token_id
    if not audio_mask.any():
        return None

    audio_tower_vec = captured["pre_proj"][0].float().mean(dim=0).cpu().numpy()
    projector_vec = captured["post_proj"][0].float().mean(dim=0).cpu().numpy()
    layer_vecs = np.stack([
        hs[0][audio_mask].float().mean(dim=0).cpu().numpy() for hs in outputs.hidden_states
    ])
    return audio_tower_vec, projector_vec, layer_vecs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2-Audio-7B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sample", type=int, default=200, help="Random sample size (0 = all rows).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True, help="Output .npz path.")
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    if args.sample and args.sample < len(rows):
        rng = random.Random(args.seed)
        rows = rng.sample(rows, args.sample)

    processor = AutoProcessor.from_pretrained(args.base_model)
    sr = processor.feature_extractor.sampling_rate
    model = load_base_model(args.base_model)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    base = model.get_base_model()

    audio_tower_vecs, projector_vecs, layer_vecs, labels, kept_paths = [], [], [], [], []
    skipped = 0
    for i, row in enumerate(rows):
        gold = (row.get("emotion") or "").lower()
        if not gold:
            skipped += 1
            continue
        result = extract_one(model, base, processor, sr, row["audio_path"])
        if result is None:
            skipped += 1
            continue
        at_vec, pj_vec, ly_vecs = result
        if i == 0:
            print(
                f"  shape check: audio_tower={at_vec.shape} projector={pj_vec.shape} "
                f"llm_layers={ly_vecs.shape} (n_layers incl. embedding, hidden_dim)"
            )
        audio_tower_vecs.append(at_vec)
        projector_vecs.append(pj_vec)
        layer_vecs.append(ly_vecs)
        labels.append(gold)
        kept_paths.append(row["audio_path"])
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(rows)} clips processed ({len(labels)} kept, {skipped} skipped)")

    if not labels:
        raise SystemExit("No usable rows extracted -- check --manifest's 'emotion' field / audio paths.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out_path,
        audio_tower=np.stack(audio_tower_vecs),
        projector=np.stack(projector_vecs),
        llm_layers=np.stack(layer_vecs),
        labels=np.array(labels),
        audio_paths=np.array(kept_paths),
        adapter=np.array([args.adapter]),
    )
    print(f"\nWrote {len(labels)} rows ({skipped} skipped) to {out_path}")


if __name__ == "__main__":
    main()
