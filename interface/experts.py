from __future__ import annotations
from .schemas import ToolPrediction, ToolVerdict
from debate.llm import LLM

_HI = 0.60   # score at/above this -> the tool is calling the residue "interface"

_CAVEATS = {
    "AlphaFold-Multimer":
        "AF-Multimer interface confidence is model-derived, not experimental, and "
        "can be overconfident on shallow or transient interfaces.",
    "HADDOCK":
        "HADDOCK scores depend on the input restraints and sampling; they reflect "
        "docking energetics, not direct observation.",
    "PISA-contacts":
        "PISA contacts come from a single static pose; they are sensitive to which "
        "docked model was chosen.",
}


def tool_expert(pred: ToolPrediction, llm: LLM) -> ToolVerdict:
    called = [s.residue for s in pred.scores if s.score >= _HI]
    caveat = _CAVEATS.get(pred.tool, "Tool-specific systematic bias may apply.")

    # Confidence from the real signal: how cleanly the tool separates
    # interface from non-interface (bigger spread = more decisive).
    vals = [s.score for s in pred.scores]
    spread = max(vals) - min(vals)
    confidence = round(min(0.9, 0.5 + spread / 2), 2)

    fallback = (f"{pred.tool} flags interface residues [{', '.join(called) or 'none'}]. "
                f"Caveat: {caveat}")
    prompt = (
        f"You are interpreting ONLY the output of {pred.tool} ({pred.source_id}, "
        f"{pred.params}) for the FAT10:MAD2 interface. Per-residue interface scores: "
        f"{[(s.residue, round(s.score, 2)) for s in pred.scores]}. In two sentences, "
        f"name the residues this tool considers interface and state this tool's key "
        f"caveat ({caveat}). Do not invent residues or cite other tools."
    )
    rationale = llm.phrase(prompt, fallback)
    return ToolVerdict(pred.tool, pred.source_id, called, confidence, caveat, rationale)
