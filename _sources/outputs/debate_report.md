# Multi-Agent Method-Comparison Brief - EGFR T790M

**Question:** Do MD and NMA agree on the dynamics of EGFR T790M, and where should we trust which?

## 1. Expert Verdicts

### MD-view - source `traj:egfr_t790m_demo` - confidence 0.82
MD flags [P-loop, activation-loop] as flexible; core [hinge, gatekeeper(T790), N-lobe beta-sheet, C-lobe core] stays rigid. Interpretation constrained by: MD captures anharmonic and solvent-coupled motion but depends on sampling and convergence (here a 400 ns demo).

| Region | MD flex | stance |
| --- | --- | --- |
| P-loop | 0.70 | flexible |
| alphaC-helix | 0.45 | intermediate |
| hinge | 0.30 | rigid |
| gatekeeper(T790) | 0.25 | rigid |
| activation-loop | 0.85 | flexible |
| N-lobe beta-sheet | 0.32 | rigid |
| C-lobe core | 0.20 | rigid |

### NMA-view - source `enm:egfr_t790m_anm` - confidence 0.75
NMA flags [P-loop, N-lobe beta-sheet] as flexible; core [hinge, gatekeeper(T790), C-lobe core] stays rigid. Interpretation constrained by: ENM/NMA captures slow collective modes cheaply but is harmonic, solvent-free, and tends to underestimate large anharmonic loop motions.

| Region | NMA flex | stance |
| --- | --- | --- |
| P-loop | 0.65 | flexible |
| alphaC-helix | 0.50 | intermediate |
| hinge | 0.35 | rigid |
| gatekeeper(T790) | 0.20 | rigid |
| activation-loop | 0.40 | intermediate |
| N-lobe beta-sheet | 0.60 | flexible |
| C-lobe core | 0.15 | rigid |

## 2. Debate (who agrees with whom)
- **NMA-view -> MD-view** on *P-loop* [agree]: P-loop: both ~0.68; methods concur.
- **NMA-view -> MD-view** on *alphaC-helix* [agree]: alphaC-helix: both ~0.47; methods concur.
- **NMA-view -> MD-view** on *hinge* [agree]: hinge: both ~0.32; methods concur.
- **NMA-view -> MD-view** on *gatekeeper(T790)* [agree]: gatekeeper(T790): both ~0.23; methods concur.
- **MD-view -> NMA-view** on *activation-loop* [disagree]: activation-loop: MD=0.85 vs NMA=0.40; MD sees more motion, likely anharmonic loop motion that MD captures but harmonic NMA flattens.
- **MD-view -> NMA-view** on *N-lobe beta-sheet* [disagree]: N-lobe beta-sheet: MD=0.32 vs NMA=0.60; NMA sees more motion, likely a slow collective mode NMA resolves but the trajectory under-samples.
- **NMA-view -> MD-view** on *C-lobe core* [agree]: C-lobe core: both ~0.17; methods concur.

## 3. Aggregate Judgment
**Verdict:** MD and NMA agree on the rigid core and shared flexible regions, but DISAGREE on [activation-loop, N-lobe beta-sheet] — treat those as method-dependent, not settled.

- Agreement (Pearson r): **0.52**
- Confidence: **0.61**
- Consensus regions: P-loop, alphaC-helix, hinge, gatekeeper(T790), C-lobe core
- Conflict regions: activation-loop, N-lobe beta-sheet

| Region | MD | NMA | delta | status |
| --- | --- | --- | --- | --- |
| P-loop | 0.70 | 0.65 | 0.05 | consensus |
| alphaC-helix | 0.45 | 0.50 | 0.05 | consensus |
| hinge | 0.30 | 0.35 | 0.05 | consensus |
| gatekeeper(T790) | 0.25 | 0.20 | 0.05 | consensus |
| activation-loop | 0.85 | 0.40 | 0.45 | conflict |
| N-lobe beta-sheet | 0.32 | 0.60 | 0.28 | conflict |
| C-lobe core | 0.20 | 0.15 | 0.05 | consensus |

## 4. Reliability Audit (critic)
- Flag for human / experimental check: activation-loop (MD vs NMA disagree).
- Flag for human / experimental check: N-lobe beta-sheet (MD vs NMA disagree).

---
*MD = molecular dynamics (the real engine). NMA = normal-mode analysis. The agents
interpret and reconcile both methods; they do not generate the dynamics. Current run
uses demo profiles - swap in real MDAnalysis RMSF + ENM fluctuations on HPC.*
