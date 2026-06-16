# EGFR T790M Minimum Real-PDBe HPC PoC

## Query

- Provider: official PDBe MCP `pdbe_search_server`
- Tool: `run_pdbe_search_query`
- Query: `title:*EGFR* AND title:*T790M*`
- Resolution cutoff: 3.5 A
- Host: `compbioasia-cpu-32-student3`

## Parsed Structures

| PDB | Resolution | Method | Mutation | State | Title |
| --- | --- | --- | --- | --- | --- |
| 5ug9 | 1.33 | X-ray diffraction | T790M | ligand-bound | Crystal structure of the EGFR kinase domain (L858R, T790M, V948R) in complex with a covalent inhibitor N-[(3R,4R)-4-fluoro-1-{6-[(3-methoxy-1-methyl-1H-pyrazol-4-yl)amino]-9-(propan-2-yl)-9H-purin-2-yl}pyrrolidin-3-yl]propanamide |
| 5hg8 | 1.42 | X-ray diffraction | T790M | ligand-bound | EGFR (L858R, T790M, V948R) in complex with N-[3-({2-[(1-methyl-1H-pyrazol-4-yl)amino]-7H-pyrrolo[2,3-d]pyrimidin-4-yl}oxy)phenyl]prop-2-enamide |
| 5ug8 | 1.46 | X-ray diffraction | T790M | ligand-bound | Crystal structure of the EGFR kinase domain (L858R, T790M, V948R) in complex with a covalent inhibitor N-[(3R,4R)-4-fluoro-1-{6-[(1-methyl-1H-pyrazol-4-yl)amino]-9-(propan-2-yl)-9H-purin-2-yl}pyrrolidin-3-yl]propanamide |
| 6tg0 | 1.5 | X-ray diffraction | T790M | ligand-bound | Crystal Structure of EGFR T790M/V948R in Complex with Covalent Pyrrolopyrimidine 21a |
| 6tfv | 1.5 | X-ray diffraction | T790M | ligand-bound | Crystal Structure of EGFR T790M/V948R in Complex with Covalent Pyrrolopyrimidine 18b |
| 5hg5 | 1.52 | X-ray diffraction | T790M | ligand-bound | EGFR (L858R, T790M, V948R) in complex with N-{3-[(2-{[4-(4-methylpiperazin-1-yl)phenyl]amino}-7H-pyrrolo[2,3-d]pyrimidin-4-yl)oxy]phenyl}prop-2-enamide |
| 5ugc | 1.58 | X-ray diffraction | T790M | ligand-bound | Crystal structure of the EGFR kinase domain (L858R, T790M, V948R) in complex with a covalent inhibitor N-[(3R,4R)-4-fluoro-1-{6-[(3-methoxy-1-methyl-1H-pyrazol-4-yl)amino]-9-methyl-9H-purin-2-yl}pyrrolidin-3-yl]propanamide |
| 6tg1 | 1.6 | X-ray diffraction | T790M | ligand-bound | Crystal Structure of EGFR T790M/V948R in Complex with Covalent Pyrrolopyrimidine 21b |
| 6tfy | 1.7 | X-ray diffraction | T790M | ligand-bound | Crystal Structure of EGFR T790M/V948R in Complex with Covalent Pyrrolopyrimidine 18c |
| 4i22 | 1.71 | X-ray diffraction | T790M | ligand-bound | Structure of the monomeric (V948R)gefitinib/erlotinib resistant double mutant (L858R+T790M) EGFR kinase domain co-crystallized with gefitinib |

## Evidence Claims

| Claim | Evidence Type | Source | Confidence | Limitations |
| --- | --- | --- | --- | --- |
| Real PDBe MCP search identifies high-resolution EGFR T790M kinase-domain inhibitor-complex structures suitable for downstream interpretation. | structure | PDB:5ug9,5hg8,5ug8,6tg0,6tfv | High: Candidates were retrieved from the official PDBe MCP search server with a title-constrained EGFR/T790M query and resolution filter. | Parsed text output should later be replaced with structured MCP/REST JSON if exposed. |
| EGFR T790M may alter inhibitor-pocket dynamics near the gatekeeper position; current dynamics are a placeholder metric set until real MD trajectories are attached. | inference | PDB:5ug9,5hg8,5ug8,6tg0,6tfv; Trajectory:hpc_min_demo | Medium: The structure evidence is real, but MD metrics in this minimum pass are schema-valid demo values. | Do not treat the MD-derived mechanism as experimentally supported until real MDAnalysis output is used. |

## MD Metrics

- gatekeeper_to_pocket_min_distance
- pocket_volume_proxy_key_distance
- gatekeeper_region_rmsf
- key_contact_occupancy

## Critic Findings

- No critical consistency issues detected in minimum real-PDBe HPC PoC.

## ????

???????????????????? EGFR T790M ??????? PDBe MCP ??????????????? evidence JSON??? canonical EGFR 790 mapping?MD ?? schema?claim ??? critic ??????? MD ?????? demo metrics????????? MDAnalysis/HPC ???
