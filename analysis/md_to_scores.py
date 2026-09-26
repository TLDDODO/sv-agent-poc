#!/usr/bin/env python3
"""Turn cpptraj nativecontacts output into REAL per-residue interface scores.

Run this ON THE NODE where the MD files live (stdlib only, no deps):

    python3 md_to_scores.py ablhmr.prmtop fat10_mad2_pairs.dat

It writes md_interface_scores.json in the INTERFACE_SCORES format
({tool: {residue: score}}) and prints a summary that immediately shows whether
the placeholder "consensus interface" (N-terminal residues) actually carries the
MAD2 contacts in the 100 ns MD, or whether the real interface is elsewhere.

Score = per FAT10 residue, the MAX fraction-of-frames (Frac.) over all its
atom-atom native contacts with MAD2 = how persistently that residue touches MAD2.
Caveat: cpptraj `nativecontacts` defines "native" from the reference/first frame,
so contacts that only form later may be undercounted; this is a first real pass.
"""
import json
import re
import sys

FAT10_MAX_RES = 165          # residues 1-165 = FAT10; 166-370 = MAD2
TOOL = "MD-contacts(100ns)"
WATCH = ["C7", "C9", "F22", "A24", "Q46", "Q48", "S64", "Y66"]  # placeholder residues

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "ASH": "D", "CYS": "C",
    "CYX": "C", "CYM": "C", "GLN": "Q", "GLU": "E", "GLH": "E", "GLY": "G",
    "HIS": "H", "HIE": "H", "HID": "H", "HIP": "H", "ILE": "I", "LEU": "L",
    "LYS": "K", "LYN": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S",
    "THR": "T", "TRP": "W", "TYR": "Y", "TYM": "Y", "VAL": "V",
}


def read_residue_labels(prmtop_path):
    """Parse %FLAG RESIDUE_LABEL from an Amber prmtop -> list of 3-letter names."""
    labels, grab = [], False
    with open(prmtop_path) as fh:
        for line in fh:
            if line.startswith("%FLAG"):
                grab = line.split()[1] == "RESIDUE_LABEL"
                continue
            if grab and line.startswith("%FORMAT"):
                continue
            if grab:
                if line.startswith("%"):
                    break
                labels += [line[i:i + 4].strip() for i in range(0, len(line.rstrip("\n")), 4)]
    return [x for x in labels if x]


def parse_pairs(pairs_path):
    """Per FAT10 residue (<=165), max Frac over its atom-atom contacts with MAD2."""
    best = {}
    res = re.compile(r":(\d+)@")
    with open(pairs_path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            contact, frac = parts[1], parts[3]
            nums = [int(n) for n in res.findall(contact)]
            if len(nums) != 2:
                continue
            fat10 = [n for n in nums if n <= FAT10_MAX_RES]
            mad2 = [n for n in nums if n > FAT10_MAX_RES]
            if len(fat10) != 1 or len(mad2) != 1:
                continue
            try:
                f = float(frac)
            except ValueError:
                continue
            r = fat10[0]
            best[r] = max(best.get(r, 0.0), f)
    return best


def main():
    prmtop = sys.argv[1] if len(sys.argv) > 1 else "ablhmr.prmtop"
    pairs = sys.argv[2] if len(sys.argv) > 2 else "fat10_mad2_pairs.dat"

    names = read_residue_labels(prmtop)
    best = parse_pairs(pairs)

    def label(resnum):
        three = names[resnum - 1] if resnum - 1 < len(names) else "UNK"
        return f"{THREE_TO_ONE.get(three, 'X')}{resnum}"

    scores = {label(r): round(best[r], 3) for r in sorted(best)}
    out = {TOOL: scores}
    with open("md_interface_scores.json", "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"\nWROTE md_interface_scores.json  ({len(scores)} FAT10 residues contact MAD2)\n")

    print("=== Placeholder residues vs REAL MD contact occupancy ===")
    label_by_num = {}
    for r in best:
        label_by_num[label(r)] = best[r]
    for w in WATCH:
        occ = label_by_num.get(w)
        verdict = f"{occ:.3f}" if occ is not None else "0.000  <-- NO MD contact with MAD2"
        print(f"  {w:5s} -> {verdict}")

    print("\n=== Where the REAL interface is (top 15 FAT10 residues by MD occupancy) ===")
    top = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:15]
    for r, f in top:
        print(f"  {label(r):6s} (res {r:3d})  occupancy {f:.3f}")


if __name__ == "__main__":
    main()
