# FAT10 : MAD2 Interface-Tool Adjudication — Flow

The agent layer does not predict the interface. Several prediction tools do that;
the agents **compare, adjudicate, and audit** them — surfacing where the tools
agree (use for MD) and where they disagree (flag for MD / experiment).

```mermaid
flowchart TD
    Q["Question:<br/>which FAT10 residues bind MAD2?"]

    Q --> T1["AlphaFold-Multimer"]
    Q --> T2["HADDOCK"]
    Q --> T3["PISA-contacts"]

    T1 --> A1["Agent: interpret AFM<br/>(called residues + caveat)"]
    T2 --> A2["Agent: interpret HADDOCK<br/>(called residues + caveat)"]
    T3 --> A3["Agent: interpret PISA<br/>(called residues + caveat)"]

    A1 --> AGG["Aggregator<br/>per-residue: consensus vs dispute<br/>agreement + confidence"]
    A2 --> AGG
    A3 --> AGG

    AGG --> CON["Consensus interface<br/>I7 L9 Y22 K24 F46<br/>→ MD interface model"]
    AGG --> DIS["Disputed<br/>V64 D66<br/>→ flag for MD / experiment"]

    CON --> CRIT["Critic<br/>reliability audit"]
    DIS --> CRIT
    CRIT --> REP["Report<br/>interface_report.md + .json"]

    classDef tool fill:#e0f2fe,stroke:#0369a1,color:#0f2440;
    classDef agent fill:#eef5ff,stroke:#1d4ed8,color:#0f2440;
    classDef good fill:#d5f2e5,stroke:#0f9d6b,color:#0f2440;
    classDef warn fill:#fde9c8,stroke:#b45309,color:#0f2440;
    class T1,T2,T3 tool;
    class A1,A2,A3,AGG agent;
    class CON,REP good;
    class DIS,CRIT warn;
```

**Where this plugs into the team's plan:** the project flow is
*compare interface-prediction tools → pick one interface model → run MD →
interface features for inhibitor design.* This layer automates the
**compare → pick** step and produces an auditable, evidence-grounded interface
selection instead of a by-hand choice.
