# FAT10–MAD2 Interface — Agentic Adjudication

This book runs an LLM-agent pipeline end to end and lets you play with each stage.

The pipeline:

1. **Literature** — an agent searches PubMed and extracts which FAT10 region binds MAD2.
2. **Grounding** — real PDBe structures + UniProt-verified domain boundaries (UBL1 = 6–81).
3. **Evidence** — real per-residue MAD2-contact occupancy from a 100 ns MD simulation.
4. **Adjudication** — a deterministic check: does the MD interface fall in the expected domain?
5. **Debate (the highlight)** — two agents argue the same real facts (MD C-terminal vs NMR
   N-terminal); a judge weighs them and recommends an experiment instead of declaring a winner.

## Honest boundary

The MD occupancies, structures, and domain boundaries are **real**. But there is **no
experimental FAT10–MAD2 complex structure**, so the interface *conclusion* is a method
demo, not ground truth. The pipeline's value is making the conflict explicit and
auditable — the model's MD interface (C-terminal) contradicts the literature-expected
UBL1, which is a real, actionable flag.

## How to use

```bash
export DEEPSEEK_API_KEY=...        # enables the literature + debate (LLM) stages
pip install jupyterlab             # then open notebooks/fat10_mad2_pipeline.ipynb
jupyter lab
```

Run the notebook cell by cell. To build this browsable book:

```bash
pip install jupyter-book
jupyter-book build .
# open _build/html/index.html
```

→ Start with **the pipeline notebook** in the sidebar.
