"""Data behind the single-page web client (GET /).

Everything shown to the user is derived from the agent's structured result and its tool
outputs; nothing is written by hand. Each evidence row carries one of three labels:

  live     the tool fetched or read real data during this query (PDBe, UniProt, PubMed, or the
           committed real MD result file). `source` says exactly which.
  cited    a published result or a verified snapshot quoted as-is, not re-derived now
  pending  no data (the tool has none, or the query failed). Never filled with a number.
"""
from __future__ import annotations

from agent import runlog
from agent.cases import Case, custom_case, default_case, find_case, load_benchmark
from agent.structures import NTERM_UBL_RANGE

CAVEAT_PAIR = "这是根据 UniProt 注释、文献和结构库信息得出的预测,不是实验测得的界面。"
CAVEAT_FAT10 = ("FAT10–MAD2 没有实验解出的复合物结构:如果 MD 结果与文献预期不一致,"
                "系统只报告矛盾,不判定哪一方正确。")
CAVEAT_HELD_OUT = "这个示例已隐藏该复合物的实验结构,系统是在“没看答案”的情况下预测的。"


def preset_cases() -> list[dict]:
    """The FAT10-MAD2 case study plus the benchmark pairs (their answers are never shown)."""
    out = []
    for c in [default_case(), *load_benchmark()]:
        out.append({"id": c.id, "name": f"{c.name_a} – {c.name_b}", "uniprot_a": c.uniprot_a,
                    "uniprot_b": c.uniprot_b,
                    "kind": "benchmark" if c.benchmark else "case_study"})
    return out


def resolve_case(case_id: str | None, uniprot_a: str | None, uniprot_b: str | None) -> Case:
    if case_id:
        try:
            return find_case(case_id)
        except KeyError as exc:
            raise ValueError(str(exc)) from None
    if uniprot_a and uniprot_b:
        # A typed pair that IS a benchmark pair (either order) runs as that benchmark case, so
        # its held-out experimental complex and papers stay hidden (leak filter + output guard).
        typed = {uniprot_a.strip().upper(), uniprot_b.strip().upper()}
        for c in load_benchmark():
            if {c.uniprot_a, c.uniprot_b} == typed:
                return c
        return custom_case(uniprot_a, uniprot_b)
    raise ValueError("choose a preset case, or give two UniProt accessions")


# --- evidence rows --------------------------------------------------------------------------
def _row(item, detail, label, source, records=None):
    return {"item": item, "detail": detail, "label": label, "source": source, "records": records}


def _rows_for(name: str, args: dict, out: dict) -> list[dict]:
    if not isinstance(out, dict):
        return []
    if name == "fetch_structures":
        n = len(out.get("structures", []))
        acc = args.get("uniprot", "")
        src = out.get("source")
        if src == "pdbe_mcp_live":
            ids = ", ".join(s["pdb_id"] for s in out["structures"][:5])
            return [_row(f"PDBe 结构 ({acc})", f"{n} 个条目" + (f":{ids}" if ids else ""), "live",
                         "PDBe 实时查询", n)]
        if src == "verified_snapshot":
            return [_row(f"PDBe 结构 ({acc})", f"{n} 个条目(已核实的快照,非本次查询)", "cited",
                         "已核实的 PDBe 快照", n)]
        return [_row(f"PDBe 结构 ({acc})", "没有取到数据", "pending", "PDBe", 0)]
    if name == "search_literature":
        if out.get("retrieved_live"):
            n = len(out.get("pmids", []))
            return [_row("PubMed 文献", f"{n} 篇摘要(PMID {', '.join(out.get('pmids', [])[:5])})", "live",
                         "PubMed 实时检索", n)]
        if out.get("fallback"):
            return [_row("文献结论", out["fallback"], "cited", "已发表文献(检索未成功,引用已知结论)", 0)]
        return [_row("PubMed 文献", "没有取到数据", "pending", "PubMed", 0)]
    if name == "get_expected_interface_region":
        if "proteins" in out:
            feats = sum(len(p["features"]) for p in out["proteins"].values())
            return [_row("UniProt 结构域 / 区域注释", f"{len(out['proteins'])} 个蛋白,共 {feats} 条注释",
                         "live", "UniProt 实时查询", feats)]
        if "residue_range" in out:
            lo, hi = out["residue_range"]
            return [_row("文献预期的结合区域", f"{out.get('expected_region')},第 {lo}–{hi} 位", "cited",
                         "文献 / NMR(不是本系统推导)", 1)]
        return [_row("结构域注释", "没有取到数据", "pending", "UniProt", 0)]
    if name == "get_md_interface_scores":
        if out.get("status") == "pending" or "occupancy" not in out:
            return [_row("分子动力学接触数据", "这一对蛋白没有 MD 数据", "pending", "—", 0)]
        n = len(out["occupancy"])
        return [_row("分子动力学接触数据", f"{n} 个残基的接触比例(100 ns 模拟)", "live",
                     "本地真实 MD 结果文件", n)]
    if name == "list_interface_tools":
        return [_row(f"{t} 预测", "尚无数据", "pending", "—", 0) for t in out.get("pending_no_data_yet", [])]
    if name == "validate_residues":
        if "error" in out:
            return [_row(f"残基核对 ({args.get('uniprot', '')})", "无法取得序列,残基未核对", "pending",
                         "UniProt", 0)]
        n, bad = len(out.get("validated", [])), out.get("n_mismatches", 0)
        return [_row(f"残基核对 ({out['uniprot']})",
                     f"{n} 个残基,其中 {bad} 个与真实序列不符", "live", "UniProt 实时序列", n)]
    return []


def evidence_rows(transcript: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for step in transcript:
        for a in step.get("actions", []):
            for r in _rows_for(a["tool"], a.get("args") or {}, a.get("result")):
                key = (r["item"], r["detail"], r["label"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows


# --- plain-language conclusion --------------------------------------------------------------
def _span(regions, acc):
    xs = [(int(r["start"]), int(r["end"])) for r in regions or [] if r.get("uniprot") == acc]
    return (min(a for a, _ in xs), max(b for _, b in xs)) if xs else None


def conclusion(case: Case, result: dict | None) -> dict:
    result = result or {}
    flags = [str(f) for f in (result.get("flags") or [])]
    if "predicted_regions" in result:
        parts = []
        for acc, name in ((case.uniprot_a, case.name_a), (case.uniprot_b, case.name_b)):
            sp = _span(result["predicted_regions"], acc)
            parts.append(f"{name} 上大致在第 {sp[0]}–{sp[1]} 位氨基酸" if sp else f"{name} 上没有给出区域")
        headline = "系统预测,两个蛋白的结合区域:" + ";".join(parts) + "。"
        caveat = CAVEAT_PAIR + (CAVEAT_HELD_OUT if case.benchmark else "")
    elif "consensus_interface" in result:
        core = ", ".join(result.get("consensus_interface") or []) or "没有"
        lo, hi = NTERM_UBL_RANGE
        headline = (f"系统给出的 FAT10 界面残基(依据分子动力学接触数据,由系统综合判断):{core}。"
                    f"注意:文献 / NMR 预期的结合区域是 FAT10 的第 {lo}–{hi} 位(引用,不是本系统推导),"
                    f"两者是否一致见下面的“需要留意”。")
        caveat = CAVEAT_FAT10
    else:
        headline = "系统没有给出结构化结论。"
        caveat = CAVEAT_PAIR
    points = []
    if isinstance(result.get("confidence"), (int, float)):
        points.append(f"系统自评的把握程度:{result['confidence']}(0 表示没把握,1 表示很有把握)。")
    return {"headline": headline, "points": points, "flags": flags, "caveat": caveat,
            "details": result.get("reasoning") or result.get("final_text")}


# --- one query ------------------------------------------------------------------------------
def run_query(case: Case, max_steps: int = 12) -> dict:
    from agent.run_agent import run   # lazy: no LLM client is built until here
    runlog.LAST_RECORD.set(None)
    result, transcript = run(case.goal, max_steps=max_steps, verbose=False, case=case)
    rec = runlog.LAST_RECORD.get() or {}
    return {
        "case": {"id": case.id, "name": f"{case.name_a} – {case.name_b}",
                 "uniprot_a": case.uniprot_a, "uniprot_b": case.uniprot_b},
        "conclusion": conclusion(case, result),
        "evidence": evidence_rows(transcript),
        "usage": {"seconds": rec.get("wall_clock_s"), "cost_usd": rec.get("cost_usd"),
                  "llm_calls": rec.get("llm_calls"), "prompt_tokens": rec.get("prompt_tokens"),
                  "completion_tokens": rec.get("completion_tokens"), "model": rec.get("model"),
                  "pricing_last_checked": rec.get("pricing_last_checked")},
        "steps": [{"tool": a["tool"], "args": a.get("args")} for s in transcript for a in s["actions"]],
    }
