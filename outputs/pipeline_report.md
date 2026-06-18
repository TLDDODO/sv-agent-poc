# End-to-End Mutation Brief - EGFR T790M

**Pipeline:** PDBe retrieval (offline) -> canonical residue 790 mapping
-> MD-vs-NMA multi-agent debate -> combined reliability audit.

## 1. Structure Retrieval
| PDB | Resolution | Method | Mutation | State | Title |
| --- | --- | --- | --- | --- | --- |
| 5UG9 | 1.33 | X-ray diffraction | T790M | ligand-bound | EGFR L858R/T790M/V948R kinase domain in complex with inhibitor |
| 5HG8 | 1.42 | X-ray diffraction | T790M | ligand-bound | EGFR T790M kinase domain bound to covalent inhibitor |
| 5UG8 | 1.46 | X-ray diffraction | T790M | ligand-bound | EGFR T790M kinase domain inhibitor complex |
| 6TG0 | 1.5 | X-ray diffraction | T790M | ligand-bound | EGFR T790M kinase domain with ATP-competitive inhibitor |
| 6TFV | 1.5 | X-ray diffraction | T790M | ligand-bound | EGFR T790M kinase domain inhibitor complex |

## 2. Canonical Residue Mapping (EGFR / UniProt P00533)
| PDB | Chain | auth_seq | canonical | residue | observed |
| --- | --- | --- | --- | --- | --- |
| 5UG9 | A | 790 | P00533:790 | THR->MET | True |
| 5HG8 | A | 790 | P00533:790 | THR->MET | True |
| 5UG8 | A | 790 | P00533:790 | THR->MET | True |
| 6TG0 | A | 790 | P00533:790 | THR->MET | True |
| 6TFV | A | 790 | P00533:790 | THR->MET | True |

## 3. Dynamics: MD-vs-NMA Debate
The mapped system is interpreted by two method-bound experts over canonical regions.

**MD-view** (`traj:egfr_t790m_demo`, conf 0.82): MD flags [P-loop, activation-loop] as flexible; core [hinge, gatekeeper(T790), N-lobe beta-sheet, C-lobe core] stays rigid.
**NMA-view** (`enm:egfr_t790m_anm`, conf 0.75): NMA flags [P-loop, N-lobe beta-sheet] as flexible; core [hinge, gatekeeper(T790), C-lobe core] stays rigid.

- **NMA-view -> MD-view** on *P-loop* [agree]: P-loop: both ~0.68; methods concur.
- **NMA-view -> MD-view** on *alphaC-helix* [agree]: alphaC-helix: both ~0.47; methods concur.
- **NMA-view -> MD-view** on *hinge* [agree]: hinge: both ~0.32; methods concur.
- **NMA-view -> MD-view** on *gatekeeper(T790)* [agree]: gatekeeper(T790): both ~0.23; methods concur.
- **MD-view -> NMA-view** on *activation-loop* [disagree]: activation-loop: MD=0.85 vs NMA=0.40; MD sees more motion, likely anharmonic loop motion that MD captures but harmonic NMA flattens.
- **MD-view -> NMA-view** on *N-lobe beta-sheet* [disagree]: N-lobe beta-sheet: MD=0.32 vs NMA=0.60; NMA sees more motion, likely a slow collective mode NMA resolves but the trajectory under-samples.
- **NMA-view -> MD-view** on *C-lobe core* [agree]: C-lobe core: both ~0.17; methods concur.

### Aggregate judgment
**MD and NMA agree on the rigid core and shared flexible regions, but DISAGREE on [activation-loop, N-lobe beta-sheet] — treat those as method-dependent, not settled.**

- Agreement (Pearson r): **0.52** | Confidence: **0.61**
- Consensus: P-loop, alphaC-helix, hinge, gatekeeper(T790), C-lobe core
- Conflict: activation-loop, N-lobe beta-sheet

| Region | MD | NMA | delta | status |
| --- | --- | --- | --- | --- |
| P-loop | 0.70 | 0.65 | 0.05 | consensus |
| alphaC-helix | 0.45 | 0.50 | 0.05 | consensus |
| hinge | 0.30 | 0.35 | 0.05 | consensus |
| gatekeeper(T790) | 0.25 | 0.20 | 0.05 | consensus |
| activation-loop | 0.85 | 0.40 | 0.45 | conflict |
| N-lobe beta-sheet | 0.32 | 0.60 | 0.28 | conflict |
| C-lobe core | 0.20 | 0.15 | 0.05 | consensus |

## 4. Combined Reliability Audit
Evidence: structures [5UG9, 5HG8, 5UG8, 6TG0, 6TFV]; dynamics [traj:egfr_t790m_demo, enm:egfr_t790m_anm].

- Flag for human / experimental check: activation-loop (MD vs NMA disagree).
- Flag for human / experimental check: N-lobe beta-sheet (MD vs NMA disagree).

---
*Static structure evidence (PDBe) anchors the system and canonical numbering; the agents
interpret and reconcile the dynamics (MD vs NMA) but never generate it. MD stays the engine.
Dynamics use demo profiles - swap in real MDAnalysis RMSF + ENM fluctuations on HPC.*
