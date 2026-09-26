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
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TBD = "TBD — 人工基线"


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


def _ei_line(data: dict, zh: bool) -> str:
    ei = data.get("error_injection") or {}
    if ei.get("status") != "ok":
        return "错误注入:尚无结果。" if zh else "Error injection: no result yet."
    s = ei["summary"]
    if zh:
        return (f"错误注入(FAT10–MAD2):{s['injected']} 个注入错误中拦截 {s['caught']} 个"
                f"({s['intercept_rate']:.0%});未被发现 {s['passed_through']} 个;无法判定 {s['inconclusive']} 个。")
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
    L += ["", _ei_line(data, zh=False), "",
          "Full table (stability, latency, cost): [`results/benchmark.md`](results/benchmark.md)."]
    return "\n".join(L)


# --- business case block --------------------------------------------------------------
def _runs(data: dict, arm: str) -> list[dict]:
    return [r for c in data["cases"] for r in c[arm]["runs"]]


def business_block(data: dict) -> str:
    if not _live(data):
        why = "dry run" if data.get("dry_run") else data.get("status")
        return (f"_`results/benchmark.json` 没有真实运行结果({why}),所以这里不填数字。"
                "请先运行 `python scripts/run_benchmark.py`。_")
    rows = []
    for arm, label in (("agent", "调查 agent(带工具)"), ("baseline", "无工具基线(同一模型直接回答)")):
        runs = _runs(data, arm)
        calls = [r["llm_calls"] for r in runs if r.get("llm_calls") is not None]
        costs = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
        lats = [r["latency_s"] for r in runs if r.get("latency_s") is not None]
        rows.append(f"| {label} | {len(runs)} | {_f(statistics.mean(calls) if calls else None, '{:.1f}')} | "
                    f"{_cost(statistics.mean(costs) if costs else None)} | "
                    f"{_f(statistics.median(lats) if lats else None, '{:.1f}')} 秒 |")
    total = sum(r["cost_usd"] for arm in ("agent", "baseline") for r in _runs(data, arm)
                if r.get("cost_usd") is not None)
    o = data["overall"]
    L = [f"数据来源:`results/benchmark.json`(模型 `{data['model']}`,生成于 {data['generated_at']},"
         f"价格表核对日期 {data['pricing_last_checked']},价格来自第三方价格表,见 `config/pricing.yaml`)。", "",
         "| 流程 | 运行次数 | 平均 LLM 调用次数 | 单次平均成本 | 单次耗时(中位数) |", "|---|---|---|---|---|"]
    L += rows
    L.append(f"| 人工流程 | {TBD} | {TBD} | {TBD} | {TBD} |")
    L += ["", f"整套基准评估(agent 与基线所有运行)的总成本:{_cost(total)}。", "",
          f"同一批案例上的准确率:agent {_f(o['agent']['mean_score'])},无工具基线 {_f(o['baseline']['mean_score'])}"
          "(评分规则见 `docs/benchmark_design.md`;基线用来衡量 agent 比"
          "\"模型自己背答案\"多带来了什么)。", "", _ei_line(data, zh=True)]
    return "\n".join(L)


BLOCKS = {
    "README.md": ("BENCHMARK", readme_block),
    "docs/business_case.md": ("BUSINESS", business_block),
}


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
    out = {}
    for rel, (name, fn) in BLOCKS.items():
        out[rel] = _replace(_read(root / rel), name, fn(data))
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
