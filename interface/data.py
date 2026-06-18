from __future__ import annotations
from .schemas import ToolPrediction, ResidueScore

# --- System identity (real, verifiable accessions) ---------------------------
FAT10_UNIPROT = "O15205"        # UBD / FAT10
MAD2_UNIPROT = "Q13257"         # MAD2L1
SYSTEM = "FAT10 N-terminal ubl domain : MAD2"

# Candidate interface residues on FAT10's N-terminal ubiquitin-like domain.
# (Mock residue set for the demo; replace with real tool outputs on HPC.)
_RESIDUES = ["I7", "L9", "Y22", "K24", "F46", "R48", "V64", "D66"]

# Mock per-residue interface propensity (0..1) from three tools, with built-in
# consensus AND two genuine disagreements:
#   - V64: HADDOCK calls it interface; AFM and PISA do not.
#   - D66: AFM and PISA call it interface; HADDOCK does not.
_TOOLS = {
    "AlphaFold-Multimer": {
        "I7": 0.80, "L9": 0.90, "Y22": 0.70, "K24": 0.85,
        "F46": 0.75, "R48": 0.30, "V64": 0.20, "D66": 0.65,
    },
    "HADDOCK": {
        "I7": 0.75, "L9": 0.85, "Y22": 0.65, "K24": 0.80,
        "F46": 0.70, "R48": 0.35, "V64": 0.55, "D66": 0.25,
    },
    "PISA-contacts": {
        "I7": 0.82, "L9": 0.88, "Y22": 0.68, "K24": 0.82,
        "F46": 0.72, "R48": 0.28, "V64": 0.25, "D66": 0.60,
    },
}

_PARAMS = {
    "AlphaFold-Multimer": "AF-Multimer, per-residue interface PAE/ipTM mapped to 0..1",
    "HADDOCK": "HADDOCK2.4, top cluster, residue interface-energy contribution",
    "PISA-contacts": "PDBePISA on top docked pose, per-residue contact fraction",
}
_SOURCE = {
    "AlphaFold-Multimer": "afm:fat10_mad2_demo",
    "HADDOCK": "haddock:fat10_mad2_demo",
    "PISA-contacts": "pisa:fat10_mad2_demo",
}


def mock_predictions() -> list[ToolPrediction]:
    return [
        ToolPrediction(
            tool=t, source_id=_SOURCE[t], params=_PARAMS[t],
            scores=[ResidueScore(r, _TOOLS[t][r]) for r in _RESIDUES],
        )
        for t in _TOOLS
    ]


# --- Real loader (wire on HPC) -----------------------------------------------
def load_tool_prediction(tool: str, csv_path: str) -> ToolPrediction:
    """Build a ToolPrediction from a real tool's per-residue interface scores.

    Expected CSV: two columns `residue,score` over the FAT10 ubl numbering.
    """
    raise NotImplementedError("Wire to real AFM / HADDOCK / PISA per-residue output.")
