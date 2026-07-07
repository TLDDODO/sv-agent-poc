#!/usr/bin/env bash
# run_cell.sh — ONE command that takes a freshly-rented single-GPU box from nothing to a
# banked N/15 tracking number: preflight -> data (cache-first) -> seed cache -> smoke ->
# full train -> eval -> backup -> teardown.
#
# Design rules (each one exists because its absence burned a real run — see SKILL.md postmortem):
#   1. PROVE credentials in preflight by DOING the real operation (an actual HF upload, an
#      actual RunPod API call) before any money/time is spent. Never trust "it should work".
#   2. Bank expensive artifacts the moment they exist: the extracted-audio cache uploads
#      right after extraction (BEFORE training), the adapter right after eval.
#   3. Every stage drops a marker file; re-running the script skips finished stages, so a
#      reclaimed pod costs only the unfinished stage.
#   4. Teardown is auto if the RunPod key can manage pods; otherwise the script REFUSES to
#      start unless ACK_MANUAL_TERMINATE=1, so "I'll turn it off later" is an explicit choice.
#
# Launch (inside tmux so an SSH drop can't kill it):
#   cd audio_llm_mental_health
#   tmux new -s cell 'bash scripts/run_cell.sh 2>&1 | tee outputs/run_cell.log; exec bash'
#
# Parameters (env overrides; defaults = the dual-encoder MELD cell):
#   CELL=dual_meld
#   TRAIN_CONFIG=configs/train_config_dual_meld_4bit.yaml
#   SMOKE_CONFIG=configs/train_config_dual_smoke.yaml
#   TRAIN_SCRIPT=scripts/train_dual_encoder.py
#   EVAL_SCRIPT=scripts/eval_dual_encoder.py
#   ADAPTER_DIR=outputs/dual_meld/final
#   EVAL_OUT=outputs/ablation_dual_meld.jsonl
#   EVAL_FLAGS=""                # "--audio-only" ONLY for audio-only-trained cells (ruler must match training)
#   HF_BACKUP_REPO=Avery11/audio-llm-mh-backup
#   ACK_MANUAL_TERMINATE=0      # set 1 to accept manual pod teardown when no working RunPod key
#   SKIP_TRAIN=0                # set 1 for eval-only cells (adapter re-pulled from backup)
set -euo pipefail

CELL="${CELL:-dual_meld}"
TRAIN_CONFIG="${TRAIN_CONFIG:-configs/train_config_dual_meld_4bit.yaml}"
SMOKE_CONFIG="${SMOKE_CONFIG:-configs/train_config_dual_smoke.yaml}"
TRAIN_SCRIPT="${TRAIN_SCRIPT:-scripts/train_dual_encoder.py}"
EVAL_SCRIPT="${EVAL_SCRIPT:-scripts/eval_dual_encoder.py}"
ADAPTER_DIR="${ADAPTER_DIR:-outputs/dual_meld/final}"
EVAL_OUT="${EVAL_OUT:-outputs/ablation_dual_meld.jsonl}"
EVAL_FLAGS="${EVAL_FLAGS:-}"
HF_BACKUP_REPO="${HF_BACKUP_REPO:-Avery11/audio-llm-mh-backup}"
ACK_MANUAL_TERMINATE="${ACK_MANUAL_TERMINATE:-0}"
SKIP_TRAIN="${SKIP_TRAIN:-0}"
# The pinned 15-row donor-swap ruler — identical for every cell in the gradient table.
RULER_INDICES="${RULER_INDICES:-228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034}"

STATE_DIR="outputs/.pipeline_${CELL}"
mkdir -p "$STATE_DIR" outputs

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }
done_marker() { [[ -f "$STATE_DIR/$1.done" ]]; }
mark() { touch "$STATE_DIR/$1.done"; say "stage $1 done"; }

[[ -f "scripts/prepare_meld_manifest.py" ]] \
  || die "run from audio_llm_mental_health/ (manifests store RELATIVE audio paths; cwd matters)"
[[ -z "${TMUX:-}" ]] && say "WARNING: not inside tmux — an SSH drop kills this run. Prefer: tmux new -s cell 'bash scripts/run_cell.sh'"

############################################################################
# Stage 00 — PREFLIGHT: prove everything BEFORE spending GPU-hours.
############################################################################
if ! done_marker 00_preflight; then
  say "[00] preflight"

  command -v ffmpeg >/dev/null || die "ffmpeg missing: apt-get update && apt-get install -y ffmpeg"

  python - <<'PY' || die "torch/CUDA/transformers check failed (need torch 2.x + CUDA + transformers==5.12.1 — the Qwen2AudioProcessor signature is pinned to that exact version)"
import sys, torch, transformers
ok = torch.cuda.is_available() and transformers.__version__ == "5.12.1"
print(f"torch={torch.__version__} cuda={torch.cuda.is_available()} transformers={transformers.__version__}")
sys.exit(0 if ok else 1)
PY

  avail_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
  [[ "$avail_gb" -ge 60 ]] || die "only ${avail_gb}GB free disk; MELD needs >=60GB. Rent with a bigger volume."

  # HF write access: PROVE it with a real upload, not whoami. A read-only token passes
  # every check except the one that matters.
  command -v hf >/dev/null || die "hf CLI missing: pip install -U huggingface_hub"
  hf auth whoami >/dev/null 2>&1 || die "not logged in to HF: hf auth login (WRITE-scope token)"
  echo "write-probe from $(hostname) cell=${CELL}" > "$STATE_DIR/write_probe.txt"
  hf repo create "$HF_BACKUP_REPO" --repo-type model --private --exist-ok >/dev/null
  hf upload "$HF_BACKUP_REPO" "$STATE_DIR/write_probe.txt" ".preflight/write_probe.txt" --repo-type model >/dev/null \
    || die "HF token CANNOT WRITE to $HF_BACKUP_REPO. Fix the token now — otherwise nothing you produce can be backed up and a reclaimed pod eats it all."
  say "HF write access PROVEN (real upload succeeded)"

  # Teardown mode: auto only if a RunPod API call actually succeeds from this box.
  TEARDOWN="manual"
  if [[ -n "${RUNPOD_POD_ID:-}" ]] && command -v runpodctl >/dev/null && runpodctl get pod >/dev/null 2>&1; then
    TEARDOWN="auto"
  fi
  echo "$TEARDOWN" > "$STATE_DIR/teardown_mode"
  if [[ "$TEARDOWN" == "manual" && "$ACK_MANUAL_TERMINATE" != "1" ]]; then
    die "no working RunPod API key on this box, so AUTO-TERMINATE IS IMPOSSIBLE.
Either (a) fix it: RunPod console -> Settings -> API Keys -> create a key with pod-management
permission (not Read Only), then: runpodctl config --apiKey '<key>' && runpodctl get pod
or (b) accept manual teardown: ACK_MANUAL_TERMINATE=1 bash scripts/run_cell.sh
       (you are promising to Terminate the pod AND delete leftover network volumes yourself —
        volumes bill separately even after the pod is gone)"
  fi
  say "teardown mode: $TEARDOWN"
  mark 00_preflight
fi

############################################################################
# Stage 10 — DATA: cache-first. Full download+extract only on a true miss.
############################################################################
manifests_ok() {
  [[ -f data/meld_train_manifest.jsonl && -f data/meld_dev_manifest.jsonl ]] || return 1
  head -1 data/meld_train_manifest.jsonl | python -c \
    'import json,sys,os; sys.exit(0 if os.path.exists(json.loads(sys.stdin.read())["audio_path"]) else 1)'
}

if ! done_marker 10_data; then
  say "[10] data"
  if manifests_ok; then
    say "data already present and paths resolve"
  else
    say "trying HF cache (manifests + extracted audio + CSVs)"
    hf download "$HF_BACKUP_REPO" --repo-type model --local-dir . \
      --include "data/meld_*" "audio/meld_*" >/dev/null 2>&1 || true
    if [[ -d audio/meld_train_audio && -d audio/meld_dev_audio ]]; then
      say "cache HIT — mapping cached audio to the paths manifests expect"
      mkdir -p MELD.Raw
      ln -sfn "$PWD/audio/meld_train_audio" MELD.Raw/train_audio
      ln -sfn "$PWD/audio/meld_dev_audio"   MELD.Raw/dev_audio
      if ! manifests_ok; then
        # Cached manifests carry another box's paths — rebuild from cached CSVs (seconds, no ffmpeg).
        [[ -f data/train_sent_emo.csv && -f data/dev_sent_emo.csv ]] \
          || die "cache has audio but no CSVs to rebuild manifests; do a full run once (rm $STATE_DIR/10_data.done after wiping audio/) so seeding uploads the CSVs"
        python scripts/prepare_meld_manifest.py --csv data/train_sent_emo.csv \
          --audio-dir MELD.Raw/train_audio --out data/meld_train_manifest.jsonl
        python scripts/prepare_meld_manifest.py --csv data/dev_sent_emo.csv \
          --audio-dir MELD.Raw/dev_audio   --out data/meld_dev_manifest.jsonl
        manifests_ok || die "rebuilt manifests still don't resolve — inspect audio/ contents"
      fi
      touch "$STATE_DIR/15_seed.done"   # cache was already seeded by whoever uploaded it
    else
      say "cache MISS — full MELD download + extraction (the slow path, ~hours for ffmpeg)"
      [[ -f MELD.Raw.tar.gz ]] || wget --tries=4 --waitretry=5 -O MELD.Raw.tar.gz \
        "https://web.eecs.umich.edu/~mihalcea/downloads/MELD.Raw.tar.gz" \
        || die "MELD mirror unreachable — get the current link from https://affective-meld.github.io/"
      tar xzf MELD.Raw.tar.gz
      tar xzf MELD.Raw/train.tar.gz -C MELD.Raw/
      tar xzf MELD.Raw/dev.tar.gz   -C MELD.Raw/
      python scripts/extract_meld_audio.py --video-dir MELD.Raw/train_splits        --out-dir MELD.Raw/train_audio
      python scripts/extract_meld_audio.py --video-dir MELD.Raw/dev_splits_complete --out-dir MELD.Raw/dev_audio
      python scripts/prepare_meld_manifest.py --csv MELD.Raw/train_sent_emo.csv \
        --audio-dir MELD.Raw/train_audio --out data/meld_train_manifest.jsonl
      python scripts/prepare_meld_manifest.py --csv MELD.Raw/dev_sent_emo.csv \
        --audio-dir MELD.Raw/dev_audio   --out data/meld_dev_manifest.jsonl
      manifests_ok || die "manifests built but paths don't resolve — check extraction output"
    fi
  fi
  mark 10_data
fi

############################################################################
# Stage 15 — SEED THE CACHE NOW (before training, not after). Half a day of
# ffmpeg work gets banked while the write token is proven fresh.
############################################################################
if ! done_marker 15_seed; then
  say "[15] seeding HF cache (manifests + CSVs + extracted audio)"
  hf upload "$HF_BACKUP_REPO" data/meld_train_manifest.jsonl data/meld_train_manifest.jsonl --repo-type model
  hf upload "$HF_BACKUP_REPO" data/meld_dev_manifest.jsonl   data/meld_dev_manifest.jsonl   --repo-type model
  hf upload "$HF_BACKUP_REPO" MELD.Raw/train_sent_emo.csv    data/train_sent_emo.csv        --repo-type model
  hf upload "$HF_BACKUP_REPO" MELD.Raw/dev_sent_emo.csv      data/dev_sent_emo.csv          --repo-type model
  hf upload "$HF_BACKUP_REPO" MELD.Raw/train_audio           audio/meld_train_audio         --repo-type model
  hf upload "$HF_BACKUP_REPO" MELD.Raw/dev_audio             audio/meld_dev_audio           --repo-type model
  mark 15_seed
fi

############################################################################
# Stage 20 — SMOKE (a few minutes; gates the paid hour)
############################################################################
if [[ "$SKIP_TRAIN" != "1" ]] && ! done_marker 20_smoke; then
  say "[20] smoke test: $SMOKE_CONFIG"
  python "$TRAIN_SCRIPT" --config "$SMOKE_CONFIG" 2>&1 | tee "outputs/${CELL}_smoke.log"
  mark 20_smoke
fi

############################################################################
# Stage 30 — FULL TRAIN (4-bit; ~1-1.5h on a full 24GB GPU)
############################################################################
if [[ "$SKIP_TRAIN" != "1" ]] && ! done_marker 30_train; then
  say "[30] full train: $TRAIN_CONFIG"
  python "$TRAIN_SCRIPT" --config "$TRAIN_CONFIG" 2>&1 | tee "outputs/${CELL}_train.log"
  mark 30_train
fi

############################################################################
# Stage 40 — EVAL on the pinned 15-row ruler
############################################################################
if ! done_marker 40_eval; then
  say "[40] eval (ruler mode: ${EVAL_FLAGS:-with-transcript})"
  # shellcheck disable=SC2086
  python "$EVAL_SCRIPT" --adapter "$ADAPTER_DIR" \
    --manifest data/meld_dev_manifest.jsonl \
    --indices "$RULER_INDICES" \
    --out "$EVAL_OUT" $EVAL_FLAGS 2>&1 | tee "outputs/${CELL}_eval.log"
  grep "tracking:" "outputs/${CELL}_eval.log" > "outputs/RESULT_${CELL}.txt" \
    || die "eval finished but printed no 'tracking:' line — inspect outputs/${CELL}_eval.log"
  mark 40_eval
fi

############################################################################
# Stage 50 — BACKUP EVERYTHING immediately
############################################################################
if ! done_marker 50_backup; then
  say "[50] backup to $HF_BACKUP_REPO"
  [[ -d "$ADAPTER_DIR" ]] && hf upload "$HF_BACKUP_REPO" "$ADAPTER_DIR" "adapters/${CELL}/final" --repo-type model
  hf upload "$HF_BACKUP_REPO" "$EVAL_OUT"                  "results/$(basename "$EVAL_OUT")"     --repo-type model
  hf upload "$HF_BACKUP_REPO" "outputs/RESULT_${CELL}.txt" "results/RESULT_${CELL}.txt"          --repo-type model
  [[ -f "outputs/${CELL}_train.log" ]] && hf upload "$HF_BACKUP_REPO" "outputs/${CELL}_train.log" "logs/${CELL}_train.log" --repo-type model
  mark 50_backup
fi

############################################################################
# Stage 60 — RESULT + TEARDOWN
############################################################################
say "RESULT for cell '${CELL}':"
cat "outputs/RESULT_${CELL}.txt"
say "compare against: baseline 3/15 | textmask1 9/15 | LIME 13/15 | ESD 15/15"
say "next: write this number into RP.md's gradient table (see SKILL.md write-back rules)"

TEARDOWN="$(cat "$STATE_DIR/teardown_mode" 2>/dev/null || echo manual)"
if [[ "$TEARDOWN" == "auto" ]]; then
  say "AUTO-TERMINATING pod ${RUNPOD_POD_ID} in 60s (everything is backed up; Ctrl-C to keep the box)"
  sleep 60
  runpodctl remove pod "$RUNPOD_POD_ID"
else
  cat <<'BANNER'

  ############################################################################
  #  MANUAL TEARDOWN REQUIRED — the meter is still running until YOU act:    #
  #   1. RunPod console -> Pods -> Terminate this pod                        #
  #   2. RunPod console -> Storage -> DELETE any network volume you made     #
  #      (volumes bill separately; deleting the pod does NOT stop them)      #
  ############################################################################
BANNER
fi
