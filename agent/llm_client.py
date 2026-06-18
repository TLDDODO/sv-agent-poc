from __future__ import annotations
import os


def make_client():
    """OpenAI-compatible client pointed at DeepSeek (cheap). Set DEEPSEEK_API_KEY."""
    from openai import OpenAI
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(
            "Set DEEPSEEK_API_KEY (and optionally DEEPSEEK_BASE_URL / DEEPSEEK_MODEL).")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=key, base_url=base)


MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
