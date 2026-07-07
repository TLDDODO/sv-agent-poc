---
name: audio-llm-mh
description: >-
  Everything about the audio_llm_mental_health study (modality collapse in audio-LLMs, Qwen2-Audio
  QLoRA on MELD/ESD, the N/15 donor-swap gradient table in RP.md). Use for ANY task on this project:
  producing/reproducing a cell on a rented cloud GPU (RunPod/Vast/Lambda/GCP), the dual-encoder MELD
  run, data setup or the HF cache, backups, RunPod billing/teardown questions, writing results into
  RP.md, or adding a new experimental arm. The whole run is ONE resumable command —
  scripts/run_cell.sh — with credential preflight gates that exist because a real run died without
  them. NOT for the school MIG-slice box (that's OPERATIONS.md's playbooks).
---

# audio_llm_mental_health — the whole project, one pipeline

## What this project is (30 seconds)

Claim under study: audio-LLMs trained on emotion data collapse onto the transcript and ignore
audio ("modality collapse"). Measurement: the **donor-swap tracking ruler** — 15 fixed MELD dev
rows; swap in a donor's audio, count how often the predicted label follows the donor's audio
rather than the transcript. Every intervention lands in one gradient table in `RP.md`:

| cell | intervention level | tracking | p vs chance |
|---|---|---|---|
| baseline bf16 | none (precision differs — NOT the anchor) | 2/15 | 0.65 |
| baseline 4-bit | none — **the apples-to-apples anchor** | 3/15 | 0.36 |
| grounded (CoT+mask0.3) | supervision | 7/15 | 2.7e-3 |
| textmask1 | data (mask transcript fully) | 9/15 | 5.4e-5 |
| textmask1_acoustic | data+supervision (adds nothing) | 9/15 | 5.4e-5 |
| LIME part B | data (no transcript by construction) | 13/15 | 8.2e-10 |
| ESD | data (parallel text, acted) | 100/100 (≡15/15) | 1.3e-70 |
| **dual_meld** | **objective (dual-encoder + disentangle λ=100)** | **MISSING — the run to produce** | — |

Machine-readable version with configs/adapters/index-sets: `results/ledger.jsonl` (CI re-derives
its p-values). p-values come from `scripts/significance.py` (exact binomial, null 1/7 MELD/LIME,
1/5 ESD) — never hand-compute them again.

Producing one cell = rent a single GPU (~$2, 1–2 h), run the pipeline, get `N/15`, write it back.

## Repo map

- `RP.md` — research plan + the gradient table (the write-back target).
- `CLOUD_RUNBOOK.md` — manual step-by-step explanation of what the pipeline automates.
- `OPERATIONS.md` — playbooks for the SCHOOL shared-MIG H100 only (OOM, disk, tmux, `<placeholder>` traps).
- `scripts/run_cell.sh` — **THE pipeline.** Preflight → data (cache-first) → seed cache → smoke →
  train → eval → backup → teardown, all resumable via markers in `outputs/.pipeline_<CELL>/`.
- `scripts/train_dual_encoder.py` / `train_lora.py` — training; `eval_dual_encoder.py` /
  `audio_ablation.py` — eval; `extract_meld_audio.py` + `prepare_meld_manifest.py` — data.
- `configs/` — all 4-bit QLoRA. `train_config_dual_meld_4bit.yaml` is the missing cell;
  `train_config_dual_smoke.yaml` its 3-step gate.
- HF backup repo: `Avery11/audio-llm-mh-backup` (private) — adapters under `adapters/`, results
  under `results/`, the data cache under `data/` + `audio/`.

## Running a cell (the whole job)

On a freshly rented box (PyTorch template, ≥16 GB GPU, ≥60 GB disk):

```bash
git clone <repo url> sv-agent-poc && cd sv-agent-poc
git checkout claude/audio-llm-mental-health-setup-pjrkc0
cd audio_llm_mental_health
pip install -r requirements.txt && apt-get update && apt-get install -y ffmpeg
hf auth login    # WRITE-scope token — preflight will PROVE it, not trust it
tmux new -s cell 'bash scripts/run_cell.sh 2>&1 | tee outputs/run_cell.log; exec bash'
```

That's it. The script gates itself: if a credential can't do its job, it dies in preflight —
**before** any GPU-hour is spent. Re-running after any failure resumes at the failed stage.

Cell parameterization (env vars; defaults = dual_meld):

| cell | override |
|---|---|
| dual_meld (default) | none |
| plain-LoRA cell | `TRAIN_SCRIPT=scripts/train_lora.py EVAL_SCRIPT=scripts/audio_ablation.py` + its configs |
| audio-only-trained cell | add `EVAL_FLAGS=--audio-only` (ruler must match training — see below) |
| eval-only (adapter from backup) | `SKIP_TRAIN=1 ADAPTER_DIR=<pulled dir>` after `hf download`-ing the adapter |

## Iron rules — each one is a scar, not a preference

1. **Prove, don't assume, every credential in preflight — by doing the real operation.**
   A run died because the RunPod key turned out unauthorized (discovered only when auto-teardown
   was needed) and the HF cache turned out never seeded (discovered only when a new box tried to
   download it). `run_cell.sh` therefore performs an actual `hf upload` write-probe and an actual
   `runpodctl get pod` before stage 1. Never bypass these gates.
2. **Bank artifacts the moment they exist.** The extracted-audio cache uploads BEFORE training
   (stage 15), the adapter immediately after eval (stage 50). "Back up at the end" is how the
   first attempt lost everything when pod + volume were deleted.
3. **Teardown is part of the run, and pods are not the only meter.** Auto-terminate fires only if
   the RunPod key works; otherwise the operator explicitly acks manual teardown up front
   (`ACK_MANUAL_TERMINATE=1`). Terminating a pod does NOT stop billing for **network storage
   volumes** — those are separate objects on the console's Storage page and bill per hour until
   deleted (a real $0.01/hr leak ran for days this way).
4. **Keep it 4-bit.** Every cell in the table is 4-bit QLoRA. A bigger rented card is not a
   reason for bf16 — that breaks apples-to-apples and the number becomes unusable.
5. **Match the eval ruler to how the cell was TRAINED** (the #1 way to produce a worthless
   number): trained with transcript present (`text_mask_prob=0.0`, e.g. dual_meld) → eval
   with-transcript (no flag). Trained audio-only (`text_mask_prob=1.0`) → `EVAL_FLAGS=--audio-only`
   (never `--hide-transcript`). The 15 indices never change.
6. **One number at a time.** Produce this cell's `N/15`, write it back, commit, then decide the
   next cell. No mid-cell mechanism changes.
7. **Pins that look wrong but aren't:** `transformers==5.12.1` exactly (Qwen2AudioProcessor call
   signature; newer majors break at runtime, not install time). Manifests store **relative**
   audio paths — always run from `audio_llm_mental_health/`. Never paste real values into
   `<placeholder>` syntax in shell (redirection eats it silently — OPERATIONS.md Playbook G).
   On Deep-Learning-VM images use the preinstalled torch; a fresh venv hides it.

## Reproducibility stack (what exists at each layer — keep all of it green)

- **Environment**: `requirements.txt` pins `transformers==5.12.1` exactly; per-run
  `outputs/pip_freeze_<cell>.txt` captures the box's real env (uploaded with the backup).
- **Data**: manifests store relative paths (portability contract, CI-tested); the HF cache
  under `data/` + `audio/` includes the CSVs so any box can rebuild manifests in seconds;
  `outputs/meld_raw_sha256.txt` records the tarball checksum at download time.
- **Run provenance**: the pipeline's stage 45 emits `outputs/run_card_<cell>.json` — git
  commit, config sha256, library versions, GPU/driver, data checksum, backup-repo revision,
  the result, its p-value. Training itself also writes `run_metadata.jsonl` + `metrics.jsonl`
  per run (append-only: old crashed-run lines persist; read timestamps, not just steps).
- **Claims**: `RP.md` (narrative truth) ↔ `results/ledger.jsonl` (machine index) ↔
  `scripts/significance.py` (the math). CI (`.github/workflows/repro-guards.yml`) fails the
  push if the ledger's p-values don't re-derive, the ruler indices drift between files, the
  manifest contract breaks, or a config stops parsing.
- **AI continuity**: repo-root `CLAUDE.md` auto-loads into every future Claude session and
  points here. Deliberately NO wandb/MLflow: each new tracked service adds a credential
  dependency, and credentials are this project's proven #1 failure mode — the run card +
  HF backup achieve the same provenance on infrastructure the project already trusts.

## Research-layer traps (deep knowledge that changes results, not just workflow)

- **Ruler index sets differ per corpus** — do not mix them: MELD uses
  `228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034` over `meld_dev_manifest`;
  LIME uses `51,61,65,178,191,209,228,285,447,457,476,501,563,864,1116` (note 1034→1116)
  over `lime_dev_manifest`; ESD used a 100-row `random.Random(42).sample(range(1750),100)`.
- **The PEFT `target_modules` suffix-match trap** (RP.md Core Finding correction): with
  list-valued `target_modules: [q_proj,k_proj,v_proj,o_proj]`, PEFT matches by component-name
  suffix across the WHOLE model — so every adapter trained so far also LoRA'd the audio
  tower's q/k/v (only `out_proj` escaped). Any LoRA-placement arm needs path-qualified regex
  strings (see RP.md Future Work for the exact patterns) and a
  `scripts/check_target_modules.py` sanity pass before training.
- **Probe noise floor**: a single fixed-fold-seed AUC point on ~200 rows cannot support any
  claim under a 0.05–0.07 gap — three such readings were already retracted after 20-seed
  `probe_robustness.py` sweeps. Any "this stage looks elevated/depressed" reading needs the
  sweep (and ideally a fresh `--seed` re-extract) first.
- **Single 200-row accuracy points carry ~3.4% SE** — a 0.005 delta is noise, not signal.
- **Absolute accuracy is not comparable across corpora** (class balance differs); only the
  audio-vs-silence delta and per-class recall shapes are read across regimes.
- **Cross-eval-regime numbers are not comparable**: audio-only cells' absolute accuracy lives
  on a different task framing than with-transcript cells' — compare within regime.

## Write-back (after the pipeline prints RESULT)

`outputs/RESULT_<cell>.txt` holds the `tracking: N/15` line (also backed up to
`results/RESULT_<cell>.txt` on HF). Slot it into RP.md's gradient table following the project's
discipline: exact ratio, exact-binomial test vs the 1/7 null, which cell it's compared against and
on what axis, and the honest limit (for dual_meld: it isolates objective-level vs data-level on
the same ruler; a single 15-row number carries no causal claim beyond that). In the same
commit: flip the cell's row in `results/ledger.jsonl` from `pending` to `published` with the
real `tracking_k` and `p_exact` (from `scripts/significance.py`), and copy
`run_card_<cell>.json` from the HF backup into `results/`. CI will verify the ledger math.
Commit on `claude/audio-llm-mental-health-setup-pjrkc0`.

## Adding a new arm

New cell = new config under `configs/` (stay 4-bit, same manifests, same 15-row ruler) + one env
block invoking `run_cell.sh`. If it needs a new eval mode, extend the eval script rather than
changing the ruler. Update the table in RP.md and the cell table here.

## Postmortem the gates encode (why this file exists)

One full attempt produced zero banked artifacts: box rented → env built → cache probe returned
`no cache` (nothing was ever seeded) → operator balked at re-extraction → RunPod key found to be
unauthorized so auto-teardown failed → pod + 200GB volume manually deleted → all local work gone;
the volume kept billing until separately deleted. Every failure was knowable in the first five
minutes. That is what stage 00 now checks, in order, before a single expensive step runs.
