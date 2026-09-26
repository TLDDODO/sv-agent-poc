"""The Interface Adjudicator as an MCP server (official MCP Python SDK, v2 `MCPServer`).

Three tools, all thin wrappers over the functions the web client and FastAPI already use:
  list_cases        -> api.webview.preset_cases
  get_evidence      -> api.main.evidence  (+ webview.evidence_rows / findings for the labels)
  run_adjudication  -> api.webview.run_query  (the real agent loop; needs DEEPSEEK_API_KEY)

    python -m mcp_server                      # stdio (Claude Desktop)
    python -m mcp_server --transport http     # streamable HTTP on 127.0.0.1:8765/mcp (Dify)
"""
from __future__ import annotations
import argparse
import contextlib
import os
import sys
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from agent.cases import default_case
from api import webview

DEFAULT_HOST = "127.0.0.1"        # localhost only unless the operator passes --host
DEFAULT_PORT = 8765

INSTRUCTIONS = (
    "Adjudicates protein-protein interfaces from real evidence (PDBe, UniProt, MD contact occupancy, "
    "PubMed). Evidence rows are labelled live / cited / pending; nothing is invented. For FAT10-MAD2 the "
    "MD interface and the literature/NMR-expected region disagree; the system reports that contradiction "
    "and does not say which side is right. Start with list_cases, then get_evidence (free, no model call) "
    "or run_adjudication (calls the language model; costs a little and takes a while).")


def _resolve(case_id, uniprot_a, uniprot_b):
    try:
        return webview.resolve_case(case_id, uniprot_a, uniprot_b)
    except ValueError as exc:                    # bad case id / accession: an error the caller can read
        raise ToolError(str(exc)) from None


def _run_quietly(case):
    """The debate prints progress lines with print(); on stdio that would corrupt the protocol
    stream, so anything the run prints goes to stderr instead."""
    with contextlib.redirect_stdout(sys.stderr):
        return webview.run_query(case)


def build_server() -> MCPServer:
    mcp = MCPServer("interface-adjudicator", instructions=INSTRUCTIONS)

    @mcp.tool()
    def list_cases() -> dict[str, Any]:
        """List the preset cases (the FAT10-MAD2 case study and the benchmark protein pairs).
        Benchmark pairs are run with their experimental complex hidden; no answers are returned."""
        return {"cases": webview.preset_cases()}

    @mcp.tool()
    def get_evidence(case_id: str = "fat10_mad2") -> dict[str, Any]:
        """Get the real evidence without calling the language model: for FAT10-MAD2, the per-residue MD
        contact occupancy (from the committed 100 ns MD result file), the literature/NMR-expected region,
        and the deterministic check of whether they agree. `evidence` rows are labelled live / cited /
        pending; `findings` are computed by code from the tool outputs. Other pairs have no evidence
        outside an agent run: use run_adjudication for them."""
        case = _resolve(case_id, None, None)
        if case.id != default_case().id:
            return {"case": case.id, "status": "pending",
                    "note": "Evidence for this pair is gathered inside run_adjudication (with the held-out "
                            "complex filtered out); it is not available on its own."}
        from api import main as api              # lazy: builds the FastAPI app only when needed
        payload = api.evidence()
        md = {"occupancy": payload["md_occupancy"], "method": payload["md_method"]}
        transcript = [{"actions": [
            {"tool": "get_md_interface_scores", "args": {}, "result": md},
            {"tool": "get_expected_interface_region", "args": {}, "result": payload["expected_region"]}]}]
        return {"case": case.id, "status": "ok", "evidence_data": payload,
                "evidence": webview.evidence_rows(transcript),
                "findings": webview.findings(case, transcript)}

    @mcp.tool()
    async def run_adjudication(case_id: str | None = None, uniprot_a: str | None = None,
                               uniprot_b: str | None = None) -> dict[str, Any]:
        """Run the investigator agent on a preset case (`case_id`) or on a protein pair (two UniProt
        accessions). Returns `conclusion` (plain language in zh and en, with `findings` and the agent's
        `flags`), `evidence` rows labelled live / cited / pending, and `usage` (seconds and cost of
        this query). Needs DEEPSEEK_API_KEY on the server; costs a little money and takes tens of seconds."""
        case = _resolve(case_id, uniprot_a, uniprot_b)
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise ToolError("DEEPSEEK_API_KEY is not set on the MCP server, so run_adjudication is "
                               "disabled. list_cases and get_evidence still work.")
        return await anyio.to_thread.run_sync(_run_quietly, case)

    return mcp


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m mcp_server", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default=DEFAULT_HOST, help="HTTP only; default is localhost only")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP only")
    ap.add_argument("--allow-host", action="append", default=[], metavar="HOST[:PORT]",
                    help="HTTP only: extra Host header value to accept (e.g. host.docker.internal:8765 for "
                         "a Dify container); repeatable")
    args = ap.parse_args(argv)
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
        return
    allowed = [f"{h}:{args.port}" for h in ("127.0.0.1", "localhost")] + list(args.allow_host)
    server.run("streamable-http", host=args.host, port=args.port,
               transport_security=TransportSecuritySettings(allowed_hosts=allowed))
