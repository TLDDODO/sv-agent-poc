# Current-state inventory (v1, S1)

> Read-only inventory; no code was changed. Based on commit `4069eaa`.

## 1. Purpose

An LLM agent (DeepSeek, ReAct loop) that adjudicates the FAT10–MAD2 protein interface from real evidence (PDBe structures, UniProt sequence, 100 ns MD contact occupancy, PubMed). When the evidence and the literature conflict it convenes a three-way debate (MD advocate / NMR advocate / judge) and reports the contradiction without declaring which side is right.

## 2. File / module list

**agent/**
- `agent/__init__.py` — package note (the LLM decides which tools to call).
- `agent/llm_client.py` — `make_client()`: an OpenAI-compatible client pointing at DeepSeek; `MODEL` comes from an environment variable.
- `agent/run_agent.py` — the ReAct main loop `run()`; `render()` builds a markdown report; the CLI writes to `outputs/`.
- `agent/tools.py` — all tool implementations + the `DISPATCH` map + `TOOLS` (function-calling schema).
- `agent/structures.py` — PDBe: the verified snapshot `offline_structures()`, the live MCP client `mcp_structures()`, `canonical_map()`.
- `agent/literature.py` — PubMed E-utilities search; `retrieve_binding_region()` uses the LLM to extract the binding region from abstracts.
- `agent/debate.py` — three-way debate: `evidence_bundle()` assembles the real facts; two advocates + a judge; writes to `outputs/`.
- `agent/compare.py` — weak-vs-strong model comparison: the same evidence goes to two models and the disagreement is compared.
- `agent/skills.py` — loads role prompts from `skills/` (the text after `===PROMPT===`).

**skills/** (role prompts loaded at run time)
- `skills/README.md` — description of the skills directory.
- `skills/investigator.md` — main agent prompt.
- `skills/md_advocate.md` — MD advocate prompt.
- `skills/nmr_advocate.md` — NMR / literature advocate prompt.
- `skills/judge.md` — judge prompt (forces JSON, separates "is there a contradiction" from "who is right").

**analysis/**
- `analysis/md_to_scores.py` — on the HPC, turns an Amber prmtop + cpptraj nativecontacts output into a per-residue occupancy JSON.
- `analysis/md_interface_scores.json` — the product of the previous step: contact occupancy of each FAT10 residue with MAD2 (100 ns).
- `analysis/adjudicate_md.py` — deterministic conflict check (no LLM, no network): does the MD core interface fall inside UBL1 6–81?
- `analysis/build_report.py` — pure-Python HTML report (includes literature and the debate when a key is available).
- `analysis/render_structure.py` — PyMOL + Pillow rendering of the annotated structure figure.

**api/**
- `api/__init__.py` — package note.
- `api/main.py` — FastAPI: `/`, `/health`, `/evidence` (no key needed), `/adjudicate`, `/debate` (key needed).

**Data / figures / other**
- `complex_protein.pdb` — frame 1 of the MD trajectory (water and ions removed).
- `interface.png`, `interface_labeled.png` — rendered structure figures (the latter annotated).
- `outputs/md_vs_nmr_adjudication.md` — sample output of `analysis/adjudicate_md.py` (the only committed run product).
- `outputs/.gitkeep` — keeps the run-time output directory.
- `notebooks/fat10_mad2_pipeline.ipynb` — executable demo of the five-stage pipeline.
- `FLOW.md` — architecture diagrams (mermaid).
- `README.md` — project description + an honest status table.
- `CLAUDE.md` — the rules for this Agent 2.0 autonomous run.
- `.claude/agents/reviewer.md` — the independent reviewer sub-agent.
- `Dockerfile`, `docker-compose.yml`, `.dockerignore` — containerisation.
- `requirements.txt` — run-time dependencies.
- `.gitignore` — ignore rules.

## 3. Typical tool-call order in a full run

The repository contains **no recorded trace of a complete run**, so the order below is not measured. It is the order that the `skills/investigator.md` prompt suggests (the real order is decided by the LLM each time):

1. `search_literature` — query PubMed and read the abstracts to learn where MAD2 is expected to bind FAT10
2. `get_expected_interface_region` — get the literature / NMR expected region (UBL1 6–81)
3. `fetch_structures` — confirm the system (PDBe structures)
4. `validate_residues` — check the residue labels against the real UniProt sequence
5. `map_residues` — map to UniProt numbering and decide whether they lie inside the domain
6. `get_md_interface_scores` — get the real MD contact occupancy
7. `convene_debate` — if the MD interface falls outside the expected region (a conflict), convene the debate (3 LLM calls inside)
8. `submit_adjudication` — submit the final verdict and end the loop

`list_interface_tools` / `get_tool_prediction` are also available in the schema but the prompt does not mention them; for AFM / HADDOCK / PISA they return `pending`.

## 4. Data sources by kind

**Live (network access on every run)**
- `search_literature` → NCBI E-utilities (esearch + efetch); on failure it returns a cited fallback conclusion marked `retrieved_live: False`.
- `validate_residues` → the FASTA from `rest.uniprot.org`.
- All LLM calls → the DeepSeek API (`run_agent`, `debate`, `compare`, `literature.retrieve_binding_region`).
- `mcp_structures()` → the PDBe MCP server (through `uvx`) — the code exists but **no entry point calls it at present**.

**Snapshot (verified snapshots committed in the code)**
- `fetch_structures` → `offline_structures()`: 6GF1, 6GF2, 2MBE, 7PYV (all FAT10 structures; there is no FAT10:MAD2 complex). The function **ignores the `uniprot` argument** and always returns these 4 entries.

**Local files**
- `analysis/md_interface_scores.json` — real MD occupancy (the original prmtop / trajectory are not in the repository).
- `complex_protein.pdb`, `interface.png`, `interface_labeled.png` — the MD structure and the renderings.
- The prompt files under `skills/`.

**Hard-coded cited facts (cited, not derived by this system)**
- `get_expected_interface_region`: UBL1 6–81, from Theng et al. 2014 PNAS + NMR 2MBE + the UniProt domain table.
- The `FALLBACK` conclusion in `agent/literature.py`.
- The FAT10 domain table `DOMAINS` is written out once each in `analysis/adjudicate_md.py`, `agent/debate.py`, `analysis/build_report.py` and `notebooks/fat10_mad2_pipeline.ipynb` (four copies).

**Pending (no data, never invented)**
- Per-residue scores from AlphaFold-Multimer, HADDOCK and PISA (`get_tool_prediction` returns `status: pending`).

**Comparison with the README status table — disagreements**
1. The README says PDBe retrieval is a "live MCP client or verified snapshot"; in reality the agent, the API and the CLI **use only the snapshot**, and `mcp_structures()` has no entry point (the old `--source mcp` entry point was deleted with the old module in `7c3627b`).
2. The README says the FAT10 domain boundaries are "UBL1 6–81 ✅ verified", but `map_residues` still defaults to `domain_hi=80`, `NTERM_UBL_RANGE = (1, 80)` in `agent/structures.py`, and `gather_evidence(domain=(1, 80))` in `agent/compare.py` — the old, unverified 1–80.
3. The pending tool name is inconsistent: `agent/tools.py` uses `PISA`, `_CAVEATS` in `agent/compare.py` uses `PISA-contacts` (no practical effect on the pending status).

> These 3 items were handled in S1b (see `docs/progress.md`); this section is kept as the original S1 inventory.

The remaining items (the ReAct loop, the MD data, `validate_residues`, the cited expected region, the debate, the weak-vs-strong comparison, the three pending tools) agree with the README.

## 5. Running locally

Run from the **repository root** (the data paths are relative).

```bash
pip install -r requirements.txt            # this cloud image needs --ignore-installed
export DEEPSEEK_API_KEY=...                # required (LLM parts)
export DEEPSEEK_BASE_URL=https://api.deepseek.com   # optional, default value
export DEEPSEEK_MODEL=deepseek-chat        # optional, default value
export INTERFACE_SCORES=analysis/md_interface_scores.json   # optional, default value

python -m agent.run_agent                  # autonomous agent → outputs/
python -m agent.debate                     # three-way debate → outputs/
python -m agent.compare                    # weak/strong model comparison → outputs/
python analysis/adjudicate_md.py           # deterministic conflict check (no key / network needed)
python -m analysis.build_report            # HTML report
uvicorn api.main:app --reload              # API, docs at /docs
docker compose up --build                  # run the API in a container
```

Re-rendering the figure also needs `pymol-open-source` + `pillow` (`analysis/render_structure.py`); `analysis/md_to_scores.py` has to run on an HPC node that has the MD files.

## 6. What has no test coverage

The repository currently has **no tests at all** (no tests directory and no CI). All of the following is uncovered:
- the loop in `agent/run_agent.py` (tool dispatch, termination on `submit_adjudication`, the case of reaching `max_steps`)
- every tool in `agent/tools.py` (including the fallback branches when the network fails)
- the snapshot, the MCP parser `_parse()` and `canonical_map()` in `agent/structures.py`
- `agent/literature.py`, `agent/debate.py`, `agent/compare.py` (including JSON parsing)
- loading and fallback in `agent/skills.py`
- every endpoint of `api/main.py`
- every script under `analysis/`, and `notebooks/fat10_mad2_pipeline.ipynb`

## 7. The 3 most fragile points

1. **`fetch_structures` hard-codes FAT10**: it ignores the `uniprot` argument, always returns the FAT10 snapshot, and the live MCP is not wired in. Any other protein pair would get wrong structures; and 7PYV in the snapshot is an experimental FAT10–UBA6 complex — if the benchmark chose that pair it would be a ready-made source of answer leakage.
2. **FAT10 constants and relative paths are scattered**: the domain table is copied four times, the domain ranges 1–80 and 6–81 coexist, and both the MD path and `outputs/` are relative paths. Outside the repository root the data cannot be found; changing one place later makes it easy to miss the other three.
3. **LLM output parsing is fragile and silent**: `debate`, `compare` and `literature` extract JSON with the greedy regex `\{.*\}` and return `{"error": ...}` instead of raising on failure; `search_literature` silently falls back to the cited conclusion on any exception; the debate is nested inside the agent loop, and its 3 LLM calls have no timeout / retry control.
