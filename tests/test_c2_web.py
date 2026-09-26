"""C2: the single-page web client. GET / serves the page; /api/run runs one query end to end
(with the scripted fake LLM, offline) and returns a plain-language answer, evidence rows labelled
live / cited / pending, and the query's time and cost."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import cases, tools
from agent.structures import StructureHit
from api import main as api
from api import webview
from fakes import tool_result

client = TestClient(api.app)


# --- the page --------------------------------------------------------------------------------
def test_root_serves_the_web_page():
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    for needle in ("蛋白质界面裁决器", "/api/run", "/api/cases", "实时", "引用", "待定"):
        assert needle in html
    # no external assets and no new dependency: everything is inline
    assert not re.search(r"""(?:src|href)=["']https?://""", html)
    assert "cdn" not in html.lower()


def test_the_page_is_not_part_of_the_openapi_schema_and_info_moved_to_slash_info():
    assert "/" not in api.app.openapi()["paths"]
    info = client.get("/info").json()
    assert info["service"] and "POST /api/run" in info["endpoints"]


def test_preset_cases_list():
    r = client.get("/api/cases")
    assert r.status_code == 200
    got = r.json()
    ids = [c["id"] for c in got]
    assert ids[0] == "fat10_mad2" and len(ids) == 1 + len(cases.load_benchmark())
    assert {c["kind"] for c in got} == {"case_study", "benchmark"}
    assert "ground_truth" not in json.dumps(got) and "1YCR" not in json.dumps(got)   # answers never listed


# --- input handling ----------------------------------------------------------------------------
@pytest.mark.parametrize("body", [{}, {"case_id": "nope"}, {"uniprot_a": "P04637"},
                                  {"uniprot_a": "not-an-accession", "uniprot_b": "Q00987"}])
def test_bad_input_is_a_422_even_without_a_key(body):
    assert client.post("/api/run", json=body).status_code == 422


def test_run_without_a_key_is_a_400(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.post("/api/run", json={"case_id": "mdm2_p53"})
    assert r.status_code == 400 and "DEEPSEEK_API_KEY" in r.json()["detail"]


def test_custom_case_is_generic_and_holds_nothing_out():
    c = cases.custom_case("p04637", "Q00987")
    assert c.custom and c.generic and not c.benchmark and c.ground_truth is None
    assert (c.uniprot_a, c.uniprot_b) == ("P04637", "Q00987")
    with pytest.raises(ValueError):
        cases.custom_case("P04637", "12345")


# --- end to end with the fake LLM ---------------------------------------------------------------
def _submit_regions(case, a=(26, 109), b=(17, 29)):
    def step(msgs):
        return "done", [("submit_adjudication", {
            "consensus_interface": [], "disputed": [], "confidence": 0.6, "flags": ["check the linker"],
            "reasoning": "based on the annotation table",
            "predicted_regions": [{"uniprot": case.uniprot_a, "start": a[0], "end": a[1]},
                                  {"uniprot": case.uniprot_b, "start": b[0], "end": b[1]}]})]
    return step


def test_end_to_end_preset_query(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    case = cases.find_case("mdm2_p53")

    def ask_md(msgs):
        return "look", [("get_md_interface_scores", {}), ("list_interface_tools", {}),
                        ("get_expected_interface_region", {})]

    llm = fake_llm([ask_md, _submit_regions(case), _para("check the linker")])
    r = client.post("/api/run", json={"case_id": "mdm2_p53"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case"]["id"] == "mdm2_p53"
    # plain-language conclusion built from the agent's structured result
    c = d["conclusion"]
    assert "第 26–109 位" in c["headline"]["zh"] and "第 17–29 位" in c["headline"]["zh"]
    assert "residues 26–109" in c["headline"]["en"] and "residues 17–29" in c["headline"]["en"]
    assert [f["raw"] for f in c["flags"]] == ["check the linker"]          # the raw wording is kept
    assert c["flags"][0]["plain"] == {"zh": "提醒:check the linker", "en": "Note: check the linker"}
    assert "0.6" in c["points"][0]["zh"] and "0.6" in c["points"][0]["en"]
    assert "不是实验测得" in c["caveat"]["zh"] and "没看答案" in c["caveat"]["zh"]
    assert "not an experimentally measured" in c["caveat"]["en"] and "without seeing the answer" in c["caveat"]["en"]
    # evidence rows carry exactly the three labels; missing data is pending, never a number
    rows = d["evidence"]
    assert rows and {r["label"] for r in rows} <= {"live", "cited", "pending"}
    md = next(r for r in rows if r["item"]["zh"] == "分子动力学接触数据")
    assert md["label"] == "pending" and md["records"] == 0
    assert {r["item"]["zh"] for r in rows if r["label"] == "pending"} >= {"PISA 预测", "HADDOCK 预测"}
    assert {r["item"]["en"] for r in rows if r["label"] == "pending"} >= {"PISA prediction", "HADDOCK prediction"}
    feat = next(r for r in rows if r["item"]["zh"] == "结构域注释")      # UniProt is unreachable in tests
    assert feat["label"] == "pending"
    # time and cost of this query, from the run-log record
    u = d["usage"]
    assert u["llm_calls"] == 3 == len(llm.requests) and u["seconds"] >= 0   # 2 agent calls + 1 flag paraphrase
    assert u["paraphrase_llm_calls"] == 1
    assert u["prompt_tokens"] == 300 and u["completion_tokens"] == 60      # the fake's fixed usage, all 3 calls
    assert u["cost_usd"] is not None and u["cost_usd"] > 0 and u["pricing_last_checked"]
    assert [s["tool"] for s in d["steps"]] == ["get_md_interface_scores", "list_interface_tools",
                                              "get_expected_interface_region", "submit_adjudication"]
    # the held-out complex never appears anywhere in the answer
    assert case.ground_truth["pdb"].lower() not in json.dumps(d).lower()


def test_end_to_end_custom_pair(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    case = cases.custom_case("P04637", "P24941")          # not a benchmark pair
    fake_llm([lambda m: ("md?", [("get_md_interface_scores", {})]), _submit_regions(case)])
    d = client.post("/api/run", json={"uniprot_a": "P04637", "uniprot_b": "P24941"}).json()
    assert d["case"]["id"] == "custom_P04637_P24941"
    assert "P04637" in d["conclusion"]["headline"]["zh"] and "没看答案" not in d["conclusion"]["caveat"]["zh"]
    assert "without seeing the answer" not in d["conclusion"]["caveat"]["en"]
    assert d["evidence"][0]["label"] == "pending"


def test_end_to_end_fat10_case_keeps_the_contradiction_wording(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")

    def md(msgs):
        return "md", [("get_md_interface_scores", {}), ("get_expected_interface_region", {})]

    def submit(msgs):
        md_ = tool_result(msgs, "get_md_interface_scores")
        core = [r for r, v in md_["occupancy"].items() if v >= 0.5]
        return "done", [("submit_adjudication", {
            "consensus_interface": core, "disputed": [], "confidence": 0.3,
            "flags": ["CONTRADICTION: test flag"], "reasoning": "r"})]

    fake_llm([md, submit, _para("CONTRADICTION: test flag")])
    d = client.post("/api/run", json={"case_id": "fat10_mad2"}).json()
    assert "I163" in d["conclusion"]["headline"]["zh"] and "I163" in d["conclusion"]["headline"]["en"]
    assert "第 6–81 位" in d["conclusion"]["headline"]["zh"]     # the literature expectation is always shown
    assert "residues 6–81" in d["conclusion"]["headline"]["en"]
    assert d["conclusion"]["caveat"] == webview.CAVEAT_FAT10
    (flag,) = d["conclusion"]["flags"]
    assert flag["raw"] == "CONTRADICTION: test flag"                   # the raw wording is kept separately
    finding = d["conclusion"]["findings"][0]                           # ...and the contradiction is computed from data
    assert "不一致" in finding["plain"]["zh"] and "disagree" in finding["plain"]["en"]
    assert "I163" in finding["basis"] and "6–81" in finding["basis"]
    labels = {r["item"]["zh"]: r["label"] for r in d["evidence"]}
    assert labels["分子动力学接触数据"] == "live"          # the real committed MD file
    assert labels["文献预期的结合区域"] == "cited"          # a cited fact, not re-derived


def test_upstream_failure_is_a_502_not_a_fake_answer(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    monkeypatch.setattr("agent.run_agent.make_client", lambda: (_ for _ in ()).throw(TimeoutError("down")))
    r = client.post("/api/run", json={"case_id": "mdm2_p53"})
    assert r.status_code == 502 and "TimeoutError" in r.json()["detail"]


# --- evidence-row mapping -------------------------------------------------------------------------
def test_structure_rows_are_labelled_by_where_the_data_came_from():
    def row(source):
        out = {"source": source, "structures": [{"pdb_id": "1abc"}]}
        return webview._rows_for("fetch_structures", {"uniprot": "X"}, out)[0]["label"]
    assert row("pdbe_mcp_live") == "live" and row("verified_snapshot") == "cited"
    assert row("unavailable") == "pending" and row("withheld") == "pending"


def test_literature_and_validation_rows():
    live = webview._rows_for("search_literature", {}, {"retrieved_live": True, "pmids": ["1", "2"]})[0]
    assert live["label"] == "live" and live["records"] == 2
    cited = webview._rows_for("search_literature", {}, {"retrieved_live": False, "fallback": "quoted result"})[0]
    assert cited["label"] == "cited"
    assert webview._rows_for("search_literature", {}, {"retrieved_live": False})[0]["label"] == "pending"
    ok = webview._rows_for("validate_residues", {}, {"uniprot": "X", "validated": [{}, {}], "n_mismatches": 1})[0]
    assert ok["label"] == "live" and "2 个残基" in ok["detail"]["zh"] and "1 个" in ok["detail"]["zh"]
    assert "2 residues" in ok["detail"]["en"] and "1 of which" in ok["detail"]["en"]
    assert webview._rows_for("validate_residues", {"uniprot": "X"}, {"error": "e", "validated": []})[0]["label"] == "pending"


def test_evidence_rows_are_deduplicated():
    act = {"tool": "get_md_interface_scores", "args": {}, "result": {"status": "pending"}}
    rows = webview.evidence_rows([{"actions": [act]}, {"actions": [act]}])
    assert len(rows) == 1


def test_the_page_can_render_every_label():
    html = client.get("/").text
    for lab in ("live", "cited", "pending"):
        assert f".badge.{lab}" in html


# --- a typed benchmark pair must stay blind (review finding) -------------------------------------
@pytest.mark.parametrize("a,b", [("P04637", "Q00987"), ("Q00987", "P04637"), (" q00987 ", "p04637")])
def test_a_typed_benchmark_pair_runs_as_the_filtered_benchmark_case(a, b):
    c = webview.resolve_case(None, a, b)
    assert c.benchmark and c.id == "mdm2_p53" and c.ground_truth["pdb"] == "1YCR"


def test_a_non_benchmark_pair_stays_custom():
    assert webview.resolve_case(None, "P04637", "P24941").custom


@pytest.mark.parametrize("body", [{"uniprot_a": "P04637", "uniprot_b": "Q00987"},
                                  {"uniprot_a": "Q00987", "uniprot_b": "P04637"}])
def test_typed_benchmark_pair_never_leaks_the_held_out_complex(body, fake_llm, monkeypatch):
    from agent import literature, leakage
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    monkeypatch.setenv("PDBE_SOURCE", "mcp")
    case = cases.find_case("mdm2_p53")
    banned = sorted(leakage.co_complex_entries(case))
    monkeypatch.setattr(tools, "mcp_structures", lambda uniprot: [
        *[StructureHit(e.lower(), "held-out complex", None, None, "fake") for e in banned],
        StructureHit("9zzz", "apo structure", None, None, "fake")])
    seen = {}

    def fake_search(query, retmax=5, exclude_pmids=()):
        seen["exclude"] = set(exclude_pmids)
        return ["111"], "abstract"

    monkeypatch.setattr(literature, "search_pubmed", fake_search)
    # a tool that wrongly names the held-out complex must be withheld by the output guard
    monkeypatch.setitem(tools.DISPATCH, "list_interface_tools", lambda **kw: {"note": "see 1ycr"})

    def ask(msgs):
        return "go", [("fetch_structures", {"uniprot": case.uniprot_a}), ("search_literature", {}),
                      ("list_interface_tools", {})]

    fake_llm([ask, _submit_regions(case)])
    r = client.post("/api/run", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case"]["id"] == "mdm2_p53"
    assert seen["exclude"] == set(leakage.co_complex_pmids(case)) and seen["exclude"]
    text = json.dumps(d, ensure_ascii=False).lower()
    assert not any(e.lower() in text for e in banned)
    assert "9zzz" in text                                    # unrelated structures still come through


# --- language switch, plain-language flags, sorted residues (client tweaks) ------------------------------
CJK = re.compile(r"[\u4e00-\u9fff]")


def _walk_bilingual(x, found):
    """Collect every {zh, en} pair in a response."""
    if isinstance(x, dict):
        if set(x) == {"zh", "en"}:
            found.append(x)
        else:
            for v in x.values():
                _walk_bilingual(v, found)
    elif isinstance(x, list):
        for v in x:
            _walk_bilingual(v, found)


def test_interface_residues_are_sorted_by_sequence_number():
    assert sorted(["G165", "I163", "C7", "C162", "L9"], key=webview.residue_sort_key) == \
        ["C7", "L9", "C162", "I163", "G165"]
    assert sorted(["K10", "note", "A2"], key=webview.residue_sort_key) == ["A2", "K10", "note"]
    c = webview.conclusion(cases.default_case(), {"consensus_interface": ["G165", "I163", "C7", "C162", "L9"]})
    for lang in ("zh", "en"):
        h = c["headline"][lang]
        order = [h.index(x) for x in ("C7,", "L9,", "C162,", "I163,", "G165")]
        assert order == sorted(order), h


def test_the_whole_response_is_bilingual_and_the_english_has_no_chinese(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    case = cases.find_case("mdm2_p53")
    fake_llm([lambda m: ("x", [("get_md_interface_scores", {}), ("list_interface_tools", {}),
                               ("get_expected_interface_region", {}), ("validate_residues", {"uniprot": case.uniprot_a, "residues": ["A1"]})]),
              _submit_regions(case), _para("check the linker")])
    d = client.post("/api/run", json={"case_id": "mdm2_p53"}).json()
    found = []
    _walk_bilingual(d["conclusion"], found)
    _walk_bilingual(d["evidence"], found)
    assert len(found) >= 8
    for pair in found:
        assert pair["zh"].strip() and pair["en"].strip()
        assert not CJK.search(pair["en"]), pair
    # the only untranslated free text is the system's own wording, which is kept apart
    assert isinstance(d["conclusion"]["details"], str)


def test_the_page_switches_language_and_defaults_to_chinese():
    html = client.get("/").text
    assert '<html lang="zh">' in html and 'id="lang-zh" aria-pressed="true"' in html
    assert 'id="lang-en" aria-pressed="false"' in html and 'var lang = "zh"' in html


def test_every_ui_string_has_an_english_version():
    html = client.get("/").text
    script = html.split("<script>")[1]
    zh_block = script.split("zh: {", 1)[1].split("    en: {", 1)[0]
    en_block = script.split("    en: {", 1)[1].split("  var $ =", 1)[0]
    key_re = re.compile(r'(?:^\s+|",\s+)([a-z][a-z_0-9]*): (?:"|function)', re.M)   # dictionary keys only
    zh_keys, en_keys = set(key_re.findall(zh_block)), set(key_re.findall(en_block))
    assert zh_keys == en_keys and len(zh_keys) > 40
    used = set(re.findall(r'data-i18n(?:-ph)?="([a-z_0-9]+)"', html)) | set(re.findall(r'\bt\("([a-z_0-9]+)"\)', html))
    assert used <= zh_keys, used - zh_keys
    for k in ("live", "cited", "pending", "err_400", "err_422", "err_502", "tech", "tech_flags", "h_flags"):
        assert k in zh_keys
    # nothing Chinese in the English dictionary, and the visible HTML text is filled from a dictionary
    assert not CJK.search(en_block)


def test_flags_show_plain_sentences_and_the_raw_wording_sits_under_technical_details():
    html = client.get("/").text
    assert 'id="tech-box"' in html and "<details" in html
    assert "pick(f.plain)" in html                                  # the visible list uses the plain sentence
    tech = html.split('id="tech-box"', 1)[1].split("</details>", 1)[0]
    assert 'id="tech-flags"' in tech and 'data-i18n="tech"' in tech  # raw codes are inside the collapsible block
    assert 'id="flags"' not in tech


# --- points to watch: computed findings + guarded paraphrase of the agent's flags -------------------------------
def _para(*raws):
    """A faithful fake paraphraser: the scripted LLM's answer to the flag-paraphrase call."""
    def step(msgs):
        return json.dumps({"items": [{"zh": f"提醒:{r}", "en": f"Note: {r}"} for r in raws]}), []
    return step


RUNS = Path(__file__).resolve().parent.parent / "results" / "runs.jsonl"


def _real_flags(pred):
    out = []
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d["kind"] == "agent" and pred(d):
            out += list((d.get("verdict") or {}).get("flags") or [])
    return out


REAL_ALL = _real_flags(lambda d: True)


def test_no_keyword_rules_remain_to_misread_a_flag():
    assert not hasattr(webview, "explain_flag") and not hasattr(webview, "_FLAG_RULES")


def _fat10_run(fake_llm, flags, para=True):
    def md(msgs):
        return "m", [("get_md_interface_scores", {}), ("get_expected_interface_region", {})]

    def submit(msgs):
        core = [r for r, v in tool_result(msgs, "get_md_interface_scores")["occupancy"].items() if v >= 0.5]
        return "d", [("submit_adjudication", {"consensus_interface": core, "disputed": [], "confidence": 0.3,
                                              "flags": flags, "reasoning": "r"})]

    fake_llm([md, submit] + ([_para(*flags)] if flags and para else []))
    return client.post("/api/run", json={"case_id": "fat10_mad2"}).json()


def test_the_fat10_contradiction_comes_from_structured_data_using_the_real_agent_flags(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    real = _real_flags(lambda d: "FAT10" in d["goal"])
    assert real                                          # the committed run log has real FAT10 flags
    d = _fat10_run(fake_llm, real)
    f = d["conclusion"]["findings"][0]
    assert "不一致" in f["plain"]["zh"] and "第 6–81 位" in f["plain"]["zh"] and "不判断哪一方正确" in f["plain"]["zh"]
    assert "disagree" in f["plain"]["en"] and "residues 6–81" in f["plain"]["en"]
    assert "FAT10" in f["plain"]["en"] and "FAT10" in f["plain"]["zh"]        # protein name comes from the case
    assert [x["raw"] for x in d["conclusion"]["flags"]] == real      # every raw flag is kept for technical details


def test_findings_do_not_depend_on_the_agents_flags_and_no_extra_call_without_flags(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    d = _fat10_run(fake_llm, [])
    assert d["conclusion"]["flags"] == [] and "不一致" in d["conclusion"]["findings"][0]["plain"]["zh"]
    assert d["usage"]["llm_calls"] == 2 and d["usage"]["paraphrase_llm_calls"] == 0


def test_a_faithful_paraphrase_passes_the_guard_for_every_real_flag():
    assert len(set(REAL_ALL)) > 100
    for raw in REAL_ALL:
        assert webview.paraphrase_ok(raw, {"zh": f"提醒:{raw}", "en": f"Note: {raw}"}), raw


def test_the_guard_rejects_paraphrases_that_change_numbers_identifiers_or_drift():
    ok = webview.paraphrase_ok
    numbered = next(f for f in REAL_ALL if "guessed" in f and re.search(r"\d", f))
    assert ok(numbered, {"zh": f"提醒:{numbered}", "en": f"Note: {numbered}"})
    assert not ok(numbered, {"zh": "有一些猜测的残基没有通过核对", "en": "Some guessed residues failed sequence validation"})   # numbers dropped
    assert not ok(numbered, {"zh": f"提醒:{numbered} 4242", "en": f"Note: {numbered} 4242"})                                   # number invented
    # a reworded note that says something else, for a note with no numbers at all (the reviewer's example)
    plain = next(f for f in REAL_ALL if "failed" in f and "sequence validation" in f and not re.search(r"\d", f))
    assert ok(plain, {"zh": f"提醒:{plain}", "en": f"Note: {plain}"})
    assert not ok(plain, {"zh": "有数据源这次没有取到数据", "en": "A data source could not be reached this time"})
    # identifiers (residue names, acronyms) must survive in both languages
    assert not ok("G131 failed validation", {"zh": "有一个残基没通过核对", "en": "A residue failed validation"})
    assert ok("G131 failed validation", {"zh": "G131 没通过核对", "en": "G131 failed validation"})
    # language / shape
    assert not ok("x pending", {"zh": "still english", "en": "pending"}) and not ok("x pending", {"zh": "待定", "en": "待定"})
    assert not ok("x pending", {"zh": "待定"}) and not ok("x pending", None)


def test_paraphrase_falls_back_per_item_and_never_crashes(fake_llm):
    raws = ["MD scores are pending for this pair", "6 residues failed validation"]
    # one good item, one that invents a number -> [good, fallback]
    fake_llm([lambda m: (json.dumps({"items": [{"zh": "提醒:MD scores are pending for this pair", "en": "Note: MD scores are pending for this pair"},
                                               {"zh": "有 7 个残基没通过核对", "en": "7 residues failed validation"}]}), [])])
    out, line = webview.paraphrase_flags(raws, "x")
    assert out[0]["en"].startswith("Note:") and out[1] == webview.FLAG_FALLBACK
    assert line["kind"] == "flag_paraphrase" and line["llm_calls"] == 1


def test_paraphrase_with_the_wrong_item_count_or_a_failed_call_uses_the_fallback(fake_llm):
    raws = ["a pending note", "another pending note"]
    fake_llm([lambda m: (json.dumps({"items": [{"zh": "提醒", "en": "Note"}]}), [])])
    out, _ = webview.paraphrase_flags(raws, "x")
    assert out == [webview.FLAG_FALLBACK, webview.FLAG_FALLBACK]
    fake_llm([])                                          # the scripted client raises on the first call
    out, _ = webview.paraphrase_flags(raws, "x")
    assert out == [webview.FLAG_FALLBACK, webview.FLAG_FALLBACK]
    fake_llm([lambda m: ("not json at all", [])])
    assert webview.paraphrase_flags(raws, "x")[0] == [webview.FLAG_FALLBACK] * 2
    assert webview.paraphrase_flags([], "x") == ([], None)


def _tr(*acts):
    return [{"actions": [{"tool": t, "args": a, "result": r} for t, a, r in acts]}]


def test_findings_for_pending_missing_and_mismatching_evidence():
    case = cases.custom_case("P04637", "P24941")
    f = webview.findings(case, _tr(
        ("get_md_interface_scores", {}, {"status": "pending"}),
        ("list_interface_tools", {}, {"pending_no_data_yet": ["HADDOCK", "PISA"]}),
        ("validate_residues", {"uniprot": "P04637"}, {"uniprot": "P04637", "validated": [{}, {}, {}], "n_mismatches": 2}),
        ("fetch_structures", {"uniprot": "P04637"}, {"source": "unavailable", "structures": []}),
        ("search_literature", {}, {"retrieved_live": False, "error": "URLError"}),
        ("get_expected_interface_region", {}, {"status": "unavailable"})))
    zh = " ".join(x["plain"]["zh"] for x in f)
    for needle in ("没有分子动力学数据", "HADDOCK、PISA", "P04637 上有 2 个残基", "PDBe 这次没有取到数据",
                   "PubMed 这次没有取到数据", "UniProt 这次没有取到数据"):
        assert needle in zh, needle
    for x in f:
        assert x["basis"] and x["plain"]["zh"] and x["plain"]["en"] and not CJK.search(x["plain"]["en"])


def test_no_findings_when_nothing_is_wrong():
    case = cases.custom_case("P04637", "P24941")
    assert webview.findings(case, _tr(
        ("fetch_structures", {"uniprot": "P04637"}, {"source": "pdbe_mcp_live", "structures": [{"pdb_id": "1abc"}]}),
        ("search_literature", {}, {"retrieved_live": True, "pmids": ["1"]}),
        ("get_expected_interface_region", {}, {"proteins": {"P04637": {"features": []}}}),
        ("validate_residues", {"uniprot": "P04637"}, {"uniprot": "P04637", "validated": [{}], "n_mismatches": 0}))) == []


def test_fat10_findings_say_agree_when_the_md_residues_lie_inside_the_expected_region():
    case = cases.default_case()
    inside = webview.findings(case, _tr(
        ("get_md_interface_scores", {}, {"occupancy": {"K9": 0.9, "L20": 0.8, "C162": 0.1}}),
        ("get_expected_interface_region", {}, {"residue_range": [6, 81]})))
    assert "一致" in inside[0]["plain"]["zh"] and "不一致" not in inside[0]["plain"]["zh"] and "agree" in inside[0]["plain"]["en"]
    mixed = webview.findings(case, _tr(
        ("get_md_interface_scores", {}, {"occupancy": {"K9": 0.9, "I163": 0.8}}),
        ("get_expected_interface_region", {}, {"residue_range": [6, 81]})))
    assert "其中 1 个" in mixed[0]["plain"]["zh"] and "1 of them" in mixed[0]["plain"]["en"]
    assert webview.findings(case, _tr(("get_md_interface_scores", {}, {"occupancy": {"K9": 0.2}}),
                                      ("get_expected_interface_region", {}, {"residue_range": [6, 81]}))) == []


def test_usage_adds_the_paraphrase_call_and_never_hides_an_unknown_cost():
    agent = {"wall_clock_s": 1.0, "cost_usd": 0.5, "llm_calls": 2, "prompt_tokens": 10, "completion_tokens": 4, "model": "m"}
    extra = {"wall_clock_s": 2.0, "cost_usd": 0.25, "llm_calls": 1, "prompt_tokens": 5, "completion_tokens": 1}
    u = webview._merged_usage(agent, extra)
    assert (u["seconds"], u["cost_usd"], u["llm_calls"], u["prompt_tokens"], u["paraphrase_llm_calls"]) == (3.0, 0.75, 3, 15, 1)
    assert webview._merged_usage(dict(agent, cost_usd=None), extra)["cost_usd"] is None
    assert webview._merged_usage(agent, None)["llm_calls"] == 2


def test_the_page_lists_computed_findings_first_and_says_the_rewording_may_be_imperfect():
    html = client.get("/").text
    assert "c.findings.map" in html and 'id="flags-hint"' in html and 'id="tech-basis"' in html
    assert "可能不完美" in html and "may be imperfect" in html
