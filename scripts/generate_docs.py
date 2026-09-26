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
MANUAL_NOTE = "人工耗时未测量"


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
def _wl_row(label, g):
    return (f"| {label} | {g['queries']} | {_f(g['mean_tool_calls'], '{:.1f}')} | "
            f"{_f(g['mean_databases'], '{:.1f}')} | {_f(g['mean_data_api_calls'], '{:.1f}')} | "
            f"{_f(g['mean_llm_calls'], '{:.1f}')} | {_f(g['mean_records_processed'], '{:.0f}')} | "
            f"{_f(g['median_wall_clock_s'], '{:.1f}')} 秒 | {_cost(g['mean_cost_usd'])} |")


def business_block(data: dict) -> str:
    if not _live(data):
        why = "dry run" if data.get("dry_run") else data.get("status")
        return (f"_`results/benchmark.json` 没有真实运行结果({why}),所以这里不填数字。"
                "请先运行 `python scripts/run_benchmark.py`。_")
    w = data.get("workload") or {}
    if w.get("status") != "ok" or not w.get("groups"):
        return ("_还没有工作量指标。请运行 `python scripts/workload_metrics.py`(它读取 `results/runs.jsonl`)。_")
    names = {"benchmark_agent": "调查 agent(带工具,基准案例)", "benchmark_baseline": "无工具基线(同一模型直接回答)",
             "other_agent": "调查 agent(网页 / 命令行查询)"}
    L = [f"数据来源:`results/runs.jsonl` 经 `scripts/workload_metrics.py` 汇总(`results/workload.json`);"
         f"模型 `{data['model']}`,价格表核对日期 {data['pricing_last_checked']},价格来自第三方价格表,见 "
         "`config/pricing.yaml`。以下数字是每次查询的平均值(耗时为中位数),由程序在运行时计数,不是估计。", "",
         "| 流程 | 查询数 | 工具调用 | 访问的数据库 | 数据接口调用 | 模型调用 | 处理的记录 | 耗时 | 成本 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for key, g in w["groups"].items():
        L.append(_wl_row(names.get(key, key), g))
    L += ["", "口径:",
          "- **数据接口调用**:程序向外部数据源(PDBe、UniProt、PubMed)发出的请求次数,发出即计,失败的也算;"
          "PDBe 的 MCP 查询按一次计。",
          "- **访问的数据库**:至少成功访问过一次的外部数据库个数(本地 MD 结果文件不算数据库)。",
          "- **处理的记录**:数据源返回或被核对的记录数(PDBe 条目、PubMed 摘要、UniProt 注释、被核对的残基),"
          "加上从本地 MD 结果文件读到的残基行数。",
          f"- 运行日志里在计数功能加入之前写下的 {w['excluded_lines_without_activity']} 行没有这些字段,已排除,没有猜测补全。",
          "", "**" + MANUAL_NOTE + "。** 没有做过人工基线测量,本文不估计人工耗时和人工成本,因此也不能据此说 agent 节省了多少;"
          "上表只描述自动化流程本身的工作量。", "",
          f"同一批案例上的准确率:agent {_f(data['overall']['agent']['mean_score'])},无工具基线 "
          f"{_f(data['overall']['baseline']['mean_score'])}(评分规则见 `docs/benchmark_design.md`;基线用来衡量 "
          "agent 比\"模型自己背答案\"多带来了什么)。", "", _ei_line(data, zh=True)]
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
