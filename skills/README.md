# Skills — agent role definitions

Each file defines one **role** the pipeline plays. The code loads the text after the
`===PROMPT===` marker at runtime (`agent/skills.py`), so these files are the **real
source** of each agent's behaviour — not documentation copies. Edit a skill here and
the agent's behaviour changes; no code edit needed.

| Skill | Used by | Role |
| --- | --- | --- |
| `investigator.md` | `agent/run_agent.py` | The autonomous agent: picks tools, grounds the model, flags conflicts |
| `md_advocate.md` | `agent/debate.py` | Argues the strongest honest case for the C-terminal (MD) interface |
| `nmr_advocate.md` | `agent/debate.py` | Argues for the N-terminal (literature/NMR) interface |
| `judge.md` | `agent/debate.py` | Neutral judge: separates "contradicts literature" (fact) from "which side is right" (unknown) |

Design rule shared by every skill: **use only tool-provided data, never invent
residues or scores, and never claim a ground truth that does not exist.**
