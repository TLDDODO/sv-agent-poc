"""Fill the generated blocks of README.md and docs/business_case.md from results/*.json.

    python scripts/generate_docs.py           # rewrite the blocks
    python scripts/generate_docs.py --check   # exit 1 if either file is out of date

Only the text between `<!-- GENERATED:<name>:START -->` and `<!-- GENERATED:<name>:END -->`
is rewritten; every number in those blocks comes from results/benchmark.json (and its
error_injection section). Running the script twice gives no diff. Dry-run or BLOCKED
results are never turned into numbers.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL_NOTE = "Manual time was not measured"


def _load(root: Path) -> dict:
    try:
        return json.loads((root / "results" / "benchmark.json").read_text(encoding="utf-8"))
    except Exception:
        return {"status": "missing"}


def _live(data: dict) -> bool:
    return data.get("status") == "ok" and not data.get("dry_run")


def _f(x, fmt="{:.2f}"):
    return "n/a" if x is None else fmt.format(x)


def _cost(x):
    return "n/a" if x is None else f"${x:.4f}"


def _ei_line(data: dict) -> str:
    ei = data.get("error_injection") or {}
    if ei.get("status") != "ok":
        return "Error injection: no result yet."
    s = ei["summary"]
    return (f"Error injection (FAT10–MAD2): {s['caught']} of {s['injected']} injected errors caught "
            f"({s['intercept_rate']:.0%}); passed through {s['passed_through']}; inconclusive {s['inconclusive']}.")


# --- README block ---------------------------------------------------------------------
def readme_block(data: dict) -> str:
    if not _live(data):
        why = "dry run" if data.get("dry_run") else data.get("status")
        return (f"_No live benchmark results in `results/benchmark.json` ({why}); "
                "run `python scripts/run_benchmark.py` with `DEEPSEEK_API_KEY` set._")
    o = data["overall"]
    L = [f"Model `{data['model']}`, {data['runs_per_case']} run(s) per case and arm, generated "
         f"{data['generated_at']}. Score = mean of the two proteins' region hits "
         f"(recall ≥ {data['scoring']['recall_min']:.0%}, predicted length ≤ "
         f"{data['scoring']['max_span_ratio']:g}× the true span).", "",
         "| pair | truth PDB | agent | no-tool baseline |", "|---|---|---|---|"]
    for c in data["cases"]:
        L.append(f"| {c['pair']} | {c['ground_truth_pdb']} | {_f(c['agent']['mean_score'])} | "
                 f"{_f(c['baseline']['mean_score'])} |")
    L.append(f"| **overall** | | **{_f(o['agent']['mean_score'])}** | **{_f(o['baseline']['mean_score'])}** |")
    L += ["", _ei_line(data), "",
          "Full table (stability, latency, cost): [`results/benchmark.md`](results/benchmark.md)."]
    return "\n".join(L)


# --- business case block --------------------------------------------------------------
def _wl_row(label, g):
    return (f"| {label} | {g['queries']} | {_f(g['mean_tool_calls'], '{:.1f}')} | "
            f"{_f(g['mean_databases'], '{:.1f}')} | {_f(g['mean_data_api_calls'], '{:.1f}')} | "
            f"{_f(g['mean_llm_calls'], '{:.1f}')} | {_f(g['mean_records_processed'], '{:.0f}')} | "
            f"{_f(g['median_wall_clock_s'], '{:.1f}')} s | {_cost(g['mean_cost_usd'])} |")


def business_block(data: dict) -> str:
    if not _live(data):
        why = "dry run" if data.get("dry_run") else data.get("status")
        return (f"_`results/benchmark.json` has no live run results ({why}), so no numbers are filled in here. "
                "Run `python scripts/run_benchmark.py` first._")
    w = data.get("workload") or {}
    if w.get("status") != "ok" or not w.get("groups"):
        return ("_No workload metrics yet. Run `python scripts/workload_metrics.py` "
                "(it reads `results/runs.jsonl`)._")
    names = {"benchmark_agent": "Investigator agent (with tools, benchmark cases)",
             "benchmark_baseline": "No-tool baseline (same model answering directly)",
             "other_agent": "Investigator agent (non-benchmark: web app / CLI use)",
             "other_debate": "Debate (no benchmark case recorded: web app / CLI use)"}
    comp = w.get("log_composition") or {}
    L = [f"Source: `results/runs.jsonl`, aggregated by `scripts/workload_metrics.py` (`results/workload.json`); "
         f"model `{data['model']}`, price list checked {data['pricing_last_checked']}; prices come from a "
         "third-party price list, see `config/pricing.yaml`. The figures are per-query means (time is the "
         "median), counted by the program at run time, not estimated.", "",
         "| flow | queries | tool calls | databases reached | data API calls | model calls | records processed | time | cost |",
         "|---|---|---|---|---|---|---|---|---|"]
    for key, g in w["groups"].items():
        L.append(_wl_row(names.get(key, key), g))
    L += ["", "Definitions:",
          "- **Data API calls**: requests our code sent to external data sources (PDBe, UniProt, PubMed), "
          "counted when sent, failed ones included; a PDBe MCP query counts as one.",
          "- **Databases reached**: the number of external databases reached successfully at least once "
          "(the local MD result file is not a database).",
          "- **Records processed**: records returned by or checked against the data sources (PDBe entries, "
          "PubMed abstracts, UniProt annotations, residues checked), plus the residue rows read from the "
          "local MD result file.",
          f"- {w['excluded_lines_without_activity']} run-log lines written before the counters existed have "
          "no such fields; they are excluded and were not back-filled by guessing.",
          (f"- Log composition: {w['log_lines']} lines in all, of which {comp['benchmark_case_lines']} carry a "
           f"benchmark case id (the log does not record which program wrote them); the other "
           f"{comp['non_benchmark_lines']} carry no benchmark case id and are treated as non-benchmark queries "
           "run through the web app or the CLI (the log does not tell them apart). They are listed separately "
           "and are in no benchmark score.") if comp else "",
          "", "**" + MANUAL_NOTE + ".** No manual baseline was ever measured, so this document estimates neither "
          "manual time nor manual cost and cannot say how much the agent saves; the table above only describes "
          "the workload of the automated flow itself.", "",
          f"Accuracy on the same cases: agent {_f(data['overall']['agent']['mean_score'])}, no-tool baseline "
          f"{_f(data['overall']['baseline']['mean_score'])} (scoring rule in `docs/benchmark_design.md`; the "
          "baseline measures what the agent adds over the model \"reciting the answer\").", "", _ei_line(data)]
    return "\n".join(L)


# --- README "Key results" block (short version, for the top of the file) --------------
def key_results_block(data: dict) -> str:
    if not _live(data):
        why = "dry run" if data.get("dry_run") else data.get("status")
        return f"_No live results yet ({why}). Run `python scripts/run_benchmark.py`._"
    o = data["overall"]
    ei = data.get("error_injection") or {}
    w = data.get("workload") or {}
    g = (w.get("groups") or {}).get("benchmark_agent") if w.get("status") == "ok" else None
    L = ["| Metric | Value |", "|---|---|",
         f"| Benchmark accuracy — agent (with tools) | {_f(o['agent']['mean_score'])} |",
         f"| Benchmark accuracy — no-tool baseline | {_f(o['baseline']['mean_score'])} |"]
    if ei.get("status") == "ok":
        s = ei["summary"]
        L.append(f"| Injected errors caught | {s['caught']} / {s['injected']} ({s['intercept_rate']:.0%}) |")
    if g:
        L.append(f"| Time per query (median) | {_f(g['median_wall_clock_s'], '{:.1f}')} s |")
        L.append(f"| Cost per query (mean) | {_cost(g['mean_cost_usd'])} |")
    L.append("")
    L.append(f"{len(data['cases'])} protein pairs, {data['runs_per_case']} run(s) each, model `{data['model']}`. Full numbers, "
             "scoring rule and the training-data caveat for the baseline: "
             "[`results/benchmark.md`](results/benchmark.md), [`docs/benchmark_design.md`](docs/benchmark_design.md).")
    return "\n".join(L)


# (path, marker name, render fn); a path may appear more than once (README.md has two blocks).
BLOCKS = [
    ("README.md", "KEYRESULTS", key_results_block),
    ("README.md", "BENCHMARK", readme_block),
    ("docs/business_case.md", "BUSINESS", business_block),
]


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as fh:      # keep the file's own line endings
        return fh.read()


def _replace(text: str, name: str, body: str) -> str:
    eol = "\r\n" if "\r\n" in text else "\n"
    pat = re.compile(rf"(<!-- GENERATED:{name}:START -->\r?\n).*?(\r?\n<!-- GENERATED:{name}:END -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"missing GENERATED:{name} markers")
    return pat.sub(lambda m: m.group(1) + body.replace("\n", eol) + m.group(2), text)


def render_all(root: Path = ROOT) -> dict[str, str]:
    data = _load(root)
    out: dict[str, str] = {}
    for rel, name, fn in BLOCKS:
        if rel not in out:
            out[rel] = _read(root / rel)
        out[rel] = _replace(out[rel], name, fn(data))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    new = render_all()
    stale = [rel for rel, text in new.items() if _read(ROOT / rel) != text]
    if args.check:
        print("up to date" if not stale else "OUT OF DATE: " + ", ".join(stale))
        return 1 if stale else 0
    for rel in stale:
        with (ROOT / rel).open("w", encoding="utf-8", newline="") as fh:
            fh.write(new[rel])
    print("updated: " + (", ".join(stale) if stale else "nothing (already up to date)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
