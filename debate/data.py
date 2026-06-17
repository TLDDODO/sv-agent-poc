from __future__ import annotations
from .schemas import MethodProfile, RegionFlexibility

# EGFR kinase-domain-style region layout (canonical-ish residue ranges).
_REGIONS = [
    ("P-loop",            "718-725"),
    ("alphaC-helix",      "755-765"),
    ("hinge",             "790-797"),
    ("gatekeeper(T790)",  "788-792"),
    ("activation-loop",   "855-883"),
    ("N-lobe beta-sheet", "700-718"),
    ("C-lobe core",       "900-920"),
]

# Mock per-region flexibility, normalized 0..1. Two *genuine* MD/NMA conflicts
# are built in for a realistic, defensible demo:
#   - activation-loop: MD sees large anharmonic loop motion; harmonic NMA flattens it.
#   - N-lobe beta-sheet: NMA resolves a slow collective breathing mode the
#     short trajectory under-samples.
_MD = {
    "P-loop": 0.70, "alphaC-helix": 0.45, "hinge": 0.30, "gatekeeper(T790)": 0.25,
    "activation-loop": 0.85, "N-lobe beta-sheet": 0.32, "C-lobe core": 0.20,
}
_NMA = {
    "P-loop": 0.65, "alphaC-helix": 0.50, "hinge": 0.35, "gatekeeper(T790)": 0.20,
    "activation-loop": 0.40, "N-lobe beta-sheet": 0.60, "C-lobe core": 0.15,
}


def mock_profiles() -> tuple[MethodProfile, MethodProfile]:
    md = MethodProfile(
        "MD", "traj:egfr_t790m_demo", "400 ns, AMBER ff19SB, C-alpha RMSF",
        [RegionFlexibility(r, rng, _MD[r]) for r, rng in _REGIONS],
    )
    nma = MethodProfile(
        "NMA", "enm:egfr_t790m_anm", "ANM, cutoff 15A, 20 slowest modes",
        [RegionFlexibility(r, rng, _NMA[r]) for r, rng in _REGIONS],
    )
    return md, nma


# --- Real loaders (wire these on the HPC) ------------------------------------
def load_md_profile(rmsf_csv: str) -> MethodProfile:
    """Build an MD profile from real MDAnalysis per-residue RMSF output."""
    raise NotImplementedError("Wire to MDAnalysis RMSF output on HPC.")


def load_nma_profile(nma_csv: str) -> MethodProfile:
    """Build an NMA profile from real ENM/ProDy normal-mode fluctuations."""
    raise NotImplementedError("Wire to ProDy/ENM mean-square fluctuations on HPC.")
