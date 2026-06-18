# Audio-LLM Mental-State Assessment (CoT)

Explainable mental-state assessment via an audio-LLM fine-tuned with LoRA to emit a
chain-of-thought (CoT) before its final judgment. See `RP.md` for the full proposal.

## Status

Code skeleton only. Written in a GPU-less, network-restricted sandbox -- nothing here has been
run yet. Copy this directory to the H100/JupyterHub environment to actually execute it.

## Why this can't run in this sandbox

Verified when this skeleton was written: no `nvidia-smi`, no `torch` installed, and
`huggingface.co` returns 403 (network policy blocks it). This sandbox is isolated from the
author's local machine, but it is also isolated from the H100 -- it's a place to author code,
not to run it.

## Layout

```
audio_llm_mental_health/
  RP.md                          research proposal
  configs/
    lora_config.yaml             PEFT LoraConfig
    train_config.yaml            paths + training hyperparameters
  data/
    prompts.py                   chat prompt + synthetic CoT target templates
    meld_dataset.py              Phase 1: MELD pipeline-validation dataset
    mmpsy_dataset.py             Phase 2 stub (blocked on raw-audio-vs-adapter decision)
  scripts/
    extract_meld_audio.py        MELD .mp4 clips -> per-utterance .wav (needs ffmpeg)
    prepare_meld_manifest.py     MELD CSV + audio dir -> JSONL manifest
    train_lora.py                LoRA SFT loop
    infer.py                     run a tuned checkpoint on one clip
  outputs/                       checkpoints land here (gitignored except .gitkeep)
```

## Setup (on the H100)

```bash
cd audio_llm_mental_health
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Phase 1: MELD pipeline validation

1. Download `MELD.Raw.tar.gz` (https://affective-meld.github.io/) and extract it. The raw
   archive ships per-split video tarballs (`train.tar.gz`, `dev.tar.gz`, `test.tar.gz`)
   containing `.mp4` clips named `dia{Dialogue_ID}_utt{Utterance_ID}.mp4`, inside
   split-specific subfolders that are named inconsistently across splits
   (`train_splits/` for train, `dev_splits_complete/` for dev). `dev_sent_emo.csv` and
   `test_sent_emo.csv` ship at the top level of the raw archive; `train_sent_emo.csv` is
   bundled inside `train.tar.gz` itself, alongside `train_splits/` -- extracting that
   tarball (next step) produces it.
2. Extract per-utterance audio from the video clips (requires `ffmpeg`):
   ```bash
   python scripts/extract_meld_audio.py --video-dir MELD.Raw/train_splits --out-dir MELD.Raw/train_audio
   python scripts/extract_meld_audio.py --video-dir MELD.Raw/dev_splits_complete --out-dir MELD.Raw/dev_audio
   ```
3. Build manifests:
   ```bash
   python scripts/prepare_meld_manifest.py \
     --csv path/to/train_sent_emo.csv \
     --audio-dir MELD.Raw/train_audio \
     --out data/meld_train_manifest.jsonl
   python scripts/prepare_meld_manifest.py \
     --csv path/to/dev_sent_emo.csv \
     --audio-dir MELD.Raw/dev_audio \
     --out data/meld_dev_manifest.jsonl
   ```
4. Train:
   ```bash
   python scripts/train_lora.py --config configs/train_config.yaml
   ```
5. Try a checkpoint:
   ```bash
   python scripts/infer.py --adapter outputs/meld_lora/final \
     --audio path/to/clip.wav --transcript "..."
   ```

MELD's emotion/sentiment labels are a stand-in task here, used only to validate that audio
loading, prompting, LoRA SFT, and CoT decoding work end to end. This is not a mental-health
result -- see RP.md.

## Phase 2: MMPsy

Blocked on a design decision: MMPsy ships mel-spectrograms/embeddings, not raw audio, and
Qwen2-Audio's audio tower expects raw waveform. See `data/mmpsy_dataset.py` for the two options.
Decide once Phase 1 is validated.

## Known simplifications

- CoT training targets are templated from the gold label and generic cue phrases (see
  `data/prompts.py`), not human-annotated rationales -- there are no human CoT annotations for
  either dataset. Good enough to validate the mechanics; not a claim that the model's reasoning
  is causally verified.
- `train_lora.py` is a plain training loop, not a `transformers.Trainer` integration, to keep
  the multimodal batching logic visible and easy to adapt to whatever the installed
  `transformers` version's `Qwen2Audio` processor actually returns.
