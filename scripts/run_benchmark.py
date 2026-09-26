"""Run the benchmark: agent vs no-tool baseline.

    python scripts/run_benchmark.py --cases benchmark/ --runs 3          # live (needs DEEPSEEK_API_KEY)
    python scripts/run_benchmark.py --cases benchmark/ --dry-run         # fake client, plumbing only
    python scripts/run_benchmark.py --render-only                        # rebuild the .md from the .json

Writes results/benchmark.json and results/benchmark.md. Without a key the live run is
marked BLOCKED (no numbers are produced).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import benchmark  # noqa: E402
from agent.llm_client import MODEL  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default="benchmark/")
    ap.add_argument("--runs", type=int, default=None, help="runs per case and arm (default 3; 1 for --dry-run)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--out", default="results")
    args = ap.parse_args(argv)

    if args.render_only:
        data = json.loads((Path(args.out) / "benchmark.json").read_text(encoding="utf-8"))
        benchmark.write_outputs(data, args.out)
        print(f"re-rendered {args.out}/benchmark.md")
        return 0
    if not args.dry_run and not os.environ.get("DEEPSEEK_API_KEY"):
        benchmark.write_outputs(benchmark.blocked("DEEPSEEK_API_KEY is not set"), args.out)
        print("BLOCKED: DEEPSEEK_API_KEY is not set; no live run was made")
        return 0
    runs = args.runs or (1 if args.dry_run else 3)
    data = benchmark.run_benchmark(benchmark.load_cases(args.cases), runs, dry_run=args.dry_run,
                                   model=args.model, max_steps=args.max_steps)
    benchmark.write_outputs(data, args.out)
    print(f"wrote {args.out}/benchmark.json and {args.out}/benchmark.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
