"""Shared 4-bit base-model loading for Qwen2-Audio-7B-Instruct.

This cluster's per-student GPU allocation is a MIG slice (~9.75 GiB, confirmed via
`nvidia-smi` -- the physical card is an H100 80GB split into seven `1g.10gb` slices), too
small to hold the model in bf16 (~16 GB for weights alone, confirmed by a CUDA OOM during
`from_pretrained` itself, before any training data is touched). 4-bit (QLoRA-style) loading
via bitsandbytes brings the base weights to ~4 GB, leaving headroom for activations and the
LoRA adapter. See RP.md "Environment".
"""

import torch
from transformers import BitsAndBytesConfig, Qwen2AudioForConditionalGeneration

QUANTIZATION_CONFIG = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)


def load_base_model(model_name_or_path: str) -> Qwen2AudioForConditionalGeneration:
    return Qwen2AudioForConditionalGeneration.from_pretrained(
        model_name_or_path, quantization_config=QUANTIZATION_CONFIG, device_map="cuda"
    )


def prepare_for_qlora_training(model: Qwen2AudioForConditionalGeneration):
    """Gradient-checkpointing setup for QLoRA training, minus peft's blanket fp32 upcast.

    peft.prepare_model_for_kbit_training() casts every bf16/fp16 param that ISN'T a 4-bit
    Params4bit -- i.e. embeddings, lm_head, norms -- to fp32, doubling their footprint. On this
    9.75 GiB MIG slice that cast alone OOMs (observed: ~8.5 GiB already used right after loading
    the 4-bit model, then a 2.38 GiB fp32-upcast allocation request that doesn't fit). The base
    model is frozen and never receives gradients either way (get_peft_model() below freezes
    everything outside the LoRA adapters), and bnb_4bit_compute_dtype=bf16 already runs every
    4-bit matmul in bf16 regardless of the stored dtype of the unquantized leftovers, so the
    upcast buys numerical-stability headroom this setup can't afford and doesn't need.
    """
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable()
    # Incompatible with gradient checkpointing during training (the checkpointed forward is
    # recomputed on backward, which conflicts with the incremental KV cache); irrelevant here
    # since training does one full-sequence forward per step, not incremental decoding.
    model.config.use_cache = False
    return model
