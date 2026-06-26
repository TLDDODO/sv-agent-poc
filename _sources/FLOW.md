# Pipeline Flow — Autonomous FAT10–MAD2 Interface Investigation

You give one goal; the **LLM agent decides the tool order itself** and reaches a
calibrated verdict. Legend: ✅ real data · 📚 cited literature fact · ⏳ no data yet.

## 1. Autonomous agent loop

```mermaid
flowchart TD
    G["Goal: where does MAD2 bind FAT10?"] --> AG["LLM agent (DeepSeek)<br/>chooses tools & order, in a loop"]

    AG -->|"📚 cited"| LIT["search_literature (PubMed, real)<br/>+ get_expected_interface_region<br/>UBL1 6–81 — cited Theng 2014 / UniProt"]
    AG -->|"✅ real"| STR["fetch_structures (PDBe)<br/>+ validate_residues (UniProt seq)"]
    AG -->|"✅ real"| MD["get_md_interface_scores<br/>100 ns MD contact occupancy"]
    AG -->|"⏳ no data"| TOOLS["list_interface_tools / get_tool_prediction<br/>AFM · HADDOCK · PISA = PENDING<br/>(not fabricated; multi-tool consensus blocked)"]

    LIT --> CMP{"MD interface vs<br/>expected domain<br/>conflict?"}
    STR --> CMP
    MD --> CMP
    CMP -->|yes| DEB["convene_debate"]
    CMP -->|no| OUT
    DEB --> OUT["verdict: contradiction = fact;<br/>which side is right = unknown;<br/>recommend an experiment"]

    classDef agent fill:#eef5ff,stroke:#1d4ed8,color:#0f2440;
    classDef real fill:#d5f2e5,stroke:#0f9d6b,color:#0f2440;
    classDef cite fill:#e0f2fe,stroke:#0369a1,color:#0f2440;
    classDef pend fill:#fde9c8,stroke:#b45309,color:#0f2440;
    class AG agent;
    class STR,MD,OUT real;
    class LIT cite;
    class TOOLS pend;
```

## 2. The multi-agent debate (the highlight)

```mermaid
flowchart LR
    F["Real facts: MD occupancies<br/>+ UniProt domains"] --> A["🧬 MD advocate<br/>(defends C-terminal)"]
    F --> B["📚 NMR advocate<br/>(defends UBL1 N-terminal)"]
    A --> J["⚖️ Judge"]
    B --> J
    J --> V["contradicts_literature: true (high conf)<br/>which_side_right: unknown (low conf)<br/>recommendation: XL-MS / mutagenesis"]

    classDef real fill:#d5f2e5,stroke:#0f9d6b,color:#0f2440;
    classDef warn fill:#fde9c8,stroke:#b45309,color:#0f2440;
    class F,V real; class A,B warn; class J real;
```

## Honest status — what is real vs not

| Part | Status |
| --- | --- |
| Agent loop (LLM picks tools/order itself) | ✅ real |
| MD per-residue contact occupancy | ✅ real (your 100 ns run) |
| PDBe structures + UniProt domain boundaries | ✅ real (live-verified) |
| Multi-agent debate + judge | ✅ real LLM over real facts |
| Expected binding region (UBL1) | 📚 **cited fact** (Theng 2014 / UniProt) — hand-fed, corroborated by `search_literature`, NOT derived by the agent |
| **AFM / HADDOCK / PISA multi-tool scores** | ⏳ **no data yet** — reported as *pending*, never fabricated. The "compare tools → pick best model" step is blocked on team data. |
| Any claim of the *true* interface | ❌ no experimental complex structure exists — not ground truth |
