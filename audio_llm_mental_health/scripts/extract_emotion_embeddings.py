#!/usr/bin/env python
"""Pre-compute a per-clip emotion-encoder embedding and store it in the manifest.

This is the OFFLINE half of the architecture-level intervention (RP.md "Approach" point 1, the
dual-encoder + disentanglement design). The idea: Qwen2-Audio's built-in audio tower is a
Whisper-style SEMANTIC encoder; on emotion-from-speech it carries mostly transcript-aligned
information, which is exactly the channel the LLM decoder already over-uses (modality collapse).
A second, EMOTION-centric encoder (emotion2vec) carries acoustic-affect information the semantic
tower does not. We add that tower's embedding as an extra LLM input token and train a small
projection adapter (+ the usual LoRA) to use it, with a disentanglement loss (data/disentangle.py)
forcing it to stay complementary to the semantic tower.

Why offline (and not a second live tower at train time): the MIG slice is ~9.75 GiB and the
existing 4-bit base + LoRA run already sits at ~9.5 GiB (RP.md "Environment") -- there is no room
to also load and run a second encoder during training. So we run the emotion tower ONCE here, over
each clip, and cache its fixed (frozen-encoder) embedding in the manifest. Training then loads a
768-float vector per row and never touches the emotion encoder at all -- zero extra GPU memory for
the tower, only the small trainable projection MLP. This mirrors the existing offline-feature
pattern in scripts/extract_acoustic_priors.py.

The embedding is frozen (the encoder is not fine-tuned), so caching it loses nothing vs. running
it live -- the only trainable thing downstream is the projection adapter, which sees the cached
vector either way.

Run on the H100 (needs the raw audio + the encoder), once per split, BEFORE train_dual_encoder.py:

    pip install -U funasr            # emotion2vec is served through FunASR's AutoModel
    python scripts/extract_emotion_embeddings.py \
        --in data/meld_train_manifest.jsonl --out data/meld_train_manifest_emo.jsonl

emotion2vec_base outputs a single 768-d utterance vector at 16 kHz (granularity="utterance");
the field written is `emotion_embed` (a list of 768 floats). See
https://github.com/ddlBoJack/emotion2vec and https://huggingface.co/emotion2vec/emotion2vec_base.
"""

import argparse
import json
from pathlib import Path

import numpy as np

# emotion2vec model ids (FunASR hub). _base is ~90M / 768-d; _plus_large is ~300M / 1024-d.
# Keep _base as the default: smallest, and 768-d keeps the cached manifest and the projection
# adapter small. If you switch to a _plus_large model, the embedding dim changes (1024) and the
# projection adapter's in_features in models/dual_encoder.py must match -- it reads the dim from
# the cached vector length at load time, so no code change is needed, just re-run this script.
DEFAULT_MODEL = "iic/emotion2vec_base"


def load_encoder(model_id: str, hub: str):
    """Load emotion2vec via FunASR. Imported lazily so the sandbox (no funasr/torch) can still
    import this module for inspection; the import only fires when actually extracting."""
    from funasr import AutoModel

    return AutoModel(model=model_id, hub=hub)


def embed_one(model, audio_path: str) -> np.ndarray:
    """Utterance-level 768-d emotion embedding for one clip.

    FunASR's generate() returns a list (one entry per input); each entry's 'feats' is the
    utterance vector under granularity="utterance". We do NOT pass output_dir, so nothing is
    written to disk -- we read the vector straight out of the return value.
    """
    res = model.generate(audio_path, granularity="utterance", extract_embedding=True)
    feats = np.asarray(res[0]["feats"], dtype=np.float32).reshape(-1)
    return feats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", required=True, help="Input JSONL manifest.")
    parser.add_argument("--out", required=True, help="Output JSONL with an added 'emotion_embed'.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="FunASR/emotion2vec model id.")
    parser.add_argument(
        "--hub", default="hf", choices=["hf", "ms"],
        help="'hf' (HuggingFace, default) or 'ms' (ModelScope, for mainland-China mirrors).",
    )
    args = parser.parse_args()

    rows = []
    with open(args.inp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    model = load_encoder(args.model, args.hub)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dim = None
    failures = 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for i, row in enumerate(rows):
            try:
                vec = embed_one(model, row["audio_path"])
                if dim is None:
                    dim = vec.shape[0]
                elif vec.shape[0] != dim:
                    raise ValueError(f"dim {vec.shape[0]} != expected {dim}")
                # round to 5 dp: keeps the manifest a few-MB smaller with no measurable effect on a
                # downstream projection adapter (the encoder is frozen, so this is the only lossy step
                # and it is far below the encoder's own noise floor).
                row["emotion_embed"] = [round(float(x), 5) for x in vec]
            except Exception as e:  # noqa: BLE001 -- one bad clip shouldn't kill a 10k-row pass
                failures += 1
                row["emotion_embed"] = None
                print(f"  !! row {i} ({row.get('audio_path')}): {e}")
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if (i + 1) % 200 == 0:
                print(f"  ...{i + 1}/{len(rows)} clips embedded")

    print(f"\nWrote {len(rows)} rows with {dim}-d 'emotion_embed' to {out_path} "
          f"(embed failures: {failures}).")
    if failures:
        print("NOTE: rows with emotion_embed=null fall back to a zero emotion token at train time "
              "(see models/dual_encoder.py) -- a few are harmless; many means a path/encoder issue.")


if __name__ == "__main__":
    main()
