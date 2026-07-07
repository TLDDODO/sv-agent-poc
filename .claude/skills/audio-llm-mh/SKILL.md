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

| cell | intervention level | tracking |
|---|---|---|
| baseline 4-bit | none | 3/15 |
| textmask1 | data (mask transcript) | 9/15 |
| LIME part B | data (decoupled synth) | 13/15 |
| ESD | data (acted, decoupled) | 15/15 |
| **dual_meld** | **objective (dual-encoder + disentangle λ=100)** | **MISSING — the run to produce** |

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

## Write-back (after the pipeline prints RESULT)

`outputs/RESULT_<cell>.txt` holds the `tracking: N/15` line (also backed up to
`results/RESULT_<cell>.txt` on HF). Slot it into RP.md's gradient table following the project's
discipline: exact ratio, exact-binomial test vs the 1/7 null, which cell it's compared against and
on what axis, and the honest limit (for dual_meld: it isolates objective-level vs data-level on
the same ruler; a single 15-row number carries no causal claim beyond that). Commit on
`claude/audio-llm-mental-health-setup-pjrkc0`.

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
