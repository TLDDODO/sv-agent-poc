# Diagnosing and Mitigating Modality Collapse in Audio-LLMs

A controlled study of *modality collapse* (text dominance) in a LoRA-fine-tuned
`Qwen2-Audio-7B-Instruct`: the model rides the transcript and underuses the acoustic channel on
emotion-from-speech. The MELD pipeline here is the fixed measurement instrument (a silence/
hide-transcript/donor-swap ablation ruler); interventions are measured against it. See `RP.md`
for the full proposal, hypothesis, and the controlled coupled-vs-decoupled comparison.

## Status

- **Baseline + collapse, established.** LoRA SFT on MELD runs end to end on an H100 (model
  download, LoRA init, masked-loss SFT, checkpoint save/load, CoT+label decoding). The ablation
  trio confirms collapse: removing audio does not hurt (and slightly helps) accuracy, and a
  donor-clip swap rarely moves the label. Numbers in `RP.md` "Core Finding".
- **Data-side fix, staged (running).** `extract_acoustic_priors.py` measures real per-clip
  acoustics and buckets them by corpus tertiles; `data/prompts.py` turns those buckets into a
  CoT target that can only be produced by listening, plus `text_mask_prob` transcript dropout.
  A `train_config.yaml`-driven retrain on the `*_acoustic.jsonl` manifests is the current run;
  the same ablation trio is re-run on the result to measure whether collapse moved.
- See "Known simplifications" for what this does and doesn't validate.

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
    train_config.yaml            paths + training hyperparameters (MELD)
    train_config_smoke.yaml      same, pointed at a tiny manifest subset for a quick sanity run
    train_config_esd.yaml        same shape as train_config.yaml, ESD acoustic-grounded run
    train_config_esd_plain.yaml  ESD plain baseline (no acoustic priors, no text masking)
    train_config_esd_smoke.yaml  ESD smoke test, same pattern as train_config_smoke.yaml
  data/
    prompts.py                   chat prompt + acoustic-grounded / synthetic CoT target templates
    meld_dataset.py              MELD dataset: the baseline measurement instrument
    mmpsy_dataset.py             parked stub (superseded by the LIME data-level intervention; see RP.md)
    model_loading.py             shared 4-bit (QLoRA-style) base-model loader -- see "Setup" below
  scripts/
    extract_meld_audio.py        MELD .mp4 clips -> per-utterance .wav (needs ffmpeg)
    prepare_meld_manifest.py     MELD CSV + audio dir -> JSONL manifest
    extract_acoustic_priors.py   measure real acoustics, bucket by corpus tertiles -> *_acoustic.jsonl
    train_lora.py                LoRA SFT loop
    infer.py                     run a tuned checkpoint on one clip
    batch_infer.py               run a tuned checkpoint over several manifest rows, dump a report
    eval_accuracy.py             emotion accuracy vs gold (supports --silence / --hide-transcript)
    compare_audio_contribution.py  diff two eval dumps to isolate audio's marginal contribution
    audio_ablation.py            silence/swap intervention: does the label track the audio?
    find_conflict_candidates.py  surface text/label mismatches for conflict-robustness testing
    probe_lime_partB.py          JSON-only check of LIME-440K's text-identical/multi-emotion grouping claim
    build_lime_manifest.py       LIME-440K Part B -> per-utterance .wav + JSONL manifest (group-level train/dev split)
    build_esd_manifest.py        ESD -> per-utterance .wav + JSONL manifest (real parallel-text decoupling, group-level split)
  outputs/                       checkpoints land here (gitignored except .gitkeep)
```

## Setup (on the H100)

```bash
cd audio_llm_mental_health
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Check `nvidia-smi` before training: if MIG is enabled, the per-student allocation may be a
single `1g.10gb` (~9.75 GiB) slice of the physical 80GB card rather than the whole card. Qwen2-
Audio-7B-Instruct needs ~16 GB for bf16 weights alone, which OOMs inside `from_pretrained` on
such a slice regardless of batch size. All five scripts that load the base model
(`train_lora.py`, `infer.py`, `batch_infer.py`, `eval_accuracy.py`, `audio_ablation.py`) go
through `data/model_loading.py::load_base_model`, which loads it 4-bit-quantized
(QLoRA-style nf4 via `bitsandbytes`) to fit this budget. See RP.md "Environment" for the
`nvidia-smi` evidence and the open comparability caveat against earlier bf16 runs.

## MELD: building the baseline instrument

MELD is the naturally-coupled (text-acoustic) arm of the study and the fixed ablation ruler.
These steps build the manifests, add acoustic priors, and run the LoRA SFT that the ablation
trio is then measured against.

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
4. Add acoustic priors (the data-side fix). Reads raw audio once per split and writes
   `*_acoustic.jsonl` with a tertile-bucketed `acoustic` field; `train_config.yaml` points at
   these. Note the printed corpus tertile thresholds -- if a feature's t33 and t67 collapse
   together it has no discriminating power and the bucketing degrades:
   ```bash
   python scripts/extract_acoustic_priors.py \
     --in data/meld_train_manifest.jsonl --out data/meld_train_manifest_acoustic.jsonl
   python scripts/extract_acoustic_priors.py \
     --in data/meld_dev_manifest.jsonl   --out data/meld_dev_manifest_acoustic.jsonl
   ```
5. Smoke-test the training loop on a tiny subset before a full run:
   ```bash
   head -n 16 data/meld_train_manifest.jsonl > data/meld_train_manifest_smoke.jsonl
   head -n 8 data/meld_dev_manifest.jsonl > data/meld_dev_manifest_smoke.jsonl
   python scripts/train_lora.py --config configs/train_config_smoke.yaml
   ```
   Confirms the multimodal batching, masking, and LoRA SFT step run end to end (and that loss
   is finite and moving) without committing to a multi-hour full run.
6. Train (`train_config.yaml` points at the `*_acoustic.jsonl` manifests, `text_mask_prob=0.3`,
   output to `outputs/meld_lora_grounded`):
   ```bash
   python scripts/train_lora.py --config configs/train_config.yaml
   ```
7. Try a checkpoint:
   ```bash
   python scripts/infer.py --adapter outputs/meld_lora_grounded/final \
     --audio path/to/clip.wav --transcript "..."
   ```

MELD's emotion labels are not the point; emotion accuracy is the surface on which collapse is
measured. The acoustic-grounded CoT + transcript dropout is the data-level intervention, and
the silence-vs-audio ablation is re-run on the result to test whether collapse moved. This is
not a mental-health result -- see RP.md.

## Evaluation

Loss going down confirms the mechanics run; it says nothing about whether the CoT is actually
grounded in the audio rather than just paraphrasing the transcript.

**The ablation ruler (primary, quantitative).** The same trio is run on every condition; use a
fixed `--seed`/`--sample` and a recorded `--indices` set so runs are comparable across
conditions:

```bash
# (a) three-condition accuracy: real audio vs silenced (transcript kept), same seed/sample
python scripts/eval_accuracy.py --adapter outputs/meld_lora_grounded/final \
    --manifest data/meld_dev_manifest_acoustic.jsonl --sample 200 --seed 42 \
    --out outputs/eval_grounded.jsonl
python scripts/eval_accuracy.py --adapter outputs/meld_lora_grounded/final \
    --manifest data/meld_dev_manifest_acoustic.jsonl --sample 200 --seed 42 \
    --silence --out outputs/eval_grounded_silence.jsonl
python scripts/compare_audio_contribution.py \
    --with-audio outputs/eval_grounded.jsonl --silenced outputs/eval_grounded_silence.jsonl

# (b) silence/swap intervention on a fixed recorded index set (does the label track the audio?)
python scripts/audio_ablation.py --adapter outputs/meld_lora_grounded/final \
    --manifest data/meld_dev_manifest_acoustic.jsonl --indices "$IDX" \
    --out outputs/ablation_grounded.jsonl
```

A silence-vs-audio delta that has risen from the baseline (where removing audio did *not* hurt)
is the signal that the data-side fix moved collapse. Record the `$IDX` set used so the swap/
tracking numbers are reproducible.

**Qualitative checks (after a real, non-smoke training pass):**

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
   python scripts/batch_infer.py --adapter outputs/meld_lora_grounded/final \
     --manifest data/meld_dev_manifest_acoustic.jsonl --indices <comma-separated indices> \
     --out outputs/review_conflict.jsonl
   ```
   If the CoT explains its answer purely from the words ("said 'get out', so angry") despite
   audio that actually sounds playful, the model is leaning on text and ignoring the audio
   tower's signal -- worth knowing before trusting any of its explanations.
3. **EIPS-depth check.** Score each CoT on how many of these stages it actually articulates,
   instead of collapsing straight from transcript to label:
   - *Perception*: names a specific acoustic cue (pitch, pace, voice quality), not just "the tone".
   - *Semantic check*: explicitly notes whether the literal wording agrees or conflicts with that cue.
   - *Psychological inference*: connects the cue and the semantic check to an emotional/mental
     state, rather than just restating the label.

   A CoT that jumps straight from transcript to label without any of these stages is shallow
   evidence of audio grounding, regardless of whether the label happens to be correct. If most
   outputs from a real (non-smoke) training pass are shallow, the place to add this structure is
   the templated synthetic CoT targets in `data/prompts.py` (`build_synthetic_cot_target`), for a
   future training round -- not a reason to redo the current pass.

   This check is adapted from the "EIPS" 4-step (Perception -> Intent -> Psychology -> Strategy)
   chain-of-thought framework described in CogAudio-LLM (arXiv:2606.06940, 2026) and from a
   multi-task reasoning-augmented-supervision approach described in a 2026 A\*STAR Singapore
   speech-emotion-reasoning paper. Both postdate this model's training data, so their specific
   claims are taken as the source's transcription, not independently verified -- used here only
   as a qualitative rubric, not a benchmark to match.

## Next: the controlled comparison

Once the data-side fix is measured on MELD, the study's contribution is the coupled-vs-decoupled
comparison (see `RP.md`): the same dual-encoder + disentanglement architecture run on a
three-tier gradient that varies only in how informative the transcript is about the label --
**MELD** (natural, coupled, transcript predictive -- the baseline above), **ESD** (acted,
decoupled but transcript present -- the primary condition), and **LIME-Core Part B** (synthetic,
decoupled, no transcript at all -- the strictest supplementary condition) -- all English, to
test whether data-level and objective-level interventions reduce collapse by the same amount,
and whether the *form* of decoupling (uninformative-but-present text vs. no text at all) matters.

### ESD (primary data-level corpus)

Kun Zhou, Berrak Sisman, Rui Liu, Haizhou Li (NUS/SUTD), "Emotional Voice Conversion: Theory,
Databases and ESD" (arXiv:2105.14762, later in *Speech Communication*). License-gated,
research-only -- email the license form to `zhoukun@u.nus.edu`, then download via the Google
Drive link in the dataset's own GitHub README (`HLTSingapore/Emotional-Speech-Data`). Confirmed
by direct read of the extracted release (see `RP.md` "Open premises"): 10 English + 10 Mandarin
speakers each read the same 350 sentences under 5 emotions (neutral/happy/angry/sad/surprise);
for English speaker `0011`, the literal sentence text recurs at utt-id offsets of exactly 350
across all 5 emotions, so the transcript is present but carries zero label signal by
construction. Audio is already 16kHz mono PCM_16; the release ships flat per-speaker/per-emotion
folders with no train/evaluation/test split.

```bash
python scripts/build_esd_manifest.py --root "/data/.../Emotion Speech Dataset" \
    --audio-out-dir data/esd_audio --train-out data/esd_train_manifest.jsonl \
    --dev-out data/esd_dev_manifest.jsonl --dev-frac 0.1
```

Defaults to the 10 English speakers (`0011`-`0020`); splits by `(speaker, sentence-index)` GROUP
(derived from the utt-id numbering, since the source has no explicit group field) so a sentence's
5 emotion-variants never land on both sides of the split. Because the transcript is present, both
halves of the silence-vs-audio ablation ruler can be run on the result, exactly mirroring the
MELD ablation.

Smoke-test the training loop first, same pattern as MELD:

```bash
head -n 20 data/esd_train_manifest.jsonl > data/esd_train_manifest_smoke.jsonl
head -n 10 data/esd_dev_manifest.jsonl   > data/esd_dev_manifest_smoke.jsonl
python scripts/train_lora.py --config configs/train_config_esd_smoke.yaml
```

Two real runs answer two different questions, both worth recording:

1. **Plain baseline (data-level decoupling alone)** -- `configs/train_config_esd_plain.yaml`
   points at the un-grounded manifests (`data/esd_train_manifest.jsonl` /
   `data/esd_dev_manifest.jsonl`, `text_mask_prob: 0.0`, templated CoT):
   ```bash
   python scripts/train_lora.py --config configs/train_config_esd_plain.yaml
   ```
   Since ESD's transcript is already uninformative about the label by construction, this
   isolates whether *removing the shortcut at the data level alone* -- with no acoustic-grounded
   CoT, no transcript masking -- stops the model from collapsing onto audio-irrelevant shortcuts
   (here, the templated CoT-from-gold-label one diagnosed in MELD's Core Finding, since the
   transcript itself no longer offers an easier path). Run the same ablation trio as MELD to
   measure it.
2. **Acoustic-grounded fix (mirrors the MELD data-side fix)** -- `configs/train_config_esd.yaml`:
   ```bash
   python scripts/extract_acoustic_priors.py \
     --in data/esd_train_manifest.jsonl --out data/esd_train_manifest_acoustic.jsonl
   python scripts/extract_acoustic_priors.py \
     --in data/esd_dev_manifest.jsonl   --out data/esd_dev_manifest_acoustic.jsonl
   python scripts/train_lora.py --config configs/train_config_esd.yaml
   ```
   `configs/train_config_esd.yaml` already points at the `*_acoustic.jsonl` manifests with
   `text_mask_prob: 0.3`, the same hyperparameters as `train_config.yaml`, so the only variable
   between the MELD and ESD grounded runs is the corpus. `eval_accuracy.py`,
   `audio_ablation.py`, and `compare_audio_contribution.py` all take `--manifest` and need no
   ESD-specific changes -- point them at the ESD manifests/checkpoint the same way the MELD
   "Evaluation" section above does.

### LIME Part B (strictest supplementary corpus)

`scripts/probe_lime_partB.py` is the first gate -- it confirms by direct read that LIME's
same-group/different-emotion structure holds before any download of its 52 GB audio.

The repo's real layout (confirmed by a direct `HfApi.list_repo_files` + `json.load()` read, not
the paper's prose) splits by language-coded folder prefix rather than a HF `datasets` split:
`PartA_json_CN/*.json` (Chinese, 223,884 utterances) and `PartB_json_EN/*.json` (English, 96,000
utterances -- the one this project trains/evals on). Each `*.json` file is a dict keyed by
utterance id (`{"4_5_surprise": {"text", "emotion", "scenario", "group", "wav_path"}}`), not
JSON-Lines, so `datasets.load_dataset(...)` cannot read it directly; both scripts use
`huggingface_hub.hf_hub_download` + `json.load()` instead. The audio itself ships as one archive
per part (`PartB_wav_en.tar.gz`), not per-row -- extract it once and point
`build_lime_manifest.py --audio-root` at the extracted directory (see that script's docstring for
the exact extraction command). **`text` is `null` for 100% of Part B's ~96,000 records in this
public release** (confirmed by an exhaustive scan, not just the paper's "lexically-identical
text" framing -- see `RP.md` "Open premises"), so `build_lime_manifest.py` writes
`transcript: ""` for every row and the corpus trains/evals audio-only by construction -- the
strictest decoupling in the gradient, but only the audio-only half of the ablation ruler can be
run on it. `build_lime_manifest.py` resamples each clip to 16 kHz mono and writes a MELD-shaped
JSONL manifest, splitting train/dev by GROUP (not by row) so rows from the same scenario/cluster
group never land on both sides of the split.

The earlier MMPsy plan is parked: it ships mel-spectrograms/embeddings rather than raw waveform
(a tower mismatch documented in `data/mmpsy_dataset.py`), and ESD/LIME Part B are the cleaner
data-level decoupling corpora. Revisit only if a clinical raw-audio corpus becomes available.

## Known simplifications

- CoT training targets are templated from the gold label and generic cue phrases (see
  `data/prompts.py`), not human-annotated rationales -- there are no human CoT annotations for
  either dataset. Good enough to validate the mechanics; not a claim that the model's reasoning
  is causally verified.
- `train_lora.py` is a plain training loop, not a `transformers.Trainer` integration, to keep
  the multimodal batching logic visible and easy to adapt to whatever the installed
  `transformers` version's `Qwen2Audio` processor actually returns.
