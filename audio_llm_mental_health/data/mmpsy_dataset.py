"""Phase 2 stub for the real mental-health target domain (see RP.md, Phase 2).

MMPsy's public release ships mel-spectrograms and embeddings, not raw waveform. Qwen2-Audio's
audio tower expects raw audio (Whisper-style frontend), so MMPsy features cannot be fed through
the same path as MELDDataset without one of:

  (a) sourcing raw audio for MMPsy out-of-band and reusing MELDDataset's path, or
  (b) adding a projection adapter that maps MMPsy's precomputed features directly into the
      language model's embedding space, bypassing the raw-audio encoder.

Deliberately left unimplemented until that decision is made.
"""

from torch.utils.data import Dataset


class MMPsyDataset(Dataset):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "MMPsy loader depends on the raw-audio-vs-adapter decision described in this "
            "module's docstring and in RP.md Phase 2."
        )
