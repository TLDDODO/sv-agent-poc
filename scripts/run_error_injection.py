"""Run the FAT10-MAD2 error-injection check (needs the network: UniProt) and fold the
intercept rate into the evaluation report.

    python scripts/run_error_injection.py [--out results]

Writes results/error_injection.json; if results/benchmark.json exists, it is re-written
with the error-injection section attached and results/benchmark.md is re-rendered.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import benchmark, error_injection  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = error_injection.run_error_injection()
    (out / "error_injection.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    print(f"error injection: {data['status']}")
    bj = out / "benchmark.json"
    if bj.exists():
        bench = json.loads(bj.read_text(encoding="utf-8"))
        bench.pop("error_injection", None)              # write_outputs re-attaches the fresh file
        benchmark.write_outputs(bench, args.out)
        print(f"updated {args.out}/benchmark.json and benchmark.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
