# Diagnosing and Mitigating Modality Collapse in Audio-LLMs: A Controlled Study Across Naturally-Coupled and Synthetically-Decoupled Speech

## Problem

Audio-LLMs (Qwen2-Audio-class) are built on text-native LLMs, so their latent space is biased toward textual semantics; in emotion-from-speech tasks they ride the transcript and underuse the acoustic channel — *modality collapse*. That this collapse has **both data-level and architecture-level origins is now well established**: noisy features of one modality entangle with the predictive features of another in shared fusion neurons and get masked [arXiv 2505.22483, "A Closer Look at Multimodal Representation Collapse," Chaudhuri, Dutta, Bui & Georgescu, ICML 2025 Spotlight — confirmed via the arXiv abstract and ICML poster page], while on the architecture side the modal information is *not* lost in the encoder (speaker identity and emotion remain linearly decodable) — the decoder simply exploits only the text-aligned directions and treats the rest as noise, a bottleneck shown to be governed by the decoder's training objective / scoring rule (a generalized-mutual-information limit) rather than by the projection or adapter choice [arXiv 2602.23136, "Modality Collapse as Mismatched Decoding: Information-Theoretic Limits of Multimodal LLMs," Jayadev Billa, submitted 2026-02-26 — confirmed via the arXiv abstract page]. The same work reports that changing the training objective (e.g. adding an emotion task) raises modal accessibility (+7.5% [cite — VERIFY: exact figure; titles/authors/venue/core claims for both papers above are confirmed, but this specific number was not surfaced by a search summary and needs a direct read of the paper text]), confirming the objective — not the architecture per se — gates which modalities get used.

What remains **unaddressed is whether these two families of intervention are equivalent**. Data-level interventions (removing the transcript shortcut) and objective/architecture-level interventions (a dedicated emotion path with a disentanglement objective) have each been shown to reduce collapse *in isolation*, but no study compares them on a single ruler with coupling as the only manipulated variable. Whether removing the cause at the data level and counteracting it at the objective level reduce collapse by the same amount is an open question with no published systematic control.

## Core Finding (already obtained)

A LoRA-fine-tuned `Qwen2-Audio-7B-Instruct` baseline (MELD; audio + transcript → CoT + emotion label, 9,988 utterances) exhibits the expected collapse. On a 200-row dev sample (greedy decoding): audio + transcript = 0.645; **silence** + transcript = 0.670; audio + placeholder transcript = 0.515 (majority baseline 0.370). Removing audio raises accuracy; a donor-clip swap changes the predicted label to the donor's emotion only 2/15 times (chance for 7-way). Diagnosed proximate cause: the CoT supervision target is a deterministic function of the gold label, giving gradient descent no reason to use the audio encoder once the transcript offers an easier path. This baseline is the fixed measurement instrument; the same ablation is re-run under every condition below.

The first re-run of this ruler — the supervision-level intervention named below (acoustic-grounded CoT targets via `extract_acoustic_priors.py`'s corpus-tertile pitch/loudness-variance/pace buckets, plus `text_mask_prob=0.3` transcript dropout at train time) — already shows movement. Same 200-row dev sample, same greedy decoding: audio + transcript = 0.635 (127/200); silence + transcript = 0.600 (120/200); delta (audio − silence) = **+0.035**, flipping the sign of the collapsed baseline (where audio *hurt*, 0.645 vs 0.670). Row-level, real audio was needed for the right label on 17/200 rows (correct → wrong when silenced), against 10/200 the other way. Donor-swap tracking, on a fixed, recorded 15-row index set (`228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034`, seeded) rose to 7/15, against the collapsed baseline's 2/15 chance-level rate (exact binomial test vs. the chance null p=1/7: P(X≥7 | n=15) ≈ 0.003). Collapse is reduced, not eliminated: under silence the model still retreats toward the majority class (neutral recall 0.892 → 0.973), and anger/surprise/sadness recall drops measurably without audio (e.g. surprise 0.556 → 0.296) — the partial-reduction outcome the Success Criterion below names as valid. Caveat: the swap indices are a newly-recorded fixed set, not the same rows as the collapsed baseline's unrecorded 2/15, so this is a rate-to-rate, not row-identical, comparison.

## Hypothesis

Modality collapse is gated by the presence of a transcript shortcut and by the decoder's training objective. Removing the shortcut at the data level (a lexically-identical, multi-emotion corpus) and counteracting it at the objective/architecture level (a dedicated emotion encoder with a disentanglement objective) are *distinct* mechanisms whose effects can be measured on a single, fixed ruler. Holding language constant, a coupled vs. decoupled comparison should reveal how much of the collapse is data-attributable vs. architecture-correctable.

## Approach: interventions measured on one ruler

The silence-vs-audio delta (and conflict-subset accuracy) is the fixed ruler across all conditions.

1. **Architecture/objective-level.** Add an emotion-centric encoder (Emotion2Vec / HuBERT) as a second tower beside the Whisper-style semantic path, with a modality-specific adapter and an orthogonality / disparity loss forcing the emotion tower to carry signal the semantic tower does not. Adapts the dual-encoder design of Zhang et al. (I2R/A\*STAR 2025) and the disentanglement losses of Chang et al. (IEEE JBHI 2026) to an audio-LLM.
2. **Data-level.** Train and evaluate on LIME-Core Part B (English, ~200 speakers, 96,000 utterances, 113.8 h; `zhaoxiaoxian/LIME-440K_CogAudio-LLM` on Hugging Face), introduced in "Beyond Semantic Dominance: Cognitive Affective Reasoning and Empathetic Response Alignment in Audio Language Models" (Zhao, Wang, Tian, Hu, Zhang, Xie; ASLP@NPU; arXiv:2606.06940, accepted at INTERSPEECH 2026 per the arXiv listing), a "lexically-identical, multi-emotion" synthetic corpus where the same text maps to multiple emotions, so the transcript carries no label signal by construction.

(A lighter supervision-level intervention — feature-anchored CoT targets computed from real acoustics plus transcript-masking — is already implemented and measured; see Core Finding above.)

## The controlled comparison (contribution)

The same dual-encoder + disentanglement architecture is run on **MELD** (natural speech, text-acoustic *coupled*, transcript shortcut available) and on **LIME Part B** (synthetic speech, *decoupled*, no shortcut) — both English, so language is held constant and coupling is the only manipulated variable. This **directly tests the equivalence of data-level vs. objective-level interventions**: when the transcript shortcut is removed at the data level versus counteracted at the architecture/objective level, does modality collapse change by the same amount? It supplies the systematic control that the cited works — each operating within a single data regime and testing one intervention family in isolation — do not provide.

## Open premises to verify (honest)

- LIME Part B's decoupling is taken from the paper; a JSON-only probe must confirm that within each grouping field the text is genuinely identical while emotion varies, and how many such groups exist. The Part A/B utterance counts (223,884 / 96,000) are confirmed via a direct read of the dataset card (`zhaoxiaoxian/LIME-440K_CogAudio-LLM`); the exact column/field names for the text-identity grouping are not yet confirmed and must come from the same direct read, not assumed from the paper's prose.
- LIME is TTS-synthesized; a residual TTS-vs-spontaneous prosody gap is a known limitation, reported rather than hidden.
- The two framing citations (arXiv 2505.22483, 2602.23136) are now corroborated by independent search of their arXiv/ICML listing pages — titles, authors, venue, and core claims all match the prose above, no longer flagged. The one open item is the specific **+7.5% modal-accessibility** figure attributed to arXiv 2602.23136: a search summary did not surface that exact number, so it still needs a direct read of the paper text before submission. (The LIME-440K citation, arXiv 2606.06940, is confirmed directly from the arXiv listing page itself, author list and INTERSPEECH 2026 acceptance included.)

## Expected Contribution

Not beating SOTA on emotion accuracy. Rather: a clean, reproducible, single-GPU study that (1) measures modality collapse on a fixed ablation ruler, (2) applies mechanistically distinct interventions, and (3) compares coupled vs. decoupled speech under one language to directly test whether data-level and objective-level interventions are equivalent — a control absent from prior work, each of which establishes one intervention in isolation. Every claim ties to a re-runnable ablation rather than to the cited papers.

## Success Criterion

For each condition, re-running the silence-vs-audio ablation yields a measurable, reported shift; the coupled-vs-decoupled contrast yields an interpretable difference in collapse magnitude. A partial outcome on natural MELD (collapse reduced, not eliminated) is a valid result and the stated motivation for data-level decoupling.

## Future Work

The same evidence-grounded CoT mechanism — a model that states the acoustic cues behind its emotion judgment — could serve as a case-level interpretable layer atop existing classical pipelines in clinical speech assessment, complementing rather than competing with feature-based methods. Pursuing this in a UHR / clinical setting would require not only data access and ethics approval but genuine domain grounding in the clinical construct, which is a prerequisite to be built, not an asset already in hand. Out of scope here.

## Environment

All training/inference on the GPU cluster (H100). Login/transfer node for downloads (compute nodes offline); `$SCRATCH`, not `$HOME`, for the 52 GB LIME audio and HF caches.
