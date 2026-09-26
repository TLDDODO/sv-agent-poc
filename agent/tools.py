from __future__ import annotations
import json
import os
import re
import urllib.request
from dataclasses import asdict

from . import leakage
from .cases import active_case
from .structures import (FAT10_UNIPROT, NTERM_UBL_RANGE, canonical_map,
                         mcp_structures, offline_structures)


# Tools whose per-residue interface scores the team has NOT produced yet. We do not
# fabricate them — the agent is told they are pending so it cannot pretend a
# multi-tool consensus exists.
PENDING_TOOLS = ["AlphaFold-Multimer", "HADDOCK", "PISA"]


def _predictions() -> dict:
    """REAL per-tool, per-residue interface scores. Defaults to the real MD output;
    set INTERFACE_SCORES to override. Returns {} if none present — NO mock data.
    A case without an MD score file (every benchmark pair) has none."""
    path = os.environ.get("INTERFACE_SCORES", active_case().md_scores)
    if path and os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def get_md_interface_scores(scores_path: str | None = None) -> dict:
    """Real per-residue MAD2-contact occupancy from the 100 ns MD (0..1 = fraction
    of frames in contact). This is real evidence, not a prediction. A case with no MD
    run reports `pending` — never placeholder numbers."""
    scores_path = scores_path or active_case().md_scores
    if not scores_path:
        return {"status": "pending", "real": False,
                "note": "no MD simulation exists for this protein pair — do not use placeholder numbers"}
    if not os.path.exists(scores_path):
        return {"error": f"no MD scores at {scores_path}"}
    with open(scores_path) as fh:
        data = json.load(fh)
    method, occ = next(iter(data.items()))
    return {"method": method, "occupancy": occ,
            "note": "fraction of MD frames each FAT10 residue contacts MAD2 (real)"}


def search_literature(query: str | None = None) -> dict:
    """Search PubMed for the binding region and return real abstracts for the agent to
    read. FAT10-MAD2: falls back to a cited result if PubMed is unreachable. Benchmark
    pairs: papers reporting an experimental complex of the pair are removed, and there
    is no fallback claim."""
    case = active_case()
    query = query or case.literature_query
    if case.generic:
        try:
            from .literature import search_pubmed
            ids, abstracts = search_pubmed(
                query, exclude_pmids=leakage.co_complex_pmids(case) if case.benchmark else ())
        except Exception as exc:
            return {"retrieved_live": False, "error": type(exc).__name__}
        return {"retrieved_live": bool(abstracts.strip()), "pmids": ids, "abstracts": abstracts[:4000]}
    try:
        from .literature import search_pubmed
        ids, abstracts = search_pubmed(query)
        if abstracts.strip():
            return {"retrieved_live": True, "pmids": ids, "abstracts": abstracts[:4000]}
    except Exception as exc:
        return {"retrieved_live": False, "error": type(exc).__name__,
                "fallback": "Theng et al. 2014 PNAS: MAD2 binds the N-terminal "
                            "(first) ubiquitin-like domain of FAT10"}
    return {"retrieved_live": False,
            "fallback": "Theng et al. 2014 PNAS: MAD2 binds the N-terminal "
                        "(first) ubiquitin-like domain of FAT10"}


def convene_debate() -> dict:
    """Convene the multi-agent debate (MD advocate vs NMR advocate + judge) over the
    current real evidence, and return the judge's calibrated verdict. Call this when
    the MD interface and the literature/domain expectation conflict."""
    if active_case().generic:
        return {"status": "pending", "real": False,
                "note": "no MD run and no NMR/literature conflict exist for this pair, so there is nothing to debate"}
    from .debate import run as _run_debate
    return _run_debate()


def _uniprot_features(acc: str) -> dict:
    url = f"https://rest.uniprot.org/uniprotkb/{acc}.json"
    with urllib.request.urlopen(url, timeout=20) as resp:
        j = json.loads(resp.read().decode())
    feats = [{"type": f["type"], "description": f.get("description"),
              "start": f["location"]["start"]["value"], "end": f["location"]["end"]["value"]}
             for f in j.get("features", [])
             if f["type"] in ("Domain", "Region", "Motif", "Repeat", "Zinc finger")]
    return {"name": j["proteinDescription"].get("recommendedName", {}).get("fullName", {}).get("value"),
            "length": j["sequence"]["length"], "features": feats}


def get_expected_interface_region(uniprot: str = "O15205") -> dict:
    """Literature/NMR prior for where MAD2 is expected to bind FAT10. Use this as
    the standard to compare the predicted/MD interface against, and FLAG the model
    if the interface falls outside this region. For a benchmark pair there is no such
    prior: it returns the live UniProt domain/region/motif table of both proteins
    (features only - no comments or cross-references, which can name the complex)."""
    case = active_case()
    if case.generic:
        try:
            return {"evidence_type": "UniProt feature table (live) - annotations, NOT a known interface",
                    "proteins": {a: _uniprot_features(a) for a in (case.uniprot_a, case.uniprot_b)}}
        except Exception as exc:
            return {"status": "unavailable", "error": type(exc).__name__,
                    "note": "UniProt feature table could not be fetched; nothing is substituted"}
    return {
        "uniprot": uniprot,
        "expected_region": "Ubiquitin-like 1 (N-terminal domain)",
        "residue_range": list(NTERM_UBL_RANGE),   # UniProt O15205 DOMAIN "Ubiquitin-like 1" (verified)
        "other_domains": {"Ubiquitin-like 2 (C-term)": [90, 163], "C-terminal tail": [164, 165]},
        "evidence_type": "CITED literature fact (not derived by this agent)",
        "source": "Domain ranges: UniProt O15205 feature table (verified). Binding region: "
                  "Theng et al. 2014 PNAS + NMR PDB 2MBE (first FAT10 domain). Use "
                  "search_literature to corroborate the binding-region claim live.",
        "note": "If the interface residues fall outside UBL1 (6-81), the model disagrees "
                "with the literature and must be flagged (e.g. an AF3 model that "
                "docked MAD2 onto FAT10's C-terminal region).",
    }


# --- tool implementations (the agent calls these) ----------------------------
def fetch_structures(uniprot: str) -> dict:
    """PDB structures for a UniProt accession. Tries the live PDBe MCP search server
    first; if it cannot be reached, falls back to the verified snapshot, which exists
    only for FAT10 (O15205). PDBE_SOURCE=snapshot skips the live query (offline runs);
    PDBE_SOURCE=mcp disables the fallback."""
    out = _fetch_structures(uniprot)
    case = active_case()
    return leakage.filter_structures(out, case) if case.benchmark else out


def _fetch_structures(uniprot: str) -> dict:
    source = os.environ.get("PDBE_SOURCE", "auto")
    live_error = None
    if source in ("auto", "mcp"):
        try:
            hits = mcp_structures(uniprot)
            return {"uniprot": uniprot, "source": "pdbe_mcp_live",
                    "structures": [asdict(h) for h in hits]}
        except Exception as exc:
            live_error = f"{type(exc).__name__}: {exc}"[:300]
            if source == "mcp":
                return {"uniprot": uniprot, "source": "pdbe_mcp_live", "structures": [],
                        "error": live_error}
    if uniprot == FAT10_UNIPROT:
        out = {"uniprot": uniprot, "source": "verified_snapshot",
               "structures": [asdict(h) for h in offline_structures()]}
    else:
        out = {"uniprot": uniprot, "source": "unavailable", "structures": [],
               "note": "live PDBe query failed and there is no snapshot for this accession"}
    if live_error:
        out["live_error"] = live_error
    return out


def list_interface_tools() -> dict:
    return {"available_real": list(_predictions().keys()),
            "pending_no_data_yet": PENDING_TOOLS,
            "note": "Only methods under 'available_real' have real per-residue scores. "
                    "AFM/HADDOCK/PISA are pending team data; a multi-tool consensus "
                    "cannot be computed until they arrive — do not fabricate them."}


def get_tool_prediction(tool: str) -> dict:
    preds = _predictions()
    if tool in preds:
        return {"tool": tool, "scores": preds[tool], "real": True}
    if tool in PENDING_TOOLS:
        return {"tool": tool, "status": "pending", "real": False,
                "note": "no real data yet — awaiting team output; do not use placeholder numbers"}
    return {"error": f"unknown tool '{tool}'", "available": list(preds)}


def map_residues(residues: list, uniprot: str, domain_lo: int = NTERM_UBL_RANGE[0],
                 domain_hi: int = NTERM_UBL_RANGE[1]) -> dict:
    ms = canonical_map(residues, uniprot=uniprot, domain=(domain_lo, domain_hi))
    return {"mappings": [asdict(m) for m in ms]}


def validate_residues(uniprot: str, residues: list) -> dict:
    """Ground-truth check: fetch the real UniProt sequence and verify each
    predicted residue label (e.g. 'L9') matches the actual amino acid at that
    position. Catches wrong numbering or fabricated residues."""
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot}.fasta"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            fasta = resp.read().decode()
    except Exception as exc:
        out = {"error": f"could not fetch UniProt {uniprot}: {type(exc).__name__}",
               "validated": [], "note": "residues are NOT grounded against a real sequence"}
        if getattr(exc, "code", None) is not None:      # HTTPError: keep the status for callers
            out["http_status"] = exc.code
        return out
    seq = "".join(l.strip() for l in fasta.splitlines() if l and not l.startswith(">"))
    out = []
    for lab in residues:
        m = re.match(r"([A-Z])(\d+)$", lab)
        if not m:
            out.append({"residue": lab, "valid": False, "reason": "unparseable label"})
            continue
        aa, pos = m.group(1), int(m.group(2))
        actual = seq[pos - 1] if 1 <= pos <= len(seq) else None
        out.append({"residue": lab, "expected": aa, "actual_in_sequence": actual,
                    "valid": actual == aa})
    n_bad = sum(1 for v in out if not v.get("valid"))
    return {"uniprot": uniprot, "sequence_length": len(seq),
            "n_mismatches": n_bad, "validated": out}


DISPATCH = {
    "fetch_structures": fetch_structures,
    "list_interface_tools": list_interface_tools,
    "get_tool_prediction": get_tool_prediction,
    "map_residues": map_residues,
    "validate_residues": validate_residues,
    "get_expected_interface_region": get_expected_interface_region,
    "get_md_interface_scores": get_md_interface_scores,
    "search_literature": search_literature,
    "convene_debate": convene_debate,
}

# --- tool schemas (OpenAI / DeepSeek function-calling format) -----------------
TOOLS = [
    {"type": "function", "function": {
        "name": "fetch_structures",
        "description": "Retrieve PDB structures for a UniProt accession from PDBe, to confirm the system.",
        "parameters": {"type": "object", "properties": {
            "uniprot": {"type": "string", "description": "UniProt accession, e.g. O15205"}},
            "required": ["uniprot"]}}},
    {"type": "function", "function": {
        "name": "list_interface_tools",
        "description": "List the interface-prediction tools whose per-residue predictions are available.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_tool_prediction",
        "description": "Get one tool's per-residue interface propensity scores (0..1) and its known caveat.",
        "parameters": {"type": "object", "properties": {
            "tool": {"type": "string", "description": "Tool name from list_interface_tools"}},
            "required": ["tool"]}}},
    {"type": "function", "function": {
        "name": "get_expected_interface_region",
        "description": "Get the literature/NMR-expected binding region (the standard). Compare the predicted/MD interface against it and FLAG the model if the interface falls outside this region.",
        "parameters": {"type": "object", "properties": {
            "uniprot": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_md_interface_scores",
        "description": "Get the REAL per-residue MAD2-contact occupancy from the 100 ns MD simulation (0..1). This is real interface evidence.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "search_literature",
        "description": "Search PubMed for the FAT10-MAD2 binding region and read the real abstracts to learn which FAT10 domain binds MAD2.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "convene_debate",
        "description": "Convene a multi-agent debate (MD advocate vs NMR advocate + judge) over the real evidence and get a calibrated verdict. Use this when the MD interface and the literature/domain expectation conflict.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "map_residues",
        "description": "Map residue labels (e.g. L9) to canonical UniProt numbering and flag whether each is inside the binding domain range.",
        "parameters": {"type": "object", "properties": {
            "residues": {"type": "array", "items": {"type": "string"}},
            "uniprot": {"type": "string"},
            "domain_lo": {"type": "integer"},
            "domain_hi": {"type": "integer"}},
            "required": ["residues", "uniprot"]}}},
    {"type": "function", "function": {
        "name": "validate_residues",
        "description": "Ground-truth check: verify each predicted residue label against the real UniProt sequence (does position 9 really hold Leu for 'L9'?). Use this to catch fabricated or mis-numbered residues before trusting any prediction.",
        "parameters": {"type": "object", "properties": {
            "uniprot": {"type": "string"},
            "residues": {"type": "array", "items": {"type": "string"}}},
            "required": ["uniprot", "residues"]}}},
    {"type": "function", "function": {
        "name": "submit_adjudication",
        "description": "Submit the final interface adjudication and end the task. Call this once you have reasoned over all tools.",
        "parameters": {"type": "object", "properties": {
            "consensus_interface": {"type": "array", "items": {"type": "string"},
                                    "description": "Residues all tools agree are interface."},
            "disputed": {"type": "array", "items": {"type": "string"},
                         "description": "Residues where tools strongly disagree; flag for MD/experiment."},
            "weak": {"type": "array", "items": {"type": "string"},
                     "description": "Ambiguous residues no tool is decisive about."},
            "confidence": {"type": "number", "description": "0..1; lower it if disputes are unresolved."},
            "flags": {"type": "array", "items": {"type": "string"},
                      "description": "Reliability flags / things needing human or MD confirmation."},
            "reasoning": {"type": "string", "description": "Short justification grounded in the tool outputs."}},
            "required": ["consensus_interface", "disputed", "confidence", "reasoning"]}}},
]


# submit_adjudication for a benchmark pair also carries the predicted interface regions
# (scored by the benchmark). The v1 schema (TOOLS) is left untouched for the v1 case.
_PREDICTED_REGIONS = {
    "type": "array",
    "description": "Predicted interface region for EACH of the two proteins, UniProt numbering.",
    "items": {"type": "object", "properties": {
        "uniprot": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}},
        "required": ["uniprot", "start", "end"]}}


def tools_for(case) -> list:
    if not case.generic:
        return TOOLS
    import copy
    tools = copy.deepcopy(TOOLS)
    sub = next(t for t in tools if t["function"]["name"] == "submit_adjudication")
    params = sub["function"]["parameters"]
    params["properties"]["predicted_regions"] = _PREDICTED_REGIONS
    params["required"] = params["required"] + ["predicted_regions"]
    # the 6-81 default is FAT10's UBL1; a benchmark pair has no such default
    mp = next(t for t in tools if t["function"]["name"] == "map_residues")["function"]["parameters"]
    mp["required"] = mp["required"] + ["domain_lo", "domain_hi"]
    return tools
