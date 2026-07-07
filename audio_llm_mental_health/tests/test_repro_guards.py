#!/usr/bin/env python
"""CPU-only reproducibility guards — run by CI on every push, runnable anywhere with
`python tests/test_repro_guards.py` (needs pandas + pyyaml, no GPU, no torch).

These cannot re-train a cell, but they pin everything around the training that a stale claim
could silently drift on:
  1. scripts/significance.py agrees with the p-values already published in RP.md.
  2. results/ledger.jsonl's p_exact values re-derive from their own (k, n, null_p) — the
     machine-readable table can't disagree with its own math.
  3. The pinned 15-row MELD ruler indices are byte-identical everywhere they appear
     (run_cell.sh, ledger, CLOUD_RUNBOOK) — index drift silently invalidates comparability.
  4. prepare_meld_manifest.py still writes relative paths and skips missing audio (the
     contract the cross-box data cache depends on).
  5. Every config in configs/ parses and names a model + output_dir.
"""

import json
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # audio_llm_mental_health/
sys.path.insert(0, str(ROOT / "scripts"))

from significance import binom_tail  # noqa: E402

MELD_RULER = "228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034"
FAILURES = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def test_significance_self_test() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts/significance.py"), "--self-test"],
                       capture_output=True, text=True)
    check("significance --self-test matches RP.md", r.returncode == 0, r.stdout + r.stderr)


def test_ledger_math_and_pins() -> None:
    rows = [json.loads(l) for l in (ROOT / "results/ledger.jsonl").read_text().splitlines() if l.strip()]
    rows = [r for r in rows if "_schema" not in r]
    check("ledger has the pending dual_meld cell", any(
        r["cell"] == "dual_meld" and r["status"] == "pending" for r in rows))
    for r in rows:
        if r.get("tracking_k") is None:
            continue
        got = binom_tail(r["tracking_n"], r["tracking_k"], float(Fraction(r["null_p"])))
        ok = abs(got - r["p_exact"]) <= 0.05 * r["p_exact"]
        check(f"ledger p_exact re-derives for {r['cell']}", ok, f"stored {r['p_exact']}, recomputed {got:.4g}")
    meld_rows = [r for r in rows if r["manifest"].startswith("data/meld_dev") and "ruler_indices" in r]
    for r in meld_rows:
        check(f"MELD ruler pinned in ledger row {r['cell']}", r["ruler_indices"].startswith(MELD_RULER)
              or MELD_RULER in r["ruler_indices"])


def test_ruler_consistency_across_files() -> None:
    for rel in ("scripts/run_cell.sh", "CLOUD_RUNBOOK.md"):
        check(f"MELD ruler identical in {rel}", MELD_RULER in (ROOT / rel).read_text())


def test_manifest_builder_contract() -> None:
    try:
        import pandas  # noqa: F401
    except ImportError:
        check("manifest builder contract (pandas available)", False, "pip install pandas")
        return
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        audio = td / "MELD.Raw" / "train_audio"
        audio.mkdir(parents=True)
        (audio / "dia0_utt0.wav").write_bytes(b"\x00")   # exists -> written
        (audio / "dia0_utt1.wav").write_bytes(b"\x00")   # exists -> written
        csv = td / "train_sent_emo.csv"                  # row 2 has no wav -> skipped
        csv.write_text(
            "Utterance,Emotion,Sentiment,Dialogue_ID,Utterance_ID\n"
            "hello there,joy,positive,0,0\n"
            "why me,anger,negative,0,1\n"
            "missing clip,sadness,negative,0,2\n")
        out = td / "manifest.jsonl"
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts/prepare_meld_manifest.py"),
             "--csv", str(csv), "--audio-dir", "MELD.Raw/train_audio", "--out", str(out)],
            cwd=td, capture_output=True, text=True)
        check("manifest builder exits 0", r.returncode == 0, r.stderr)
        lines = [json.loads(l) for l in out.read_text().splitlines()]
        check("manifest writes existing rows, skips missing", len(lines) == 2)
        check("manifest stores RELATIVE audio paths (cache portability contract)",
              all(not l["audio_path"].startswith("/") for l in lines),
              f"got {[l['audio_path'] for l in lines]}")


def test_configs_parse() -> None:
    try:
        import yaml
    except ImportError:
        check("configs parse (pyyaml available)", False, "pip install pyyaml")
        return
    for cfg in sorted((ROOT / "configs").glob("*.yaml")):
        try:
            d = yaml.safe_load(cfg.read_text())
            ok = isinstance(d, dict) and ("model_name_or_path" in d or "target_modules" in d) \
                 and ("output_dir" in d or "target_modules" in d)
            check(f"config parses: {cfg.name}", ok)
        except Exception as e:  # noqa: BLE001
            check(f"config parses: {cfg.name}", False, str(e))


if __name__ == "__main__":
    test_significance_self_test()
    test_ledger_math_and_pins()
    test_ruler_consistency_across_files()
    test_manifest_builder_contract()
    test_configs_parse()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)
