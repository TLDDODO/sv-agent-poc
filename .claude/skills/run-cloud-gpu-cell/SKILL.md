---
name: run-cloud-gpu-cell
description: >-
  Run one training+eval "cell" of the audio_llm_mental_health study on a rented single-GPU cloud box
  (RunPod / Vast.ai / Lambda / GCP g2-standard-4) and slot the resulting donor-swap tracking number
  into RP.md's gradient table. Use whenever the user wants to reproduce or add a cell — the missing
  dual-encoder MELD run (outputs/dual_meld), a LoRA-placement attribution arm, an ESD-grounded eval,
  or any other "rent a box and produce one N/15 number" job. Encodes the rent→env→data→smoke→full→
  eval→backup→write-back workflow from CLOUD_RUNBOOK.md plus the hard-won gotchas, so a cell is one
  guided pass instead of re-reading the runbook. NOT for the school MIG-slice box (that's OPERATIONS.md).
---

# Run one cloud-GPU cell

Goal: on a rented single GPU, produce **one** result — train a config, eval it on the fixed 15-row
donor-swap ruler, get an `N/15` tracking number, back it up so a reclaimed pod can't eat it, and write
it into `RP.md`'s gradient table next to the existing cells (baseline 3/15, textmask1 9/15, LIME 13/15,
ESD 15/15). The canonical first use is the missing **dual-encoder + disentanglement on MELD**
(`outputs/dual_meld`); the same flow serves the other cells the runbook predicts.

The source of truth is `audio_llm_mental_health/CLOUD_RUNBOOK.md` — read it once before starting. This
skill is the checklist that wraps it, with the gates and traps made non-skippable.

## Parameters to pin before starting

Ask / confirm these up front; everything below references them:

- **CELL** — which result. Default: dual-encoder MELD (`outputs/dual_meld`).
- **CONFIG** — e.g. `configs/train_config_dual_meld_4bit.yaml`.
- **TRAIN SCRIPT** — `scripts/train_dual_encoder.py` for the dual-encoder cell; `scripts/train_lora.py`
  for plain LoRA cells.
- **EVAL** — `scripts/eval_dual_encoder.py` (dual-encoder, loads `emotion_proj.pt` too) vs
  `scripts/audio_ablation.py` (plain LoRA). Plus the **15-row index set** and whether eval is
  **with-transcript** or **`--audio-only`** (see the eval gate below — this is the #1 mistake).
- **BASELINE TO COMPARE** — which existing cell this number sits next to (default anchor: 4-bit
  baseline 3/15, the apples-to-apples same-precision point).

## Hard rules (do not violate)

- **Keep it 4-bit.** Every other cell was trained 4-bit QLoRA. Do NOT switch to bf16 "because the
  rented card is bigger" — that breaks apples-to-apples comparability. The configs already are 4-bit.
- **Smoke-test before the full run.** Always. It's a few minutes and it's the gate that validates the
  whole mechanism before you commit an hour of paid GPU.
- **Back up the moment eval finishes**, before doing anything else — pods get reclaimed without warning.
- **One number at a time.** Don't add a new mechanism/arm mid-cell. Produce this cell's number, write
  it back, then decide the next cell.

## Step 0 — rent the right box

- Single GPU, **≥16 GB** (it's 4-bit QLoRA built for a 9.75 GB slice); 24 GB (L4 / RTX 4090 / A100-40GB)
  is comfortable headroom. Do **not** rent an 8-GPU machine — one GPU for ~1–1.5 h is the whole job.
- **Disk ≥60 GB**, ideally 100 GB — MELD.Raw is ~10 GB compressed and expands much larger on extraction.
  The cloud UI's default boot disk is often too small; bump it explicitly.
- Pick a **PyTorch** template (torch + CUDA preinstalled). You're root → `apt-get` works; network is on.
- Cost sanity: ~$0.7–3/hr, job is 1–2 h → a few dollars. An 8-GPU box would burn the budget in hours.

## Step 1 — code

```bash
git clone <repo url> sv-agent-poc && cd sv-agent-poc
git checkout claude/audio-llm-mental-health-setup-pjrkc0
cd audio_llm_mental_health
```

## Step 2 — environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
# Skip the torch line if the template already ships it. Otherwise MATCH the box's CUDA
# (nvidia-smi "CUDA Version"), e.g. cu121:
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
apt-get update && apt-get install -y ffmpeg     # audio extraction needs it
hf auth login                                   # token with WRITE scope (pulls base model + backs up result)
```

## Step 3 — data (MELD, public, no license gate)

Follow CLOUD_RUNBOOK.md §3 exactly. **Capture paths into variables — never paste a real value inside a
`<placeholder>`** (`<` / `>` are shell redirection and fail silently; this has bitten the project for
real — OPERATIONS.md Playbook G). VERIFY the MELD.Raw mirror resolves before trusting it. The end state
is `data/meld_train_manifest.jsonl` + `data/meld_dev_manifest.jsonl` (plain manifests; the dual-encoder
cell needs NO acoustic priors).

## Step 4 — SMOKE TEST FIRST (gate, ~minutes)

```bash
python scripts/train_dual_encoder.py --config configs/train_config_dual_smoke.yaml
```

PASS = three `step N loss ... (lm ... dis ...)` lines with **finite** numbers + a `saved adapter +
emotion projection` line, **no traceback**. OOM → drop `per_device_train_batch_size` to 1 in the smoke
config. Do not proceed to the full run until this passes.

## Step 5 — full run (in tmux, so an SSH drop can't kill it)

```bash
tmux new -s dual_meld \
  "python scripts/train_dual_encoder.py --config configs/train_config_dual_meld_4bit.yaml 2>&1 | tee outputs/dual_meld_train.log; echo EXIT=\$?; exec bash"
# detach: Ctrl-b then d   |   reattach: tmux attach -t dual_meld
# watch: tail -f outputs/dual_meld/metrics.jsonl   (dis_loss should be same order as lm_loss and falling)
```
~1–1.5 h on a full GPU. λ=100 is already set in the config — leave it.

## Step 6 — EVAL: pick the right ruler (the #1 mistake)

Match the eval prompt to how the model was **trained**, or the number is train/test-mismatched and
worthless:

- **dual_meld trains with the transcript PRESENT** (`text_mask_prob=0.0`) → eval **with-transcript**
  (do NOT pass `--audio-only`), to stay comparable to baseline/textmask1's with-transcript cell.
- An audio-only-trained adapter (`text_mask_prob=1.0`) → eval `--audio-only`, NOT `--hide-transcript`.

```bash
python scripts/eval_dual_encoder.py --adapter outputs/dual_meld/final \
    --manifest data/meld_dev_manifest.jsonl \
    --indices 228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034 \
    --out outputs/ablation_dual_meld.jsonl
```

The printed `tracking: N/15` is the cell. Compare against 3/15 / 9/15 / 13/15 / 15/15.

## Step 7 — BACK UP IMMEDIATELY (before anything else)

```bash
R=Avery11/audio-llm-mh-backup
hf upload "$R" outputs/dual_meld/final          adapters/dual_meld/final          --repo-type=model
hf upload "$R" outputs/ablation_dual_meld.jsonl results/ablation_dual_meld.jsonl  --repo-type=model
```

## Step 8 — write the number into RP.md

Slot `N/15` into the gradient table next to the data-level cells. **Follow the project's writing
discipline** (RP.md is meticulous): report the exact ratio, an exact-binomial significance test vs.
the 1/7 chance null, which baseline it's compared to and on what axis, and an honest limit (what is
NOT isolated — for the dual-encoder cell, that it's the objective-level arm vs. the data-level arm on
the same ruler, and any remaining confound). Do not state a causal claim the single number can't carry.
Then commit on `claude/audio-llm-mental-health-setup-pjrkc0`.

## Optional, same box, while paying for it (CLOUD_RUNBOOK.md "Optional")

LoRA-placement attribution (re-pull `adapters/meld_tm1_{llm_only,audio_only,both}`), ESD-grounded eval
(`adapters/esd_lora_grounded`) — both re-run from HF-backed adapters with only manifests + audio, no
retraining. Each is another pass of steps 6–8 with its own CONFIG/EVAL/index set.
