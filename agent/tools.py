from __future__ import annotations
import json
import os
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


DISPATCH = {
    "fetch_structures": fetch_structures,
    "list_interface_tools": list_interface_tools,
    "get_tool_prediction": get_tool_prediction,
    "map_residues": map_residues,
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
        "name": "map_residues",
        "description": "Map residue labels (e.g. L9) to canonical UniProt numbering and flag whether each is inside the binding domain range.",
        "parameters": {"type": "object", "properties": {
            "residues": {"type": "array", "items": {"type": "string"}},
            "uniprot": {"type": "string"},
            "domain_lo": {"type": "integer"},
            "domain_hi": {"type": "integer"}},
            "required": ["residues", "uniprot"]}}},
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
