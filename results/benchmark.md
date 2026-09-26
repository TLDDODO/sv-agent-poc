# Benchmark results: agent vs no-tool baseline

Model `deepseek-chat`; 3 run(s) per case and arm; generated 2026-09-26T09:04:40Z; prices last checked 2026-09-25T14:49:48Z.

| case | pair | truth PDB | agent score | baseline score | agent hits | baseline hits | stability (agent / baseline) | median latency s (agent / baseline) | mean cost (agent / baseline) |
|---|---|---|---|---|---|---|---|---|---|
| b2cl1_bak | B2CL1-BAK | 1BXL | 0.67 | 0.00 | 4/6 | 0/6 | 0.67 / 1.00 | 42.7 / 0.8 | $0.0051 / $0.0001 |
| cdk2_ccna2 | CDK2-CCNA2 | 1FIN | 0.50 | 0.00 | 3/6 | 0/6 | 0.33 / 1.00 | 32.3 / 0.9 | $0.0027 / $0.0001 |
| mdm2_p53 | MDM2-P53 | 1YCR | 1.00 | 1.00 | 6/6 | 6/6 | 1.00 / 1.00 | 30.8 / 0.7 | $0.0025 / $0.0001 |
| pcna_cdn1a | PCNA-CDN1A | 1AXC | 0.50 | 0.50 | 3/6 | 3/6 | 1.00 / 1.00 | 30.6 / 0.7 | $0.0031 / $0.0001 |
| rash_raf1 | RASH-RAF1 | 4G0N | 0.00 | 0.00 | 0/6 | 0/6 | 1.00 / 1.00 | 27.6 / 0.7 | $0.0022 / $0.0001 |
| **overall** | all pairs | - | 0.53 | 0.30 | 16/30 | 9/30 | 0.80 / 1.00 | 30.8 / 0.7 | $0.0031 / $0.0001 |

Overall accuracy: agent 0.53, baseline 0.30; agent minus baseline +0.23. Failed runs (counted as misses): agent 0, baseline 0.

## How to read this

- **Scoring** (docs/benchmark_design.md, section 4): a protein is a hit when the predicted region covers at least 50% of its true interface residues and is at most 2 times the true span; a case scores the mean of its two proteins. "hits" counts protein-level hits over all runs.
- **Baseline** = the same model with no tools, answering from its own knowledge. The model may have seen these classic complexes in training, so the baseline is a measure of how much the model can recite; the difference between agent and baseline is what the tools add over "the model remembering the answer". A baseline that scores as well as the agent means the tools added nothing measurable on these cases.
- **Small sample**: 5 pairs, 3 run(s) each. Differences are indicative, not statistically established.
- **Runs vary**: the model is not deterministic, so re-running the benchmark can change the scores (an earlier run of this benchmark scored differently). Compare only within one run.
- **Leakage**: the agent never sees any experimental complex of the pair, nor its papers (docs/benchmark_design.md, section 5). The baseline gets only names and accessions, so training-data memory is its only source.
- Latency and cost come from the run logs in results/runs.jsonl; costs use config/pricing.yaml (third-party price map, see its source note).

## Error injection (FAT10-MAD2)

Real MD residue labels were corrupted one way at a time and run through the agent's validation path (the MD tool, then the UniProt sequence check). `passed_through` means the error was NOT detected; `inconclusive` means the check could not run and is not counted as caught. The uninjected control validated cleanly.

| injected error | outcome | evidence |
|---|---|---|
| shift_plus_3: Residue numbering shifted by +3 (off-by-three). | caught | 14 mismatching residue(s) of 15 |
| shift_minus_10: Residue numbering shifted by -10 (e.g. a construct offset). | caught | 15 mismatching residue(s) of 15 |
| beyond_sequence_length: Real labels plus residues past the end of the sequence (positions 166, 200, 9999). | caught | 3 mismatching residue(s) of 18 |
| fabricated_md_wrong_residues: Fabricated MD score file: invented residue identities at real positions. | caught | 15 mismatching residue(s) of 15 |
| fabricated_md_real_labels: Fabricated MD score values on real residue labels. | passed_through | 0 mismatching residue(s) of 15 |
| wrong_uniprot_other_protein: FAT10 residues checked against another real protein's accession (Q13257, MAD2). | caught | 15 mismatching residue(s) of 15 |
| wrong_uniprot_malformed: Accession that is not a UniProt accession. | caught | could not fetch UniProt NOTANACC: HTTPError |

**Intercept rate: 6 of 7 injected errors caught (86%); passed through: 1; inconclusive: 0.**

## Workload per query

Measured from the run log (results/runs.jsonl), not estimated. Data API calls are requests our code made to PDBe, UniProt and PubMed (attempted, including failed ones); records are what came back from or were checked against those sources, plus rows read from the local MD result file. Log lines written before these counters existed (30) are excluded. **Manual (human) effort was not measured**, so nothing here compares against it.

| queries | tool calls | databases reached | data API calls | LLM calls | records processed | median time s | mean cost |
|---|---|---|---|---|---|---|---|
| agent (benchmark pairs): 15 | 16.5 | 3.0 | 14.7 | 5.9 | 446 | 30.8 | $0.0031 |
| no-tool baseline: 15 | 0.0 | 0.0 | 0.0 | 1.0 | 0 | 0.7 | $0.0001 |
| agent (non-benchmark: web app / CLI use): 2 | 8.5 | 3.0 | 4.0 | 4.0 | 40 | 23.7 | $0.0020 |
| debate (no benchmark case recorded: web app / CLI use): 2 | 0.0 | 0.0 | 0.0 | 3.0 | 0 | 7.9 | $0.0012 |

Means per query. Databases reached: agent (benchmark pairs): PDBe, PubMed, UniProt; no-tool baseline: none; agent (non-benchmark: web app / CLI use): PDBe, PubMed, UniProt; debate (no benchmark case recorded: web app / CLI use): none.

Log composition: 60 of 65 lines carry a benchmark case id (the log does not record which program wrote them). The other 5 (2 agent, 2 debate, 1 flag_paraphrase) carry no benchmark case id, so they are treated as queries run through the web app or the CLI; they are reported separately and are not part of any benchmark score.
