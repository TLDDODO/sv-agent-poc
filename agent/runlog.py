"""Run logging: every agent / debate run appends one JSON line to results/runs.jsonl.

Each line: timestamp, kind, model, goal, number of LLM calls, prompt / completion
tokens (and cache-hit tokens when the API reports them), wall-clock seconds, the
ordered tool list, the verdict, and the cost from config/pricing.yaml.

Set RUNLOG_PATH to write elsewhere (the tests do). A logging failure never breaks
a run; it is reported on stderr instead.
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PRICING_PATH = Path(__file__).resolve().parent.parent / "config" / "pricing.yaml"
DEFAULT_LOG = "results/runs.jsonl"


def load_pricing(path: Path = PRICING_PATH) -> dict:
    """pricing.yaml is written as JSON (valid YAML), so the stdlib can read it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int,
             cache_hit_tokens: int = 0, pricing: dict | None = None):
    """Cost in USD, or None when the model has no listed price."""
    try:
        pricing = pricing if pricing is not None else load_pricing()
        p = pricing["models"][model]
    except Exception:
        return None
    hit = cache_hit_tokens or 0
    miss = max(prompt_tokens - hit, 0)
    hit_price = p["input_cache_hit"] if p.get("input_cache_hit") is not None else p["input_cache_miss"]
    return (miss * p["input_cache_miss"] + hit * hit_price
            + completion_tokens * p["output"]) / 1_000_000


class RunRecorder:
    def __init__(self, kind: str, model: str, goal: str, case_id: str | None = None):
        self.kind, self.model, self.goal, self.case_id = kind, model, goal, case_id
        self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._t0 = time.perf_counter()
        self.llm_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_hit_tokens = 0
        self.tools: list[str] = []

    def llm(self, response) -> None:
        self.llm_calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            self.cache_hit_tokens += getattr(usage, "prompt_cache_hit_tokens", 0) or 0

    def tool(self, name: str) -> None:
        self.tools.append(name)

    def record(self, verdict) -> dict:
        pricing = None
        try:
            pricing = load_pricing()
        except Exception:
            pass
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "model": self.model,
            "goal": self.goal,
            "case": self.case_id,
            "llm_calls": self.llm_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "wall_clock_s": round(time.perf_counter() - self._t0, 3),
            "tools": list(self.tools),
            "verdict": verdict,
            "cost_usd": cost_usd(self.model, self.prompt_tokens, self.completion_tokens,
                                 self.cache_hit_tokens, pricing),
            "pricing_last_checked": (pricing or {}).get("last_checked"),
        }

    def finish(self, verdict) -> dict | None:
        try:
            line = self.record(verdict)
            path = Path(os.environ.get("RUNLOG_PATH", DEFAULT_LOG))
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
            return line
        except Exception as exc:
            print(f"[runlog] could not write run log: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return None
