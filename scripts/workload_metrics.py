"""Compute per-query workload metrics from results/runs.jsonl and fold them into the
evaluation report.

    python scripts/workload_metrics.py [--out results]

Writes results/workload.json; if results/benchmark.json exists it is re-written with the
workload section attached and results/benchmark.md is re-rendered. Manual (human) time is not
measured and not estimated.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import benchmark, workload  # noqa: E402
from agent.cases import load_benchmark  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results")
    ap.add_argument("--log", default=None, help="run log (default: <out>/runs.jsonl)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    log = Path(args.log) if args.log else out / "runs.jsonl"
    data = workload.compute(workload.read_log(log), {c.id for c in load_benchmark()})
    out.mkdir(parents=True, exist_ok=True)
    (out / "workload.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("groups: " + ", ".join(f"{k} ({v['queries']} queries)" for k, v in data["groups"].items()))
    bj = out / "benchmark.json"
    if bj.exists():
        bench = json.loads(bj.read_text(encoding="utf-8"))
        for key in benchmark.ATTACHED:
            bench.pop(key, None)                       # write_outputs re-attaches the fresh files
        benchmark.write_outputs(bench, args.out)
        print(f"updated {args.out}/benchmark.json and benchmark.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
