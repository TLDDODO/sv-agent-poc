# EGFR T790M HPC PoC Mechanism Brief

## Search

- Query: `EGFR T790M kinase domain drug resistance structures`
- Host: `compbioasia-cpu-32-student3`
- Resolution cutoff: 3.5 A

## Evidence Table

| Claim | Evidence Type | Source | Confidence | Limitations |
| --- | --- | --- | --- | --- |
| EGFR T790M plausibly changes inhibitor-pocket dynamics near the gatekeeper site; this is a hypothesis, not a causal proof. | inference | PDB:2JIT,2ITY; Trajectory:hpc_demo | Medium: Structure context plus trajectory metrics support local contact changes, but matched real WT/T790M trajectories are still required. | HPC run currently uses schema-valid demo metrics. |
| Residue 790 is represented in canonical EGFR UniProt numbering, enabling structure-to-trajectory comparison. | structure | PDB:2JIT,2ITY | High: Both candidates map to canonical EGFR P00533 position 790. | Replace mock mapping with PDBe-SIFTS CSV when real structures are pulled. |

## Chinese Summary

HPC PoC completed the pipeline: structured PDBe MCP payload, canonical EGFR residue 790 mapping, MD metrics JSON, evidence-grounded claims, and critic audit. Current MD metrics are schema-valid demo metrics; next step is replacing them with real MDAnalysis output.

## Critic Findings

- No critical consistency issues detected in HPC PoC.
