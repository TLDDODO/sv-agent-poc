"""Phase 1 pipeline-validation dataset: MELD utterance audio -> CoT -> emotion label.

This is a plumbing test for the audio-LLM + LoRA + CoT mechanics (see RP.md, Phase 1). It is
not a mental-health dataset; emotion is used only as a stand-in label to validate that audio
loading, prompting, LoRA SFT, and CoT decoding work end to end before touching MMPsy.
"""

import json
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset

from .prompts import build_conversation, build_synthetic_cot_target

ANSWER_KEY = "Emotion"


class MELDDataset(Dataset):
    def __init__(self, manifest_path: str | Path):
        self.examples: list[dict[str, Any]] = []
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.examples.append(json.loads(line))

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        ex = self.examples[idx]
        conversation = build_conversation(ex["audio_path"], ex["transcript"], ANSWER_KEY)
        target = build_synthetic_cot_target(
            ex["transcript"], ex.get("cues", []), ANSWER_KEY, ex["emotion"]
        )
        return {
            "audio_path": ex["audio_path"],
            "conversation": conversation,
            "target": target,
        }
