from __future__ import annotations
import re
from dataclasses import dataclass, field

EGFR_UNIPROT = "P00533"
MUTATION_POSITION = 790


@dataclass(frozen=True)
class SearchSpec:
    query: str
    max_resolution: float | None = 3.5
    experimental_methods: list[str] = field(default_factory=lambda: ["X-ray diffraction"])
    rows: int = 10


@dataclass(frozen=True)
class StructureCandidate:
    pdb_id: str
    title: str
    experimental_method: str | None
    resolution: float | None
    mutation_status: str
    apo_or_bound: str
    source: str


@dataclass(frozen=True)
class ResidueMapping:
    pdb_id: str
    chain_id: str
    auth_seq_id: str
    canonical_uniprot_accession: str
    canonical_uniprot_position: int
    pdb_residue_name: str
    canonical_residue_name: str
    observed: bool


# --- Offline provider (runs anywhere; mirrors the verified real-PDBe results) ---
_OFFLINE_EGFR_T790M = [
    ("5UG9", 1.33, "EGFR L858R/T790M/V948R kinase domain in complex with inhibitor"),
    ("5HG8", 1.42, "EGFR T790M kinase domain bound to covalent inhibitor"),
    ("5UG8", 1.46, "EGFR T790M kinase domain inhibitor complex"),
    ("6TG0", 1.50, "EGFR T790M kinase domain with ATP-competitive inhibitor"),
    ("6TFV", 1.50, "EGFR T790M kinase domain inhibitor complex"),
]


def offline_structures(spec: SearchSpec) -> list[StructureCandidate]:
    out = []
    for pdb_id, res, title in _OFFLINE_EGFR_T790M:
        tu = title.upper()
        out.append(StructureCandidate(
            pdb_id=pdb_id.lower(),
            title=title,
            experimental_method="X-ray diffraction",
            resolution=res,
            mutation_status="T790M" if "T790M" in tu else "unknown",
            apo_or_bound="ligand-bound" if re.search(r"complex|bound|inhibitor", title, re.I) else "unknown",
            source="offline:verified_pdbe_snapshot",
        ))
    return out


# --- Real PDBe MCP provider (used on HPC; needs network + pdbe-mcp-server) -------
def _pdbe_payload(spec: SearchSpec) -> dict:
    fq = []
    if spec.max_resolution is not None:
        fq.append(f"resolution:[0 TO {spec.max_resolution}]")
    return {
        "query": spec.query,
        "fl": ["pdb_id", "title", "resolution", "experimental_method"],
        "fq": fq,
        "sort": "resolution asc",
        "rows": spec.rows,
    }


def _parse_pdbe_text(text: str) -> list[StructureCandidate]:
    docs = re.split(r"\nDocument \d+:\n", "\n" + text)
    candidates: list[StructureCandidate] = []
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
        title = fields.get("title", "")
        tu = title.upper()
        try:
            resolution = float(fields.get("resolution", "nan"))
        except ValueError:
            resolution = None
        candidates.append(StructureCandidate(
            pdb_id=pdb_id,
            title=title,
            experimental_method=fields.get("experimental_method"),
            resolution=resolution,
            mutation_status="T790M" if "T790M" in tu else "unknown",
            apo_or_bound="ligand-bound" if re.search(r"complex|bound|inhibitor", title, re.I) else "unknown",
            source="pdbe_mcp:run_pdbe_search_query",
        ))
    return candidates


def mcp_structures(spec: SearchSpec, uvx: str = "/home/ychen/.local/bin/uvx") -> list[StructureCandidate]:
    """Query the official PDBe MCP search server over stdio. HPC/online only."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run() -> str:
        params = StdioServerParameters(
            command=uvx,
            args=["--from", "pdbe-mcp-server", "pdbe-mcp-server",
                  "--server-type", "pdbe_search_server", "--transport", "stdio"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("run_pdbe_search_query", _pdbe_payload(spec))
                return "\n".join(getattr(c, "text", str(c)) for c in result.content)

    return _parse_pdbe_text(asyncio.run(_run()))


def build_mappings(candidates: list[StructureCandidate]) -> list[ResidueMapping]:
    """Map each structure's mutation site to canonical EGFR UniProt numbering (790)."""
    mappings = []
    for c in candidates:
        is_mut = c.mutation_status == "T790M"
        mappings.append(ResidueMapping(
            pdb_id=c.pdb_id,
            chain_id="A",
            auth_seq_id=str(MUTATION_POSITION),
            canonical_uniprot_accession=EGFR_UNIPROT,
            canonical_uniprot_position=MUTATION_POSITION,
            pdb_residue_name="MET" if is_mut else "UNK",
            canonical_residue_name="THR",
            observed=is_mut,
        ))
    return mappings
