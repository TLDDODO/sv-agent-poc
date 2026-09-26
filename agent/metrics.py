"""Workload counters: what one query actually touched.

Counted at the call sites (not guessed from tool names):
  * a *data API call* is one request our code makes to an external data source (PDBe,
    UniProt, PubMed), counted when it is attempted, whether it succeeded or failed. The
    PDBe MCP query counts as one call (the server's own requests behind it are not visible);
  * *records* are what came back from / were checked against that source: PDBe entries
    returned, PubMed abstracts, UniProt annotation features, residues validated, plus the
    per-residue rows read from the local MD result file;
  * LLM calls are counted separately by the run log.

RunRecorder starts a collector when a run begins and stores its summary in the run-log line
(`activity`); outside a run, calls are ignored.
"""
from __future__ import annotations
from contextvars import ContextVar

_ACTIVE: ContextVar[dict | None] = ContextVar("workload_collector", default=None)


def start() -> dict:
    d = {"calls": [], "local": []}
    _ACTIVE.set(d)
    return d


def stop() -> None:
    _ACTIVE.set(None)


def call(database: str, records: int = 0, ok: bool = True) -> None:
    """One request to an external data source."""
    d = _ACTIVE.get()
    if d is not None:
        d["calls"].append({"database": database, "records": int(records), "ok": bool(ok)})


def local(name: str, records: int) -> None:
    """One read of a local data file (not an external database)."""
    d = _ACTIVE.get()
    if d is not None:
        d["local"].append({"file": name, "records": int(records)})


def summary(d: dict | None) -> dict:
    d = d or {"calls": [], "local": []}
    by: dict[str, dict] = {}
    for c in d["calls"]:
        b = by.setdefault(c["database"], {"calls": 0, "failed": 0, "records": 0})
        b["calls"] += 1
        b["failed"] += 0 if c["ok"] else 1
        b["records"] += c["records"]
    return {
        "databases": sorted(k for k, v in by.items() if v["calls"] > v["failed"]),   # reached at least once
        "data_api_calls": len(d["calls"]),
        "failed_calls": sum(v["failed"] for v in by.values()),
        "by_database": by,
        "local_files": sorted({x["file"] for x in d["local"]}),
        "records_processed": sum(c["records"] for c in d["calls"]) + sum(x["records"] for x in d["local"]),
    }
