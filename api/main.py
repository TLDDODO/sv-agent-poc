"""FastAPI service for the FAT10-MAD2 interface adjudicator.

Design: the service boots and serves the REAL evidence (MD contact occupancies,
the literature-expected binding region, and the deterministic conflict flag) with
NO API key required — so a reviewer can hit `/evidence` immediately. The two
LLM-driven endpoints (the autonomous investigator agent and the multi-agent
debate) activate only when DEEPSEEK_API_KEY is set in the environment.

Run locally:   uvicorn api.main:app --reload
Interactive docs at /docs (OpenAPI).
"""
from __future__ import annotations
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.tools import get_md_interface_scores, get_expected_interface_region
from analysis.adjudicate_md import adjudicate as md_adjudicate

SCORES_PATH = "analysis/md_interface_scores.json"

app = FastAPI(
    title="FAT10-MAD2 Interface Adjudicator",
    version="1.0.0",
    description=(
        "Agentic pipeline that adjudicates the FAT10-MAD2 protein-protein interface. "
        "It grounds every fact in a tool call (PDBe, UniProt, a 100 ns MD run, PubMed), "
        "compares the real MD interface against the literature-expected binding region, "
        "and — when they conflict — convenes a multi-agent debate for a calibrated verdict."
    ),
)


def _llm_ready() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _require_llm() -> None:
    if not _llm_ready():
        raise HTTPException(
            status_code=400,
            detail="DEEPSEEK_API_KEY is not set — the LLM-driven endpoints are disabled. "
                   "Set it in the environment (docker run -e DEEPSEEK_API_KEY=... / compose).",
        )


@app.get("/", tags=["meta"])
def root() -> dict:
    """Service description and endpoint map."""
    return {
        "service": "FAT10-MAD2 Interface Adjudicator",
        "llm_configured": _llm_ready(),
        "endpoints": {
            "GET /health": "liveness + whether the LLM is configured",
            "GET /evidence": "real MD evidence + expected region + conflict flag (no key needed)",
            "POST /adjudicate": "run the autonomous investigator agent (needs DEEPSEEK_API_KEY)",
            "POST /debate": "run the multi-agent debate (needs DEEPSEEK_API_KEY)",
            "GET /docs": "interactive OpenAPI documentation",
        },
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe. Reports whether an LLM key is configured, but never needs one."""
    return {"status": "ok", "llm_configured": _llm_ready()}


@app.get("/evidence", tags=["evidence"])
def evidence() -> dict:
    """Real MD interface evidence, the literature-expected region, and the
    deterministic conflict flag. No LLM required — this endpoint always works."""
    md = get_md_interface_scores(SCORES_PATH)
    if "error" in md:
        raise HTTPException(status_code=503, detail=md["error"])
    return {
        "md_method": md["method"],
        "md_occupancy": md["occupancy"],
        "expected_region": get_expected_interface_region(),
        "adjudication": md_adjudicate(md["occupancy"]),  # includes the 'flag' field
    }


class AgentRequest(BaseModel):
    goal: str | None = Field(
        default=None,
        description="Plain-language investigation goal. Omit to use the default FAT10-MAD2 goal.",
    )
    max_steps: int = Field(default=12, ge=1, le=24, description="Max ReAct steps.")


DEFAULT_GOAL = (
    "Investigate where MAD2 (UniProt Q13257) binds FAT10 (UniProt O15205): find where "
    "the literature expects the interface, get the real MD contact evidence, and "
    "determine whether the current model's interface is consistent with the literature. "
    "If they conflict, convene the debate and reach a calibrated verdict."
)


@app.post("/adjudicate", tags=["agent"])
def adjudicate(req: AgentRequest) -> dict:
    """Run the autonomous investigator agent end-to-end. The LLM chooses which tools
    to call; the response contains its verdict and the full reasoning/tool transcript."""
    _require_llm()
    from agent.run_agent import run  # lazy import: no LLM client is built until here
    goal = req.goal or DEFAULT_GOAL
    result, transcript = run(goal, max_steps=req.max_steps, verbose=False)
    return {"goal": goal, "result": result, "transcript": transcript}


@app.post("/debate", tags=["agent"])
def debate() -> dict:
    """Convene the multi-agent debate (MD advocate vs NMR advocate + judge) over the
    current real evidence and return the judge's calibrated verdict."""
    _require_llm()
    from agent.debate import run as run_debate  # lazy import
    return run_debate()
