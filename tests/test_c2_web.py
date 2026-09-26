"""C2: the single-page web client. GET / serves the page; /api/run runs one query end to end
(with the scripted fake LLM, offline) and returns a plain-language answer, evidence rows labelled
live / cited / pending, and the query's time and cost."""
import json
import re

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

    llm = fake_llm([ask_md, _submit_regions(case)])
    r = client.post("/api/run", json={"case_id": "mdm2_p53"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case"]["id"] == "mdm2_p53"
    # plain-language conclusion built from the agent's structured result
    c = d["conclusion"]
    assert "第 26–109 位" in c["headline"] and "第 17–29 位" in c["headline"]
    assert c["flags"] == ["check the linker"] and "0.6" in c["points"][0]
    assert "不是实验测得" in c["caveat"] and "没看答案" in c["caveat"]
    # evidence rows carry exactly the three labels; missing data is pending, never a number
    rows = d["evidence"]
    assert rows and {r["label"] for r in rows} <= {"live", "cited", "pending"}
    md = next(r for r in rows if r["item"] == "分子动力学接触数据")
    assert md["label"] == "pending" and md["records"] == 0
    assert {r["item"] for r in rows if r["label"] == "pending"} >= {"PISA 预测", "HADDOCK 预测"}
    feat = next(r for r in rows if r["item"] == "结构域注释")      # UniProt is unreachable in tests
    assert feat["label"] == "pending"
    # time and cost of this query, from the run-log record
    u = d["usage"]
    assert u["llm_calls"] == 2 == len(llm.requests) and u["seconds"] >= 0
    assert u["prompt_tokens"] == 200 and u["completion_tokens"] == 40      # the fake's fixed usage
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
    assert "P04637" in d["conclusion"]["headline"] and "没看答案" not in d["conclusion"]["caveat"]
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

    fake_llm([md, submit])
    d = client.post("/api/run", json={"case_id": "fat10_mad2"}).json()
    assert "I163" in d["conclusion"]["headline"]
    assert "第 6–81 位" in d["conclusion"]["headline"]         # the literature expectation is always shown
    assert d["conclusion"]["caveat"] == webview.CAVEAT_FAT10
    labels = {r["item"]: r["label"] for r in d["evidence"]}
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
    assert ok["label"] == "live" and "2 个残基" in ok["detail"] and "1 个" in ok["detail"]
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
