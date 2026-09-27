# Benchmark design (S4, design document only)

> Status: **approved by the human (GATE passed, 2026-09-26)**. This file is a design; it changed no code.
> Every UniProt / PDB / PMID, interface residue and count in this document comes from real API calls run on 2026-09-26 on the human's local computer (Windows).
> The calls were made by the committed script `docs/benchmark_evidence/build_evidence.py`; its raw derived results are committed as `docs/benchmark_evidence/evidence.json` (including the residue-name check, dropped residues, co-complex entries with their PMIDs, and the literature searches). The numbers here are copied from that file and can be re-run and checked. The list of calls is in Appendix A.

## 1. Purpose

v1 was evaluated on one case only (n=1). v2 has to report accuracy on 5 protein pairs whose complexes have been solved experimentally: the agent sees only evidence that **does not contain the answer**, predicts which region the interface is in, and the prediction is compared with the interface that PDBe reports for that complex.

## 2. The five protein pairs

Interface = the residues with buried surface area (bsa) > 0 in the **largest interface connecting the two chains**, as reported for that entry by the PISA service hosted at PDBe (Appendix A-3). Residue numbers were converted to **UniProt numbering** with the PDBe SIFTS mapping (Appendix A-2), and each residue's three-letter name was checked against the UniProt sequence (Appendix A-4).

| # | Protein A | Protein B | Ground-truth PDB | Method / resolution | PISA interface (id / area Å²) | Chain A / chain B |
|---|---|---|---|---|---|---|
| 1 | CDK2 `P24941` | Cyclin-A2 `P20248` | `1FIN` | X-ray / 2.3 Å | 1 / 1697.5 | A / B |
| 2 | HRas `P01112` | RAF1 `P04049` | `4G0N` | X-ray / 2.45 Å | 2 / 614.0 | A / B |
| 3 | MDM2 `Q00987` | p53 `P04637` | `1YCR` | X-ray / 2.6 Å | 1 / 722.4 | A / B |
| 4 | Bcl-xL (BCL2L1) `Q07817` | BAK `Q16611` | `1BXL` | solution NMR | 1 / 865.7 | A / B |
| 5 | PCNA `P12004` | p21 (CDKN1A) `P38936` | `1AXC` | X-ray / 2.6 Å | 1 / 1087.5 | C / D |

### Ground-truth interfaces (UniProt numbering)

**1. CDK2–Cyclin A2 (1FIN)**
- CDK2 (52 residues, range 37–279): 37–46, 49, 50, 52–54, 56, 57, 69, 71–73, 76, 116, 119–122, 124, 126, 150–159, 162, 179–183, 271, 272, 274, 276–279
- Cyclin-A2 (42 residues, range 173–317): 173–178, 181, 182, 185, 186, 189, 228, 230, 263, 266–272, 274, 275, 288, 289, 292, 293, 295, 296, 299, 300, 303–309, 312, 313, 316, 317
- UniProt annotation: CDK2 `Protein kinase` 4–286 (covers 52/52); no UniProt Domain/Region/Motif feature overlaps the interface residues of Cyclin-A2 (in `evidence.json` the `features` of that protein are empty; its list of non-Disordered features `all_features_non_disordered` is also empty, and there are 2 Disordered features).

**2. HRas–RAF1 (4G0N)**
- HRas (16 residues, range 21–56): 21, 24, 25, 27, 29, 31, 33, 34, 36–41, 54, 56
- RAF1 (17 residues, range 57–90): 57, 59, 64–71, 73, 84, 85, 87–90
- UniProt annotation: RAF1 `RBD` 56–131 (covers 17/17); HRas `Effector region` 32–40 (covers 7/16).

**3. MDM2–p53 (1YCR)**
- MDM2 (26 residues, range 25–104): 25, 26, 49–51, 54, 55, 57, 58, 61, 62, 67, 70–73, 75, 86, 91, 93, 94, 96, 99, 100, 103, 104
- p53 (12 residues, range 17–29): 17–20, 22–29
- UniProt annotation: MDM2 `SWIB/MDM2` 26–109 (covers 25/26); p53 `TADI` 17–25 (covers 8/12), `Transcription activation (acidic)` 1–44 (covers 12/12).

**4. Bcl-xL–BAK (1BXL)**
- Bcl-xL (29 residues, range 93–204): 93, 96, 97, 100, 101, 104, 105, 107, 108, 111, 112, 125, 126, 129, 130, 132, 136–139, 141, 142, 146, 194, 195, 199, 200, 203, 204
- BAK (15 residues, range 72–87): 72–82, 84–87
- UniProt annotation: BAK `BH3` 74–88 (covers 13/15); Bcl-xL has no single dominant domain (BH3 4, BH1 10, BH2 2, together fewer than all 29).
- 1 residue was dropped: chain A position 210 is named LEU in the PDB, but UniProt has F at that position (the names disagree, so it cannot be used as ground truth).

**5. PCNA–p21 (1AXC)**
- PCNA (38 residues, range 27–255): 27, 29, 40, 43–47, 67–69, 96, 97, 118–129, 131, 133, 208, 211, 232–234, 250–255
- p21 (17 residues, range 143–160): 143–148, 150–160
- UniProt annotation: p21 `PIP-box K+4 motif` 140–164 (covers 17/17); PCNA has no Domain annotation (only the Region `Interaction with NUDT15` 7–100, covering 13/38).

### Why these five pairs (stated honestly)

- Each pair has a real experimental complex, and the UniProt feature table or the literature leaves the agent usable clues.
- The difficulty is graded: for #2, #3 and #5 one side has a direct UniProt domain/motif annotation (easier); for #1 the Cyclin-A2 side has **no** domain annotation, so it has to be inferred from literature/structure (harder).
- The types differ: domain–domain (#1), domain–domain (#2), domain–short peptide (#3, #4, #5).
- **Note**: with n=5 a single case is 20%, so the confidence interval of the accuracy will be wide; the result can only be read as a trend and must not be claimed statistically significant.
- Using the UniProt feature table makes some cases easier. This is deliberate ("domain annotations the agent can use"), but the report has to say so.

## 3. What the agent will see (with the kind of source)

| Evidence | Behaviour in a benchmark case |
|---|---|
| UniProt sequence + feature table (Domain/Region/Motif) | live. The UniProt Subunit and other annotation text and the cross-references are **not** provided (they can name the complex directly). Checked (`ground_truth_pdb_id_in_uniprot` for each protein in `evidence.json`): the ground-truth PDB ID appears neither in the feature table nor in the comments; but it **does** appear in the cross-references (uniProtKBCrossReferences), so the cross-references must not be shown to the agent (Appendix A-5). |
| PDBe structure list (`fetch_structures`) | live, but **with every entry that contains both proteins filtered out** (see §5), leaving only structures of a single protein or with other partners. |
| PubMed literature (`search_literature`) | live, but **with the publications of every PDB entry that contains both proteins filtered out** (see §5). |
| MD contact occupancy | `pending` (no MD was run for these pairs). |
| AlphaFold-Multimer / HADDOCK / PISA predictions | `pending`. **PISA must stay pending**: PISA is the source of the ground truth, so opening it would leak the answer. |
| Debate (MD advocate vs NMR advocate) | there is no MD evidence and no NMR conflict to argue about; no debate is convened in the benchmark, only the agent's interface judgement is assessed. |

Compared with FAT10–MAD2 the agent lacks: MD trajectory evidence, a local score file, and a hand-verified NMR/literature conclusion (FAT10's UBL1 6–81 is a manually verified prior). So the benchmark tests "can the interface be located from sequence annotations + structures + literature alone", **not** the ability to detect contradictions. The FAT10–MAD2 case is kept separately, and its conclusion — "the MD interface is in the C-terminal region vs the literature/NMR UBL1 6–81" — and its wording are unchanged.

## 4. Scoring rule

For each side of each protein pair (protein A, protein B) the agent submits a predicted interface region R (a residue interval or a set of residues, UniProt numbering). T is the ground-truth interface residue set of that side (§2).

1. **Region hit (primary metric, 0/1)**: both of the following hold
   - recall ≥ 50%: `|R ∩ T| / |T| ≥ 0.5`;
   - no cheating with "the whole chain": the length covered by R ≤ 2 × the span of T (max of T − min of T + 1).
2. **Residue overlap (secondary metric)**: F1 and Jaccard of R against T (only computed when the agent gives a residue set).
3. **Case score** = the mean of the region hits of the two sides (0, 0.5 or 1).
4. **Overall accuracy** = the mean of the case scores over all cases and all runs.
5. **Stability**: for the same case over several runs, the fraction of runs whose region-hit result agrees (for the S6 report).

The thresholds (50%, 2× span) are design choices, not fitted to data; please confirm or change them when approving. The scoring code is implemented in S6, and the numbers in the report are copied only from `results/benchmark.json`.

## 5. Preventing answer leakage

1. **Structure filter (filter by "contains both proteins" as a whole, not just block the ground-truth ID)**: for each benchmark pair, filter out every PDBe entry that maps to both UniProt accessions. This is necessary: see the table below; one protein pair often has several complex entries, and blocking only the ground-truth ID would leak through the others.

   | Pair | Number of PDBe entries containing both proteins |
   |---|---|
   | CDK2–Cyclin A2 | 111 |
   | HRas–RAF1 | 6 (`3KUD` `4G0N` `4G3X` `6NTC` `6NTD` `7JHP`) |
   | MDM2–p53 | 2 (`1YCR` `4HFZ`) |
   | Bcl-xL–BAK | 3 (`1BXL` `2LP8` `5FMK`) |
   | PCNA–p21 | 6 (`1AXC` `4RJF` `5E0U` `6CBI` `7KQ0` `7KQ1`) |

   The filter set is built **at run time** from PDBe (one query per protein, then the intersection) and is not hard-coded, so nothing is missed.
2. **Literature filter**: take the PMIDs of the publications registered at PDBe for those entries (57 / 4 / 2 / 3 / 5 of them, in the order of the table above) and remove them from the `search_literature` results. **Shown to be necessary by a real search**: for HRas–RAF1 the query "HRAS RAF1 interaction binding domain" returns, among its first 5 hits, PMID `34356620` (a crystal-structure paper on the Ras–Raf interface; it is the publication of `7JHP`, not of `4G0N`), which would leak if not filtered (Appendix A-6).
3. **PISA stays pending** (see §3).
4. **A restricted UniProt view**: only the sequence and the feature table are given (§3); the annotation text and the cross-references are not (the cross-references contain the ground-truth PDB ID, see A-5).
5. **Test** (implemented in S5): assert that the ground-truth PDB ID of a benchmark pair and the IDs of all such entries never appear in any tool output.
6. **Residual risks (stated honestly)**:
   - An abstract may still describe the binding region in words. The literature filter only blocks "complex-structure papers", not reviews and other literature. This is a kind of evidence the agent may legitimately use, but it makes some cases easier.
   - If another structure of a single protein contains a peptide mimicking the partner, it cannot be recognised automatically.
   - The UniProt feature table itself comes from historical literature and may reflect the interface indirectly.

## 6. Connection to the existing tools (for S5; this step changes no code)

- `get_md_interface_scores` / `get_tool_prediction` return `pending` for benchmark pairs and never a placeholder number.
- `get_expected_interface_region` is currently hard-coded to FAT10; for benchmark cases it has to read the UniProt feature table instead (S5).
- `map_residues` / `validate_residues` already accept any UniProt accession and can be reused.

## Appendix A: real API calls used in this design (2026-09-26, this machine)

The calls A-1 to A-6 all returned successfully (HTTP 200); A-7 lists endpoints that were probed and failed. Every value was obtained from these calls; no ID was filled in from memory.

- **A-1 UniProt feature table and sequence**: for each of `P24941 P20248 P01112 P04049 Q00987 P04637 Q07817 Q16611 P12004 P38936`, calls to
  `https://rest.uniprot.org/uniprotkb/<ACC>.json` (protein name, length, Domain/Region/Motif features) and
  `https://rest.uniprot.org/uniprotkb/<ACC>.fasta` (residue-name check).
- **A-2 SIFTS mapping**: `https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/<pdb>`, with `<pdb>` = `1fin 4g0n 1ycr 1bxl 1axc`.
  The author numbering of MDM2 chain A in 1YCR is empty in SIFTS, so the author numbering is assumed to equal the UniProt numbering, and this was verified with the residue-name check of A-4 (26/26 agree).
- **A-3 PISA interfaces**: `https://www.ebi.ac.uk/pdbe/pisa/cgi-bin/interfaces.pisa?<pdb>`, for the same 5 entries. The largest interface connecting the two mapped chains is taken; interface residues = bsa > 0.
- **A-4 Residue-name check** (per-residue results and dropped residues are in `bsa_residues_checked`, `dropped_name_mismatch` and `sifts_author_numbers_missing_assumed_equal_unp` of `evidence.json`): the three-letter residue names from A-3 were compared position by position with the UniProt sequences from A-1. Total interface residues per case and number of mismatches:
  1FIN 52+42 all agree; 4G0N 16+17 all agree; 1YCR 26+12 all agree; 1BXL 30+15 with 1 mismatch (chain A position 210, dropped); 1AXC 38+17 all agree.
- **A-5 UniProt leak check**: for the JSON of each of the 10 proteins in A-1, whether features, comments and uniProtKBCrossReferences contain the corresponding ground-truth PDB ID. Result in `evidence.json`: none of the 10 proteins has it in features or comments; all 10 have it in the cross-references (so the cross-references cannot be shown to the agent).
- **A-6 Co-complex entries and literature**:
  - `https://www.ebi.ac.uk/pdbe/search/pdb/select?q=uniprot_accession:<ACC>&fl=pdb_id&rows=20000&wt=json`, once for each of the 10 UniProt accessions; the intersection per protein pair gives the entry counts and IDs of §5.
  - `https://www.ebi.ac.uk/pdbe/api/pdb/entry/summary/<pdb>`, `.../publications/<pdb>`, `.../experiment/<pdb>` (title, method, resolution, publication PMID) for the 5 ground-truth entries; `publications/<pdb>` was also called for all co-complex entries, which gives the PMID counts of §5.
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&term=<query>`, for 5 queries ("CDK2 cyclin A binding interface", "HRAS RAF1 interaction binding domain", "MDM2 p53 interaction binding domain", "BCL2L1 BAK1 interaction binding region", "PCNA CDKN1A p21 interaction binding region"), intersected with the co-complex publication PMIDs: only HRAS–RAF1 hits `34356620`.
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=34356620` (title, journal and year are recorded in `leaked_pmid_summaries` of `evidence.json`: Crystal Structure Reveals the Full Ras-Raf Interface and Advances Mechanistic Understanding of Raf Activation, Biomolecules, 2021).
- **A-7 Endpoints that were probed and failed**: `endpoint_probes` in `evidence.json` records the URLs of three probes and their 404 results (`/pdbe/api/pisa/interfaces/1fin`, `/pdbe/api/pdb/entry/interfaces/1fin`, `data.rcsb.org/rest/v1/core/interface/1FIN/1`); none of them was used.
