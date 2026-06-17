from __future__ import annotations
from .schemas import MethodProfile, ExpertVerdict, RegionVerdict
from .llm import LLM

_HI, _LO = 0.60, 0.35


def _stance(v: float) -> str:
    return "flexible" if v >= _HI else "rigid" if v <= _LO else "intermediate"


def _expert(profile: MethodProfile, name: str, evidence_type: str,
            limitations: str, llm: LLM) -> ExpertVerdict:
    rvs = [
        RegionVerdict(r.region, _stance(r.value), r.value,
                      f"{r.region} ({r.residue_range}) flexibility={r.value:.2f}")
        for r in profile.regions
    ]
    flexible = [rv.region for rv in rvs if rv.stance == "flexible"]
    rigid = [rv.region for rv in rvs if rv.stance == "rigid"]
    overall = (f"{profile.method} flags [{', '.join(flexible) or 'no'}] as flexible; "
               f"core [{', '.join(rigid) or 'n/a'}] stays rigid.")

    # Confidence from the real signal: how well-separated the profile is.
    vals = [r.value for r in profile.regions]
    spread = max(vals) - min(vals)
    confidence = round(min(0.9, 0.5 + spread / 2), 2)

    fallback = f"{overall} Interpretation constrained by: {limitations}"
    prompt = (
        f"You are the {name} expert. Using ONLY these per-region flexibility values "
        f"from {profile.method} ({profile.source_id}, {profile.params}): "
        f"{[(r.region, round(r.value, 2)) for r in profile.regions]}. "
        f"In two sentences, say which regions are dynamically important and state the "
        f"key caveat of this method ({limitations}). Do not invent values or cite "
        f"anything not provided."
    )
    rationale = llm.phrase(prompt, fallback)
    return ExpertVerdict(name, profile.method, profile.source_id, overall, rvs,
                         evidence_type, confidence, limitations, rationale)


def expert_md(profile: MethodProfile, llm: LLM) -> ExpertVerdict:
    return _expert(
        profile, "MD-view", "dynamics",
        "MD captures anharmonic and solvent-coupled motion but depends on sampling "
        "and convergence (here a 400 ns demo).",
        llm,
    )


def expert_nma(profile: MethodProfile, llm: LLM) -> ExpertVerdict:
    return _expert(
        profile, "NMA-view", "normal-modes",
        "ENM/NMA captures slow collective modes cheaply but is harmonic, solvent-free, "
        "and tends to underestimate large anharmonic loop motions.",
        llm,
    )
