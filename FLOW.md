# Pipeline Flow — Interface-Adjudication Agent

The agent does **not** predict interfaces. Prediction tools do that; the agent
**compares, validates, adjudicates, and audits** them. The diagrams below show
the genuine agentic loop and the audit.

> **Honest status:** every box below is real *machinery* (LLM loop, PDBe
> retrieval, UniProt sequence validation, model comparison) **except the tool
> interface scores, which are placeholder/demo numbers.** Any FAT10 conclusion is
> therefore a method demo, not a real result, until real tool scores are plugged
> in (`INTERFACE_SCORES`). The PDB IDs were **confirmed by a live PDBe query** and
> are genuine FAT10 structures — but **none are FAT10:MAD2 complexes** (no such
> structure exists), so they confirm the protein's identity, not the interface.

## 1. Agentic loop (the LLM drives, in a loop)

```mermaid
flowchart TD
    G["Goal in plain English
    FAT10 O15205 N-term ubl vs MAD2 Q13257"]
    G --> AG["LLM agent (DeepSeek)
    plans and calls tools in a loop"]

    AG -->|calls| T1["list_interface_tools"]
    AG -->|calls| T2["get_tool_prediction
    per-residue scores (PLACEHOLDER)"]
    AG -->|calls| T3["validate_residues
    vs real UniProt sequence"]
    AG -->|calls| T4["fetch_structures
    PDBe (live-verified): 6GF1 6GF2 2MBE 7PYV
    FAT10 structures - none are FAT10:MAD2 complexes"]
    AG -->|calls| T5["map_residues
    canonical numbering + domain check"]

    T1 --> AG
    T2 --> AG
    T3 --> AG
    T4 --> AG
    T5 --> AG

    AG --> SUB["submit_adjudication
    consensus / disputed / weak / confidence
    + recorded step-by-step reasoning"]
    SUB --> REP["agent_report.md + agent_trace.json"]

    classDef agent fill:#eef5ff,stroke:#1d4ed8,color:#0f2440;
    classDef tool fill:#e0f2fe,stroke:#0369a1,color:#0f2440;
    classDef warn fill:#fde9c8,stroke:#b45309,color:#0f2440;
    classDef good fill:#d5f2e5,stroke:#0f9d6b,color:#0f2440;
    
    class AG agent;
    class T1, T3, T4, T5 tool;
    class T2 warn;
    class SUB, REP good;
flowchart TD
    EV["Gather evidence ONCE
    tool scores + validation + mapping + structures"]
    EV --> W["Weak model
    deepseek-chat"]
    EV --> S["Strong baseline
    deepseek-reasoner"]
    W --> D["diff adjudications"]
    S --> D
    D --> OUT["agent_compare.md
    residues where weak & strong models DISAGREE
    → flag as low-confidence (no winner declared)"]

    classDef agent fill:#eef5ff,stroke:#1d4ed8,color:#0f2440;
    classDef warn fill:#fde9c8,stroke:#b45309,color:#0f2440;
    classDef good fill:#d5f2e5,stroke:#0f9d6b,color:#0f2440;
    
    class EV agent;
    class W warn;
    class S, OUT good;
    class D agent;
