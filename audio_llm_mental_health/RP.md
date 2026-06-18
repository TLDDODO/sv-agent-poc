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

The pipeline runs end to end on the H100: `prepare_meld_manifest.py` -> `train_lora.py` (LoRA SFT
on `Qwen2-Audio-7B-Instruct`, 9,988 MELD train utterances, 3 epochs / 1,872 steps) ->
`outputs/meld_lora/final`, then `infer.py` / `batch_infer.py` produce a CoT + label for a held-out
clip. Phase 1's plumbing goal (audio loading -> prompting -> LoRA SFT -> CoT decoding, see
"Approach") is met.

The mental-state-assessment goal is not, and three controlled interventions
(`scripts/audio_ablation.py`; `scripts/eval_accuracy.py --silence` / `--hide-transcript`;
`scripts/compare_audio_contribution.py` — all on a random 200-row sample of
`data/meld_dev_manifest.jsonl`, greedy decoding) show why, precisely:

| Input given to the fine-tuned model              | Accuracy vs. gold emotion | vs. majority baseline (0.370) |
|---------------------------------------------------|----------------------------|----------------------------------|
| Audio + transcript (the trained setting)           | 0.645                       | +0.275                            |
| **Silence** + transcript (audio removed)           | 0.670                       | **+0.300**                        |
| Audio + **placeholder text** (transcript hidden)   | 0.515                       | +0.145                            |

Read together: removing the audio entirely scores *higher* than giving the model the real clip
(delta -0.025; row by row, the real audio actively hurts more rows (19/200) than it helps
(14/200)), and swapping in an emotionally-contrasting donor clip changes the predicted label to
that donor's emotion only 2/15 times — chance level for 7-way classification. Audio is not just
underused here, it is closer to noise for this trained model. Yet with the transcript hidden and
only the real audio given, accuracy is still 0.515 — clearly above baseline and spread across
most classes (recall 0.88 neutral / 0.52 anger / 0.37 surprise / 0.26 joy) — so the audio channel
does carry usable emotion signal; the jointly-trained model simply never learns to rely on it.

This is a quantified instance of *modality collapse / text dominance*, a known failure mode in
multimodal sentiment analysis (see e.g. the self-supervised modality-disentangled representation
learning approach of Chang et al., IEEE JBHI 2026, and the LIME-440K semantic-acoustic decoupling
in CogAudio-LLM, arXiv:2606.06940). The proximate cause here is specific to this skeleton's
Phase-1 simplification: `build_synthetic_cot_target` (`data/prompts.py`) generates the CoT
supervision target as a deterministic function of the gold label (a per-emotion cue-phrase
template), not from anything extracted from the audio itself, so gradient descent has no
incentive to route information through the audio encoder once the transcript offers an easier
path to the label. The model's CoT text consequently *looks* like audio-grounded reasoning (it
names a plausible-sounding acoustic cue) but is post-hoc rationalization of a transcript-driven
decision — exactly the failure README.md's "EIPS-depth check" warns manual CoT review to watch
for, now confirmed quantitatively rather than only by inspection.

The phase's actual contribution is therefore not "explainable mental-state assessment achieved,"
but a working pipeline plus a quantified diagnosis of *when and why* label-templated CoT
supervision fails to ground an audio-LLM in the audio signal it is given — evidence for why
approaches like LIME-440K-style data decoupling, dual-encoder architectures, or self-supervised
modality-disentanglement supervision exist, reproduced as a measured effect on this project's own
model and data rather than taken on faith from the cited papers.

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
