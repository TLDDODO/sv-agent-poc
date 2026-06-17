# One-Page Research Proposal

## Title

**Explainable Mental-State Assessment via Audio-LLM with Chain-of-Thought Reasoning**

## Problem

Existing multimodal mental-health prediction systems (e.g. MMPsy, Mental-Perceiver) are almost
all discriminative classifiers: they consume speech features and emit a label such as
"depressed" or "anxious" with no explanation of *why*. Clinicians and downstream users cannot
audit the reasoning, which limits trust and clinical usefulness. The 2026 trend in multimodal
speech understanding is shifting toward audio-native generative LLMs (Qwen2-Audio-class models)
that can read raw audio directly and produce free-text reasoning, not just a softmax over labels.

## Hypothesis

An audio-LLM, LoRA-fine-tuned to emit a short chain-of-thought (CoT) before its final judgment,
can produce mental-state assessments that are not only competitive in signal but also
inspectable: the rationale names the acoustic/linguistic cues (tone, pacing, word choice) that
drove the prediction. This explainability is a dimension that purely discriminative classifiers
do not provide, independent of whether raw classification accuracy matches the SOTA.

## Approach

1. **Base model:** an off-the-shelf audio-LLM in the Qwen-Audio family (e.g.
   `Qwen2-Audio-7B-Instruct`), which natively accepts raw waveform + text and is fine-tuned with
   LoRA rather than full-parameter training (fits a single H100).
2. **Input:** paired audio + transcript (dual-modality prompt).
3. **Output:** a CoT narrative grounded in observable cues, followed by a final mental-state
   judgment (e.g. depression / anxiety indicator).
4. **Data, phased:**
   - **Phase 1 — MELD.** Has real raw audio per utterance. Used purely to validate the
     mechanics of the pipeline (audio loading -> prompting -> LoRA SFT -> CoT decoding) before
     touching the target domain. Emotion/sentiment labels stand in as a proxy task; this is a
     plumbing test, not a mental-health benchmark result.
   - **Phase 2 — MMPsy.** The actual target domain (depression/anxiety-relevant speech), but the
     public release only ships mel-spectrograms and embeddings, not raw waveform. Qwen2-Audio's
     audio tower expects raw audio (Whisper-style frontend), so MMPsy needs either (a) sourcing
     raw audio out-of-band, or (b) a separate projection adapter that feeds precomputed
     mel/embedding features directly into the language model, bypassing the raw-audio encoder.
     This is a known constraint, deferred to Phase 2 by design.
5. **Training:** LoRA adapters on the language-model decoder, single H100, via
   `transformers` + `peft`.

## Preliminary Result

None yet. This proposal accompanies a code skeleton (`audio_llm_mental_health/` in this repo) —
directory layout, data loaders, LoRA config, and training/inference scripts — written in a
GPU-less sandbox and intended to be copied to the H100 environment to actually run.

## Expected Impact / Contribution

The goal is not to beat discriminative SOTA on classification accuracy. The contribution is
demonstrating that audio-LLM + CoT can add an explainability dimension to mental-state
assessment that discriminative models structurally cannot offer — a inspectable rationale tied
to specific acoustic/linguistic evidence in the input.

## Next Milestones (1.5-week deliverable)

- Get the minimal chain running end-to-end on MELD: audio + text -> LoRA-tuned audio-LLM -> CoT
  + label, on a small slice of data, on the H100.
- Inspect generated CoT outputs by hand for plausibility (do the cited cues actually match the
  audio?).
- Decide the MMPsy raw-audio-vs-adapter question based on what's actually available, then port
  the same pipeline to MMPsy.

## Success Criterion

Given a held-out MELD (then MMPsy) audio clip + transcript, the fine-tuned model should produce
a short CoT that references concrete cues in the input and a final label, end to end, runnable
on the H100 with the scripts in this directory.

## Environment Notes

- This skeleton was authored in an isolated, ephemeral cloud sandbox with **no GPU and no
  outbound access to model/dataset hosts** (verified: no `nvidia-smi`, no `torch` installed,
  `huggingface.co` blocked). It cannot run training or inference itself.
- It never had access to, and does not need access to, any local machine's files.
- All actual training/inference must run on the H100/JupyterHub workshop environment — copy this
  directory there, create a fresh virtualenv, `pip install -r requirements.txt`, then proceed
  per `README.md` in this directory.
