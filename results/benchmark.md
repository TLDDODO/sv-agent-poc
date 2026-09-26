# Benchmark results: agent vs no-tool baseline

Model `deepseek-chat`; 3 run(s) per case and arm; generated 2026-09-26T08:17:57Z; prices last checked 2026-09-25T14:49:48Z.

| case | pair | truth PDB | agent score | baseline score | agent hits | baseline hits | stability (agent / baseline) | median latency s (agent / baseline) | mean cost (agent / baseline) |
|---|---|---|---|---|---|---|---|---|---|
| b2cl1_bak | B2CL1-BAK | 1BXL | 0.50 | 0.00 | 3/6 | 0/6 | 1.00 / 1.00 | 57.9 / 0.8 | $0.0033 / $0.0001 |
| cdk2_ccna2 | CDK2-CCNA2 | 1FIN | 0.17 | 0.00 | 1/6 | 0/6 | 0.67 / 1.00 | 67.2 / 0.6 | $0.0031 / $0.0001 |
| mdm2_p53 | MDM2-P53 | 1YCR | 1.00 | 1.00 | 6/6 | 6/6 | 1.00 / 1.00 | 50.8 / 0.7 | $0.0027 / $0.0001 |
| pcna_cdn1a | PCNA-CDN1A | 1AXC | 0.50 | 0.50 | 3/6 | 3/6 | 1.00 / 1.00 | 59.1 / 0.7 | $0.0029 / $0.0001 |
| rash_raf1 | RASH-RAF1 | 4G0N | 0.00 | 0.00 | 0/6 | 0/6 | 1.00 / 1.00 | 53.5 / 0.7 | $0.0025 / $0.0001 |
| **overall** | all pairs | - | 0.43 | 0.30 | 13/30 | 9/30 | 0.93 / 1.00 | 58.3 / 0.7 | $0.0029 / $0.0001 |

Overall accuracy: agent 0.43, baseline 0.30; agent minus baseline +0.13. Failed runs (counted as misses): agent 0, baseline 0.

## How to read this

- **Scoring** (docs/benchmark_design.md, section 4): a protein is a hit when the predicted region covers at least 50% of its true interface residues and is at most 2 times the true span; a case scores the mean of its two proteins. "hits" counts protein-level hits over all runs.
- **Baseline** = the same model with no tools, answering from its own knowledge. The model may have seen these classic complexes in training, so the baseline is a measure of how much the model can recite; the difference between agent and baseline is what the tools add over "the model remembering the answer". A baseline that scores as well as the agent means the tools added nothing measurable on these cases.
- **Small sample**: 5 pairs, 3 run(s) each. Differences are indicative, not statistically established.
- **Leakage**: the agent never sees any experimental complex of the pair, nor its papers (docs/benchmark_design.md, section 5). The baseline gets only names and accessions, so training-data memory is its only source.
- Latency and cost come from the run logs in results/runs.jsonl; costs use config/pricing.yaml (third-party price map, see its source note).
