"""Error injection on the FAT10-MAD2 case: does the agent's validation path catch bad input?

Each injected case starts from the REAL MD residue labels (analysis/md_interface_scores.json)
and corrupts one thing. It is then run through the agent's own tools:
  get_md_interface_scores (for injected score files)  ->  validate_residues (UniProt sequence check).
Outcome per case:
  caught          validate_residues reports mismatches, or UniProt rejects the accession
  passed_through  validate_residues finds nothing wrong (the error is NOT detected)
  inconclusive    the check itself could not run (e.g. UniProt unreachable) — not counted as caught
A control (the uninjected real labels) must pass cleanly first; if it does not, the
whole run is BLOCKED and no intercept rate is produced, so a network failure can never
masquerade as "caught".

The injected data are test inputs written to a temp dir, clearly labelled; they are never
presented as real evidence. Numbers in the report come only from results/error_injection.json.
"""
from __future__ import annotations
import json
import random
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import tools

FAT10 = "O15205"
MAD2 = "Q13257"
MALFORMED = "NOTANACC"
REJECTED_STATUS = (400, 404)         # UniProt says "no such accession"
SEED = 0                                        # fabricated values are reproducible


def _split(label: str) -> tuple[str, int]:
    m = re.match(r"([A-Z])(\d+)$", label)
    return m.group(1), int(m.group(2))


def real_scores(path: str = "analysis/md_interface_scores.json") -> dict:
    with open(path, encoding="utf-8") as fh:
        return next(iter(json.load(fh).values()))


def build_cases(scores: dict) -> list[dict]:
    """Injected cases (+ the control). `scores_file` cases go through get_md_interface_scores."""
    labels = list(scores)
    rng = random.Random(SEED)
    shift = lambda k: [f"{_split(x)[0]}{_split(x)[1] + k}" for x in labels]
    swap = lambda aa: "W" if aa != "W" else "F"
    return [
        {"id": "control_real_labels", "control": True, "uniprot": FAT10, "residues": labels,
         "description": "No injection: the real MD residue labels against FAT10."},
        {"id": "shift_plus_3", "uniprot": FAT10, "residues": shift(3),
         "description": "Residue numbering shifted by +3 (off-by-three)."},
        {"id": "shift_minus_10", "uniprot": FAT10, "residues": shift(-10),
         "description": "Residue numbering shifted by -10 (e.g. a construct offset)."},
        {"id": "beyond_sequence_length", "uniprot": FAT10,
         "residues": labels + ["K166", "L200", "A9999"],
         "description": "Real labels plus residues past the end of the sequence (positions 166, 200, 9999)."},
        {"id": "fabricated_md_wrong_residues", "uniprot": FAT10,
         "scores_file": {f"{swap(_split(x)[0])}{_split(x)[1]}": round(rng.random(), 3) for x in labels},
         "description": "Fabricated MD score file: invented residue identities at real positions."},
        {"id": "fabricated_md_real_labels", "uniprot": FAT10,
         "scores_file": {x: round(rng.random(), 3) for x in labels},
         "description": "Fabricated MD score values on real residue labels."},
        {"id": "wrong_uniprot_other_protein", "uniprot": MAD2, "residues": labels,
         "description": f"FAT10 residues checked against another real protein's accession ({MAD2}, MAD2)."},
        {"id": "wrong_uniprot_malformed", "uniprot": MALFORMED, "residues": labels,
         "description": "Accession that is not a UniProt accession."},
    ]


def judge(out: dict) -> tuple[str, dict]:
    """Classify one validate_residues output."""
    if "error" in out:
        # only 400 / 404 mean UniProt answered and rejected the accession; a 429, a 5xx, a
        # timeout or a network error means the check did not run
        ev = {"error": out["error"], "http_status": out.get("http_status")}
        return ("caught" if out.get("http_status") in REJECTED_STATUS else "inconclusive"), ev
    bad = [v["residue"] for v in out["validated"] if not v.get("valid")]
    ev = {"sequence_length": out["sequence_length"], "n_mismatches": out["n_mismatches"],
          "mismatched": bad}
    return ("caught" if out["n_mismatches"] > 0 else "passed_through"), ev


def run_error_injection(scores_path: str = "analysis/md_interface_scores.json") -> dict:
    scores = real_scores(scores_path)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in build_cases(scores):
            residues = case.get("residues")
            if "scores_file" in case:                   # through the agent's own MD tool
                p = Path(tmp) / f"{case['id']}.json"
                p.write_text(json.dumps({"INJECTED-FABRICATED": case["scores_file"]}), encoding="utf-8")
                residues = list(tools.get_md_interface_scores(str(p))["occupancy"])
            outcome, evidence = judge(tools.validate_residues(case["uniprot"], residues))
            results.append({"id": case["id"], "control": bool(case.get("control")),
                            "description": case["description"], "uniprot": case["uniprot"],
                            "n_labels": len(residues), "outcome": outcome, "evidence": evidence})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    control = next(r for r in results if r["control"])
    if control["outcome"] != "passed_through":          # the check could not be trusted
        return {"status": "BLOCKED", "generated_at": stamp,
                "reason": "the control (uninjected real labels) did not validate cleanly "
                          f"({control['outcome']}: {control['evidence']}); no intercept rate produced",
                "control": control}
    injected = [r for r in results if not r["control"]]
    n = lambda o: sum(1 for r in injected if r["outcome"] == o)
    return {"status": "ok", "generated_at": stamp, "control": control, "cases": injected,
            "summary": {"injected": len(injected), "caught": n("caught"),
                        "passed_through": n("passed_through"), "inconclusive": n("inconclusive"),
                        "intercept_rate": n("caught") / len(injected)}}
