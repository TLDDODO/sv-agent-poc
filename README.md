# FAT10–MAD2 Interface Adjudicator

An LLM agent that adjudicates where **MAD2** binds **FAT10**, grounding every fact in
a tool call — PDBe structures, the real UniProt sequence, a 100 ns molecular-dynamics
run, and PubMed — and, when the evidence conflicts with the literature, convening a
**multi-agent debate** to reach a *calibrated* verdict instead of a false one.

The agent does not predict interfaces or invent numbers. It retrieves, validates,
compares the real MD contact map against the literature-expected binding region, and
— crucially — when the model and the literature disagree it reports the **contradiction
as a fact without declaring a winner**, because no experimental FAT10–MAD2 complex
exists to serve as ground truth.

## The finding this pipeline surfaces

The 100 ns MD (run on an AlphaFold3 starting model) puts the persistent FAT10–MAD2
interface on FAT10's **C-terminal region** (I163, C162, G164, C160, G165, Y161 …),
while the literature/NMR expects MAD2 to bind FAT10's **N-terminal UBL1 domain
(residues 6–81)**. Every persistent contact falls *outside* the expected region, so
the deterministic check **flags the model** and the debate recommends an experiment —
it does not pronounce the MD "right" or the literature "wrong."

## Architecture

```
goal ─▶ [ReAct agent: DeepSeek plans + calls tools in a loop]
             │
             ├─ search_literature            → PubMed abstracts (live) / cited fallback
             ├─ get_expected_interface_region→ UBL1 6–81 (UniProt + Theng 2014, CITED)
             ├─ fetch_structures             → PDBe (live MCP client or verified snapshot)
             ├─ validate_residues            → real UniProt sequence (catches bad numbering)
             ├─ get_md_interface_scores      → real 100 ns MD contact occupancy
             └─ convene_debate  ─▶ [MD advocate] vs [NMR advocate] ─▶ [Judge → calibrated verdict]
             │
        submit_adjudication  →  report + full reasoning/tool trace
```

Design principles: **no fabricated data** (unavailable tools report `pending`, never
placeholder numbers); **no false ground truth** (contradictions are reported, winners
are not declared); every residue and score originates from a tool, never the model.

## Honest status — real vs cited vs pending

| Component | Status |
| --- | --- |
| ReAct agent loop (LLM plans, calls tools, reasons, in a loop) | ✅ real |
| 100 ns MD contact occupancy (per-residue MAD2 contact fraction) | ✅ real evidence (own Amber run) |
| `validate_residues` vs the real UniProt O15205 sequence | ✅ real |
| PDBe retrieval — live MCP client or verified snapshot (6GF1, 6GF2, 2MBE, 7PYV) | ✅ real (all genuine FAT10; none are FAT10:MAD2 complexes — none exist) |
| FAT10 domain boundaries (UBL1 6–81, UBL2 90–163) | ✅ verified from the UniProt feature table |
| Expected binding region (MAD2 → UBL1) | 📚 cited (Theng et al. 2014 PNAS; NMR PDB 2MBE) — not derived here |
| Multi-agent debate + calibrated judge | ✅ real mechanism |
| Weak-vs-strong model comparison | ✅ real mechanism |
| AFM / HADDOCK / PISA per-residue scores | ⏳ pending — no team data yet; reported as `pending`, never faked |
| Which side (MD vs literature) is correct | ❌ unknown — no experimental complex; the pipeline recommends a test |

## Quickstart

### Run the API (Docker)

```bash
docker compose up --build          # serves on http://localhost:8000
# or:
docker build -t fat10-adjudicator .
docker run -p 8000:8000 -e DEEPSEEK_API_KEY=sk-... fat10-adjudicator
```

### Run the API (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload      # http://localhost:8000/docs
```

| Endpoint | Needs key? | What it does |
| --- | --- | --- |
| `GET /health` | no | liveness + whether the LLM is configured |
| `GET /evidence` | no | real MD occupancy + expected region + the deterministic conflict flag |
| `POST /adjudicate` | yes | run the autonomous investigator agent end-to-end |
| `POST /debate` | yes | run the multi-agent debate and return the judge's verdict |
| `GET /docs` | no | interactive OpenAPI docs |

### Run the pipeline directly (CLI)

```bash
export DEEPSEEK_API_KEY=...
python -m agent.run_agent          # autonomous agent  → outputs/agent_report.md (+ trace)
python -m agent.debate             # multi-agent debate → outputs/debate_report.md
python -m agent.compare            # weak-vs-strong     → outputs/agent_compare.md
python analysis/adjudicate_md.py   # deterministic conflict check (no key, no network)
```

## Repository layout

```
agent/       ReAct agent: llm_client, tools, structures (PDBe MCP client),
             literature (PubMed), debate (advocates + judge), run_agent, compare
analysis/    MD → per-residue scores, deterministic adjudication, HTML report, figure render
api/         FastAPI service (api.main:app)
skills/      Agent role prompts as loadable Markdown files (investigator, advocates, judge)
notebooks/   Executable walkthrough of the pipeline
FLOW.md      Architecture diagrams
```

## Data provenance & limitations

- The MD interface reflects the AF3 *starting pose*, so it is a **consistency check on
  that model, not independent validation** of the binding site.
- Analysis is a **single MD replica (n = 1)**.
- The "AlphaFold docked the flexible C-terminal tail" explanation is a **hypothesis**,
  not proven; confirming it needs AF3's own ipTM/PAE at that interface.
