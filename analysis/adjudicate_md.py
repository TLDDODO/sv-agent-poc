#!/usr/bin/env python3
"""Automatic adjudication: real MD interface vs the NMR-expected region.

Deterministic (no LLM, no network) so it runs anywhere and is reproducible.
Takes the real per-residue MD contact occupancies and checks whether the
persistent interface falls in the region the literature/NMR expects MAD2 to
bind on FAT10. If not, it FLAGS the model — this is the check that turns the
"MD says C-terminal, NMR says N-terminal" observation into an automatic verdict.

    python3 analysis/adjudicate_md.py [md_interface_scores.json]
"""
import json
import re
import sys
from pathlib import Path

# FAT10 (UniProt O15205) domain boundaries — VERIFIED from UniProt feature table.
DOMAINS = [
    ("Ubiquitin-like 1 (N-term)", 6, 81),
    ("linker", 82, 89),
    ("Ubiquitin-like 2 (C-term)", 90, 163),
    ("C-terminal tail", 164, 165),
]
# Literature / NMR expectation: MAD2 binds FAT10's FIRST (N-terminal) ubl domain.
EXPECTED = {
    "region": "Ubiquitin-like 1 (N-terminal domain)",
    "residue_range": (6, 81),   # UniProt O15205 DOMAIN "Ubiquitin-like 1"
    "source": "UniProt O15205 (domain boundaries); NMR PDB 2MBE (first FAT10 domain); "
              "Theng et al. 2014 PNAS (FAT10-MAD2 interaction)",
}
INTERFACE_CUTOFF = 0.5   # occupancy >= 0.5 = persistent interface contact
SECONDARY_CUTOFF = 0.1   # 0.1-0.5 = transient/secondary


def resnum(label: str):
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) if m else None


def domain_of(n):
    for name, lo, hi in DOMAINS:
        if lo <= n <= hi:
            return name
    return "outside annotated domains"


def adjudicate(scores: dict) -> dict:
    lo, hi = EXPECTED["residue_range"]
    core = {k: v for k, v in scores.items() if v >= INTERFACE_CUTOFF}
    secondary = {k: v for k, v in scores.items() if SECONDARY_CUTOFF <= v < INTERFACE_CUTOFF}
    in_expected = sorted([k for k in core if lo <= (resnum(k) or 0) <= hi],
                         key=lambda k: -core[k])
    out_expected = sorted([k for k in core if not (lo <= (resnum(k) or 0) <= hi)],
                          key=lambda k: -core[k])
    flag = bool(core) and not in_expected
    return {
        "core_interface": dict(sorted(core.items(), key=lambda kv: -kv[1])),
        "secondary": dict(sorted(secondary.items(), key=lambda kv: -kv[1])),
        "in_expected_region": in_expected,
        "outside_expected_region": out_expected,
        "flag": flag,
    }


def render(method: str, adj: dict) -> str:
    lo, hi = EXPECTED["residue_range"]
    core = adj["core_interface"]
    core_str = ", ".join(f"{k} ({v:.2f})" for k, v in core.items()) or "-"
    if adj["flag"]:
        verdict = (
            f"🚩 **FLAG — model inconsistent with literature.**\n\n"
            f"The persistent interface ({', '.join(core)}) lies ENTIRELY OUTSIDE the "
            f"NMR-expected MAD2-binding region (residues {lo}-{hi}, "
            f"{EXPECTED['region']}). No persistent contact occurs in the expected region.\n\n"
            f"Likely cause: the AF3 starting model docked MAD2 onto FAT10's C-terminal "
            f"region instead of the N-terminal ubl domain. Re-check the AF3 model "
            f"(interface + ipTM/PAE) before treating these contacts as the interface hotspots."
        )
    else:
        verdict = (f"✅ The persistent interface overlaps the NMR-expected region "
                   f"({lo}-{hi}): {', '.join(adj['in_expected_region'])}.")
    return f"""# Adjudication — MD interface vs NMR expectation

**Method (evidence):** `{method}`
**Expected region (standard):** {EXPECTED['region']} (residues {lo}-{hi})
**Source:** {EXPECTED['source']}

## Persistent interface from the MD (occupancy >= {INTERFACE_CUTOFF})
{core_str}

Domain of each: {', '.join(f"{k}={domain_of(resnum(k))}" for k in core)}

- Inside expected region ({lo}-{hi}, {EXPECTED['region']}): **{', '.join(adj['in_expected_region']) or 'NONE'}**
- Outside expected region: **{', '.join(adj['outside_expected_region']) or 'none'}**

## Verdict
{verdict}

---
*Deterministic check: persistent MD contacts vs the literature/NMR-expected
binding region. The MD evidence is real; the expected region is the standard.*
"""


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "analysis/md_interface_scores.json"
    data = json.loads(Path(path).read_text())
    method, scores = next(iter(data.items()))
    adj = adjudicate(scores)

    out = Path("outputs")
    out.mkdir(exist_ok=True)
    (out / "md_vs_nmr_adjudication.md").write_text(render(method, adj), encoding="utf-8")

    print(f"\nMethod: {method}")
    print(f"Persistent interface (occ >= {INTERFACE_CUTOFF}): "
          f"{', '.join(adj['core_interface']) or '-'}")
    print(f"Inside NMR-expected region {EXPECTED['residue_range']}: "
          f"{adj['in_expected_region'] or 'NONE'}")
    print(f"FLAG (interface outside expected region): {adj['flag']}")
    print("\nWROTE outputs/md_vs_nmr_adjudication.md")


if __name__ == "__main__":
    main()
