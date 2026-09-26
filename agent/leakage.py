"""Answer-leakage prevention for benchmark cases (docs/benchmark_design.md section 5).

For a benchmark pair the agent must not see ANY experimental complex of the two
proteins, nor the papers that report them:
  * structures: every PDBe entry that contains both proteins is removed (not just the
    ground-truth ID). The set is the live PDBe intersection unioned with the committed
    docs/benchmark_evidence/evidence.json, so offline runs still filter;
  * literature: PMIDs published for those entries are removed;
  * guard(): any tool output that still mentions one of those PDB IDs is withheld.
If the filter set cannot be built at all, callers get nothing rather than unfiltered data.
"""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .cases import Case

EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "docs" / "benchmark_evidence" / "evidence.json"
WITHHELD = {"error": "withheld: this output referenced a held-out experimental complex "
                     "of the pair under study (benchmark leakage guard)"}


def _committed(case: Case) -> dict:
    try:
        ev = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        return ev["cases"][(case.ground_truth or {})["pdb"]]
    except Exception:
        return {}


def _live_entries(acc: str, timeout: float = 20) -> set[str]:
    q = urllib.parse.urlencode({"q": f"uniprot_accession:{acc}", "fl": "pdb_id",
                                "rows": "20000", "wt": "json"})
    with urllib.request.urlopen("https://www.ebi.ac.uk/pdbe/search/pdb/select?" + q,
                                timeout=timeout) as r:
        return {d["pdb_id"].upper() for d in json.load(r)["response"]["docs"]}


def co_complex_entries(case: Case) -> set[str]:
    """PDB IDs of every entry containing both proteins (empty set = filter unavailable)."""
    ids = {x.upper() for x in _committed(case).get("co_complex_entries", [])}
    if case.ground_truth:
        ids.add(case.ground_truth["pdb"].upper())
    try:
        ids |= _live_entries(case.uniprot_a) & _live_entries(case.uniprot_b)
    except Exception:
        pass                                  # offline: the committed set still applies
    return ids


def co_complex_pmids(case: Case) -> set[str]:
    return set(_committed(case).get("co_complex_pmids", {}))


def filter_structures(out: dict, case: Case) -> dict:
    banned = co_complex_entries(case)
    if not banned:
        return {"uniprot": out.get("uniprot"), "source": "withheld", "structures": [],
                "note": "leak filter unavailable, so no structures are shown"}
    kept = [s for s in out.get("structures", []) if s.get("pdb_id", "").upper() not in banned]
    res = dict(out, structures=kept)
    dropped = len(out.get("structures", [])) - len(kept)
    if dropped:
        res["note"] = f"{dropped} entries containing both proteins withheld"
    return res


def guard(out, case: Case):
    """Withhold a tool output that mentions any held-out PDB ID."""
    banned = co_complex_entries(case)
    if not banned:
        return out
    pat = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(sorted(banned)) + r")(?![A-Za-z0-9])", re.I)
    return WITHHELD if pat.search(json.dumps(out, default=str)) else out
