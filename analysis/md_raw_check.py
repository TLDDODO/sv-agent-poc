"""Read-only checks against the archived HPC session record (analysis/md_raw/hpc_session_log.txt).

The record is the only surviving raw evidence of the MD run (trajectory and raw outputs are
gone), so this module only *reads* it. It never writes to it.
"""
from __future__ import annotations
import re
from pathlib import Path

LOG = Path(__file__).resolve().parent / "md_raw" / "hpc_session_log.txt"

# Amber residue names -> one letter (HIE = neutral His, epsilon-protonated).
_AA = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIE": "H", "HID": "H", "HIP": "H", "HIS": "H", "ILE": "I", "LEU": "L",
       "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
       "TYR": "Y", "VAL": "V"}

# `#Res Name First Last Natom #Orig #Mol`: "  291 ASP    4679   4690     12   291     2"
_RES = re.compile(r"^\s*(\d+)\s+([A-Z]{3})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
# pairs.dat rows: "   1   :163@N_:320@O     2000        1     2.96    0.163"
_PAIR = re.compile(r"^\s*(\d+)\s+:(\d+)@(\S+?)_:(\d+)@(\S+)\s+(\d+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s*$")


def _lines(path: Path = LOG) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def topology_residues(path: Path = LOG) -> dict[int, str]:
    """{residue number: 3-letter name} for every residue row in the record's topology tables."""
    out: dict[int, str] = {}
    for line in _lines(path):
        m = _RES.match(line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def topology_sequence(first: int, last: int, path: Path = LOG) -> str:
    """One-letter sequence of topology residues first..last; error if any is missing or non-standard."""
    res = topology_residues(path)
    missing = [i for i in range(first, last + 1) if i not in res]
    if missing:
        raise ValueError(f"residues missing from the record: {missing[:5]}...")
    return "".join(_AA[res[i]] for i in range(first, last + 1))


def pairs_rows(path: Path = LOG) -> list[dict]:
    """The pairs.dat rows the record shows: rank, FAT10 residue/atom, MAD2 residue/atom, frames, fraction."""
    rows = []
    for line in _lines(path):
        m = _PAIR.match(line)
        if m:
            rows.append({"rank": int(m.group(1)), "fat10_res": int(m.group(2)), "fat10_atom": m.group(3),
                         "mad2_res": int(m.group(4)), "mad2_atom": m.group(5),
                         "nframes": int(m.group(6)), "frac": float(m.group(7))})
    return rows
