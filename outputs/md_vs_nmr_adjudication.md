# Adjudication — MD interface vs NMR expectation

**Method (evidence):** `MD-contacts(100ns)`
**Expected region (standard):** N-terminal ubiquitin-like domain (residues 1-80)
**Source:** NMR: PDB 2MBE (first FAT10 domain); Theng et al. 2014 PNAS (FAT10-MAD2 interaction)

## Persistent interface from the MD (occupancy >= 0.5)
I163 (1.00), C162 (1.00), G164 (0.96), C160 (0.71), G165 (0.66), Y161 (0.61)

- Inside expected region (1-80): **NONE**
- Outside expected region: **I163, C162, G164, C160, G165, Y161**

## Verdict
🚩 **FLAG — model inconsistent with literature.**

The persistent interface (I163, C162, G164, C160, G165, Y161) lies ENTIRELY OUTSIDE the NMR-expected MAD2-binding region (residues 1-80, N-terminal ubiquitin-like domain). No persistent contact occurs in the expected region.

Likely cause: the AF3 starting model docked MAD2 onto FAT10's C-terminal region instead of the N-terminal ubl domain. Re-check the AF3 model (interface + ipTM/PAE) before treating these contacts as the interface hotspots.

---
*Deterministic check: persistent MD contacts vs the literature/NMR-expected
binding region. The MD evidence is real; the expected region is the standard.*
