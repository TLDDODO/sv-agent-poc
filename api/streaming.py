"""Live progress for one query (M2): the same run as `webview.run_query`, but every step is
pushed as an event while it happens (Server-Sent Events on GET /api/run/stream).

Event order:  start -> (tool_call -> tool_result | resubmit_requested | debate_round /
debate_round_done ...)* -> [flag_paraphrase start/done] -> cost -> final.  `final.result` is the
exact dict POST /api/run returns. An `error` event ends a failed run instead of `final`.

Every event has `seq` and, for the timeline, `text` = {zh, en} in plain language. Tool results carry
their evidence rows (label live / cited / pending) computed by the same code as the final table.
"""
from __future__ import annotations
import json
import queue
import threading
from typing import Iterator

from agent import events
from agent.cases import Case
from . import webview
from .webview import T

_DOING = {
    "fetch_structures": T("正在 PDBe 里查这个蛋白已解出的实验结构", "Looking up experimentally solved structures in PDBe"),
    "search_literature": T("正在 PubMed 检索相关文献", "Searching PubMed for the relevant papers"),
    "get_expected_interface_region": T("正在查文献 / UniProt 预期的结合区域", "Checking where the literature / UniProt expects the binding region"),
    "get_md_interface_scores": T("正在读取分子动力学的接触数据(本地结果文件)", "Reading the molecular-dynamics contact data (local result file)"),
    "validate_residues": T("正在用 UniProt 序列核对残基编号", "Checking the residue numbering against the UniProt sequence"),
    "map_residues": T("正在把残基对应到结构域", "Mapping residues onto protein domains"),
    "list_interface_tools": T("正在查看有哪些预测工具可用", "Checking which prediction tools are available"),
    "get_tool_prediction": T("正在查某个预测工具的结果", "Asking a prediction tool for its result"),
    "convene_debate": T("正在召集辩论:MD 一方、文献 / NMR 一方,再由裁判评判", "Convening a debate: MD side, literature / NMR side, then a judge"),
    "submit_adjudication": T("正在提交结论", "Submitting its conclusion"),
}
_ROLE = {
    "md_advocate": (T("MD / 结构一方正在陈述理由", "The MD / structure advocate is making its case"),
                    T("MD / 结构一方陈述完毕", "The MD / structure advocate has spoken")),
    "nmr_advocate": (T("文献 / NMR 一方正在陈述理由", "The literature / NMR advocate is making its case"),
                     T("文献 / NMR 一方陈述完毕", "The literature / NMR advocate has spoken")),
    "judge": (T("裁判正在权衡两方(不宣布谁对,只评估矛盾并建议实验)",
                "The judge is weighing both sides (no winner is declared; it assesses the contradiction and recommends an experiment)"),
              T("裁判已给出评估", "The judge has given its assessment")),
}
NO_ROWS = T("这一步已完成。", "This step is done.")


def args_summary(args: dict, limit: int = 80) -> str:
    """Short, harmless summary of tool arguments: lists become counts, long text is cut."""
    parts = []
    for k, v in (args or {}).items():
        if isinstance(v, (list, tuple, dict)):
            parts.append(f"{k}: {len(v)} items")
        else:
            parts.append(f"{k}={str(v)[:40]}")
    text = ", ".join(parts)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def present(e: dict) -> dict | None:
    """Turn a raw run event into a timeline event (plain language, labelled evidence)."""
    t = e["type"]
    if t == "tool_call":
        name = e["tool"]
        return {"type": "tool_call", "tool": name, "args_summary": args_summary(e.get("args")),
                "text": _DOING.get(name, T(f"正在调用工具 {name}", f"Calling the tool {name}"))}
    if t == "tool_result":
        rows = webview._rows_for(e["tool"], e.get("args") or {}, e.get("result"))
        if rows:
            text = T("拿到的证据:" + ";".join(f"{r['item']['zh']}({r['label']})" for r in rows),
                     "Evidence obtained: " + "; ".join(f"{r['item']['en']} ({r['label']})" for r in rows))
        else:
            text = NO_ROWS
        return {"type": "tool_result", "tool": e["tool"], "rows": rows, "text": text}
    if t == "resubmit_requested":
        return {"type": t, "attempt": e["attempt"],
                "text": T("结论里没有残基列表,已退回让它重新提交",
                          "The conclusion had no residue list, so it was sent back to be submitted again")}
    if t in ("debate_round", "debate_round_done"):
        start, done = _ROLE[e["role"]]
        out = {"type": t, "round": e["round"], "role": e["role"], "text": start if t == "debate_round" else done}
        if t == "debate_round_done":
            out["excerpt"] = e.get("excerpt", "")           # the model's own words, untranslated
        return out
    if t == "flag_paraphrase":
        return {"type": t, "phase": e["phase"],
                "text": T("正在把它的提醒改写成通俗的话", "Rewording its cautions in plain language")
                if e["phase"] == "start" else T("提醒已改写完毕", "Cautions reworded")}
    return None


def stream_query(case: Case, max_steps: int = 12) -> Iterator[dict]:
    """Run the query in a worker thread and yield events as they arrive."""
    q: queue.Queue = queue.Queue()

    def sink(raw: dict) -> None:
        ev = present(raw)
        if ev is not None:
            q.put(ev)

    def worker() -> None:
        token = events.set_sink(sink)
        try:
            result = webview.run_query(case, max_steps=max_steps)
            q.put({"type": "cost", "usage": result["usage"],
                   "text": T("这次查询的耗时和成本", "Time and cost of this query")})
            q.put({"type": "final", "result": result, "text": T("完成", "Done")})
        except Exception as exc:                         # an upstream (LLM / network) failure
            q.put({"type": "error", "error": type(exc).__name__,
                   "text": T("查询失败:" + type(exc).__name__, "The query failed: " + type(exc).__name__)})
        finally:
            events.reset_sink(token)
            q.put(None)

    seq = 0
    yield {"seq": seq, "type": "start",
           "case": {"id": case.id, "name": f"{case.name_a} – {case.name_b}",
                    "uniprot_a": case.uniprot_a, "uniprot_b": case.uniprot_b},
           "text": T(f"开始调查 {case.name_a} 与 {case.name_b} 的结合界面",
                     f"Starting to investigate the {case.name_a} – {case.name_b} interface")}
    threading.Thread(target=worker, daemon=True).start()
    while True:
        ev = q.get()
        if ev is None:
            return
        seq += 1
        yield {"seq": seq, **ev}


def sse(ev: dict) -> str:
    return f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
