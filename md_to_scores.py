"""md_to_scores.py

Convert the cpptraj per-residue interface output (from interface_occupancy.cpptraj)
into a clean per-FAT10-residue interface-occupancy JSON that the adjudicator agent
can consume as the MD evidence line.

    FAT10 = residues 1-165 (cpptraj residue number == the agent's residue label,
            e.g. Cys7 -> "7", Cys9 -> "9").
    MAD2  = residues 166-370.

Usage:
    python md_to_scores.py fat10_mad2_byres.dat            # writes md_interface_scores.json
    python md_to_scores.py fat10_mad2_byres.dat --pairs fat10_mad2_pairs.dat

NOTE ON THE PARSER (provisional):
    cpptraj's exact column layout for `resout` / `writecontacts` depends on
    version. The `parse_*` functions below are isolated on purpose: run the
    cpptraj deck once, look at the header of the output file, and adjust the
    column indices in ONE place. Everything downstream is format-independent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# FAT10 / MAD2 residue ranges in the topology (1-based cpptraj numbering).
FAT10_RANGE = (1, 165)
MAD2_RANGE = (166, 370)
CONTACT_CUTOFF_A = 4.5


def parse_pairs(path: Path) -> dict[int, float]:
    """Parse `writecontacts` output (residue-residue contact list with a fraction).

    Aggregates to a per-FAT10-residue occupancy by taking, for each FAT10 residue,
    the MAX fraction over all its MAD2 partner contacts -- i.e. "how much of the
    trajectory is this residue engaged in the interface at all".

    Expected line shape (whitespace separated), e.g.:
        :7@SG_:300@O      950     0.95   ...
    We pull the first residue index from the FIRST mask token and the contact
    fraction from the column that lies in [0, 1]. Adjust here if the real header
    differs.
    """
    occ: dict[int, float] = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tok = line.split()
        resid = _first_resid(tok[0])
        if resid is None or not (FAT10_RANGE[0] <= resid <= FAT10_RANGE[1]):
            continue
        frac = _first_fraction(tok[1:])
        if frac is None:
            continue
        occ[resid] = max(occ.get(resid, 0.0), frac)
    return occ


def parse_byres(path: Path) -> dict[int, float]:
    """Parse `resout` byresidue output. Fallback when pairs file is unavailable.

    This file typically lists per-residue contact counts/fractions. We keep the
    value in [0, 1] for each FAT10 residue. Adjust column picking after seeing
    the real header.
    """
    occ: dict[int, float] = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tok = line.split()
        resid = _first_resid(tok[0])
        if resid is None or not (FAT10_RANGE[0] <= resid <= FAT10_RANGE[1]):
            continue
        frac = _first_fraction(tok[1:])
        if frac is not None:
            occ[resid] = max(occ.get(resid, 0.0), frac)
    return occ


def _first_resid(token: str) -> int | None:
    """Pull the first integer residue index out of a cpptraj mask token like ':7@SG' or '7'."""
    num = ""
    started = False
    for ch in token.lstrip(":"):
        if ch.isdigit():
            num += ch
            started = True
        elif started:
            break
    return int(num) if num else None


def _first_fraction(tokens: list[str]) -> float | None:
    """Return the first float that looks like a fraction in [0, 1]."""
    for t in tokens:
        try:
            v = float(t)
        except ValueError:
            continue
        if 0.0 <= v <= 1.0:
            return v
    return None


def to_interface_scores(occupancy: dict[int, float], n_frames: int | None) -> dict:
    """Wrap per-residue occupancy in a clean, self-describing evidence object.

    This is the MD voter's output. Map `scores` onto the agent's real
    INTERFACE_SCORES keys once that schema is confirmed -- the keys here are
    plain FAT10 residue numbers as strings ("7", "9", ...), which already match
    the agent's C7 / C9 style labels.
    """
    return {
        "system": "FAT10-MAD2",
        "method": "MD",
        "metric": "interface_contact_occupancy",
        "description": (
            "Fraction of trajectory frames in which each FAT10 residue has at "
            "least one heavy-atom contact (<= %.1f A) with MAD2." % CONTACT_CUTOFF_A
        ),
        "source": "Amber pmemd.cuda, 100 ns explicit-solvent replica (ablhmr topology)",
        "cutoff_angstrom": CONTACT_CUTOFF_A,
        "chain_definitions": {
            "FAT10": f"{FAT10_RANGE[0]}-{FAT10_RANGE[1]}",
            "MAD2": f"{MAD2_RANGE[0]}-{MAD2_RANGE[1]}",
        },
        "n_frames": n_frames,
        "scores": {str(r): round(occupancy[r], 3) for r in sorted(occupancy)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("byres", help="cpptraj resout file (fat10_mad2_byres.dat)")
    ap.add_argument("--pairs", help="cpptraj writecontacts file (preferred source)")
    ap.add_argument("--n-frames", type=int, default=None, help="number of frames analysed")
    ap.add_argument("--out", default="md_interface_scores.json")
    args = ap.parse_args()

    if args.pairs and Path(args.pairs).exists():
        occ = parse_pairs(Path(args.pairs))
    else:
        occ = parse_byres(Path(args.byres))

    if not occ:
        raise SystemExit(
            "No FAT10 residues parsed -- the column layout almost certainly "
            "differs from the assumed format. Paste the first ~15 lines of the "
            "cpptraj output so the parser can be locked to the real header."
        )

    evidence = to_interface_scores(occ, args.n_frames)
    Path(args.out).write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    top = sorted(occ.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print(f"WROTE {args.out}  ({len(occ)} FAT10 residues)")
    print("Top interface residues (FAT10 resid -> occupancy):")
    for resid, frac in top:
        print(f"  {resid:>4} : {frac:.3f}")


if __name__ == "__main__":
    main()
