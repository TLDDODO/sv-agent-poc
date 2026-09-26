"""Data behind the single-page web client (GET /).

Everything shown to the user is derived from the agent's structured result and its tool
outputs; nothing is written by hand. Each evidence row carries one of three labels:

  live     the tool fetched or read real data during this query (PDBe, UniProt, PubMed, or the
           committed real MD result file). `source` says exactly which.
  cited    a published result or a verified snapshot quoted as-is, not re-derived now
  pending  no data (the tool has none, or the query failed). Never filled with a number.

Every user-facing sentence is returned in both languages as {"zh": ..., "en": ...}, so the page
can switch language without running the (slow, paid) query again. The agent's own free text
(its explanation and the raw flag wording) is passed through untranslated, under "technical
details".
"""
from __future__ import annotations
import json
import re

from agent import runlog
from agent.cases import Case, custom_case, default_case, find_case, load_benchmark
from agent.structures import NTERM_UBL_RANGE
from analysis.adjudicate_md import INTERFACE_CUTOFF


def T(zh: str, en: str) -> dict:
    return {"zh": zh, "en": en}


CAVEAT_PAIR = T("这是根据 UniProt 注释、文献和结构库信息得出的预测,不是实验测得的界面。",
                "This is a prediction from UniProt annotations, literature and structure databases, "
                "not an experimentally measured interface.")
CAVEAT_FAT10 = T("FAT10–MAD2 没有实验解出的复合物结构:如果 MD 结果与文献预期不一致,"
                 "系统只报告矛盾,不判定哪一方正确。",
                 "There is no experimentally solved FAT10–MAD2 complex: if the MD result and the "
                 "literature expectation disagree, the system only reports the contradiction and "
                 "does not decide which side is right.")
CAVEAT_HELD_OUT = T("这个示例已隐藏该复合物的实验结构,系统是在“没看答案”的情况下预测的。",
                    "For this example the experimental structure of the complex is hidden, so the "
                    "system predicted without seeing the answer.")


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
NO_DATA = T("没有取到数据", "No data retrieved")


def _row(item, detail, label, source, records=None):
    return {"item": item, "detail": detail, "label": label, "source": source, "records": records}


def _rows_for(name: str, args: dict, out: dict) -> list[dict]:
    if not isinstance(out, dict):
        return []
    if name == "fetch_structures":
        n = len(out.get("structures", []))
        acc = args.get("uniprot", "")
        item = T(f"PDBe 结构 ({acc})", f"PDBe structures ({acc})")
        src = out.get("source")
        if src == "pdbe_mcp_live":
            ids = ", ".join(s["pdb_id"] for s in out["structures"][:5])
            return [_row(item, T(f"{n} 个条目" + (f":{ids}" if ids else ""),
                                 f"{n} entries" + (f": {ids}" if ids else "")),
                         "live", T("PDBe 实时查询", "PDBe live query"), n)]
        if src == "verified_snapshot":
            return [_row(item, T(f"{n} 个条目(已核实的快照,非本次查询)",
                                 f"{n} entries (verified snapshot, not from this query)"),
                         "cited", T("已核实的 PDBe 快照", "Verified PDBe snapshot"), n)]
        return [_row(item, NO_DATA, "pending", T("PDBe", "PDBe"), 0)]
    if name == "search_literature":
        if out.get("retrieved_live"):
            pm = out.get("pmids", [])
            n = len(pm)
            return [_row(T("PubMed 文献", "PubMed literature"),
                         T(f"{n} 篇摘要(PMID {', '.join(pm[:5])})", f"{n} abstracts (PMID {', '.join(pm[:5])})"),
                         "live", T("PubMed 实时检索", "PubMed live search"), n)]
        if out.get("fallback"):
            return [_row(T("文献结论", "Literature result"), T(out["fallback"], out["fallback"]), "cited",
                         T("已发表文献(检索未成功,引用已知结论)",
                           "Published literature (search failed; quoting the known result)"), 0)]
        return [_row(T("PubMed 文献", "PubMed literature"), NO_DATA, "pending", T("PubMed", "PubMed"), 0)]
    if name == "get_expected_interface_region":
        if "proteins" in out:
            feats = sum(len(p["features"]) for p in out["proteins"].values())
            k = len(out["proteins"])
            return [_row(T("UniProt 结构域 / 区域注释", "UniProt domain / region annotations"),
                         T(f"{k} 个蛋白,共 {feats} 条注释", f"{k} proteins, {feats} annotations"),
                         "live", T("UniProt 实时查询", "UniProt live query"), feats)]
        if "residue_range" in out:
            lo, hi = out["residue_range"]
            reg = out.get("expected_region")
            return [_row(T("文献预期的结合区域", "Literature-expected binding region"),
                         T(f"{reg},第 {lo}–{hi} 位", f"{reg}, residues {lo}–{hi}"), "cited",
                         T("文献 / NMR(不是本系统推导)", "Literature / NMR (not derived by this system)"), 1)]
        return [_row(T("结构域注释", "Domain annotations"), NO_DATA, "pending", T("UniProt", "UniProt"), 0)]
    if name == "get_md_interface_scores":
        item = T("分子动力学接触数据", "Molecular-dynamics contact data")
        if out.get("status") == "pending" or "occupancy" not in out:
            return [_row(item, T("这一对蛋白没有 MD 数据", "No MD data exists for this protein pair"),
                         "pending", T("—", "—"), 0)]
        n = len(out["occupancy"])
        return [_row(item, T(f"{n} 个残基的接触比例(100 ns 模拟)",
                             f"contact fractions for {n} residues (100 ns simulation)"),
                     "live", T("本地真实 MD 结果文件", "Local real MD result file"), n)]
    if name == "list_interface_tools":
        return [_row(T(f"{t} 预测", f"{t} prediction"), T("尚无数据", "No data yet"), "pending",
                     T("—", "—"), 0) for t in out.get("pending_no_data_yet", [])]
    if name == "validate_residues":
        acc = out.get("uniprot") or args.get("uniprot", "")
        item = T(f"残基核对 ({acc})", f"Residue check ({acc})")
        if "error" in out:
            return [_row(item, T("无法取得序列,残基未核对",
                                 "Could not fetch the sequence; residues were not checked"),
                         "pending", T("UniProt", "UniProt"), 0)]
        n, bad = len(out.get("validated", [])), out.get("n_mismatches", 0)
        return [_row(item, T(f"{n} 个残基,其中 {bad} 个与真实序列不符",
                             f"{n} residues, {bad} of which do not match the real sequence"),
                     "live", T("UniProt 实时序列", "UniProt live sequence"), n)]
    return []


def evidence_rows(transcript: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for step in transcript:
        for a in step.get("actions", []):
            for r in _rows_for(a["tool"], a.get("args") or {}, a.get("result")):
                key = (r["item"]["zh"], r["detail"]["zh"], r["label"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows


# --- points to watch --------------------------------------------------------------------------
# (a) findings: computed by code from the tool outputs (exact, no free text is interpreted);
# (b) the agent's own flags: free text, paraphrased by the model with a deterministic guard.
FLAG_FALLBACK = T("系统提出了一条提醒,建议人工确认(原文见“技术细节”)。",
                  "The system raised a caution that a person should check (original wording under “Technical details”).")
SOURCE_OF = {"fetch_structures": "PDBe", "search_literature": "PubMed",
             "get_expected_interface_region": "UniProt", "validate_residues": "UniProt"}


def _results(transcript, name):
    return [(a.get("args") or {}, a.get("result")) for s in transcript for a in s.get("actions", [])
            if a["tool"] == name and isinstance(a.get("result"), dict)]


def _num(label) -> int | None:
    m = re.search(r"\d+", str(label))
    return int(m.group()) if m else None


def findings(case: Case, transcript: list[dict]) -> list[dict]:
    """Points to watch that follow from the tool outputs themselves. Each has a plain sentence in
    both languages and `basis`, the numbers it was computed from."""
    out = []
    md = next((r for _, r in reversed(_results(transcript, "get_md_interface_scores"))), None)
    exp = next((r for _, r in reversed(_results(transcript, "get_expected_interface_region"))), None)
    # the FAT10-MAD2 contradiction: MD contact residues versus the literature-expected region
    if not case.generic and md and "occupancy" in md and exp and "residue_range" in exp:
        lo, hi = exp["residue_range"]
        core = sorted((r for r, v in md["occupancy"].items() if v >= INTERFACE_CUTOFF), key=residue_sort_key)
        outside = [r for r in core if _num(r) is not None and not lo <= _num(r) <= hi]
        if core:
            nums = [_num(r) for r in core if _num(r) is not None]
            span = f"{min(nums)}–{max(nums)}"
            names = ", ".join(core)
            basis = (f"MD contact fraction >= {INTERFACE_CUTOFF}: {names}; literature-expected region {lo}–{hi}; "
                     f"{len(outside)} of {len(core)} outside it")
            if outside:
                which_zh = "全部" if len(outside) == len(core) else f"其中 {len(outside)} 个"
                which_en = "all of them" if len(outside) == len(core) else f"{len(outside)} of them"
                out.append({"plain": T(
                    f"分子动力学里稳定接触的 FAT10 残基({names},位于第 {span} 位),{which_zh}在文献预期的第 {lo}–{hi} 位之外:"
                    f"两者不一致。系统只报告这个矛盾,不判断哪一方正确。",
                    f"The FAT10 residues in stable contact in the molecular dynamics ({names}, at positions {span}): "
                    f"{which_en} lie outside the literature-expected region (residues {lo}–{hi}), so the two disagree. "
                    f"The system only reports this contradiction and does not say which side is right."), "basis": basis})
            else:
                out.append({"plain": T(
                    f"分子动力学里稳定接触的 FAT10 残基({names})都在文献预期的第 {lo}–{hi} 位之内,两者一致。",
                    f"The FAT10 residues in stable contact in the molecular dynamics ({names}) all lie inside the "
                    f"literature-expected region (residues {lo}–{hi}); the two agree."), "basis": basis})
    if md is not None and (md.get("status") == "pending" or "occupancy" not in md):
        out.append({"plain": T("这一对蛋白没有分子动力学数据,相关证据标为“待定”。",
                               "There is no molecular-dynamics data for this protein pair, so that evidence is marked “pending”."),
                    "basis": "get_md_interface_scores returned pending"})
    for _, r in _results(transcript, "list_interface_tools")[-1:]:
        names = r.get("pending_no_data_yet") or []
        if names:
            out.append({"plain": T(f"{'、'.join(names)} 这些预测工具还没有数据,所以无法做多工具对照。",
                                   f"No data yet from the prediction tools {', '.join(names)}, so no multi-tool comparison is possible."),
                        "basis": "list_interface_tools: " + ", ".join(names)})
    for args, r in _results(transcript, "validate_residues"):
        bad = r.get("n_mismatches", 0)
        if "error" not in r and bad:
            acc = r.get("uniprot") or args.get("uniprot", "")
            out.append({"plain": T(f"{acc} 上有 {bad} 个残基与真实序列对不上,用这些残基之前要先核对。",
                                   f"{bad} residue(s) on {acc} do not match the real sequence; check them before relying on them."),
                        "basis": f"validate_residues {acc}: {bad} mismatches of {len(r.get('validated', []))}"})
    unreachable = []
    for name, db in SOURCE_OF.items():
        for _, r in _results(transcript, name):
            failed = ("error" in r or r.get("status") == "unavailable" or r.get("source") in ("unavailable", "withheld")
                      or (name == "search_literature" and not r.get("retrieved_live") and "fallback" not in r))
            if failed and db not in unreachable:
                unreachable.append(db)
    for db in unreachable:
        out.append({"plain": T(f"{db} 这次没有取到数据,依赖它的结论证据不完整。",
                               f"{db} returned no data this time, so the evidence behind conclusions that depend on it is incomplete."),
                    "basis": f"a {db} tool call returned an error, was unavailable, or returned nothing"})
    return out


PARAPHRASE_PROMPT = (
    "You rewrite short technical caution notes from a protein-interface analysis tool for a non-technical "
    "scientist. For EACH note write ONE plain sentence in Chinese and ONE plain sentence in English. Rules: only "
    "restate what the note says; add no facts, causes, advice or judgement; keep every number, residue name "
    "(such as G131), accession and PDB code exactly as written; if a note is unclear, restate it literally in "
    "simple words. Reply with JSON only: {\"items\": [{\"zh\": \"...\", \"en\": \"...\"}, ...]} with exactly "
    "N items in the same order as the notes.\n\nNotes:\n")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


_IDENT = re.compile(r"\b(?:[A-Z]{2,}[A-Za-z0-9\-]*|[A-Z][a-z]+[A-Z][A-Za-z0-9\-]*|[A-Z]\d+)\b")


def _stems(text: str) -> set[str]:
    return {w[:5].lower() for w in re.findall(r"[A-Za-z]{4,}", text.replace("_", " "))}


def paraphrase_ok(raw: str, item) -> bool:
    """Deterministic guard. A paraphrase is used only if (1) it keeps exactly the numbers of the raw note,
    (2) every identifier in the raw note (residue names such as G131, acronyms such as UBL2 or PISA) appears
    in both languages, (3) the English sentence reuses at least 40% of the raw note's content words, and
    (4) each language is plausible. This catches dropped or invented figures and rewordings that drift from
    the note; it cannot prove a sentence is faithful, which is why the page says the rewording may be
    imperfect and keeps the original wording. Anything failing falls back to the generic sentence."""
    try:
        zh, en = item["zh"].strip(), item["en"].strip()
    except Exception:
        return False
    if not (0 < len(zh) <= 400 and 0 < len(en) <= 400 and _CJK.search(zh) and not _CJK.search(en)):
        return False
    if not (_digits(zh) == _digits(raw) == _digits(en)):
        return False
    if any(tok not in zh or tok not in en for tok in _IDENT.findall(raw)):
        return False
    stems = _stems(raw)
    return not stems or len(stems & _stems(en)) / len(stems) >= 0.4


def paraphrase_flags(raws: list[str], case_id: str | None = None):
    """One extra model call turns the agent's free-text flags into plain sentences. Returns
    (list of {'zh','en'} aligned with `raws`, run-log record or None). Any failure, wrong item count
    or an item that fails the guard yields FLAG_FALLBACK for it; nothing is guessed."""
    if not raws:
        return [], None
    from agent import run_agent
    from agent.llm_client import MODEL
    rec = runlog.RunRecorder("flag_paraphrase", MODEL, "paraphrase the agent's flags in plain language", case_id)
    items = None
    try:
        prompt = PARAPHRASE_PROMPT.replace("N items", f"{len(raws)} items") + "\n".join(
            f"{i + 1}. {r}" for i, r in enumerate(raws))
        resp = run_agent.make_client().chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
        rec.llm(resp)
        m = re.search(r"\{.*\}", resp.choices[0].message.content or "", re.S)
        items = json.loads(m.group(0))["items"]
        if not isinstance(items, list) or len(items) != len(raws):
            items = None
    except Exception:
        items = None
    line = rec.finish({"n_flags": len(raws), "parsed": items is not None})
    out = [T(i["zh"].strip(), i["en"].strip()) if items is not None and paraphrase_ok(r, i) else FLAG_FALLBACK
           for r, i in zip(raws, items or [None] * len(raws))]
    return out, line


# --- plain-language conclusion --------------------------------------------------------------
def residue_sort_key(label) -> tuple:
    """Order residue labels by their sequence number (C7, L9, ... I163); labels without a number last."""
    m = re.search(r"\d+", str(label))
    return (0, int(m.group()), str(label)) if m else (1, 0, str(label))


def _span(regions, acc):
    xs = [(int(r["start"]), int(r["end"])) for r in regions or [] if r.get("uniprot") == acc]
    return (min(a for a, _ in xs), max(b for _, b in xs)) if xs else None


def conclusion(case: Case, result: dict | None, paraphrases: list | None = None,
               found: list | None = None) -> dict:
    result = result or {}
    raws = [str(f) for f in (result.get("flags") or [])]
    paras = paraphrases if paraphrases is not None else [FLAG_FALLBACK] * len(raws)
    flags = [{"plain": p, "raw": r} for r, p in zip(raws, paras)]
    if "predicted_regions" in result:
        zh_parts, en_parts = [], []
        for acc, name in ((case.uniprot_a, case.name_a), (case.uniprot_b, case.name_b)):
            sp = _span(result["predicted_regions"], acc)
            zh_parts.append(f"{name} 上大致在第 {sp[0]}–{sp[1]} 位氨基酸" if sp else f"{name} 上没有给出区域")
            en_parts.append(f"on {name}, roughly residues {sp[0]}–{sp[1]}" if sp else f"no region given for {name}")
        headline = T("系统预测,两个蛋白的结合区域:" + ";".join(zh_parts) + "。",
                     "The system predicts these binding regions: " + "; ".join(en_parts) + ".")
        caveat = T(CAVEAT_PAIR["zh"] + (CAVEAT_HELD_OUT["zh"] if case.benchmark else ""),
                   CAVEAT_PAIR["en"] + (" " + CAVEAT_HELD_OUT["en"] if case.benchmark else ""))
    elif "consensus_interface" in result:
        core = sorted(result.get("consensus_interface") or [], key=residue_sort_key)
        lo, hi = NTERM_UBL_RANGE
        zh_core = ", ".join(core) or "没有"
        en_core = ", ".join(core) or "none"
        headline = T(f"系统给出的 FAT10 界面残基(依据分子动力学接触数据,由系统综合判断):{zh_core}。"
                     f"注意:文献 / NMR 预期的结合区域是 FAT10 的第 {lo}–{hi} 位(引用,不是本系统推导),"
                     f"两者是否一致见下面的“需要留意”。",
                     f"FAT10 interface residues reported by the system (based on the molecular-dynamics contact "
                     f"data, judged by the system): {en_core}. Note: the literature/NMR-expected binding region "
                     f"is residues {lo}–{hi} of FAT10 (cited, not derived by this system); whether the two "
                     f"agree is under “Points to watch” below.")
        caveat = CAVEAT_FAT10
    else:
        headline = T("系统没有给出结构化结论。", "The system did not return a structured conclusion.")
        caveat = CAVEAT_PAIR
    points = []
    if isinstance(result.get("confidence"), (int, float)):
        c = result["confidence"]
        points.append(T(f"系统自评的把握程度:{c}(0 表示没把握,1 表示很有把握)。",
                        f"The system's own confidence: {c} (0 = none, 1 = very confident)."))
    return {"headline": headline, "points": points, "findings": found or [], "flags": flags, "caveat": caveat,
            "details": result.get("reasoning") or result.get("final_text")}


# --- one query ------------------------------------------------------------------------------
def _merged_usage(agent_rec: dict, extra: dict | None) -> dict:
    """Time / cost / tokens of the whole query: the agent run plus the flag-paraphrase call."""
    def add(key):
        vals = [agent_rec.get(key), (extra or {}).get(key) if extra else 0]
        return None if any(v is None for v in vals) else vals[0] + vals[1]
    return {"seconds": add("wall_clock_s"), "cost_usd": add("cost_usd"), "llm_calls": add("llm_calls"),
            "prompt_tokens": add("prompt_tokens"), "completion_tokens": add("completion_tokens"),
            "paraphrase_llm_calls": (extra or {}).get("llm_calls", 0), "model": agent_rec.get("model"),
            "activity": agent_rec.get("activity"), "pricing_last_checked": agent_rec.get("pricing_last_checked")}


def run_query(case: Case, max_steps: int = 12) -> dict:
    from agent.run_agent import run   # lazy: no LLM client is built until here
    runlog.LAST_RECORD.set(None)
    result, transcript = run(case.goal, max_steps=max_steps, verbose=False, case=case)
    agent_rec = runlog.LAST_RECORD.get() or {}          # read before the paraphrase call overwrites it
    raws = [str(f) for f in ((result or {}).get("flags") or [])]
    paras, para_rec = paraphrase_flags(raws, case.id)
    return {
        "case": {"id": case.id, "name": f"{case.name_a} – {case.name_b}",
                 "uniprot_a": case.uniprot_a, "uniprot_b": case.uniprot_b},
        "conclusion": conclusion(case, result, paras, findings(case, transcript)),
        "evidence": evidence_rows(transcript),
        "usage": _merged_usage(agent_rec, para_rec),
        "steps": [{"tool": a["tool"], "args": a.get("args")} for s in transcript for a in s["actions"]],
    }
