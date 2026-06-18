"""Prompt and chain-of-thought (CoT) target templates shared by the MELD and MMPsy loaders."""

SYSTEM_PROMPT = (
    "You are an assistant that listens to a short speech clip and reasons step by step "
    "about the speaker's state before giving a final judgment. Cite concrete cues from "
    "the audio (tone, pacing, word choice) in your reasoning, then give a one-line final "
    "answer."
)

USER_PROMPT_TEMPLATE = (
    "Listen to the audio clip. The spoken transcript is: \"{transcript}\".\n"
    "Think step by step about what the speaker's tone and delivery suggest, then give "
    "your final answer on the last line as \"{answer_key}: <value>\"."
)

# Audio-only variant: no transcript is provided, so the model has nothing to read and must
# rely on the audio. Used for the text-masking augmentation in MELDDataset that fights the
# text-dominance failure documented in RP.md "Preliminary Result".
USER_PROMPT_AUDIO_ONLY = (
    "Listen to the audio clip. No transcript is available.\n"
    "Think step by step about what the speaker's tone and delivery suggest, then give "
    "your final answer on the last line as \"{answer_key}: <value>\"."
)


def build_conversation(
    audio_path: str, transcript: str, answer_key: str, include_transcript: bool = True
) -> list[dict]:
    """Build a Qwen2-Audio-style chat conversation with one audio + text turn.

    `answer_key` controls the label name requested on the final line, e.g. "Emotion" for
    the MELD pipeline-validation task. When `include_transcript` is False the prompt omits
    the transcript entirely (audio-only task), so the model cannot read its way to the answer.
    """
    user_text = (
        USER_PROMPT_TEMPLATE.format(transcript=transcript, answer_key=answer_key)
        if include_transcript
        else USER_PROMPT_AUDIO_ONLY.format(answer_key=answer_key)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "audio", "audio_url": audio_path},
                {"type": "text", "text": user_text},
            ],
        },
    ]


def build_synthetic_cot_target(transcript: str, cues: list[str], answer_key: str, answer_value: str) -> str:
    """Build a templated CoT supervision target (the original Phase-1 version).

    There is no human-annotated rationale in MELD or MMPsy, so the SFT target reasoning is
    templated from the gold label and a handful of cue phrases rather than freely generated.
    This is a known simplification for the pipeline-validation phase, not a claim that the
    cues are causally verified against the audio — see RP.md, "Preliminary Result". The cue
    text here is a function of the label, so this target can be reproduced without listening;
    build_decoupled_cot_target is the audio-grounded replacement.
    """
    cue_text = "; ".join(cues) if cues else "the overall tone and pacing of the clip"
    reasoning = (
        f"The speaker says \"{transcript}\". Based on {cue_text}, the delivery is "
        f"consistent with {answer_value}."
    )
    return f"{reasoning}\n{answer_key}: {answer_value}"


# Bucket -> phrase vocabulary for verbalizing the real acoustic priors measured by
# scripts/extract_acoustic_priors.py. Kept here (not in the extractor) so the supervision
# wording lives next to the rest of the prompt templates.
_ACOUSTIC_PHRASES = {
    "pitch_var": {
        "low": "a steady, near-monotone pitch",
        "mid": "moderate pitch movement",
        "high": "wide, animated pitch swings",
    },
    "loudness_var": {
        "low": "fairly even loudness",
        "mid": "some variation in loudness",
        "high": "sharp swings in loudness",
    },
    "pace": {
        "low": "a slow, deliberate pace",
        "mid": "a steady conversational pace",
        "high": "a quick, packed pace",
    },
}


def acoustic_clause(acoustic: dict | None) -> str:
    """Turn the bucketed acoustic priors into a natural-language evidence clause."""
    parts = []
    for key in ("pitch_var", "loudness_var", "pace"):
        phrase = _ACOUSTIC_PHRASES.get(key, {}).get((acoustic or {}).get(key))
        if phrase:
            parts.append(phrase)
    if not parts:
        return "the overall tone and pacing of the clip"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def build_decoupled_cot_target(
    transcript: str,
    acoustic: dict | None,
    answer_key: str,
    answer_value: str,
    include_transcript: bool = True,
) -> str:
    """Audio-grounded CoT target: the reasoning cites REAL measured acoustic features.

    Unlike build_synthetic_cot_target, the "acoustic evidence" clause is built from quantities
    extracted from the waveform (scripts/extract_acoustic_priors.py), not from the gold label.
    Those facts are only knowable by listening, so the target is unreachable from the transcript
    alone -- the intended pressure against text dominance (RP.md "Preliminary Result"). When
    `include_transcript` is False (the text-masked augmentation), the words are not referenced.
    """
    cue = acoustic_clause(acoustic)
    if include_transcript:
        reasoning = (
            f"Acoustic evidence: the delivery has {cue}. Spoken words: \"{transcript}\". "
            f"Taking the delivery together with the words, the state is consistent with {answer_value}."
        )
    else:
        reasoning = (
            f"Acoustic evidence: the delivery has {cue}. Judging from the delivery alone, "
            f"the state is consistent with {answer_value}."
        )
    return f"{reasoning}\n{answer_key}: {answer_value}"
