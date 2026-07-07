# SV Agent PoC on HPC

Minimum running proof of concept for an agent-orchestrated structural biology mutation interpretation pipeline.

## Current status

This repository has a working HPC-side demo for EGFR T790M:

```text
Natural language goal
-> official PDBe MCP pdbe_search_server
-> run_pdbe_search_query
-> real EGFR T790M structure retrieval
-> parsed structure candidates
-> canonical EGFR residue 790 mapping
-> MD metrics schema
-> evidence-grounded claims
-> critic audit
-> Markdown and JSON reports
```

## Main files

- `minimum_real_pdbe_poc.py`: minimum real-PDBe end-to-end PoC.
- `hpc_poc.py`: fully offline/mock evidence-chain demo.
- `query_pdbe.py`: broad official PDBe MCP EGFR/T790M query.
- `query_pdbe_refined.py`: refined title-constrained PDBe MCP query.
- `list_pdbe_tools.py`: lists official PDBe MCP tools.
- `outputs/minimum_real_pdbe_evidence.json`: evidence bundle from the real PDBe run.
- `outputs/minimum_real_pdbe_report.md`: report from the real PDBe run.
- `outputs/tomorrow_pitch.md`: short presentation notes.
- `outputs/one_page_rp.md`: one-page research proposal.

## Run

```bash
cd ~/sv-agent-poc
/home/ychen/.local/bin/uv run --with pdbe-mcp-server --with mcp python minimum_real_pdbe_poc.py
```

## Verified result

The real PDBe MCP run retrieved high-resolution EGFR T790M structures, including:

- `5UG9`, 1.33 A
- `5HG8`, 1.42 A
- `5UG8`, 1.46 A
- `6TG0`, 1.50 A
- `6TFV`, 1.50 A

Critic output:

```text
No critical consistency issues detected in minimum real-PDBe HPC PoC.
```

## Next steps

- Replace demo MD metrics with real MDAnalysis outputs.
- Integrate PDBe-SIFTS residue-level mapping.
- Add literature PMID retrieval and claim-level citation checks.
- Package the pipeline as a cleaner CLI or MCP tool.

## Other projects in this repo

- `audio_llm_mental_health/`: separate PoC, explainable mental-state assessment via an
  audio-LLM fine-tuned with LoRA to emit chain-of-thought reasoning. See its own README and
  `RP.md`. Unrelated to the structural-biology pipeline above.
