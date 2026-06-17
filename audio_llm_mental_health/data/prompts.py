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


def build_conversation(audio_path: str, transcript: str, answer_key: str) -> list[dict]:
    """Build a Qwen2-Audio-style chat conversation with one audio + text turn.

    `answer_key` controls the label name requested on the final line, e.g. "Emotion" for
    the MELD pipeline-validation task.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "audio", "audio_url": audio_path},
                {
                    "type": "text",
                    "text": USER_PROMPT_TEMPLATE.format(
                        transcript=transcript, answer_key=answer_key
                    ),
                },
            ],
        },
    ]


def build_synthetic_cot_target(transcript: str, cues: list[str], answer_key: str, answer_value: str) -> str:
    """Build a templated CoT supervision target.

    There is no human-annotated rationale in MELD or MMPsy, so the SFT target reasoning is
    templated from the gold label and a handful of cue phrases rather than freely generated.
    This is a known simplification for the pipeline-validation phase, not a claim that the
    cues are causally verified against the audio — see RP.md, "Preliminary Result".
    """
    cue_text = "; ".join(cues) if cues else "the overall tone and pacing of the clip"
    reasoning = (
        f"The speaker says \"{transcript}\". Based on {cue_text}, the delivery is "
        f"consistent with {answer_value}."
    )
    return f"{reasoning}\n{answer_key}: {answer_value}"
