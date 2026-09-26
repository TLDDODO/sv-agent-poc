"""Benchmark runner: agent vs no-tool baseline on the benchmark pairs.

`run_benchmark()` returns the data written to results/benchmark.json; `render_markdown()`
turns that JSON (and only that JSON) into results/benchmark.md. Latency and cost come
from the run-log lines (results/runs.jsonl) that each run appends (S3).

--dry-run uses a scripted fake client: it exercises the plumbing only. Its predictions
are meaningless placeholders by construction, so dry-run scores are NOT accuracy and
the output says so.
"""
from __future__ import annotations
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import baseline as baseline_mod
from . import run_agent, scoring
from .cases import Case, load_case
from .llm_client import MODEL
from .runlog import load_pricing


def load_cases(folder) -> list[Case]:
    return [load_case(p) for p in sorted(Path(folder).glob("*.yaml"))]


# --- dry-run fake ---------------------------------------------------------------------
def _fake_clients(case: Case):
    """Scripted stand-ins. The placeholder prediction (residues 1-10) is fixed and blind
    to the ground truth, so a dry run cannot look like a real result."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from fakes import FakeClient
    regions = [{"uniprot": case.uniprot_a, "start": 1, "end": 10},
               {"uniprot": case.uniprot_b, "start": 1, "end": 10}]
    agent = FakeClient([
        lambda m: ("Check for MD evidence.", [("get_md_interface_scores", {})]),
        lambda m: ("Submit placeholder.", [("submit_adjudication", {
            "consensus_interface": [], "disputed": [], "confidence": 0.0,
            "reasoning": "dry run placeholder", "predicted_regions": regions})]),
    ])
    base = FakeClient([lambda m: (json.dumps({"regions": regions, "confidence": 0.0}), [])])
    return agent, base


# --- one run ----------------------------------------------------------------------------
def _new_log_lines(path: Path, before: int) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[before:]
        return [json.loads(x) for x in lines]
    except Exception:
        return []


def _log_len(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def _one(arm: str, case: Case, model: str, max_steps: int, log_path: Path, dry_run: bool) -> dict:
    truth = case.ground_truth["interface_residues"]
    before = _log_len(log_path)
    rec = {"arm": arm, "error": None, "predicted_regions": None}
    saved = (run_agent.make_client, baseline_mod.make_client)
    try:
        if dry_run:
            agent_c, base_c = _fake_clients(case)
            run_agent.make_client = lambda: agent_c
            baseline_mod.make_client = lambda: base_c
        if arm == "agent":
            result, _ = run_agent.run(case.goal, model=model, max_steps=max_steps,
                                      verbose=False, case=case)
        else:
            result, _ = baseline_mod.run_baseline(case, model=model)
        regions = (result or {}).get("predicted_regions")
        rec["predicted_regions"] = regions
        if regions is None:
            rec["error"] = "no predicted_regions submitted"
    except Exception as exc:                       # an API/network failure is a failed run, not hidden
        rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        run_agent.make_client, baseline_mod.make_client = saved
    s = scoring.score_case(rec["predicted_regions"], truth)
    rec.update(score=s["score"], per_protein=s["per_protein"])
    lines = [x for x in _new_log_lines(log_path, before) if x.get("kind") == arm]
    line = lines[-1] if lines else {}
    rec.update(latency_s=line.get("wall_clock_s"), cost_usd=line.get("cost_usd"),
               llm_calls=line.get("llm_calls"), tools=line.get("tools") if arm == "agent" else [])
    return rec


# --- aggregation ------------------------------------------------------------------------
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _summarise(runs: list[dict]) -> dict:
    hits = [tuple(sorted((a, p["hit"]) for a, p in r["per_protein"].items())) for r in runs]
    modal = Counter(hits).most_common(1)[0][1] if hits else 0
    return {"n_runs": len(runs),
            "n_errors": sum(1 for r in runs if r["error"]),
            "mean_score": _mean([r["score"] for r in runs]),
            "protein_hits": sum(p["hit"] for r in runs for p in r["per_protein"].values()),
            "protein_total": sum(len(r["per_protein"]) for r in runs),
            "stability": modal / len(runs) if runs else None,
            "median_latency_s": _median([r["latency_s"] for r in runs]),
            "mean_cost_usd": _mean([r["cost_usd"] for r in runs])}


def _case_block(case: Case, runs: dict) -> dict:
    return {"id": case.id, "pair": f"{case.name_a}-{case.name_b}",
            "uniprot": [case.uniprot_a, case.uniprot_b],
            "ground_truth_pdb": case.ground_truth["pdb"],
            "agent": {**_summarise(runs["agent"]), "runs": runs["agent"]},
            "baseline": {**_summarise(runs["baseline"]), "runs": runs["baseline"]}}


def run_benchmark(cases: list[Case], n_runs: int, dry_run: bool = False, model: str = MODEL,
                  max_steps: int = 12, log_path: str | Path | None = None) -> dict:
    tmp = None
    if dry_run and log_path is None:               # dry runs never touch results/runs.jsonl
        tmp = tempfile.TemporaryDirectory()
        log_path = Path(tmp.name) / "runs.jsonl"
    log_path = Path(log_path or os.environ.get("RUNLOG_PATH", "results/runs.jsonl"))
    prev_env = os.environ.get("RUNLOG_PATH")
    os.environ["RUNLOG_PATH"] = str(log_path)
    out_cases = []
    try:
        for case in cases:
            runs = {"agent": [], "baseline": []}
            for i in range(n_runs):
                for arm in ("agent", "baseline"):
                    r = _one(arm, case, model, max_steps, log_path, dry_run)
                    r["run"] = i + 1
                    runs[arm].append(r)
            out_cases.append(_case_block(case, runs))
    finally:
        if prev_env is None:
            os.environ.pop("RUNLOG_PATH", None)
        else:
            os.environ["RUNLOG_PATH"] = prev_env
    overall = {}
    for arm in ("agent", "baseline"):
        allruns = [r for c in out_cases for r in c[arm]["runs"]]
        s = _summarise(allruns)
        s["stability"] = _mean([c[arm]["stability"] for c in out_cases])
        overall[arm] = s
    if tmp:
        tmp.cleanup()
    try:
        pricing_checked = load_pricing().get("last_checked")
    except Exception:
        pricing_checked = None
    return {"status": "ok", "dry_run": dry_run, "model": model, "runs_per_case": n_runs,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scoring": {"recall_min": scoring.RECALL_MIN, "max_span_ratio": scoring.MAX_SPAN_RATIO},
            "pricing_last_checked": pricing_checked, "cases": out_cases, "overall": overall}


def blocked(reason: str) -> dict:
    return {"status": "BLOCKED", "reason": reason, "dry_run": False}


# --- report (reads only the JSON) --------------------------------------------------------
def _f(x, fmt="{:.2f}", none="n/a"):
    return none if x is None else fmt.format(x)


def _cost(x):
    return "n/a" if x is None else f"${x:.4f}"


def _row(name, pair, gt, a, b):
    hits = lambda s: f"{s['protein_hits']}/{s['protein_total']}"
    return (f"| {name} | {pair} | {gt} | {_f(a['mean_score'])} | {_f(b['mean_score'])} | "
            f"{hits(a)} | {hits(b)} | {_f(a['stability'])} / {_f(b['stability'])} | "
            f"{_f(a['median_latency_s'], '{:.1f}')} / {_f(b['median_latency_s'], '{:.1f}')} | "
            f"{_cost(a['mean_cost_usd'])} / {_cost(b['mean_cost_usd'])} |")


def render_markdown(data: dict) -> str:
    if data.get("status") != "ok":
        return (f"# Benchmark results\n\n**{data.get('status')}** — {data.get('reason', '')}\n\n"
                "No numbers were produced.\n")
    sc = data["scoring"]
    L = ["# Benchmark results: agent vs no-tool baseline", ""]
    if data["dry_run"]:
        L += ["> **DRY RUN — plumbing check only.** The fake client submits a fixed placeholder "
              "prediction that ignores the evidence, so the scores below are NOT accuracy.", ""]
    L += [f"Model `{data['model']}`; {data['runs_per_case']} run(s) per case and arm; generated "
          f"{data['generated_at']}; prices last checked {data['pricing_last_checked']}.", "",
          "| case | pair | truth PDB | agent score | baseline score | agent hits | baseline hits | "
          "stability (agent / baseline) | median latency s (agent / baseline) | "
          "mean cost (agent / baseline) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for c in data["cases"]:
        L.append(_row(c["id"], c["pair"], c["ground_truth_pdb"], c["agent"], c["baseline"]))
    o = data["overall"]
    L.append(_row("**overall**", "all pairs", "-", o["agent"], o["baseline"]))
    diff = None
    if o["agent"]["mean_score"] is not None and o["baseline"]["mean_score"] is not None:
        diff = o["agent"]["mean_score"] - o["baseline"]["mean_score"]
    L += ["", f"Overall accuracy: agent {_f(o['agent']['mean_score'])}, baseline "
          f"{_f(o['baseline']['mean_score'])}; agent minus baseline {_f(diff, '{:+.2f}')}. "
          f"Failed runs (counted as misses): agent {o['agent']['n_errors']}, "
          f"baseline {o['baseline']['n_errors']}.", "",
          "## How to read this", "",
          f"- **Scoring** (docs/benchmark_design.md, section 4): a protein is a hit when the predicted "
          f"region covers at least {sc['recall_min']:.0%} of its true interface residues and is at most "
          f"{sc['max_span_ratio']:g} times the true span; a case scores the mean of its two proteins. "
          "\"hits\" counts protein-level hits over all runs.",
          "- **Baseline** = the same model with no tools, answering from its own knowledge. The model "
          "may have seen these classic complexes in training, so the baseline is a measure of how much "
          "the model can recite; the difference between agent and baseline is what the tools add over "
          "\"the model remembering the answer\". A baseline that scores as well as the agent means the "
          "tools added nothing measurable on these cases.",
          f"- **Small sample**: {len(data['cases'])} pairs, {data['runs_per_case']} run(s) each. Differences "
          "are indicative, not statistically established.",
          "- **Leakage**: the agent never sees any experimental complex of the pair, nor its papers "
          "(docs/benchmark_design.md, section 5). The baseline gets only names and accessions, so "
          "training-data memory is its only source.",
          "- Latency and cost come from the run logs in results/runs.jsonl; costs use "
          "config/pricing.yaml (third-party price map, see its source note).", ""]
    return "\n".join(L)


def write_outputs(data: dict, out_dir="results") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "benchmark.md").write_text(render_markdown(data), encoding="utf-8")
