from __future__ import annotations
from .schemas import ToolPrediction, ResidueScore

# --- System identity (real, verifiable accessions) ---------------------------
FAT10_UNIPROT = "O15205"        # UBD / FAT10
MAD2_UNIPROT = "Q13257"         # MAD2L1
SYSTEM = "FAT10 N-terminal ubl domain : MAD2"

# Candidate interface residues on FAT10's N-terminal ubiquitin-like domain.
# Residue identities are REAL FAT10 (UniProt O15205) amino acids at these
# positions, so they pass validate_residues. The interface SCORES below are
# still placeholders until real AF-Multimer / HADDOCK / PISA output is plugged in.
_RESIDUES = ["C7", "C9", "F22", "A24", "Q46", "Q48", "S64", "Y66"]

# Mock per-residue interface propensity (0..1) from three tools, with built-in
# consensus AND two genuine disagreements:
#   - S64: HADDOCK calls it interface; AFM and PISA do not.
#   - Y66: AFM and PISA call it interface; HADDOCK does not.
_TOOLS = {
    "AlphaFold-Multimer": {
        "C7": 0.80, "C9": 0.90, "F22": 0.70, "A24": 0.85,
        "Q46": 0.75, "Q48": 0.30, "S64": 0.20, "Y66": 0.65,
    },
    "HADDOCK": {
        "C7": 0.75, "C9": 0.85, "F22": 0.65, "A24": 0.80,
        "Q46": 0.70, "Q48": 0.35, "S64": 0.55, "Y66": 0.25,
    },
    "PISA-contacts": {
        "C7": 0.82, "C9": 0.88, "F22": 0.68, "A24": 0.82,
        "Q46": 0.72, "Q48": 0.28, "S64": 0.25, "Y66": 0.60,
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
