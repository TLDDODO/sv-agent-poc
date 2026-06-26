# Structural Biology Copilot: Agent-Orchestrated Mutation Interpretation

## 60-Second Pitch

So my idea is a **Structural Biology Copilot**: an agent that connects online structural biology databases with local molecular dynamics analysis.

The problem is that interpreting a mutation usually means jumping across PDBe, UniProt, AlphaFold DB, papers, and local MD scripts. That workflow can take days, and it is difficult for researchers without a computational background.

What I built, and what is already running on the HPC, is an agent pipeline. A user gives it a natural-language goal. The agent uses the official PDBe MCP server to retrieve real structures, maps the mutation site to the canonical residue numbering, attaches MD metrics, and then a critic agent audits the evidence before generating a report.

I tested it on **EGFR T790M**, the classic drug-resistance mutation. The system retrieved real EGFR T790M structures from PDBe, including **5UG9 at 1.33 ?**, parsed the candidates, mapped the mutation to canonical EGFR residue 790, generated evidence JSON and Markdown reports, and the critic found no critical consistency issues.

The next step is to connect the same pipeline to real MDAnalysis outputs from our trajectories. This directly connects to Thursday's session on agents: the goal is not to replace scientists, but to orchestrate fragmented scientific infrastructure and accelerate hypothesis generation.

## One-Sentence Version

I built an HPC-running agent pipeline that turns a natural-language mutation question into real PDBe structure retrieval, canonical residue mapping, MD metric schema, evidence-grounded claims, critic audit, and a report.

## What Already Works

- Official PDBe MCP server runs on HPC.
- `run_pdbe_search_query` retrieves real EGFR T790M structures.
- The pipeline parsed high-resolution candidates such as `5UG9`, `5HG8`, `5UG8`, `6TG0`, and `6TFV`.
- EGFR T790M is mapped to canonical EGFR residue 790.
- Evidence JSON and Markdown reports are generated.
- A critic agent checks residue consistency, apo/bound state, mutation status, and source grounding.

## Demo Result

```text
Query: title:*EGFR* AND title:*T790M*
Provider: official PDBe MCP pdbe_search_server
Top hit: 5UG9, 1.33 ?, EGFR L858R/T790M/V948R inhibitor complex
Critic: No critical consistency issues detected
Output: evidence JSON + Markdown report
```

## Key Message

This is not a new MD algorithm. It is an orchestration layer for broken scientific infrastructure: databases, residue mappings, local trajectories, scripts, and literature evidence. It is an accelerator for scientists, not a replacement for scientific judgment.

## If Asked: Why EGFR T790M?

EGFR T790M is a classic kinase drug-resistance mutation in lung cancer. It is structurally well studied, biologically meaningful, and directly relevant to mutation interpretation. That makes it a strong benchmark for validating the pipeline.

## If Asked: What Is Canonical Residue 790 Mapping?

Different PDB structures can use different chain IDs, residue numbering, mutations, missing residues, and construct boundaries. Canonical mapping aligns all structures back to the standard human EGFR UniProt sequence, where T790M is position 790. This makes structure-to-trajectory comparison scientifically traceable.

## If Asked: What Does the Critic Agent Do?

The critic does not generate the hypothesis. It audits the evidence chain: whether residue numbering is consistent, whether structures are mutant or wild-type, whether ligand-bound and apo states are mixed, whether claims are grounded in real PDB IDs or trajectory IDs, and whether the report overstates causality.

## Safe Wording

Use:

> It turns days of manual cross-database and scripting work into minutes of evidence-grounded triage.

Avoid:

> It speeds up science by 960x.

## Next Step

Replace the current schema-valid MD demo metrics with real MDAnalysis outputs from local or HPC trajectories, then add SIFTS-based residue-level mapping for production-grade structure normalization.