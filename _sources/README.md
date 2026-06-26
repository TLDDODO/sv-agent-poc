# SV Agent PoC — Interface-Adjudication Agent

An LLM agent that, given a protein–partner system, **compares several interface-
prediction tools and adjudicates a consensus interface vs disputed residues** —
grounding everything in real PDBe structures and the real UniProt sequence, and
auditing the result with a weak-vs-strong model comparison.

The agent does **not** predict interfaces or run physics. It compares, validates,
adjudicates, and audits. Current target system: **FAT10 N-terminal ubl domain
(UniProt O15205) : MAD2 (UniProt Q13257)** for the group's interface project.

## Honest status — what is real vs placeholder

| Component | Status |
| --- | --- |
| Agent loop (LLM plans, calls tools, reasons, in a loop) | ✅ real |
| `validate_residues` — checks residues against the real UniProt sequence | ✅ real (catches fabricated/mis-numbered residues) |
| PDBe structure retrieval (6GF1, 6GF2, 2MBE, 7PYV) | ✅ real — confirmed via live PDBe query; all genuine FAT10 structures. Note: none are FAT10:MAD2 complexes (none exist), so they confirm the protein, not the interface |
| Canonical residue mapping + domain check | ✅ real |
| Weak-vs-strong model comparison (deepseek-chat vs deepseek-reasoner) | ✅ real mechanism |
| Residue identities (C7, C9, F22 … real FAT10 amino acids) | ✅ real |
| **Per-residue interface scores (AFM / HADDOCK / PISA)** | ❌ **placeholder / demo numbers** |
| Any conclusion about *which FAT10 residues are the interface* | ❌ method demo only, not a real result |

To make conclusions real, supply real per-residue interface scores via
`INTERFACE_SCORES` (see below). Everything else already runs on real data.

## Run

Agentic adjudication (needs a DeepSeek key; tools work offline without one):

```bash
export DEEPSEEK_API_KEY=...
python -m agent.run_agent           # -> outputs/agent_report.md (+ reasoning trace)
python -m agent.compare             # weak vs strong -> outputs/agent_compare.md
```

Deterministic pipeline version (no LLM, runs anywhere):

```bash
python -m interface.run_interface               # PDBe -> mapping -> tool adjudication
python -m interface.run_interface --source mcp  # live PDBe query (HPC)
```

Plug in real tool scores (the only remaining placeholder):

```bash
export INTERFACE_SCORES=/path/to/scores.json
# scores.json: { "AlphaFold-Multimer": {"C7": 0.x, ...}, "HADDOCK": {...}, "PISA-contacts": {...} }
```

## Components

- `agent/` — genuine ReAct loop (DeepSeek): plans, calls tools, records per-step
  reasoning, submits the adjudication. `agent/compare.py` is the weak-vs-strong audit.
- `interface/` — deterministic version of the FAT10 interface adjudication
  (retrieval → mapping → tool comparison → critic).
- `pipeline/` — EGFR retrieval → canonical mapping → MD-vs-NMA debate (one shot).
- `debate/` — MD-vs-NMA decision engine (method comparison).
- `outputs/` — generated reports and run artifacts.

## Origin

Started as an EGFR T790M PDBe MCP proof of concept (the original `*pdbe*.py`
scripts at repo root and the `debate/` / `pipeline/` MD-vs-NMA line). It evolved
into the FAT10 interface-adjudication agent above.

## See also

- `FLOW.md` — flow diagrams (agent loop + weak-vs-strong audit).
- `outputs/agent_compare.md` — a concrete case where two models disagree on a
  residue (Y66), so it is flagged low-confidence rather than declared either way.
