# One-Page Research Proposal

## Title

**Structural Biology Copilot: An Agent-Orchestrated Infrastructure for High-Throughput Mutation Interpretation**

## Problem

Interpreting the structural and dynamical effects of a protein mutation is still a fragmented workflow. A researcher must search structural databases such as PDBe, inspect residue numbering and construct differences, cross-check UniProt or SIFTS mappings, run local molecular dynamics analysis scripts, and manually assemble evidence from papers and trajectories. This process is slow, difficult to reproduce, and inaccessible to many experimental researchers who do not have a computational background.

## Hypothesis

A protocol-driven agent orchestration layer can integrate online structural biology infrastructure with local or HPC-based MD analysis tools, while preserving provenance, residue-level traceability, and evidence grounding. This can reduce the time needed for mutation interpretation and hypothesis generation from days of manual work to minutes of auditable triage.

## Approach

I propose a Structural Biology Copilot that takes a natural-language mutation question and coordinates a set of scientific tools:

1. **Online structure retrieval:** The agent uses the official PDBe MCP server to generate and execute structured Solr queries against PDBe.
2. **Structure normalization:** Retrieved structures are mapped to canonical protein numbering, using EGFR UniProt residue numbering and, in production, PDBe-SIFTS residue-level mappings.
3. **Local/HPC dynamics analysis:** MD trajectory metrics are attached through a standardized tool interface, including topology hash, trajectory ID, mapped selections, frame range, and analysis metadata.
4. **Evidence-grounded reporting:** The system generates claims only when they are linked to explicit evidence sources such as PDB IDs, trajectory IDs, or PMIDs.
5. **Critic audit:** A separate critic agent checks residue mapping, apo versus ligand-bound state, mutant versus wild-type status, provenance, and causal overstatement.

## Preliminary Result

A minimum proof of concept is already running on the HPC. Using EGFR T790M, a classic lung-cancer drug-resistance mutation, the system executed a real query through the official PDBe MCP `pdbe_search_server`. It retrieved high-resolution EGFR T790M structures, including `5UG9` at 1.33 ?, parsed the candidates, mapped the mutation to canonical EGFR residue 790, generated evidence JSON and Markdown reports, and passed critic-agent consistency checks with no critical issues.

## Expected Impact

The system does not attempt to replace structural biologists or invent a new molecular dynamics algorithm. Instead, it addresses a major infrastructure gap: scientific knowledge is distributed across databases, papers, residue mappings, local scripts, and trajectories. By orchestrating these components through auditable agents, the platform can help researchers move faster from mutation to mechanistic hypothesis while maintaining scientific traceability.

## Next Milestones

- Replace demo MD metrics with real MDAnalysis outputs from laboratory trajectories.
- Integrate PDBe-SIFTS residue-level mapping for production-grade structure normalization.
- Add literature PMID retrieval and claim-level citation checks.
- Extend the benchmark beyond EGFR T790M to additional kinase resistance mutations.

## Success Criterion

Given a natural-language query such as "analyze how EGFR T790M affects inhibitor-pocket dynamics," the system should automatically retrieve relevant structures, normalize residue numbering, attach trajectory-derived metrics, audit the evidence chain, and produce a bilingual mechanism brief with explicit sources and limitations.