#!/usr/bin/env python
"""PREFLIGHT for the LoRA-placement-attribution arms -- run on the GPU box before training.

RP.md line 85 warns that the path-scoped target_modules regexes for the llm_only / audio_only /
both arms were DERIVED (the `model.` prefix, the q_proj-vs-out_proj split) and not verified against
a live checkpoint. A wrong prefix would silently match 0 modules (PEFT then trains nothing, or
errors), and a too-loose pattern would leak across towers -- reintroducing exactly the audio_tower
contamination (RP.md line 29) these arms exist to avoid. This script loads the real base model the
same way train_lora.py does, applies each arm's regex with PEFT's own matching rule (re.fullmatch
on the full dotted module path, for a STRING target_modules), and reports per-arm:

  * how many modules matched, broken down by tower (language_model / audio_tower / other)
  * a few example matched names
  * PASS/FAIL: FAIL if 0 matches, or if an arm matches the tower it must keep frozen

Exits non-zero if ANY arm fails, so it can gate a launch script. It loads the 4-bit base once and
inspects names only -- no training, no data, ~1 min on a 1g.10gb slice.

    python scripts/check_target_modules.py
"""

import re
import sys
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data.model_loading import load_base_model  # noqa: E402

# (label, lora_config_path, tower this arm MUST stay inside -- None for 'both')
ARMS = [
    ("llm_only", "configs/lora_config_llm_only.yaml", "language_model"),
    ("audio_only", "configs/lora_config_audio_only.yaml", "audio_tower"),
    ("both", "configs/lora_config_both.yaml", None),
]

REPO = Path(__file__).resolve().parent.parent


def tower_of(name: str) -> str:
    if "language_model" in name:
        return "language_model"
    if "audio_tower" in name:
        return "audio_tower"
    return "other"


def main() -> int:
    model_name = yaml.safe_load(
        (REPO / "configs/train_config_meld_textmask1_both_4bit.yaml").read_text()
    )["model_name_or_path"]
    print(f"Loading base model {model_name} (4-bit, same as training) ...", flush=True)
    model = load_base_model(model_name)
    all_names = [n for n, _ in model.named_modules()]
    print(f"Model has {len(all_names)} named modules.\n", flush=True)

    ok = True
    for label, cfg_path, must_stay_in in ARMS:
        pattern = yaml.safe_load((REPO / cfg_path).read_text())["target_modules"]
        if not isinstance(pattern, str):
            print(f"[{label}] FAIL: target_modules is not a regex string ({type(pattern).__name__}); "
                  f"the bare-list form is the leaky one this experiment avoids.")
            ok = False
            continue
        rx = re.compile(pattern)
        matched = [n for n in all_names if rx.fullmatch(n)]  # PEFT's rule for a string target_modules
        by_tower: dict[str, int] = {}
        for n in matched:
            by_tower[tower_of(n)] = by_tower.get(tower_of(n), 0) + 1

        print(f"[{label}]  pattern: {pattern}")
        print(f"          matched {len(matched)} modules  by tower: {by_tower or '{}'}")
        for ex in matched[:3]:
            print(f"            e.g. {ex}")

        arm_ok = True
        if not matched:
            print("          FAIL: 0 modules matched -- wrong prefix/path; adapter would train nothing.")
            arm_ok = False
        if must_stay_in is not None:
            leaked = {t: c for t, c in by_tower.items() if t != must_stay_in}
            if leaked:
                print(f"          FAIL: leaked outside {must_stay_in} into {leaked} "
                      f"-- exactly the cross-tower contamination this arm must avoid.")
                arm_ok = False
        else:  # 'both' must hit BOTH towers to be the real apex
            for t in ("language_model", "audio_tower"):
                if by_tower.get(t, 0) == 0:
                    print(f"          FAIL: 'both' matched nothing in {t}; not a symmetric Both.")
                    arm_ok = False
        print("          PASS\n" if arm_ok else "")
        ok = ok and arm_ok

    if ok:
        print("All arms PASS -- safe to launch the three training runs.")
        return 0
    print("One or more arms FAILED -- fix the regex/prefix before training. Inspect names with:")
    print("  python -c \"from data.model_loading import load_base_model as L; "
          "[print(n) for n,_ in L('%s').named_modules()]\"" % model_name)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
