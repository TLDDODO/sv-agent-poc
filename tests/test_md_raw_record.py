"""The archived HPC session record (analysis/md_raw/) against the committed MD scores and UniProt.

Offline tests read only committed files. The live test compares the topology sequence in the
record with the real UniProt sequences (run with --run-live).
"""
from __future__ import annotations
import json
import urllib.request

import pytest

from analysis import md_raw_check as raw

ROOT = raw.LOG.parents[2]
SCORES = json.loads((ROOT / "analysis" / "md_interface_scores.json").read_text())["MD-contacts(100ns)"]


def _fasta(acc: str) -> str:
    with urllib.request.urlopen(f"https://rest.uniprot.org/uniprotkb/{acc}.fasta", timeout=30) as r:
        return "".join(l.strip() for l in r.read().decode().splitlines() if not l.startswith(">"))


def test_record_shows_both_topology_ranges_and_twelve_pairs():
    res = raw.topology_residues()
    assert all(i in res for i in range(1, 60)) and all(i in res for i in range(291, 371))
    assert len(raw.pairs_rows()) == 12


def test_pairs_agree_with_the_committed_scores():
    rows = raw.pairs_rows()
    best: dict[int, float] = {}                       # FAT10 residue -> highest per-atom-pair fraction
    for r in rows:
        best[r["fat10_res"]] = max(best.get(r["fat10_res"], 0), r["frac"])
    by_score = {int(k[1:]): v for k, v in SCORES.items()}
    for num, frac in best.items():
        assert num in by_score, f"residue {num} in pairs.dat but not in the score file"
        # residue occupancy (any contact in a frame) can only be >= any single atom pair's fraction
        assert by_score[num] >= frac - 1e-9
    ranked = sorted(best, key=best.get, reverse=True)
    top = sorted(by_score, key=by_score.get, reverse=True)[: len(ranked)]
    assert ranked == top                              # 163 then 162 in both


@pytest.mark.live
def test_topology_sequence_matches_uniprot():
    """FAT10 = 1-59 <-> O15205 1-59; MAD2 = 291-370 <-> Q13257 126-205."""
    assert raw.topology_sequence(1, 59) == _fasta("O15205")[0:59]
    assert raw.topology_sequence(291, 370) == _fasta("Q13257")[125:205]
