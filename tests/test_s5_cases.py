"""S5: tools take the protein pair from a case; FAT10-MAD2 is unchanged; benchmark
pairs never see their held-out experimental complexes (offline, no network)."""
import json
import re

import pytest

from agent import cases, leakage, literature, run_agent, tools
from agent.structures import StructureHit
from fakes import tool_result
from test_agent_smoke import GOAL

BENCH = cases.load_benchmark()
EVIDENCE = json.loads(leakage.EVIDENCE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.fixture(autouse=True)
def _reset_case():
    yield
    cases.set_active_case(None)


def _submit(msgs):
    return "done", [("submit_adjudication", {"consensus_interface": [], "disputed": [],
                                             "confidence": 0.1, "reasoning": "test"})]


# --- FAT10-MAD2 stays the v1 case ------------------------------------------------
def test_fat10_case_is_the_v1_defaults():
    from api.main import DEFAULT_GOAL
    c = cases.default_case()
    assert (c.id, c.uniprot_a, c.uniprot_b, c.benchmark) == ("fat10_mad2", "O15205", "Q13257", False)
    assert c.goal == GOAL == DEFAULT_GOAL
    assert c.ground_truth is None                       # no experimental complex exists
    assert c.md_scores == "analysis/md_interface_scores.json"
    assert cases.find_case("fat10_mad2") == c


def test_fat10_run_uses_v1_prompt_and_tool_schema(fake_llm):
    client = fake_llm([_submit])
    run_agent.run(GOAL, verbose=False)
    first = client.requests[0]
    assert first["messages"][0]["content"] == run_agent.SYSTEM_PROMPT
    assert first["tools"] is tools.TOOLS
    sub = next(t for t in tools.TOOLS if t["function"]["name"] == "submit_adjudication")
    assert "predicted_regions" not in sub["function"]["parameters"]["properties"]


def test_fat10_tools_return_the_real_v1_evidence():
    md = tools.get_md_interface_scores()
    with open("analysis/md_interface_scores.json", encoding="utf-8") as fh:
        method, occ = next(iter(json.load(fh).items()))
    assert md["method"] == method and md["occupancy"] == occ
    assert tools.get_expected_interface_region()["residue_range"] == [6, 81]
    assert tools.list_interface_tools()["available_real"] == [method]
    assert tools.map_residues(["X6", "X82"], "O15205")["mappings"][0]["in_nterm_ubl"] is True


# --- benchmark case files ---------------------------------------------------------
def test_benchmark_cases_match_the_committed_evidence():
    assert len(BENCH) == 5
    for c in BENCH:
        gt = EVIDENCE[c.ground_truth["pdb"]]
        assert c.benchmark and c.md_scores is None
        for acc in (c.uniprot_a, c.uniprot_b):
            assert c.ground_truth["interface_residues"][acc] == gt["proteins"][acc]["interface_residues"]
        assert c.ground_truth["pdb"] in gt["co_complex_entries"]
        # the goal shown to the agent carries no answer
        assert c.ground_truth["pdb"] not in c.goal


# --- benchmark pairs: no data -> pending, never placeholders ----------------------
@pytest.mark.parametrize("case", BENCH, ids=lambda c: c.id)
def test_benchmark_tools_report_pending(case):
    cases.set_active_case(case)
    assert tools.get_md_interface_scores()["status"] == "pending"
    assert tools.list_interface_tools()["available_real"] == []
    assert tools.get_tool_prediction("PISA")["status"] == "pending"     # PISA is the ground truth
    assert tools.convene_debate()["status"] == "pending"


# --- leakage: structures ----------------------------------------------------------
@pytest.mark.parametrize("case", BENCH, ids=lambda c: c.id)
def test_structure_filter_removes_every_co_complex_entry(case, monkeypatch):
    monkeypatch.setenv("PDBE_SOURCE", "mcp")
    banned = {e.upper() for e in EVIDENCE[case.ground_truth["pdb"]]["co_complex_entries"]}
    hits = [StructureHit(e.lower(), "complex", "X-ray diffraction", 2.0, "fake") for e in sorted(banned)]
    hits.append(StructureHit("9zzz", "apo structure of one partner", "X-ray diffraction", 2.0, "fake"))
    monkeypatch.setattr(tools, "mcp_structures", lambda uniprot: hits)
    cases.set_active_case(case)
    out = tools.fetch_structures(case.uniprot_a)
    assert [s["pdb_id"] for s in out["structures"]] == ["9zzz"]
    assert case.ground_truth["pdb"].lower() not in json.dumps(out).lower()


def test_v1_case_structures_are_not_filtered(monkeypatch):
    monkeypatch.setenv("PDBE_SOURCE", "mcp")
    hits = [StructureHit("1fin", "anything", None, None, "fake")]
    monkeypatch.setattr(tools, "mcp_structures", lambda uniprot: hits)
    assert [s["pdb_id"] for s in tools.fetch_structures("O15205")["structures"]] == ["1fin"]


# --- leakage: literature ----------------------------------------------------------
def test_literature_excludes_the_co_complex_papers(monkeypatch):
    case = cases.find_case("rash_raf1")
    seen = {}

    def fake_search(query, retmax=5, exclude_pmids=()):
        seen.update(query=query, exclude=set(exclude_pmids))
        return ["111"], "abstract text"

    monkeypatch.setattr(literature, "search_pubmed", fake_search)
    cases.set_active_case(case)
    out = tools.search_literature()
    assert seen["query"] == case.literature_query
    assert seen["exclude"] == set(EVIDENCE["4G0N"]["co_complex_pmids"]) and "34356620" in seen["exclude"]
    assert out["retrieved_live"] is True


def test_search_pubmed_drops_excluded_pmids(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["1", "34356620", "2", "3"]}})
        return "abstracts"

    monkeypatch.setattr(literature, "_get", fake_get)
    ids, _ = literature.search_pubmed("q", retmax=3, exclude_pmids={"34356620"})
    assert ids == ["1", "2", "3"]
    assert "34356620" not in calls[-1]


def test_benchmark_literature_failure_makes_no_fabricated_claim():
    cases.set_active_case(cases.find_case("mdm2_p53"))
    out = tools.search_literature()                        # network is blocked in tests
    assert out["retrieved_live"] is False and "fallback" not in out


# --- leakage: the guard in the agent loop ------------------------------------------
@pytest.mark.parametrize("case", BENCH, ids=lambda c: c.id)
def test_ground_truth_pdb_id_never_reaches_the_agent(case, fake_llm, monkeypatch):
    gt = case.ground_truth["pdb"]
    # a tool that (wrongly) mentions the held-out complex, in a lower-case sentence
    monkeypatch.setitem(tools.DISPATCH, "get_expected_interface_region",
                        lambda **kw: {"note": f"see the complex {gt.lower()} for details"})

    def ask(msgs):
        return "look", [("get_expected_interface_region", {})]

    client = fake_llm([ask, _submit])
    run_agent.run(case.goal, verbose=False, case=case)
    seen = [m["content"] for m in client.requests[-1]["messages"] if m.get("role") == "tool"]
    assert seen and all(gt.lower() not in s.lower() for s in seen)
    assert json.loads(seen[0]) == leakage.WITHHELD


def test_guard_ignores_ids_that_only_look_similar():
    case = cases.find_case("cdk2_ccna2")
    assert leakage.guard({"x": "sequence 1FINGER"}, case) == {"x": "sequence 1FINGER"}
    assert leakage.guard({"x": "entry 1FIN."}, case) == leakage.WITHHELD


# --- benchmark run plumbing ---------------------------------------------------------
def test_benchmark_run_uses_generic_prompt_and_region_schema(fake_llm):
    case = cases.find_case("mdm2_p53")
    client = fake_llm([_submit])
    run_agent.run(case.goal, verbose=False, case=case)
    first = client.requests[0]
    assert first["messages"][0]["content"] == run_agent.PAIR_PROMPT
    assert "FAT10" not in run_agent.PAIR_PROMPT and "MAD2" not in run_agent.PAIR_PROMPT
    sub = next(t for t in first["tools"] if t["function"]["name"] == "submit_adjudication")
    assert "predicted_regions" in sub["function"]["parameters"]["required"]
    mp = next(t for t in first["tools"] if t["function"]["name"] == "map_residues")
    assert {"domain_lo", "domain_hi"} <= set(mp["function"]["parameters"]["required"])
    assert first["tools"] is not tools.TOOLS            # the v1 schema object is untouched


def test_benchmark_map_residues_needs_explicit_domain(fake_llm):
    case = cases.find_case("mdm2_p53")

    def ask(msgs):
        return "map", [("map_residues", {"residues": ["A26"], "uniprot": case.uniprot_a})]

    def check(msgs):
        assert "domain_lo" in tool_result(msgs, "map_residues")["error"]
        return _submit(msgs)

    fake_llm([ask, check])
    run_agent.run(case.goal, verbose=False, case=case)


def test_run_log_records_the_case(fake_llm, runlog_path):
    fake_llm([_submit])
    run_agent.run(GOAL, verbose=False)
    line = json.loads(runlog_path.read_text(encoding="utf-8").splitlines()[-1])
    assert line["case"] == "fat10_mad2"


def test_benchmark_ignores_off_schema_arguments(fake_llm, tmp_path):
    case = cases.find_case("mdm2_p53")
    secret = tmp_path / "scores.json"
    secret.write_text(json.dumps({"fake_method": {"A1": 1.0}}), encoding="utf-8")

    def ask(msgs):
        return "read", [("get_md_interface_scores", {"scores_path": str(secret)})]

    def check(msgs):
        assert tool_result(msgs, "get_md_interface_scores")["status"] == "pending"
        return _submit(msgs)

    fake_llm([ask, check])
    run_agent.run(case.goal, verbose=False, case=case)


def test_a_run_restores_the_previous_case(fake_llm):
    case = cases.find_case("mdm2_p53")
    fake_llm([_submit])
    run_agent.run(case.goal, verbose=False, case=case)
    assert cases.active_case().id == "fat10_mad2"          # the benchmark case did not leak out
    assert tools.get_expected_interface_region()["residue_range"] == [6, 81]
