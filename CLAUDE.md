# CLAUDE.md — sv-agent-poc

The active project here is **`audio_llm_mental_health/`** — a controlled study of modality
collapse in audio-LLMs (Qwen2-Audio 4-bit QLoRA on MELD/ESD/LIME), measured on one fixed
donor-swap tracking ruler. Root-level `*.py` / `outputs/*.md` are an unrelated older PoC.

**Before doing ANY work on this project, load the `audio-llm-mh` skill**
(`.claude/skills/audio-llm-mh/SKILL.md`). It holds the repo map, the cell table, the iron
rules, and the postmortem those rules come from. Do not re-derive workflow from scratch.

Ground rules (digest — the skill has the full versions and the reasons):

- Work on branch `claude/audio-llm-mental-health-setup-pjrkc0`.
- Producing a result cell = `bash scripts/run_cell.sh` (one resumable pipeline). Never
  hand-run the stages ad hoc; the pipeline's preflight gates encode real failures.
- Everything stays **4-bit QLoRA**; the eval ruler (15 pinned indices) never changes; eval
  prompt mode must match how the cell was trained (with-transcript vs `--audio-only`).
- Every credential gets PROVEN by a real operation before money is spent (an actual
  `hf upload`, an actual `runpodctl get pod`) — never assumed, never "should work".
- Back up to `Avery11/audio-llm-mh-backup` the moment an artifact exists. Terminating a
  RunPod pod does NOT stop network-volume billing — volumes are deleted separately.
- `RP.md` is the narrative source of truth; `results/ledger.jsonl` is its machine-readable
  index — they must never disagree. New numbers need `scripts/significance.py` p-values and
  an honest statement of what is NOT isolated.
- CI (`.github/workflows/repro-guards.yml`) re-checks the ledger math, ruler pins, and
  manifest contract on every push — keep it green.
- Statistical discipline from RP.md: no probe-AUC claim under a 0.05–0.07 gap without a
  20-seed `probe_robustness.py` sweep; single 200-row accuracy points carry ~3.4% SE.
