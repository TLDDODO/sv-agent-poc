"""Per-query workload metrics, computed from the run log (results/runs.jsonl).

Each run-log line carries the measured `activity` block (see agent/metrics.py) plus tokens,
time, cost, LLM calls and the ordered tool list. This module only aggregates those lines;
it never estimates. Lines written before the activity fields existed are excluded and
counted, not guessed at. Manual (human) effort is not measured anywhere in this repo.
"""
from __future__ import annotations
import collections
import json
import statistics
from pathlib import Path


def read_log(path) -> list[dict]:
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.strip():
            out.append(json.loads(raw))
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _group(lines: list[dict]) -> dict:
    acts = [x["activity"] for x in lines]
    dbs = sorted({d for a in acts for d in a["databases"]})
    return {
        "queries": len(lines),
        "mean_tool_calls": _mean([len(x["tools"]) for x in lines]),
        "mean_databases": _mean([len(a["databases"]) for a in acts]),
        "databases_used": dbs,
        "mean_data_api_calls": _mean([a["data_api_calls"] for a in acts]),
        "mean_failed_data_api_calls": _mean([a["failed_calls"] for a in acts]),
        "mean_llm_calls": _mean([x["llm_calls"] for x in lines]),
        "mean_records_processed": _mean([a["records_processed"] for a in acts]),
        "median_wall_clock_s": statistics.median([x["wall_clock_s"] for x in lines]),
        "mean_cost_usd": _mean([x.get("cost_usd") for x in lines]),
        "mean_prompt_tokens": _mean([x["prompt_tokens"] for x in lines]),
        "mean_completion_tokens": _mean([x["completion_tokens"] for x in lines]),
        "mean_calls_by_database": {d: _mean([a["by_database"].get(d, {}).get("calls", 0) for a in acts])
                                   for d in dbs},
    }


def compute(lines: list[dict], benchmark_ids: set[str]) -> dict:
    with_act = [x for x in lines if "activity" in x]
    groups = {
        "benchmark_agent": [x for x in with_act if x["kind"] == "agent" and x.get("case") in benchmark_ids],
        "benchmark_baseline": [x for x in with_act if x["kind"] == "baseline" and x.get("case") in benchmark_ids],
        "other_agent": [x for x in with_act if x["kind"] == "agent" and x.get("case") not in benchmark_ids],
        "other_debate": [x for x in with_act if x["kind"] == "debate"],
    }
    bench = [x for x in lines if x.get("case") in benchmark_ids]
    # Lines are split by whether they carry a benchmark case id. The log does not record which program
    # wrote a line (the benchmark runner, the web app or the CLI).
    composition = {"benchmark_case_lines": len(bench),
                   "non_benchmark_lines": len(lines) - len(bench),
                   "non_benchmark_by_kind": dict(sorted(collections.Counter(
                       x["kind"] for x in lines if x.get("case") not in benchmark_ids).items()))}
    return {"status": "ok", "source": "results/runs.jsonl", "log_lines": len(lines),
            "log_composition": composition,
            "excluded_lines_without_activity": len(lines) - len(with_act),
            "groups": {k: _group(v) for k, v in groups.items() if v},
            "manual_time": "not measured"}
