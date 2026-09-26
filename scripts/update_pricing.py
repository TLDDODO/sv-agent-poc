#!/usr/bin/env python3
"""Regenerate config/pricing.yaml (USD per 1M tokens per model) from a live source.

Source: the LiteLLM community price map (third-party). The official DeepSeek pricing
page is also requested, and whether it was reachable is recorded, but prices are not
parsed from its HTML — compare them by hand before trusting a cost figure.
Numbers are converted from USD/token and written by this script, never typed by hand.

The file is written as JSON, which is valid YAML, so it loads with the standard
library (no PyYAML needed at runtime).

    python scripts/update_pricing.py
"""
from __future__ import annotations
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = ("https://raw.githubusercontent.com/BerriAI/litellm/main/"
              "model_prices_and_context_window.json")
OFFICIAL_URL = "https://api-docs.deepseek.com/quick_start/pricing"
MODELS = ["deepseek-chat", "deepseek-reasoner"]
OUT = Path(__file__).resolve().parent.parent / "config" / "pricing.yaml"


def _per_million(per_token):
    return None if per_token is None else round(per_token * 1_000_000, 6)


def _official_status() -> str:
    try:
        with urllib.request.urlopen(OFFICIAL_URL, timeout=20) as r:
            return f"reachable (HTTP {r.status}); prices not parsed from it — compare by hand"
    except Exception as exc:
        return f"unreachable when checked ({type(exc).__name__}: {exc})"


def main() -> None:
    checked = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as r:
        raw = r.read()
    data = json.loads(raw)

    models = {}
    for m in MODELS:
        key = f"deepseek/{m}"
        entry = data[key]
        models[m] = {
            "input_cache_miss": _per_million(entry.get("input_cost_per_token")),
            "input_cache_hit": _per_million(entry.get("cache_read_input_token_cost")),
            "output": _per_million(entry.get("output_cost_per_token")),
            "source_key": key,
        }

    doc = {
        "_format": "JSON, which is valid YAML; kept as JSON so it loads with the standard library",
        "_generated_by": "scripts/update_pricing.py — do not edit numbers by hand",
        "unit": "USD per 1M tokens",
        "last_checked": checked,
        "source_url": SOURCE_URL,
        "source_type": "third-party community price map (LiteLLM), not the official DeepSeek page",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "official_page": OFFICIAL_URL,
        "official_page_status": _official_status(),
        "models": models,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE {OUT}")
    print(json.dumps(models, indent=2))


if __name__ == "__main__":
    main()
