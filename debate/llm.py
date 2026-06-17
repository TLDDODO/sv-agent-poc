from __future__ import annotations


class LLM:
    """Pluggable text generator.

    The decision logic (stances, conflicts, confidence) is computed
    deterministically from real numbers elsewhere; the LLM only phrases
    rationale. So the pipeline runs fully offline in 'mock' mode with no
    API key, and 'real' mode just produces richer prose.
    """

    def __init__(self, mode: str = "mock", model: str = "claude-sonnet-4-6"):
        self.mode = mode
        self.model = model

    def phrase(self, prompt: str, fallback: str) -> str:
        if self.mode == "mock":
            return fallback
        try:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
            msg = client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                b.text for b in msg.content if getattr(b, "type", "") == "text"
            ).strip()
            return text or fallback
        except Exception as exc:  # offline / no key / SDK missing -> stay graceful
            return f"{fallback}  [llm fallback: {type(exc).__name__}]"
