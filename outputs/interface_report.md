# Interface-Tool Adjudication - FAT10 N-terminal ubl domain : MAD2

**System:** FAT10 (UniProt O15205) N-terminal ubl domain : MAD2 (UniProt Q13257)
**Question:** Which FAT10 residues form the MAD2 interface, where do the prediction tools
agree, and which residues are too disputed to commit to an MD interface model?

## 1. Structure Retrieval (PDBe)
| PDB | Resolution | Method | Title |
| --- | --- | --- | --- |
| 6GF1 | 1.925 | X-ray diffraction | The structure of the ubiquitin-like modifier FAT10 reveals a novel targeting mechanism for degradation by the 26S proteasome |
| 6GF2 | - | Solution NMR | The structure of the ubiquitin-like modifier FAT10 reveals a novel targeting mechanism for degradation by the 26S proteasome |
| 2MBE | - | Solution NMR | Backbone 1H and 15N Chemical Shift Assignments for the first domain of FAT10 |
| 7PYV | 3.27 | X-ray diffraction | Crystal structure of human UBA6 in complex with the ubiquitin-like modifier FAT10 |

## 2. Canonical Residue Mapping (FAT10 / UniProt O15205)
Every predicted interface residue is anchored to canonical numbering and checked
against the MAD2-binding N-terminal ubl domain (residues 1-80),
so all tools refer to the same positions.

| Residue | Name | Canonical | In N-term ubl |
| --- | --- | --- | --- |
| C7 | CYS | O15205:7 | True |
| C9 | CYS | O15205:9 | True |
| F22 | PHE | O15205:22 | True |
| A24 | ALA | O15205:24 | True |
| Q46 | GLN | O15205:46 | True |
| Q48 | GLN | O15205:48 | True |
| S64 | SER | O15205:64 | True |
| Y66 | TYR | O15205:66 | True |

## 3. Tool Verdicts (each agent interprets one tool)
### AlphaFold-Multimer  -  source `afm:fat10_mad2_demo`  -  confidence 0.85
AlphaFold-Multimer flags interface residues [C7, C9, F22, A24, Q46, Y66]. Caveat: AF-Multimer interface confidence is model-derived, not experimental, and can be overconfident on shallow or transient interfaces.

Called interface: **C7, C9, F22, A24, Q46, Y66**

### HADDOCK  -  source `haddock:fat10_mad2_demo`  -  confidence 0.8
HADDOCK flags interface residues [C7, C9, F22, A24, Q46]. Caveat: HADDOCK scores depend on the input restraints and sampling; they reflect docking energetics, not direct observation.

Called interface: **C7, C9, F22, A24, Q46**

### PISA-contacts  -  source `pisa:fat10_mad2_demo`  -  confidence 0.81
PISA-contacts flags interface residues [C7, C9, F22, A24, Q46, Y66]. Caveat: PISA contacts come from a single static pose; they are sensitive to which docked model was chosen.

Called interface: **C7, C9, F22, A24, Q46, Y66**

## 4. Per-Residue Comparison
| Residue | AlphaFold-Multimer | HADDOCK | PISA-contacts | mean | spread | status |
| --- | --- | --- | --- | --- | --- | --- |
| C7 | 0.80 | 0.75 | 0.82 | 0.79 | 0.07 | consensus-interface |
| C9 | 0.90 | 0.85 | 0.88 | 0.88 | 0.05 | consensus-interface |
| F22 | 0.70 | 0.65 | 0.68 | 0.68 | 0.05 | consensus-interface |
| A24 | 0.85 | 0.80 | 0.82 | 0.82 | 0.05 | consensus-interface |
| Q46 | 0.75 | 0.70 | 0.72 | 0.72 | 0.05 | consensus-interface |
| Q48 | 0.30 | 0.35 | 0.28 | 0.31 | 0.07 | consensus-noninterface |
| S64 | 0.20 | 0.55 | 0.25 | 0.33 | 0.35 | disputed |
| Y66 | 0.65 | 0.25 | 0.60 | 0.50 | 0.40 | disputed |

## 5. Disagreements (who calls what)
- **AlphaFold-Multimer, HADDOCK, PISA-contacts** vs **all** on *C7* [agree]: C7: all tools ~0.79; agreed interface residue.
- **AlphaFold-Multimer, HADDOCK, PISA-contacts** vs **all** on *C9* [agree]: C9: all tools ~0.88; agreed interface residue.
- **AlphaFold-Multimer, HADDOCK, PISA-contacts** vs **all** on *F22* [agree]: F22: all tools ~0.68; agreed interface residue.
- **AlphaFold-Multimer, HADDOCK, PISA-contacts** vs **all** on *A24* [agree]: A24: all tools ~0.82; agreed interface residue.
- **AlphaFold-Multimer, HADDOCK, PISA-contacts** vs **all** on *Q46* [agree]: Q46: all tools ~0.72; agreed interface residue.
- **HADDOCK** vs **AlphaFold-Multimer, PISA-contacts** on *S64* [disagree]: S64: AlphaFold-Multimer=0.20, HADDOCK=0.55, PISA-contacts=0.25. [HADDOCK] lean interface; [AlphaFold-Multimer, PISA-contacts] lean against.
- **AlphaFold-Multimer, PISA-contacts** vs **HADDOCK** on *Y66* [disagree]: Y66: AlphaFold-Multimer=0.65, HADDOCK=0.25, PISA-contacts=0.60. [AlphaFold-Multimer, PISA-contacts] lean interface; [HADDOCK] lean against.

## 6. Adjudicated Interface
- **Consensus interface residues (use for the MD interface model):** C7, C9, F22, A24, Q46
- **Consensus non-interface:** Q48
- **Disputed (need MD / experimental check):** S64, Y66
- **Weak / ambiguous:** -
- Agreement (1 - mean spread): **0.86** | Confidence: **0.62**

## 7. Reliability Audit
Evidence: afm:fat10_mad2_demo, haddock:fat10_mad2_demo, pisa:fat10_mad2_demo

- Flag for MD / experimental check: S64 (tools disagree).
- Flag for MD / experimental check: Y66 (tools disagree).

---
*The agents do not predict the interface; they compare the tools, surface disagreement
instead of hiding it, and audit the result. The consensus residues feed the team's
"pick one interface model for MD" step; disputed residues are flagged for MD /
experimental confirmation. Demo uses mock tool scores - swap in real
AF-Multimer / HADDOCK / PISA per-residue output on HPC.*
