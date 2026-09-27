# Business case

> The numbers are filled in by a script from the result files, never typed by hand. **Manual time was not measured**: no manual baseline was ever measured, so this document estimates neither manual time nor manual cost.

## 1. The problem

Working out how two proteins bind means putting the structure database, the sequence database, simulation data and the literature side by side. The evidence often contradicts itself (this project's case, FAT10–MAD2: the MD interface is at the C-terminus while the literature/NMR expects the N-terminal UBL1 domain), and there is no experimental complex structure to serve as the answer. The core risk is not "searching is slow" but **quoting data that does not exist or does not match, or presenting a contradiction as settled**.

## 2. Manual workflow vs agent workflow

| step | manual workflow | agent workflow |
|---|---|---|
| Confirm the system | look up entries, sequences and domains by hand on the PDBe / UniProt web pages | the tool queries PDBe live (MCP query, falling back to a verified snapshot on failure) and UniProt |
| Read the literature | search PubMed, read abstracts one by one, pick out the binding region yourself | the tool searches PubMed and the agent reads the abstracts; when the search fails the result is labelled "cited" and it does not pretend to have searched |
| Get simulation evidence | compute contact occupancy yourself from the simulation output | reads the real contact-occupancy file that was already produced; reports "pending" when there is no data |
| Check residue numbering | compare with the sequence by hand, easy to miss | `validate_residues` checks each residue against the UniProt sequence and flags mismatches |
| Compare and judge | compare the MD interface and the literature region yourself | a deterministic check raises the contradiction flag; on a conflict a debate is held and a cautious conclusion is given |
| Output | write the report and citations yourself | a report with the full tool-call record; labelled live / cited / pending |
| The person's role | does everything | asks, reviews, and decides which validation experiment to run |

The agent does not replace experiments and does not declare which side is right; it automates the repetitive part — "collect and compare the evidence, spot the contradiction" — and keeps a record that can be re-checked.

## 3. Workload, cost and time per query

<!-- GENERATED:BUSINESS:START -->
Source: `results/runs.jsonl`, aggregated by `scripts/workload_metrics.py` (`results/workload.json`); model `deepseek-chat`, price list checked 2026-09-25T14:49:48Z; prices come from a third-party price list, see `config/pricing.yaml`. The figures are per-query means (time is the median), counted by the program at run time, not estimated.

| flow | queries | tool calls | databases reached | data API calls | model calls | records processed | time | cost |
|---|---|---|---|---|---|---|---|---|
| Investigator agent (with tools, benchmark cases) | 15 | 16.5 | 3.0 | 14.7 | 5.9 | 446 | 30.8 s | $0.0031 |
| No-tool baseline (same model answering directly) | 15 | 0.0 | 0.0 | 0.0 | 1.0 | 0 | 0.7 s | $0.0001 |
| Investigator agent (non-benchmark: web app / CLI use) | 4 | 8.2 | 3.0 | 3.8 | 4.0 | 40 | 24.3 s | $0.0019 |
| Debate (no benchmark case recorded: web app / CLI use) | 4 | 0.0 | 0.0 | 0.0 | 3.0 | 0 | 7.9 s | $0.0010 |

Definitions:
- **Data API calls**: requests our code sent to external data sources (PDBe, UniProt, PubMed), counted when sent, failed ones included; a PDBe MCP query counts as one.
- **Databases reached**: the number of external databases reached successfully at least once (the local MD result file is not a database).
- **Records processed**: records returned by or checked against the data sources (PDBe entries, PubMed abstracts, UniProt annotations, residues checked), plus the residue rows read from the local MD result file.
- 30 run-log lines written before the counters existed have no such fields; they are excluded and were not back-filled by guessing.
- Log composition: 71 lines in all, of which 60 carry a benchmark case id (the log does not record which program wrote them); the other 11 carry no benchmark case id and are treated as non-benchmark queries run through the web app or the CLI (the log does not tell them apart). They are listed separately and are in no benchmark score.

**Manual time was not measured.** No manual baseline was ever measured, so this document estimates neither manual time nor manual cost and cannot say how much the agent saves; the table above only describes the workload of the automated flow itself.

Accuracy on the same cases: agent 0.53, no-tool baseline 0.30 (scoring rule in `docs/benchmark_design.md`; the baseline measures what the agent adds over the model "reciting the answer").

Error injection (FAT10–MAD2): 6 of 7 injected errors caught (86%); passed through 1; inconclusive 0.
<!-- GENERATED:BUSINESS:END -->

Notes:

- Cost is computed from the prices in `config/pricing.yaml` and the token use of each run. That price list comes from a third-party price collection, not from the DeepSeek official page; check the official prices before relying on it.
- Time is end-to-end wall-clock time, including the response time of the external services (PubMed, UniProt, PDBe), and varies with the network.
- Manual time and cost were not measured, so nothing here says how much the agent "saves". To compare, the user would first have to measure a manual baseline.
- Accuracy comes from classic protein pairs that have experimental complexes (see `docs/benchmark_design.md`); the sample is small and only indicates a trend. The model may have seen these classic complexes in training, which is why the no-tool baseline has to be read alongside.

## 4. Risks and mitigations

| risk | description | mitigation (current state) |
|---|---|---|
| Fabricated data | a language model may invent residues, scores or citations | every number comes only from tools; tools without data report "pending"; `validate_residues` checks the sequence; the report keeps the full tool-call record |
| Wrong input goes unnoticed | the error-injection test shows that numbering shifts, out-of-range residues, invented residue identities and wrong UniProt accessions are caught by the sequence check; **fabricated MD scores that change only the values and not the residue labels cannot be detected by the sequence check** | recorded honestly in the evaluation report; a provenance check for the MD score file (for example a checksum or a record of the generating script) is still needed and is **not yet implemented** |
| Presenting a contradiction as settled | without an experimental complex structure neither side is the ground truth | the prompts and the judge role require only reporting the contradiction, not declaring a winner, and suggesting a validation experiment; a test pins this wording |
| The benchmark is optimistic or unstable | few cases; the model may have memorised the classic complexes; the UniProt feature table itself comes from historical literature | the no-tool baseline is shown alongside; a leakage filter (every complex structure and matching paper of the same protein pair is withheld from the agent); the report says the sample is small and indicative only |
| Answer leakage | the agent sees the experimental complex or the paper of the same protein pair | structure and literature filters, an output guard, dropping arguments that are not in the tool schema during benchmark runs; residual risk remains (review text, other structures containing a mimicking ligand), see `docs/benchmark_design.md` |
| External services unavailable | PDBe / UniProt / PubMed / DeepSeek may time out or rate-limit | failures are recorded honestly as failed or "inconclusive" and never counted as success; PDBe has a verified snapshot as a fallback (FAT10 only) |
| Cost runaway | the in-depth investigation and the debate call an external model, so repeated triggering keeps costing money | the maximum number of steps is limited; the run log records the cost of every run; the API itself has no rate limiting or authentication, so a reverse proxy and a key are needed before public deployment (see `docs/dify_setup.md`) |
| Unauthorised API access | the service has no authentication of its own | open to the local machine only by default; public access must go through a proxy with a key; read-only endpoints can be allowed separately |
| Stale price information | cost depends on a third-party price list | `config/pricing.yaml` records the check date and the source; check the official prices before real use |
| Limits of a single MD | the case has one MD trajectory and the interface reflects the AF3 starting pose | the README states it plainly as "a consistency check on that model, not independent validation" |
| The Dify integration was only partly verified | see `docs/dify_setup.md` for what was and was not checked on a real Dify install | the document states exactly what was checked; walk through it yourself before going live |
