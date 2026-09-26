"""S6b: FAT10-MAD2 error injection. Offline: UniProt is replaced by SYNTHETIC sequences
(a fixture, not real proteins): the "FAT10" one is built so the real committed MD labels
match at their positions; the "MAD2" one is a different, all-glycine sequence."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

from agent import benchmark, cases, error_injection as ei, tools

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_error_injection as cli  # noqa: E402


class _Resp:
    def __init__(self, text):
        self._b = text.encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _synthetic_fat10() -> str:
    seq = ["A"] * 165
    for lab in ei.real_scores():
        aa, pos = ei._split(lab)
        seq[pos - 1] = aa
    return "".join(seq)


def _serve(monkeypatch, mad2_error=None):
    def fake(url, timeout=20):
        acc = url.rsplit("/", 1)[1].split(".")[0]
        if acc == ei.FAT10:
            return _Resp(f">synthetic\n{_synthetic_fat10()}\n")
        if acc == ei.MAD2:
            if mad2_error:
                raise mad2_error
            return _Resp(">synthetic\n" + "G" * 205 + "\n")
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b""))

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake)


EXPECTED = {
    "shift_plus_3": "caught",
    "shift_minus_10": "caught",
    "beyond_sequence_length": "caught",
    "fabricated_md_wrong_residues": "caught",
    "fabricated_md_real_labels": "passed_through",      # known limit: invented values are undetectable
    "wrong_uniprot_other_protein": "caught",
    "wrong_uniprot_malformed": "caught",
}


def test_each_injected_error_is_caught_or_counted_as_a_miss(monkeypatch):
    _serve(monkeypatch)
    data = ei.run_error_injection()
    assert data["status"] == "ok" and data["control"]["outcome"] == "passed_through"
    assert data["control"]["evidence"]["n_mismatches"] == 0            # no false alarm on real labels
    assert {c["id"]: c["outcome"] for c in data["cases"]} == EXPECTED
    s = data["summary"]
    assert (s["injected"], s["caught"], s["passed_through"], s["inconclusive"]) == (7, 6, 1, 0)
    assert s["intercept_rate"] == 6 / 7


def test_at_least_the_four_required_error_kinds_are_present():
    kinds = {c["id"] for c in ei.build_cases(ei.real_scores())}
    assert {"shift_plus_3", "beyond_sequence_length", "fabricated_md_wrong_residues",
            "wrong_uniprot_other_protein"} <= kinds


def test_injected_inputs_differ_from_the_real_data_and_are_reproducible():
    real = ei.real_scores()
    a, b = ei.build_cases(real), ei.build_cases(real)
    assert a == b
    by = {c["id"]: c for c in a}
    assert by["control_real_labels"]["residues"] == list(real)
    assert by["shift_plus_3"]["residues"] != list(real)
    assert any(int(x[1:]) > 165 for x in by["beyond_sequence_length"]["residues"])
    assert set(by["fabricated_md_wrong_residues"]["scores_file"]) & set(real) == set()
    assert set(by["fabricated_md_real_labels"]["scores_file"]) == set(real)
    assert by["fabricated_md_real_labels"]["scores_file"] != real


def test_a_failed_check_is_inconclusive_never_caught(monkeypatch):
    _serve(monkeypatch, mad2_error=urllib.error.URLError("network down"))
    data = ei.run_error_injection()
    cases_ = {c["id"]: c["outcome"] for c in data["cases"]}
    assert cases_["wrong_uniprot_other_protein"] == "inconclusive"
    assert data["summary"]["inconclusive"] == 1 and data["summary"]["caught"] == 5


@pytest.mark.parametrize("status,outcome", [(400, "caught"), (404, "caught"),
                                            (429, "inconclusive"), (503, "inconclusive")])
def test_only_a_400_or_404_counts_as_a_rejected_accession(status, outcome):
    err = {"error": "could not fetch UniProt X: HTTPError", "http_status": status, "validated": []}
    assert ei.judge(err)[0] == outcome
    assert ei.judge({"error": "could not fetch UniProt X: URLError", "validated": []})[0] == "inconclusive"


def test_a_server_error_on_one_case_is_not_counted_as_caught(monkeypatch):
    _serve(monkeypatch)
    real = tools.urllib.request.urlopen

    def flaky(url, timeout=20):
        if "NOTANACC" in url:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(b""))
        return real(url, timeout)

    monkeypatch.setattr(tools.urllib.request, "urlopen", flaky)
    data = ei.run_error_injection()
    assert {c["id"]: c["outcome"] for c in data["cases"]}["wrong_uniprot_malformed"] == "inconclusive"
    assert data["summary"]["caught"] == 5 and data["summary"]["inconclusive"] == 1


def test_no_network_blocks_instead_of_reporting_a_rate():
    data = ei.run_error_injection()                       # network is blocked by conftest
    assert data["status"] == "BLOCKED" and "summary" not in data
    assert "control" in data["reason"]


def test_fabricated_scores_go_through_the_agents_md_tool(monkeypatch):
    _serve(monkeypatch)
    seen = []
    real = tools.get_md_interface_scores
    monkeypatch.setattr(tools, "get_md_interface_scores", lambda p=None: (seen.append(p), real(p))[1])
    ei.run_error_injection()
    assert len(seen) == 2 and all(p.endswith(".json") for p in seen)


# --- report ---------------------------------------------------------------------------------
def test_cli_folds_the_intercept_rate_into_the_benchmark_report(tmp_path, monkeypatch):
    _serve(monkeypatch)
    bench = benchmark.run_benchmark(cases.load_benchmark()[:1], 1, dry_run=True)
    benchmark.write_outputs(bench, tmp_path)
    assert "Error injection" not in (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert cli.main(["--out", str(tmp_path)]) == 0
    ej = json.loads((tmp_path / "error_injection.json").read_text(encoding="utf-8"))
    merged = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    md = (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert merged["error_injection"] == ej
    assert md == benchmark.render_markdown(merged)
    s = ej["summary"]
    assert f"Intercept rate: {s['caught']} of {s['injected']} injected errors caught" in md
    assert "passed_through" in md and "NOT detected" in md
    # a later benchmark rewrite keeps the section
    benchmark.write_outputs(bench, tmp_path)
    assert "Intercept rate" in (tmp_path / "benchmark.md").read_text(encoding="utf-8")


def test_blocked_error_injection_is_reported_as_blocked(tmp_path):
    bench = benchmark.run_benchmark(cases.load_benchmark()[:1], 1, dry_run=True)
    (tmp_path / "error_injection.json").write_text(json.dumps(ei.run_error_injection()), encoding="utf-8")
    benchmark.write_outputs(bench, tmp_path)
    md = (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert "BLOCKED" in md and "No intercept rate was produced" in md
