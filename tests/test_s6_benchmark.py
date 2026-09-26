"""S6: scoring rule, no-tool baseline, benchmark runner (dry-run, fake client, offline)."""
import json
import os

import pytest

from agent import baseline, benchmark, cases, run_agent, scoring
from agent.scoring import score_case, score_protein
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_benchmark as cli  # noqa: E402

T = list(range(41, 51))          # true residues 41..50, span 10


# --- scoring rule (approved thresholds: recall >= 50%, predicted length <= 2x true span) ---
def _reg(lo, hi, acc="P1"):
    return [{"uniprot": acc, "start": lo, "end": hi}]


def test_exact_prediction_is_a_hit():
    s = score_protein(_reg(41, 50), "P1", T)
    assert s["hit"] and s["recall"] == 1 and s["f1"] == 1 and s["jaccard"] == 1


def test_recall_threshold_is_inclusive_at_half():
    assert score_protein(_reg(46, 50), "P1", T)["hit"]            # recall exactly 0.5
    assert not score_protein(_reg(47, 50), "P1", T)["hit"]        # recall 0.4


def test_span_limit_is_twice_the_true_span():
    assert score_protein(_reg(41, 60), "P1", T)["hit"]            # length 20 == 2 x 10
    assert not score_protein(_reg(41, 61), "P1", T)["hit"]        # length 21
    assert not score_protein(_reg(1, 300), "P1", T)["hit"]        # whole chain does not count


def test_missing_wrong_or_malformed_prediction_is_a_miss():
    for regions in (None, [], _reg(41, 50, acc="OTHER"), _reg(50, 41),
                    [{"uniprot": "P1", "start": "x", "end": 5}], [{"uniprot": "P1"}], _reg(0, 0)):
        assert not score_protein(regions, "P1", T)["hit"]


def test_ranges_are_unioned_and_case_score_is_the_mean():
    two = _reg(41, 45) + _reg(46, 50)
    assert score_protein(two, "P1", T)["hit"]
    s = score_case(_reg(41, 50, "A") + _reg(1, 5, "B"), {"A": T, "B": T})
    assert s["score"] == 0.5 and s["per_protein"]["A"]["hit"] and not s["per_protein"]["B"]["hit"]


def test_f1_and_jaccard_values():
    s = score_protein(_reg(41, 45), "P1", T)                      # 5 of 10 found, 5 predicted
    assert (s["recall"], s["f1"], s["jaccard"]) == (0.5, pytest.approx(2 / 3), 0.5)


# --- no-tool baseline ---------------------------------------------------------------------
def test_baseline_parser():
    ok = baseline.parse_regions('```json\n{"regions": [{"uniprot": "P1", "start": 1, "end": 9}], "confidence": 0.4}\n```')
    assert ok["predicted_regions"] == _reg(1, 9) and ok["confidence"] == 0.4
    assert baseline.parse_regions("I do not know")["parse_error"] is True
    assert baseline.parse_regions('{"regions": "nope"}')["parse_error"] is True
    assert baseline.parse_regions(None)["parse_error"] is True


def test_baseline_makes_one_call_without_tools_and_logs_it(monkeypatch, runlog_path):
    from fakes import FakeClient
    case = cases.find_case("mdm2_p53")
    client = FakeClient([lambda m: (json.dumps({"regions": _reg(1, 5, case.uniprot_a)}), [])])
    monkeypatch.setattr(baseline, "make_client", lambda: client)
    result, line = baseline.run_baseline(case)
    (req,) = client.requests
    assert "tools" not in req and len(req["messages"]) == 1
    prompt = req["messages"][0]["content"]
    assert case.uniprot_a in prompt and case.ground_truth["pdb"] not in prompt
    assert result["predicted_regions"] == _reg(1, 5, case.uniprot_a)
    logged = json.loads(runlog_path.read_text(encoding="utf-8").splitlines()[-1])
    assert logged["kind"] == "baseline" and logged["case"] == case.id and logged["llm_calls"] == 1


# --- runner (dry run) ---------------------------------------------------------------------
def test_dry_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNLOG_PATH", raising=False)
    data = benchmark.run_benchmark(cases.load_benchmark(), 2, dry_run=True)
    assert data["status"] == "ok" and data["dry_run"] is True and data["runs_per_case"] == 2
    assert len(data["cases"]) == 5
    for c in data["cases"]:
        for arm in ("agent", "baseline"):
            assert c[arm]["n_runs"] == 2 and c[arm]["n_errors"] == 0
            assert c[arm]["stability"] == 1.0
            assert c[arm]["mean_cost_usd"] is not None          # from the run-log lines
            assert c[arm]["median_latency_s"] is not None
            # the placeholder (residues 1-10) is blind to the truth and misses every protein
            assert c[arm]["mean_score"] == 0 and c[arm]["protein_hits"] == 0
        assert [r["tools"] for r in c["agent"]["runs"]] == [["get_md_interface_scores", "submit_adjudication"]] * 2
    assert data["overall"]["agent"]["n_runs"] == 10
    assert "RUNLOG_PATH" not in os.environ                       # runner restored the environment
    assert run_agent.make_client.__module__ == "agent.llm_client"  # ...and the real client factory


def test_dry_run_does_not_write_the_real_run_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RUNLOG_PATH", raising=False)
    benchmark.run_benchmark(cases.load_benchmark()[:1], 1, dry_run=True)
    assert not (tmp_path / "results" / "runs.jsonl").exists()


def test_failed_runs_are_counted_not_hidden(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise TimeoutError("api down")

    monkeypatch.setattr(run_agent, "run", boom)
    data = benchmark.run_benchmark(cases.load_benchmark()[:1], 2, dry_run=True)
    a = data["cases"][0]["agent"]
    assert a["n_errors"] == 2 and a["mean_score"] == 0
    assert "TimeoutError" in a["runs"][0]["error"]
    assert data["overall"]["baseline"]["n_errors"] == 0


def test_stability_is_the_share_of_runs_with_the_modal_outcome():
    def run(hit_a, hit_b):
        return {"score": (hit_a + hit_b) / 2, "error": None, "latency_s": 1.0, "cost_usd": 0.1,
                "per_protein": {"A": {"hit": hit_a}, "B": {"hit": hit_b}}}
    s = benchmark._summarise([run(True, True), run(True, True), run(True, False)])
    assert s["stability"] == pytest.approx(2 / 3) and s["mean_score"] == pytest.approx(5 / 6)
    assert (s["protein_hits"], s["protein_total"]) == (5, 6)


# --- report reads only the JSON -------------------------------------------------------------
def test_cli_dry_run_writes_json_and_matching_markdown(tmp_path):
    assert cli.main(["--dry-run", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    md = (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert md == benchmark.render_markdown(data)
    assert "DRY RUN" in md and "not accuracy" in md.lower()
    assert "training" in md and "no tools" in md              # the honest baseline caveat
    for c in data["cases"]:
        assert c["id"] in md and c["ground_truth_pdb"] in md
    # rendering again from the JSON alone reproduces the file
    assert cli.main(["--render-only", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "benchmark.md").read_text(encoding="utf-8") == md
    # no true residues are written into the results
    assert "interface_residues" not in json.dumps(data)


def test_every_number_in_the_report_comes_from_the_json():
    data = benchmark.run_benchmark(cases.load_benchmark()[:1], 1, dry_run=True)
    data["overall"]["agent"]["mean_score"] = 0.37
    data["overall"]["baseline"]["mean_score"] = 0.11
    data["scoring"]["recall_min"] = 0.7
    md = benchmark.render_markdown(data)
    assert "0.37" in md and "0.11" in md and "70%" in md and "+0.26" in md


def test_without_a_key_the_live_run_is_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert cli.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert data["status"] == "BLOCKED" and "cases" not in data
    assert "BLOCKED" in (tmp_path / "benchmark.md").read_text(encoding="utf-8")
