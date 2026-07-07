"""Phase 1 pipeline-validation dataset: MELD utterance audio -> CoT -> emotion label.

This is a plumbing test for the audio-LLM + LoRA + CoT mechanics (see RP.md, Phase 1). It is
not a mental-health dataset; emotion is used only as a stand-in label to validate that audio
loading, prompting, LoRA SFT, and CoT decoding work end to end before touching MMPsy.
"""

import json
import random
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset

from .prompts import build_conversation, build_decoupled_cot_target, build_synthetic_cot_target

ANSWER_KEY = "Emotion"


class MELDDataset(Dataset):
    def __init__(self, manifest_path: str | Path, text_mask_prob: float = 0.0, seed: int = 42):
        """`text_mask_prob` drops the transcript from a fraction of training examples (both the
        prompt and the CoT target), turning them into audio-only tasks. Combined with the
        audio-grounded targets from build_decoupled_cot_target (used when the manifest carries an
        'acoustic' field from scripts/extract_acoustic_priors.py), this is the countermeasure to
        the text-dominance result in RP.md "Preliminary Result". Default 0.0 reproduces the
        original Phase-1 behavior.

        Rows with no transcript at all (LIME Part B, whose public release ships `text: null` --
        see RP.md "Open premises") are always treated as audio-only, independent of
        `text_mask_prob`: there's nothing to probabilistically mask if the row never had a
        transcript to begin with.
        """
        self.examples: list[dict[str, Any]] = []
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.examples.append(json.loads(line))
        self.text_mask_prob = text_mask_prob
        self.rng = random.Random(seed)

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        ex = self.examples[idx]
        include_transcript = bool(ex["transcript"]) and not (
            self.text_mask_prob > 0 and self.rng.random() < self.text_mask_prob
        )
        conversation = build_conversation(
            ex["audio_path"], ex["transcript"], ANSWER_KEY, include_transcript=include_transcript
        )
        acoustic = ex.get("acoustic")
        if acoustic:
            target = build_decoupled_cot_target(
                ex["transcript"], acoustic, ANSWER_KEY, ex["emotion"],
                include_transcript=include_transcript,
            )
        else:
            # No acoustic priors in this manifest: fall back to the original templated target.
            target = build_synthetic_cot_target(
                ex["transcript"], ex.get("cues", []), ANSWER_KEY, ex["emotion"]
            )
        return {
            "audio_path": ex["audio_path"],
            "conversation": conversation,
            "target": target,
        }
