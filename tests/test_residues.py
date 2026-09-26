"""Unit tests for validate_residues and map_residues.

validate_residues normally fetches the UniProt FASTA. The offline tests feed it a
SYNTHETIC sequence under a synthetic accession ("SYNTH1") to test the logic only; it
is not a real protein. The real O15205 check is the `live` test at the bottom.
"""
import json

import pytest

from agent import tools

SYNTH_ACC = "SYNTH1"
SYNTH_SEQ = "MACDEFGHIK"          # synthetic test fixture, 10 residues


class _Resp:
    def __init__(self, text):
        self._b = text.encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve_synthetic(monkeypatch):
    seen = []

    def fake_urlopen(url, timeout=20):
        seen.append(url)
        return _Resp(f">synthetic|{SYNTH_ACC}|test fixture\n{SYNTH_SEQ}\n")

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_validate_residues_flags_matches_and_mismatches(monkeypatch):
    seen = _serve_synthetic(monkeypatch)
    out = tools.validate_residues(SYNTH_ACC, ["M1", "C3", "A3", "K10", "K11", "9K"])

    assert seen == [f"https://rest.uniprot.org/uniprotkb/{SYNTH_ACC}.fasta"]
    assert out["sequence_length"] == len(SYNTH_SEQ)
    by = {v["residue"]: v for v in out["validated"]}
    assert by["M1"]["valid"] and by["C3"]["valid"] and by["K10"]["valid"]
    assert not by["A3"]["valid"] and by["A3"]["actual_in_sequence"] == "C"
    assert not by["K11"]["valid"] and by["K11"]["actual_in_sequence"] is None
    assert not by["9K"]["valid"] and by["9K"]["reason"] == "unparseable label"
    assert out["n_mismatches"] == 3


def test_validate_residues_reports_ungrounded_when_offline():
    out = tools.validate_residues("O15205", ["I163"])      # network blocked by conftest
    assert "error" in out and out["validated"] == []
    assert "NOT grounded" in out["note"]


def test_map_residues_domain_membership():
    out = tools.map_residues(["K31", "I163", "G164"], "O15205", domain_lo=6, domain_hi=81)
    m = {x["residue_label"]: x for x in out["mappings"]}
    assert m["K31"]["in_nterm_ubl"] is True
    assert m["I163"]["in_nterm_ubl"] is False and m["G164"]["in_nterm_ubl"] is False
    assert (m["K31"]["residue_name"], m["I163"]["residue_name"], m["G164"]["residue_name"]) \
        == ("LYS", "ILE", "GLY")
    assert m["I163"]["canonical_uniprot_position"] == 163
    assert all(x["canonical_uniprot_accession"] == "O15205" for x in out["mappings"])


def test_map_residues_skips_unparseable_labels():
    assert tools.map_residues(["31K", "k31", ""], "O15205")["mappings"] == []


@pytest.mark.live
def test_md_labels_match_real_uniprot_sequence():
    """Live: every residue label in the committed MD scores matches UniProt O15205."""
    with open("analysis/md_interface_scores.json") as fh:
        labels = list(next(iter(json.load(fh).values())))
    out = tools.validate_residues("O15205", labels)
    assert "error" not in out, out
    assert out["n_mismatches"] == 0, [v for v in out["validated"] if not v["valid"]]
