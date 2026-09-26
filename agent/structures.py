from __future__ import annotations
import os
import re
from dataclasses import dataclass

FAT10_UNIPROT = "O15205"        # UBD / FAT10
MAD2_UNIPROT = "Q13257"         # MAD2L1
NTERM_UBL_RANGE = (6, 81)       # FAT10 UBL1, UniProt O15205 DOMAIN "Ubiquitin-like 1" (verified)

_THREE = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS", "Q": "GLN",
    "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE", "L": "LEU", "K": "LYS",
    "M": "MET", "F": "PHE", "P": "PRO", "S": "SER", "T": "THR", "W": "TRP",
    "Y": "TYR", "V": "VAL",
}


@dataclass(frozen=True)
class StructureHit:
    pdb_id: str
    title: str
    experimental_method: str | None
    resolution: float | None
    source: str


@dataclass(frozen=True)
class ResidueMapping:
    residue_label: str              # e.g. "L9"
    residue_name: str               # LEU
    canonical_uniprot_accession: str
    canonical_uniprot_position: int
    in_nterm_ubl: bool              # falls inside the MAD2-binding domain?


# Snapshot of the verified live PDBe query (uniprot_accession:O15205) for offline use.
_VERIFIED_FAT10 = [
    ("6GF1", 1.925, "X-ray diffraction",
     "The structure of the ubiquitin-like modifier FAT10 reveals a novel targeting "
     "mechanism for degradation by the 26S proteasome"),
    ("6GF2", None, "Solution NMR",
     "The structure of the ubiquitin-like modifier FAT10 reveals a novel targeting "
     "mechanism for degradation by the 26S proteasome"),
    ("2MBE", None, "Solution NMR",
     "Backbone 1H and 15N Chemical Shift Assignments for the first domain of FAT10"),
    ("7PYV", 3.27, "X-ray diffraction",
     "Crystal structure of human UBA6 in complex with the ubiquitin-like modifier FAT10"),
]


def offline_structures() -> list[StructureHit]:
    """Verified snapshot of the live PDBe query (uniprot_accession:O15205), so the
    offline demo shows the real FAT10 structures. 2MBE is the N-terminal (MAD2-binding)
    domain; 6GF1/6GF2 are full FAT10. Use mcp_structures() for a fresh live query."""
    return [
        StructureHit(pdb_id=p.lower(), title=t, experimental_method=m,
                     resolution=r, source="offline:verified_pdbe_snapshot")
        for p, r, m, t in _VERIFIED_FAT10
    ]


# --- Real PDBe MCP query (HPC / online) --------------------------------------
def _pdbe_payload(uniprot: str = FAT10_UNIPROT) -> dict:
    # Filter by UniProt accession (reliable) rather than a free-text molecule name,
    # which Solr treated as match-all and returned the whole PDB by resolution.
    return {
        "query": f"uniprot_accession:{uniprot}",
        "fl": ["pdb_id", "title", "resolution", "experimental_method"],
        "rows": 10,
    }


def _parse(text: str) -> list[StructureHit]:
    docs = re.split(r"\nDocument \d+:\n", "\n" + text)
    hits: list[StructureHit] = []
    for doc in docs[1:]:
        fields: dict[str, str] = {}
        key = None
        for raw in doc.splitlines():
            if not raw.strip():
                continue
            m = re.match(r"\s{2}([A-Za-z0-9_]+):\s*(.*)", raw)
            if m:
                key = m.group(1)
                fields[key] = m.group(2).strip()
            elif key:
                fields[key] += " " + raw.strip()
        pdb_id = fields.get("pdb_id", "").lower()
        if not pdb_id:
            continue
        try:
            resolution = float(fields.get("resolution", "nan"))
        except ValueError:
            resolution = None
        hits.append(StructureHit(
            pdb_id=pdb_id,
            title=fields.get("title", ""),
            experimental_method=fields.get("experimental_method"),
            resolution=resolution,
            source="pdbe_mcp:run_pdbe_search_query",
        ))
    return hits


# The MCP stdio client only passes HOME/PATH/SHELL/TERM to the server process. Behind
# an HTTPS proxy the server also needs the proxy and CA settings, so pass exactly those
# through (never the whole environment: that would hand API keys to the subprocess).
_PASSTHROUGH_ENV = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "NO_PROXY",
                    "no_proxy", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE")


def mcp_structures(uniprot: str = FAT10_UNIPROT, uvx: str | None = None,
                   timeout: float | None = None) -> list[StructureHit]:
    """Query the official PDBe MCP search server for a UniProt accession's structures
    (live; needs network + `uvx`). This is the real MCP client — a stdio session to
    the PDBe server. Raises on any failure; `agent.tools.fetch_structures` decides
    what to fall back to."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import get_default_environment, stdio_client

    uvx = uvx or os.environ.get("UVX", "uvx")
    timeout = timeout or float(os.environ.get("PDBE_MCP_TIMEOUT", "90"))
    env = {**get_default_environment(),
           **{k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ}}

    async def _run() -> str:
        params = StdioServerParameters(
            command=uvx,
            args=["--from", "pdbe-mcp-server", "pdbe-mcp-server",
                  "--server-type", "pdbe_search_server", "--transport", "stdio"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("run_pdbe_search_query", _pdbe_payload(uniprot))
                return "\n".join(getattr(c, "text", str(c)) for c in result.content)

    from . import metrics
    try:
        text = asyncio.run(asyncio.wait_for(_run(), timeout))
        if "Documents:" not in text:
            raise RuntimeError(f"unexpected PDBe MCP response: {text[:200]}")
        hits = _parse(text)
    except Exception:
        metrics.call("PDBe", 0, ok=False)
        raise
    metrics.call("PDBe", len(hits))
    return hits


def canonical_map(residue_labels: list[str], uniprot: str = FAT10_UNIPROT,
                  domain: tuple[int, int] = NTERM_UBL_RANGE) -> list[ResidueMapping]:
    """Map each predicted interface residue (e.g. 'L9') to canonical UniProt
    numbering, and check it sits in the given domain range. This guarantees all
    tools' residue numbers refer to the same positions. Works for any protein."""
    out = []
    lo, hi = domain
    for lab in residue_labels:
        m = re.match(r"([A-Z])(\d+)$", lab)
        if not m:
            continue
        aa, num = m.group(1), int(m.group(2))
        out.append(ResidueMapping(
            residue_label=lab,
            residue_name=_THREE.get(aa, "UNK"),
            canonical_uniprot_accession=uniprot,
            canonical_uniprot_position=num,
            in_nterm_ubl=lo <= num <= hi,
        ))
    return out
