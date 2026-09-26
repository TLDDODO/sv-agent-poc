"""FastAPI service for the FAT10-MAD2 interface adjudicator.

Design: the service boots and serves the REAL evidence (MD contact occupancies,
the literature-expected binding region, and the deterministic conflict flag) with
NO API key required — so a reviewer can hit `/evidence` immediately. The two
LLM-driven endpoints (the autonomous investigator agent and the multi-agent
debate) activate only when DEEPSEEK_API_KEY is set in the environment.

Run locally:   uvicorn api.main:app --reload
The single-page web client is served at / (api/index.html); its JSON API is /api/cases and
/api/run. Interactive docs at /docs (OpenAPI). The schema is exported to docs/openapi.json by
scripts/export_openapi.py (import it into Dify as a Custom Tool; see docs/dify_setup.md).
"""
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent.tools import get_md_interface_scores, get_expected_interface_region
from analysis.adjudicate_md import adjudicate as md_adjudicate
from api import webview

SCORES_PATH = "analysis/md_interface_scores.json"

app = FastAPI(
    title="FAT10-MAD2 Interface Adjudicator",
    version="1.0.0",
    description=(
        "Agentic pipeline that adjudicates the FAT10-MAD2 protein-protein interface. "
        "It grounds every fact in a tool call (PDBe, UniProt, a 100 ns MD run, PubMed), "
        "compares the real MD interface against the literature-expected binding region, "
        "and — when they conflict — convenes a multi-agent debate for a calibrated verdict.\n\n"
        "Labels in every answer: **real** = measured or fetched by a tool in this run, "
        "**cited** = a published result quoted from the literature (not re-derived here), "
        "**pending** = no data exists yet (never filled with placeholder numbers).\n\n"
        "There is no experimental FAT10-MAD2 complex structure, so no answer is ground truth: "
        "when the MD result and the literature disagree the service reports the "
        "contradiction and does not declare a winner."
    ),
    # Dify (running in Docker) reaches a service on the host machine at this address;
    # change it to wherever the API is reachable from Dify (see docs/dify_setup.md).
    servers=[{"url": "http://host.docker.internal:8000",
              "description": "The API as seen from a Dify running in Docker on the same machine"}],
    openapi_tags=[
        {"name": "meta", "description": "Service description and health."},
        {"name": "web", "description": "Endpoints behind the web page at / (preset cases, run a query)."},
        {"name": "evidence", "description": "Real evidence, no LLM and no key needed."},
        {"name": "agent", "description": "LLM-driven endpoints; need DEEPSEEK_API_KEY and take a while."},
    ],
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


def _evidence_payload() -> dict:
    md = get_md_interface_scores(SCORES_PATH)
    if "error" in md:
        raise HTTPException(status_code=503, detail=md["error"])
    return {
        "md_method": md["method"],
        "md_occupancy": md["occupancy"],
        "expected_region": get_expected_interface_region(),
        "adjudication": md_adjudicate(md["occupancy"]),  # includes the 'flag' field
    }


def _evidence_example() -> dict | None:
    """The real committed evidence, used as the documented example response."""
    try:
        return _evidence_payload()
    except Exception:
        return None


_EX = _evidence_example()
_EVIDENCE_RESPONSES = {200: {"content": {"application/json": {"example": _EX}}}} if _EX else {}


PAGE = Path(__file__).resolve().parent / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_page() -> HTMLResponse:
    """The single-page web client (plain HTML, no external assets)."""
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


@app.get("/info", tags=["meta"], operation_id="service_info",
         summary="Describe the service and list its endpoints",
         description="Returns the service name, whether an LLM key is configured, and a one-line "
                     "description of each endpoint. Safe to call any time.",
         responses={200: {"content": {"application/json": {"example": {
             "service": "FAT10-MAD2 Interface Adjudicator", "llm_configured": True,
             "endpoints": {"GET /health": "liveness + whether the LLM is configured"}}}}}})
def root() -> dict:
    """Service description and endpoint map."""
    return {
        "service": "FAT10-MAD2 Interface Adjudicator",
        "llm_configured": _llm_ready(),
        "endpoints": {
            "GET /": "the web page (pick a case or a protein pair, read the answer)",
            "GET /health": "liveness + whether the LLM is configured",
            "GET /api/cases": "preset cases for the web page",
            "POST /api/run": "run one query for the web page (needs DEEPSEEK_API_KEY)",
            "GET /evidence": "real MD evidence + expected region + conflict flag (no key needed)",
            "POST /adjudicate": "run the autonomous investigator agent (needs DEEPSEEK_API_KEY)",
            "POST /debate": "run the multi-agent debate (needs DEEPSEEK_API_KEY)",
            "GET /docs": "interactive OpenAPI documentation",
        },
    }


@app.get("/health", tags=["meta"], operation_id="health_check",
         summary="Check that the service is running",
         description="Liveness probe. Reports whether an LLM key is configured "
                     "(`llm_configured`); never needs one. If `llm_configured` is false, "
                     "`/adjudicate` and `/debate` will refuse and `/evidence` still works.",
         responses={200: {"content": {"application/json": {"example": {
             "status": "ok", "llm_configured": True}}}}})
def health() -> dict:
    """Liveness probe. Reports whether an LLM key is configured, but never needs one."""
    return {"status": "ok", "llm_configured": _llm_ready()}


@app.get("/evidence", tags=["evidence"], operation_id="get_evidence",
         summary="Get the real MD evidence, the literature-expected region and the conflict flag",
         description="Returns (1) the per-residue contact occupancy from the real 100 ns MD run "
                     "(real), (2) the binding region the literature / NMR expects (cited, not "
                     "derived here), and (3) a deterministic check of whether the MD interface "
                     "falls inside that region, including the `flag` that reports a contradiction. "
                     "No LLM and no key needed, so this always works and is the safest first call. "
                     "It reports the disagreement; it does not say which side is right.",
         responses=_EVIDENCE_RESPONSES)
def evidence() -> dict:
    """Real MD interface evidence, the literature-expected region, and the
    deterministic conflict flag. No LLM required — this endpoint always works."""
    return _evidence_payload()


class AgentRequest(BaseModel):
    goal: str | None = Field(
        default=None,
        description="Plain-language investigation goal about FAT10-MAD2. Omit to use the default goal.",
        examples=["Where does MAD2 bind FAT10, and does the MD interface agree with the literature?"],
    )
    max_steps: int = Field(default=12, ge=1, le=24,
                           description="Maximum number of reasoning/tool steps the agent may take.",
                           examples=[12])


DEFAULT_GOAL = (
    "Investigate where MAD2 (UniProt Q13257) binds FAT10 (UniProt O15205): find where "
    "the literature expects the interface, get the real MD contact evidence, and "
    "determine whether the current model's interface is consistent with the literature. "
    "If they conflict, convene the debate and reach a calibrated verdict."
)

_SHAPE_NOTE = "shape only: placeholders in angle brackets, not data"


@app.post("/adjudicate", tags=["agent"], operation_id="run_adjudication",
          summary="Ask the investigator agent a question about the FAT10-MAD2 interface",
          description="Runs the autonomous investigator agent end to end. The agent itself decides "
                      "which tools to call (literature search, PDBe structures, UniProt sequence "
                      "check, the MD evidence, and the debate if the evidence conflicts). The answer "
                      "has the agent's `result` (interface residues, disputed residues, confidence, "
                      "flags and reasoning) and the full step-by-step `transcript`. It needs "
                      "DEEPSEEK_API_KEY (otherwise HTTP 400), costs a little money per call and can "
                      "take a while, so raise your client's timeout. Tools with no data report "
                      "`pending`; the agent never invents numbers.",
          responses={200: {"content": {"application/json": {"example": {
              "goal": "<the goal that was used>",
              "result": {"consensus_interface": ["<residue labels>"], "disputed": ["<residue labels>"],
                         "confidence": "<0..1>", "flags": ["<reliability flags>"],
                         "reasoning": "<the agent's grounded justification>"},
              "transcript": [{"step": "<n>", "actions": ["<tool calls and results>"]}],
              "_note": _SHAPE_NOTE}}}},
              400: {"description": "DEEPSEEK_API_KEY is not set."}})
def adjudicate(req: AgentRequest) -> dict:
    """Run the autonomous investigator agent end-to-end. The LLM chooses which tools
    to call; the response contains its verdict and the full reasoning/tool transcript."""
    _require_llm()
    from agent.run_agent import run  # lazy import: no LLM client is built until here
    goal = req.goal or DEFAULT_GOAL
    result, transcript = run(goal, max_steps=req.max_steps, verbose=False)
    return {"goal": goal, "result": result, "transcript": transcript}


@app.post("/debate", tags=["agent"], operation_id="run_debate",
          summary="Run the MD-vs-NMR debate and get a calibrated verdict",
          description="Convenes three roles over the real evidence: an advocate for the MD result, an "
                      "advocate for the literature/NMR result, and a judge. The judge says whether the "
                      "two really contradict and how confident it is, without declaring which side "
                      "is correct (no experimental complex exists). Needs DEEPSEEK_API_KEY "
                      "(otherwise HTTP 400) and can take a while.",
          responses={200: {"content": {"application/json": {"example": {
              "interface_shown_by_data": ["<residue labels>"],
              "contradicts_literature_expectation": "<true or false>",
              "true_interface_experimentally_known": "<true or false>",
              "confidence_in_contradiction": "<0..1>",
              "confidence_in_which_side_is_right": "<0..1>",
              "flags": ["<flags>"], "recommendation": "<a concrete next experiment or check>",
              "reasoning": "<the judge's grounded reasoning>", "_note": _SHAPE_NOTE}}}},
              400: {"description": "DEEPSEEK_API_KEY is not set."}})
def debate() -> dict:
    """Convene the multi-agent debate (MD advocate vs NMR advocate + judge) over the
    current real evidence and return the judge's calibrated verdict."""
    _require_llm()
    from agent.debate import run as run_debate  # lazy import
    return run_debate()


# --- web client API ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    case_id: str | None = Field(
        default=None, description="A preset case id from GET /api/cases.", examples=["fat10_mad2"])
    uniprot_a: str | None = Field(
        default=None, description="Protein A UniProt accession (use with uniprot_b instead of case_id).",
        examples=["<UniProt accession>"])
    uniprot_b: str | None = Field(
        default=None, description="Protein B UniProt accession.", examples=["<UniProt accession>"])


@app.get("/api/cases", tags=["web"], operation_id="list_cases",
         summary="List the preset cases for the web page",
         description="The FAT10-MAD2 case study plus the benchmark protein pairs. Benchmark pairs are run "
                     "with their experimental complex hidden from the agent; no answers are returned here.",
         responses={200: {"content": {"application/json": {"example": webview.preset_cases()}}}})
def list_cases() -> list:
    return webview.preset_cases()


@app.post("/api/run", tags=["web"], operation_id="run_query",
          summary="Run one query and return a plain-language answer with labelled evidence",
          description="Runs the agent on a preset case or on a protein pair given by two UniProt "
                      "accessions. Returns `conclusion` (plain language), `evidence` rows each labelled "
                      "`live`, `cited` or `pending`, and `usage` (seconds and cost of this query). "
                      "Needs DEEPSEEK_API_KEY (otherwise HTTP 400), costs a little money and can take "
                      "a while. A malformed accession gives HTTP 422.",
         responses={200: {"content": {"application/json": {"example": {
             "case": {"id": "<case id>", "name": "<A – B>", "uniprot_a": "<accession>", "uniprot_b": "<accession>"},
             "conclusion": {"headline": "<plain-language answer>", "points": ["<...>"], "flags": ["<...>"],
                            "caveat": "<what this is not>", "details": "<agent explanation>"},
             "evidence": [{"item": "<what>", "detail": "<detail>", "label": "<live | cited | pending>",
                           "source": "<where from>", "records": "<count>"}],
             "usage": {"seconds": "<n>", "cost_usd": "<n>", "llm_calls": "<n>", "model": "<model>"},
             "steps": [{"tool": "<tool name>", "args": {}}],
             "_note": _SHAPE_NOTE}}}},
             400: {"description": "DEEPSEEK_API_KEY is not set."},
             422: {"description": "Neither a valid case_id nor two valid UniProt accessions."}})
def run_query(req: RunRequest) -> dict:
    try:
        case = webview.resolve_case(req.case_id, req.uniprot_a, req.uniprot_b)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _require_llm()
    try:
        return webview.run_query(case)
    except Exception as exc:                       # an upstream (LLM / network) failure, not a bad request
        raise HTTPException(status_code=502, detail=f"the query failed: {type(exc).__name__}")
