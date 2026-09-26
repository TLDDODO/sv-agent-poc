"""S1b regression tests: one UBL1 range (6-81) everywhere, one PISA name, and
fetch_structures really going through the PDBe MCP query with an honest fallback."""
import inspect
import json
import re

import pytest

from agent import compare, debate, structures, tools
from agent.structures import NTERM_UBL_RANGE, offline_structures
from analysis import adjudicate_md

SNAPSHOT_IDS = [h.pdb_id for h in offline_structures()]


# --- (2) UBL1 domain range: 6-81 everywhere ---------------------------------
def test_ubl1_range_is_the_verified_6_81():
    assert NTERM_UBL_RANGE == (6, 81)


def test_every_ubl1_copy_agrees():
    assert tools.get_expected_interface_region()["residue_range"] == list(NTERM_UBL_RANGE)
    assert tuple(adjudicate_md.EXPECTED["residue_range"]) == NTERM_UBL_RANGE
    assert adjudicate_md.DOMAINS[0][1:] == NTERM_UBL_RANGE
    assert debate.DOMAINS[0][1:] == NTERM_UBL_RANGE
    nb = json.load(open("notebooks/fat10_mad2_pipeline.ipynb", encoding="utf-8"))
    src = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert re.search(r"\('UBL1 \(N-term\)',\s*6,\s*81\)", src)
    report_src = open("analysis/build_report.py", encoding="utf-8").read()
    assert '("UBL1 (N-term)", 6, 81)' in report_src


def test_default_domain_parameters_use_6_81():
    assert inspect.signature(compare.gather_evidence).parameters["domain"].default == NTERM_UBL_RANGE
    sig = inspect.signature(tools.map_residues).parameters
    assert (sig["domain_lo"].default, sig["domain_hi"].default) == NTERM_UBL_RANGE
    # X-labelled boundary probes: map_residues only uses the position
    out = tools.map_residues(["X5", "X6", "X81", "X82"], "O15205")
    flags = {m["residue_label"]: m["in_nterm_ubl"] for m in out["mappings"]}
    assert flags == {"X5": False, "X6": True, "X81": True, "X82": False}


# --- (3) one PISA name -------------------------------------------------------
def test_pending_tool_names_match_caveat_names():
    assert set(compare._CAVEATS) == set(tools.PENDING_TOOLS)


# --- (1) fetch_structures: live MCP first, honest fallback -------------------
def test_offline_fat10_uses_the_verified_snapshot():
    out = tools.fetch_structures("O15205")            # conftest: PDBE_SOURCE=snapshot
    assert out["source"] == "verified_snapshot"
    assert [s["pdb_id"] for s in out["structures"]] == SNAPSHOT_IDS


def test_offline_other_accession_is_unavailable_not_fat10():
    out = tools.fetch_structures("Q13257")
    assert out["source"] == "unavailable" and out["structures"] == []


def test_auto_uses_the_live_mcp_result(monkeypatch):
    monkeypatch.setenv("PDBE_SOURCE", "auto")
    asked = []
    hit = structures.StructureHit(pdb_id="6gf1", title="t", experimental_method=None,
                                  resolution=None, source="pdbe_mcp:run_pdbe_search_query")
    monkeypatch.setattr(tools, "mcp_structures", lambda acc: asked.append(acc) or [hit])
    out = tools.fetch_structures("O15205")
    assert asked == ["O15205"]
    assert out["source"] == "pdbe_mcp_live" and out["structures"][0]["pdb_id"] == "6gf1"


def _raise(acc):
    raise RuntimeError("PDBe unreachable")


def test_auto_falls_back_and_records_why(monkeypatch):
    monkeypatch.setenv("PDBE_SOURCE", "auto")
    monkeypatch.setattr(tools, "mcp_structures", _raise)
    out = tools.fetch_structures("O15205")
    assert out["source"] == "verified_snapshot" and "PDBe unreachable" in out["live_error"]
    other = tools.fetch_structures("Q13257")
    assert other["source"] == "unavailable" and other["structures"] == []


def test_mcp_mode_never_falls_back(monkeypatch):
    monkeypatch.setenv("PDBE_SOURCE", "mcp")
    monkeypatch.setattr(tools, "mcp_structures", _raise)
    out = tools.fetch_structures("O15205")
    assert out["structures"] == [] and "PDBe unreachable" in out["error"]


def test_parse_reads_the_server_output_format():
    # Format of pdbe-mcp-server 1.1.6 run_pdbe_search_query ("Document N:" then
    # two-space "key: value" lines); values are the committed snapshot's.
    snap = offline_structures()
    lines = ["Results metadata:", f"Number of documents found: {len(snap)}",
             "Start index: 0", "Documents:"]
    for i, h in enumerate(snap, start=1):
        lines += [f"Document {i}:", f"  pdb_id: {h.pdb_id}", f"  title: {h.title}",
                  f"  experimental_method: {h.experimental_method}"]
    hits = structures._parse("\n".join(lines))
    assert [h.pdb_id for h in hits] == SNAPSHOT_IDS
    assert all(h.source == "pdbe_mcp:run_pdbe_search_query" for h in hits)


def test_mcp_server_gets_proxy_settings_but_not_api_keys(monkeypatch):
    stdio = pytest.importorskip("mcp.client.stdio")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/ca.pem")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-leak")
    seen = {}

    def capture(params):
        seen["params"] = params
        raise RuntimeError("stop after capturing the launch parameters")

    monkeypatch.setattr(stdio, "stdio_client", capture)
    with pytest.raises(Exception):
        structures.mcp_structures("O15205", timeout=5)
    p = seen["params"]
    assert p.args[-4:] == ["--server-type", "pdbe_search_server", "--transport", "stdio"]
    assert p.env["HTTPS_PROXY"] == "http://proxy.example:3128"
    assert p.env["REQUESTS_CA_BUNDLE"] == "/tmp/ca.pem"
    assert "DEEPSEEK_API_KEY" not in p.env


@pytest.mark.live
def test_live_mcp_query_returns_the_fat10_structures(monkeypatch):
    """Live: the real PDBe MCP query for O15205 returns the snapshot's entries."""
    monkeypatch.setenv("PDBE_SOURCE", "mcp")
    out = tools.fetch_structures("O15205")
    assert "error" not in out, out
    assert out["source"] == "pdbe_mcp_live"
    assert set(SNAPSHOT_IDS) <= {s["pdb_id"] for s in out["structures"]}
