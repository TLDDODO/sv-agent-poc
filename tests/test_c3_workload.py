"""C3: per-query workload metrics (databases, data API calls, records, time, cost), counted at the
call sites, logged per run, aggregated from the run log by a script, and reported in the evaluation
report and business case. Manual (human) time is never estimated."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import baseline, benchmark, cases, leakage, literature, metrics, run_agent, structures, tools, workload
from api import main as api
from fakes import FakeClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_docs as gd  # noqa: E402
import workload_metrics as cli  # noqa: E402

SEQ = "MACDEFGHIK"


class _Resp:
    def __init__(self, text):
        self._b = text.encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch):
    """Synthetic stand-ins for UniProt / PDBe search / PubMed; returns the list of requested URLs."""
    seen = []

    def fake(url, timeout=20):
        seen.append(url)
        if url.startswith("https://rest.uniprot.org") and url.endswith(".fasta"):
            return _Resp(f">synthetic\n{SEQ}\n")
        if url.startswith("https://rest.uniprot.org"):
            return _Resp(json.dumps({
                "proteinDescription": {"recommendedName": {"fullName": {"value": "Synthetic protein"}}},
                "sequence": {"length": len(SEQ)},
                "features": [{"type": "Domain", "description": "D1", "location": {"start": {"value": 1}, "end": {"value": 5}}},
                             {"type": "Region", "description": "R1", "location": {"start": {"value": 6}, "end": {"value": 9}}}]}))
        if "pdbe/search" in url:
            ids = ["1ycr", "9zzz"] if "P04637" in url else ["1ycr", "8yyy"]
            return _Resp(json.dumps({"response": {"docs": [{"pdb_id": i} for i in ids]}}))
        if "esearch" in url:
            return _Resp(json.dumps({"esearchresult": {"idlist": ["11", "22", "33"]}}))
        if "efetch" in url:
            return _Resp("abstract text")
        raise AssertionError(url)

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake)
    return seen


@pytest.fixture(autouse=True)
def _clean():
    leakage.clear_cache()
    metrics.stop()
    yield
    metrics.stop()


# --- counters --------------------------------------------------------------------------------------
def test_summary_math_and_calls_outside_a_run_are_ignored():
    metrics.call("UniProt", 5)                      # no collector -> ignored
    d = metrics.start()
    metrics.call("UniProt", 5)
    metrics.call("UniProt", 0, ok=False)
    metrics.call("PubMed", 3)
    metrics.local("MD result file", 15)
    s = metrics.summary(d)
    assert s["databases"] == ["PubMed", "UniProt"] and s["data_api_calls"] == 3 and s["failed_calls"] == 1
    assert s["by_database"]["UniProt"] == {"calls": 2, "failed": 1, "records": 5}
    assert s["local_files"] == ["MD result file"] and s["records_processed"] == 5 + 3 + 15


def test_a_database_that_only_failed_is_not_counted_as_reached():
    d = metrics.start()
    metrics.call("PDBe", 0, ok=False)
    s = metrics.summary(d)
    assert s["databases"] == [] and s["data_api_calls"] == 1 and s["failed_calls"] == 1


# --- instrumentation at the real call sites ---------------------------------------------------------
def _run(fake_llm, script, case=None, goal="g"):
    fake_llm(script)
    run_agent.run(goal, verbose=False, case=case)


def _last_line(runlog_path):
    return json.loads(runlog_path.read_text(encoding="utf-8").splitlines()[-1])


def test_run_log_records_measured_activity(fake_llm, runlog_path, monkeypatch):
    _serve(monkeypatch)
    _run(fake_llm, [
        lambda m: ("x", [("get_md_interface_scores", {}), ("validate_residues", {"uniprot": "O15205", "residues": ["M1", "C3"]})]),
        lambda m: ("done", [("submit_adjudication", {"consensus_interface": [], "disputed": [], "confidence": 0.1, "reasoning": "r"})])])
    a = _last_line(runlog_path)["activity"]
    assert a["databases"] == ["UniProt"] and a["data_api_calls"] == 1 and a["failed_calls"] == 0
    assert a["by_database"] == {"UniProt": {"calls": 1, "failed": 0, "records": 2}}     # 2 residues checked
    assert a["local_files"] == ["MD result file"]
    n_md = len(next(iter(json.load(open("analysis/md_interface_scores.json", encoding="utf-8")).values())))
    assert a["records_processed"] == 2 + n_md


def test_failed_requests_are_counted_as_failed(fake_llm, runlog_path):
    _run(fake_llm, [
        lambda m: ("x", [("validate_residues", {"uniprot": "O15205", "residues": ["M1"]})]),
        lambda m: ("done", [("submit_adjudication", {"consensus_interface": [], "disputed": [], "confidence": 0.1, "reasoning": "r"})])])
    a = _last_line(runlog_path)["activity"]                  # the network is blocked in tests
    assert a["databases"] == [] and a["data_api_calls"] == 1 and a["failed_calls"] == 1


def test_pubmed_counts_esearch_and_efetch(fake_llm, runlog_path, monkeypatch):
    _serve(monkeypatch)
    _run(fake_llm, [
        lambda m: ("x", [("search_literature", {})]),
        lambda m: ("done", [("submit_adjudication", {"consensus_interface": [], "disputed": [], "confidence": 0.1, "reasoning": "r"})])])
    a = _last_line(runlog_path)["activity"]
    assert a["by_database"]["PubMed"] == {"calls": 2, "failed": 0, "records": 3 + 3}


def test_generic_case_counts_the_uniprot_feature_table(fake_llm, runlog_path, monkeypatch):
    _serve(monkeypatch)
    case = cases.custom_case("P04637", "P24941")
    _run(fake_llm, [
        lambda m: ("x", [("get_expected_interface_region", {})]),
        lambda m: ("done", [("submit_adjudication", {"consensus_interface": [], "disputed": [], "confidence": 0.1,
                                                     "reasoning": "r", "predicted_regions": []})])], case=case)
    a = _last_line(runlog_path)["activity"]
    assert a["by_database"]["UniProt"] == {"calls": 2, "failed": 0, "records": 4}       # 2 proteins x 2 features
    assert a["local_files"] == []


@pytest.mark.filterwarnings("ignore::RuntimeWarning")   # the patched asyncio.run drops the coroutine
def test_pdbe_mcp_query_counts_one_call(monkeypatch):
    text = "Results metadata:\nDocuments:\nDocument 1:\n  pdb_id: 1abc\n  title: t\n  experimental_method: X\nDocument 2:\n  pdb_id: 2abc\n  title: t2\n"
    monkeypatch.setattr("asyncio.run", lambda coro, **k: (coro.close(), text)[1])
    d = metrics.start()
    hits = structures.mcp_structures("P04637")
    assert len(hits) == 2
    assert metrics.summary(d)["by_database"] == {"PDBe": {"calls": 1, "failed": 0, "records": 2}}
    metrics.stop()
    d = metrics.start()
    monkeypatch.setattr("asyncio.run", lambda coro, **k: (coro.close(), (_ for _ in ()).throw(OSError("x")))[1])
    with pytest.raises(OSError):
        structures.mcp_structures("P04637")
    assert metrics.summary(d)["by_database"]["PDBe"] == {"calls": 1, "failed": 1, "records": 0}


def test_leak_filter_does_not_repeat_its_pdbe_requests_within_a_run(monkeypatch):
    seen = _serve(monkeypatch)
    case = cases.find_case("mdm2_p53")
    d = metrics.start()
    for _ in range(5):                                        # the guard runs after every tool call
        leakage.guard({"x": 1}, case)
    assert len([u for u in seen if "pdbe/search" in u]) == 2  # one request per protein, then cached
    assert metrics.summary(d)["by_database"]["PDBe"]["calls"] == 2
    leakage.clear_cache()                                     # a new run asks again
    leakage.guard({"x": 1}, case)
    assert len([u for u in seen if "pdbe/search" in u]) == 4


def test_baseline_run_has_no_data_activity(monkeypatch, runlog_path):
    import json as _j
    client = FakeClient([lambda m: (_j.dumps({"regions": []}), [])])
    monkeypatch.setattr(baseline, "make_client", lambda: client)
    baseline.run_baseline(cases.find_case("mdm2_p53"))
    a = _last_line(runlog_path)["activity"]
    assert a["data_api_calls"] == 0 and a["databases"] == [] and a["records_processed"] == 0


# --- aggregation from the run log ----------------------------------------------------------------------
def _line(kind, case, calls, records, dbs, llm=3, wall=10.0, cost=0.002, tools_=("a", "b")):
    return {"kind": kind, "case": case, "llm_calls": llm, "prompt_tokens": 100, "completion_tokens": 10,
            "wall_clock_s": wall, "cost_usd": cost, "tools": list(tools_),
            "activity": {"databases": dbs, "data_api_calls": calls, "failed_calls": 0, "records_processed": records,
                         "by_database": {d: {"calls": calls, "failed": 0, "records": records} for d in dbs},
                         "local_files": []}}


def test_workload_aggregation():
    lines = [{"kind": "agent", "case": "mdm2_p53", "tools": []},                   # legacy line, no activity
             _line("agent", "mdm2_p53", 4, 100, ["PDBe", "UniProt"], wall=10),
             _line("agent", "mdm2_p53", 6, 200, ["PDBe", "PubMed", "UniProt"], wall=30),
             _line("baseline", "mdm2_p53", 0, 0, [], llm=1, wall=1, tools_=()),
             _line("agent", "custom_A_B", 2, 8, ["UniProt"])]
    w = workload.compute(lines, {"mdm2_p53"})
    assert w["excluded_lines_without_activity"] == 1 and w["manual_time"] == "not measured"
    g = w["groups"]["benchmark_agent"]
    assert g["queries"] == 2 and g["mean_data_api_calls"] == 5 and g["mean_records_processed"] == 150
    assert g["mean_databases"] == 2.5 and g["databases_used"] == ["PDBe", "PubMed", "UniProt"]
    assert g["median_wall_clock_s"] == 20 and g["mean_tool_calls"] == 2
    assert g["mean_calls_by_database"]["PubMed"] == 3                                # 6 calls in 1 of 2 queries
    assert w["groups"]["benchmark_baseline"]["mean_data_api_calls"] == 0
    assert w["groups"]["other_agent"]["queries"] == 1


def test_the_committed_workload_matches_the_committed_run_log():
    ids = {c.id for c in cases.load_benchmark()}
    got = json.loads((ROOT / "results" / "workload.json").read_text(encoding="utf-8"))
    # workload.json covers the first `log_lines` lines of the log; anything appended later (someone
    # using the app) is not part of it yet, and must not make this check fail
    lines = workload.read_log(ROOT / "results" / "runs.jsonl")
    assert len(lines) >= got["log_lines"]
    want = workload.compute(lines[:got["log_lines"]], ids)
    assert got == want
    assert got["groups"]["benchmark_agent"]["queries"] > 0 and got["groups"]["benchmark_baseline"]["queries"] > 0


def test_script_writes_workload_and_folds_it_into_the_report(tmp_path):
    ids = [c.id for c in cases.load_benchmark()]
    (tmp_path / "runs.jsonl").write_text("\n".join(
        json.dumps(x) for x in [_line("agent", ids[0], 4, 100, ["PDBe"]), _line("baseline", ids[0], 0, 0, [])]) + "\n",
        encoding="utf-8")
    bench = benchmark.run_benchmark(cases.load_benchmark()[:1], 1, dry_run=True)
    benchmark.write_outputs(bench, tmp_path)
    assert "Workload per query" not in (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert cli.main(["--out", str(tmp_path)]) == 0
    w = json.loads((tmp_path / "workload.json").read_text(encoding="utf-8"))
    md = (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    merged = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert merged["workload"] == w and md == benchmark.render_markdown(merged)
    assert "Workload per query" in md and "Manual (human) effort was not measured" in md
    assert "| agent (benchmark pairs): 1 | 2.0 | 1.0 | 4.0 | 3.0 | 100 | 10.0 | $0.0020 |" in md


# --- business case ---------------------------------------------------------------------------------------
def _sandbox(tmp_path, mutate=None):
    (tmp_path / "docs").mkdir()
    (tmp_path / "results").mkdir()
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    shutil.copy(ROOT / "docs" / "business_case.md", tmp_path / "docs" / "business_case.md")
    data = json.loads((ROOT / "results" / "benchmark.json").read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    (tmp_path / "results" / "benchmark.json").write_text(json.dumps(data), encoding="utf-8")


def test_business_case_replaces_tbd_with_automated_metrics_and_says_manual_time_is_unmeasured():
    biz = gd._read(ROOT / "docs" / "business_case.md")
    assert "TBD" not in biz
    assert "人工耗时未测量" in biz and "不估计人工耗时" in biz
    block = re.search(r"GENERATED:BUSINESS:START -->\r?\n(.*?)\r?\n<!-- GENERATED:BUSINESS:END", biz, re.S).group(1)
    assert "| 数据接口调用 |" in block or "数据接口调用" in block
    w = json.loads((ROOT / "results" / "workload.json").read_text(encoding="utf-8"))["groups"]["benchmark_agent"]
    assert f"{w['mean_data_api_calls']:.1f}" in block and f"{w['mean_records_processed']:.0f}" in block
    # no human-time number anywhere: the only mentions of manual effort say it is unmeasured
    for line in biz.splitlines():
        if "人工" in line and re.search(r"\d+\s*(分钟|小时|天|min|h\b)", line):
            pytest.fail(f"a manual-time figure appears: {line}")


def test_business_case_numbers_follow_the_workload_file(tmp_path):
    def mutate(d):
        d["workload"]["groups"]["benchmark_agent"]["mean_data_api_calls"] = 7.7
        d["workload"]["groups"]["benchmark_agent"]["mean_records_processed"] = 4321
    _sandbox(tmp_path, mutate)
    for rel, text in gd.render_all(tmp_path).items():
        with (tmp_path / rel).open("w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    biz = gd._read(tmp_path / "docs" / "business_case.md")
    assert "| 7.7 |" in biz and "| 4321 |" in biz


def test_business_case_without_workload_says_so_and_invents_nothing(tmp_path):
    def mutate(d):
        d.pop("workload", None)
    _sandbox(tmp_path, mutate)
    text = gd.render_all(tmp_path)["docs/business_case.md"]
    assert "还没有工作量指标" in text and "TBD" not in text


# --- web client shows the same counters ---------------------------------------------------------------------
def test_web_usage_includes_the_activity(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    _serve(monkeypatch)
    case = cases.find_case("mdm2_p53")
    fake_llm([lambda m: ("x", [("get_expected_interface_region", {})]),
              lambda m: ("d", [("submit_adjudication", {"consensus_interface": [], "disputed": [], "confidence": 0.5,
                                                        "reasoning": "r", "predicted_regions": [
                                                            {"uniprot": case.uniprot_a, "start": 1, "end": 5},
                                                            {"uniprot": case.uniprot_b, "start": 1, "end": 5}]})])])
    d = TestClient(api.app).post("/api/run", json={"case_id": "mdm2_p53"}).json()
    a = d["usage"]["activity"]
    assert "UniProt" in a["databases"] and a["data_api_calls"] >= 2 and a["records_processed"] >= 1
    assert 'stat(t("s_dbs")' in TestClient(api.app).get("/").text          # the page shows the counters
