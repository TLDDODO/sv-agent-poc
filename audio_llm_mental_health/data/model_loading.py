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
