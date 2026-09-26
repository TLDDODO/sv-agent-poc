"""S8: README v2 and business case are generated from results/*.json (no hand-typed numbers)."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_docs as gd  # noqa: E402


def _read(p):
    return gd._read(p)


def _sandbox(tmp_path, mutate=None):
    (tmp_path / "docs").mkdir()
    (tmp_path / "results").mkdir()
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    shutil.copy(ROOT / "docs" / "business_case.md", tmp_path / "docs" / "business_case.md")
    data = json.loads((ROOT / "results" / "benchmark.json").read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    (tmp_path / "results" / "benchmark.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def _write_all(root):
    for rel, text in gd.render_all(root).items():
        with (root / rel).open("w", encoding="utf-8", newline="") as fh:
            fh.write(text)


def test_committed_files_are_up_to_date():
    assert gd.main(["--check"]) == 0


def test_generating_twice_gives_no_diff(tmp_path):
    _sandbox(tmp_path)
    _write_all(tmp_path)
    first = {r: _read(tmp_path / r) for r in gd.BLOCKS}
    _write_all(tmp_path)
    assert {r: _read(tmp_path / r) for r in gd.BLOCKS} == first
    # the sandbox result equals the committed files (which were produced the same way)
    assert first == {r: _read(ROOT / r) for r in gd.BLOCKS}


def test_line_endings_are_preserved(tmp_path):
    _sandbox(tmp_path)
    before = (tmp_path / "README.md").read_bytes().count(b"\r\n")
    _write_all(tmp_path)
    assert (tmp_path / "README.md").read_bytes().count(b"\r\n") >= before


def test_numbers_come_only_from_the_json(tmp_path):
    def mutate(d):
        d["overall"]["agent"]["mean_score"] = 0.777
        d["overall"]["baseline"]["mean_score"] = 0.123
        d["cases"][0]["agent"]["mean_score"] = 0.611
        for r in d["cases"][0]["agent"]["runs"]:
            r["cost_usd"] = 1.0
    _sandbox(tmp_path, mutate)
    _write_all(tmp_path)
    readme, biz = _read(tmp_path / "README.md"), _read(tmp_path / "docs" / "business_case.md")
    assert "**0.78**" in readme and "**0.12**" in readme and "| 0.61 |" in readme
    assert "agent 0.78" in biz and "0.12" in biz
    assert "0.43" not in readme and "0.43" not in biz       # the old value is gone


def test_business_case_manual_time_is_tbd_and_untyped(tmp_path):
    biz = _read(ROOT / "docs" / "business_case.md")
    row = next(l for l in biz.splitlines() if l.startswith("| 人工流程"))
    assert row.count("TBD — 人工基线") == 4 and not re.search(r"\d", row)


@pytest.mark.parametrize("state", ["dry_run", "blocked", "missing"])
def test_no_numbers_from_dry_run_blocked_or_missing_results(tmp_path, state):
    def mutate(d):
        if state == "dry_run":
            d["dry_run"] = True
        elif state == "blocked":
            d.clear()
            d.update({"status": "BLOCKED", "reason": "no key"})
    _sandbox(tmp_path, mutate)
    if state == "missing":
        (tmp_path / "results" / "benchmark.json").unlink()
    _write_all(tmp_path)
    for rel, name in (("README.md", "BENCHMARK"), ("docs/business_case.md", "BUSINESS")):
        block = re.search(rf"GENERATED:{name}:START -->\r?\n(.*?)\r?\n<!-- GENERATED:{name}:END",
                          _read(tmp_path / rel), re.S).group(1)
        assert not re.search(r"\d\.\d|\$\d|%", block), (rel, block)


def test_hand_written_text_has_no_metrics():
    for rel in ("README.md", "docs/business_case.md"):
        text = re.sub(r"<!-- GENERATED:(\w+):START -->.*?<!-- GENERATED:\1:END -->", "",
                      _read(ROOT / rel), flags=re.S)
        assert not re.search(r"\d\s*%", text), rel
        assert not re.search(r"\d+\.\d+", re.sub(r"\d+\.\d+\.\d+", "", text)) or rel == "README.md", rel
        assert not re.search(r"\$\s*\d", text), rel
    readme = _read(ROOT / "README.md")
    # the only hand-written decimals in the README are pre-existing v1 facts, none are benchmark scores
    results = json.loads((ROOT / "results" / "benchmark.json").read_text(encoding="utf-8"))
    scores = {f"{results['overall'][a]['mean_score']:.2f}" for a in ("agent", "baseline")}
    outside = re.sub(r"<!-- GENERATED:(\w+):START -->.*?<!-- GENERATED:\1:END -->", "", readme, flags=re.S)
    assert not any(s in outside for s in scores)


def test_each_generated_marker_appears_exactly_once():
    for rel, (name, _) in gd.BLOCKS.items():
        text = _read(ROOT / rel)
        assert text.count(f"GENERATED:{name}:START") == 1 and text.count(f"GENERATED:{name}:END") == 1


def test_readme_status_matches_the_recorded_live_checks():
    readme = _read(ROOT / "README.md")
    progress = (ROOT / "docs" / "progress.md").read_text(encoding="utf-8")
    assert "2026-09-26" in readme and "PASSED 2/2" in progress          # the live checks it cites happened
    assert "v1 → v2" in readme and "Honest status" in readme
    assert "not walked through on a real Dify" in readme                 # unverified things stay marked


def test_files_named_in_the_readme_exist():
    readme = _read(ROOT / "README.md")
    for rel in re.findall(r"`((?:docs|scripts|results|benchmark|cases|agent)/[\w./-]+\.(?:md|py|json|yaml|jsonl))`", readme):
        assert (ROOT / rel).exists(), rel
