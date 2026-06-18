# Audio-LLM Mental-State Assessment (CoT)

Explainable mental-state assessment via an audio-LLM fine-tuned with LoRA to emit a
chain-of-thought (CoT) before its final judgment. See `RP.md` for the full proposal.

## Status

Smoke-tested end to end on an H100: model download, LoRA init, audio actually reaching the
model, masked-loss SFT step, checkpoint save/load, and CoT+label decoding via `infer.py` all
ran without errors on a 16-example slice. A full run over the MELD train split is in progress.
See "Known simplifications" below for what this does and doesn't validate.

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
    train_config_smoke.yaml      same, pointed at a tiny manifest subset for a quick sanity run
  data/
    prompts.py                   chat prompt + synthetic CoT target templates
    meld_dataset.py              Phase 1: MELD pipeline-validation dataset
    mmpsy_dataset.py             Phase 2 stub (blocked on raw-audio-vs-adapter decision)
  scripts/
    extract_meld_audio.py        MELD .mp4 clips -> per-utterance .wav (needs ffmpeg)
    prepare_meld_manifest.py     MELD CSV + audio dir -> JSONL manifest
    train_lora.py                LoRA SFT loop
    infer.py                     run a tuned checkpoint on one clip
    batch_infer.py               run a tuned checkpoint over several manifest rows, dump a report
    find_conflict_candidates.py  surface text/label mismatches for conflict-robustness testing
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
4. Smoke-test the training loop on a tiny subset before a full run:
   ```bash
   head -n 16 data/meld_train_manifest.jsonl > data/meld_train_manifest_smoke.jsonl
   head -n 8 data/meld_dev_manifest.jsonl > data/meld_dev_manifest_smoke.jsonl
   python scripts/train_lora.py --config configs/train_config_smoke.yaml
   ```
   Confirms the multimodal batching, masking, and LoRA SFT step run end to end (and that loss
   is finite and moving) without committing to a multi-hour full run.
5. Train:
   ```bash
   python scripts/train_lora.py --config configs/train_config.yaml
   ```
6. Try a checkpoint:
   ```bash
   python scripts/infer.py --adapter outputs/meld_lora/final \
     --audio path/to/clip.wav --transcript "..."
   ```

MELD's emotion/sentiment labels are a stand-in task here, used only to validate that audio
loading, prompting, LoRA SFT, and CoT decoding work end to end. This is not a mental-health
result -- see RP.md.

## Evaluation

Loss going down confirms the mechanics run; it says nothing about whether the CoT is actually
grounded in the audio rather than just paraphrasing the transcript. Two manual checks, run after
a real training pass (not the smoke checkpoint, which has seen far too little data to have
learned anything):

1. **Acoustic-text congruence.** Pick a handful of dev rows, generate with `batch_infer.py`,
   and for each one that cites a concrete acoustic cue ("shaky voice", "raised pitch"), listen
   to the clip and check whether the cue is actually audible -- or whether the model is just
   inferring tone from the transcript's wording.
2. **Conflict robustness.** Find rows where the literal wording and the gold label disagree
   (MELD's labels were assigned by watching the full scene, audio and video, so a mismatch
   between bare wording and the gold label is a proxy for "the words alone are misleading"):
   ```bash
   python scripts/find_conflict_candidates.py --manifest data/meld_dev_manifest.jsonl
   ```
   Confirm a couple of candidates by listening, then run them through the model:
   ```bash
   python scripts/batch_infer.py --adapter outputs/meld_lora/final \
     --manifest data/meld_dev_manifest.jsonl --indices <comma-separated indices> \
     --out outputs/review_conflict.jsonl
   ```
   If the CoT explains its answer purely from the words ("said 'get out', so angry") despite
   audio that actually sounds playful, the model is leaning on text and ignoring the audio
   tower's signal -- worth knowing before trusting any of its explanations.

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
