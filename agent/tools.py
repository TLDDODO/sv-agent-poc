from __future__ import annotations
import json
import os
import re
import urllib.request
from dataclasses import asdict

from interface.structures import offline_structures, canonical_map
from interface.data import mock_predictions
from interface.experts import _CAVEATS


def _predictions() -> dict:
    """Per-tool, per-residue interface scores. Demo uses mock numbers; set
    INTERFACE_SCORES to a JSON file ({tool: {residue: score}}) to use real data.
    These are the tools' OUTPUTS (data), not the agent's decision."""
    path = os.environ.get("INTERFACE_SCORES")
    if path and os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {p.tool: {s.residue: s.score for s in p.scores} for p in mock_predictions()}


def get_expected_interface_region(uniprot: str = "O15205") -> dict:
    """Literature/NMR prior for where MAD2 is expected to bind FAT10. Use this as
    the standard to compare the predicted/MD interface against, and FLAG the model
    if the interface falls outside this region."""
    return {
        "uniprot": uniprot,
        "expected_region": "Ubiquitin-like 1 (N-terminal domain)",
        "residue_range": [6, 81],   # UniProt O15205 DOMAIN "Ubiquitin-like 1" (verified)
        "other_domains": {"Ubiquitin-like 2 (C-term)": [90, 163], "C-terminal tail": [164, 165]},
        "source": "UniProt O15205 domain table; NMR PDB 2MBE (first FAT10 domain); "
                  "Theng et al. 2014 PNAS (FAT10-MAD2)",
        "note": "If the interface residues fall outside UBL1 (6-81), the model disagrees "
                "with the literature and must be flagged (e.g. an AF3 model that "
                "docked MAD2 onto FAT10's C-terminal region).",
    }


# --- tool implementations (the agent calls these) ----------------------------
def fetch_structures(uniprot: str) -> dict:
    hits = offline_structures()          # verified PDBe snapshot (or --mcp live on HPC)
    return {"uniprot": uniprot, "structures": [asdict(h) for h in hits]}


def list_interface_tools() -> dict:
    return {"tools": list(_predictions().keys())}


def get_tool_prediction(tool: str) -> dict:
    preds = _predictions()
    if tool not in preds:
        return {"error": f"unknown tool '{tool}'", "available": list(preds)}
    return {"tool": tool, "scores": preds[tool], "caveat": _CAVEATS.get(tool, "")}


def map_residues(residues: list, uniprot: str, domain_lo: int = 1, domain_hi: int = 80) -> dict:
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
        return {"error": f"could not fetch UniProt {uniprot}: {type(exc).__name__}",
                "validated": [], "note": "residues are NOT grounded against a real sequence"}
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
