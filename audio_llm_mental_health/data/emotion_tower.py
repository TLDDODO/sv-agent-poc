"""Emotion tower for the dual-encoder intervention (RP.md "Approach" point 1).

The second tower beside Qwen2-Audio's semantic (Whisper-style) path. A FROZEN paralinguistic audio
encoder produces a per-clip embedding; a small TRAINABLE projection head maps it into the LLM hidden
space so it can be injected as one extra token in the prompt and decorrelated from the semantic audio
features by data/disentangle.py's losses. Only the projection head trains -- the encoder stays frozen
(and 4-bit-friendly: it runs in bf16, no gradients), which is what keeps this affordable on the
~9.75 GiB MIG slice alongside the 4-bit Qwen2-Audio base.

Encoder choice is a config knob (`encoder_name`). Default is a transformers-native HuBERT
(`facebook/hubert-base-ls960`, ~95M, hidden 768) rather than emotion2vec: emotion2vec ships in
funasr/fairseq format that is awkward to load on this cluster, whereas any HF `AutoModel` audio
encoder loads cleanly here. HuBERT's frozen features carry strong paralinguistic/emotion signal and
the trained projection + disentanglement objective shape it into the emotion channel; swap in a
SER-fine-tuned encoder (e.g. `superb/hubert-large-superb-er`) by changing only `encoder_name` if the
slice has room. The disentanglement loss does not care which encoder produced `emo` -- only that it
is a (B, D_llm) pooled vector aligned with the semantic one.

Smoke test (runs on CPU, no real audio needed -- verifies load + output shape + frozen/trainable split):
    python data/emotion_tower.py
"""

import numpy as np
import torch
import torch.nn as nn
from transformers import AutoFeatureExtractor, AutoModel

DEFAULT_ENCODER = "facebook/hubert-base-ls960"
TARGET_SR = 16000  # HuBERT/wav2vec2 family operate at 16 kHz; resample upstream if needed.


class EmotionTower(nn.Module):
    """Frozen audio encoder + trainable projection to the LLM hidden dim.

    forward(waveforms) -> (B, llm_hidden) one pooled emotion embedding per clip, masked-mean over
    the encoder's frame outputs so right-padding in a batch does not bias the pool.
    """

    def __init__(self, llm_hidden: int, encoder_name: str = DEFAULT_ENCODER,
                 proj_hidden: int = 1024, dtype: torch.dtype = torch.bfloat16):
        super().__init__()
        self.encoder_name = encoder_name
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(encoder_name)
        self.encoder = AutoModel.from_pretrained(encoder_name, torch_dtype=dtype)
        self.encoder.eval()
        for p in self.encoder.parameters():
            p.requires_grad_(False)

        enc_hidden = self.encoder.config.hidden_size
        # Two-layer projection head (the only trained part). Kept in fp32 for optimizer stability;
        # it is tiny (enc_hidden*proj_hidden + proj_hidden*llm_hidden) relative to everything else.
        self.proj = nn.Sequential(
            nn.Linear(enc_hidden, proj_hidden),
            nn.GELU(),
            nn.Linear(proj_hidden, llm_hidden),
        )

    @property
    def device(self) -> torch.device:
        return next(self.proj.parameters()).device

    def _masked_mean(self, hidden: torch.Tensor, attn: torch.Tensor | None) -> torch.Tensor:
        """hidden (B, T, H), attn (B, T) frame mask or None -> (B, H) mean over valid frames."""
        if attn is None:
            return hidden.mean(dim=1)
        attn = attn.to(hidden.dtype).unsqueeze(-1)  # (B, T, 1)
        return (hidden * attn).sum(dim=1) / attn.sum(dim=1).clamp(min=1.0)

    def forward(self, waveforms: list[np.ndarray]) -> torch.Tensor:
        """waveforms: list of 1-D float arrays at TARGET_SR. Returns (B, llm_hidden), grad flows
        only through the projection head (encoder is frozen + run under no_grad)."""
        proc = self.feature_extractor(
            waveforms, sampling_rate=TARGET_SR, return_tensors="pt",
            padding=True, return_attention_mask=True,
        )
        input_values = proc["input_values"].to(self.device, dtype=self.encoder.dtype)
        in_mask = proc.get("attention_mask")
        enc_kwargs = {}
        if in_mask is not None:
            in_mask = in_mask.to(self.device)
            enc_kwargs["attention_mask"] = in_mask

        with torch.no_grad():
            out = self.encoder(input_values, **enc_kwargs)
        hidden = out.last_hidden_state  # (B, T, enc_hidden), bf16

        # Map the sample-level input mask to the encoder's frame rate so the pool ignores padding.
        frame_mask = None
        if in_mask is not None and hasattr(self.encoder, "_get_feat_extract_output_lengths"):
            out_lens = self.encoder._get_feat_extract_output_lengths(in_mask.sum(-1)).to(torch.long)
            T = hidden.shape[1]
            frame_mask = (torch.arange(T, device=hidden.device)[None, :] < out_lens[:, None])

        pooled = self._masked_mean(hidden, frame_mask)          # (B, enc_hidden), bf16
        return self.proj(pooled.float())                        # (B, llm_hidden), fp32


def _smoke() -> None:
    torch.manual_seed(0)
    llm_hidden = 3584  # Qwen2-Audio-7B's text hidden size; the real value is read from the model.
    tower = EmotionTower(llm_hidden=llm_hidden)
    # Two clips of different lengths -> exercises padding + masked pooling.
    waveforms = [np.random.randn(16000).astype("float32"),
                 np.random.randn(24000).astype("float32")]
    out = tower(waveforms)
    n_train = sum(p.numel() for p in tower.parameters() if p.requires_grad)
    n_frozen = sum(p.numel() for p in tower.parameters() if not p.requires_grad)
    print(f"encoder           : {tower.encoder_name} (hidden {tower.encoder.config.hidden_size})")
    print(f"output shape      : {tuple(out.shape)}  (expect (2, {llm_hidden}))")
    print(f"output dtype      : {out.dtype}  requires_grad={out.requires_grad}")
    print(f"trainable params  : {n_train:,}  (projection head only)")
    print(f"frozen params     : {n_frozen:,}  (encoder)")
    assert out.shape == (2, llm_hidden), "projection output dim mismatch"
    assert out.requires_grad, "no grad path through projection -- check requires_grad on proj"
    print("SMOKE OK")


if __name__ == "__main__":
    _smoke()
