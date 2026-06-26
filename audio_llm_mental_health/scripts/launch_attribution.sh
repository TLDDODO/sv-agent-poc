#!/usr/bin/env bash
# Launch the 4-way parallel batch (3 LoRA-placement arms + ESD acoustic-grounded) across 4 MIG
# slices, each in its OWN detached tmux session so it survives SSH disconnect. Run on the GPU box
# from the repo's audio_llm_mental_health/ dir.
#
#   bash scripts/launch_attribution.sh              # preflight, then launch all 4
#   bash scripts/launch_attribution.sh --skip-check # skip the target-modules preflight (not advised)
#
# Watch a job:   tmux attach -t tm1_llm_only        (detach with Ctrl-b d)
# List sessions: tmux ls
# Tail a log:    tail -f outputs/train_tm1_llm_only.log
# Kill one job:  tmux kill-session -t tm1_llm_only
set -euo pipefail

cd "$(dirname "$0")/.."   # -> audio_llm_mental_health/
mkdir -p outputs

# Absolute python path so each tmux session uses THIS venv regardless of its shell init.
PYBIN="$(command -v python)"
echo "Using python: $PYBIN"
command -v tmux >/dev/null || { echo "ERROR: tmux not installed"; exit 2; }

# --- preflight: verify the target_modules regexes against the live checkpoint -----------------
if [[ "${1:-}" != "--skip-check" ]]; then
  echo "==> Preflight: scripts/check_target_modules.py (must PASS before launch) ..."
  # Run on the first slice so it doesn't fight a job for memory.
  if ! CUDA_VISIBLE_DEVICES=MIG-d7c98f93-6e8c-598c-9c27-16c6045b2771 "$PYBIN" scripts/check_target_modules.py; then
    echo "ABORT: preflight FAILED -- fix the regex/prefix before launching. Nothing was started." >&2
    exit 1
  fi
fi

# --- job table: session_name | MIG uuid | config | logfile -------------------------------------
# Slices 0-3 used; 4-6 left free.
JOBS=(
  "tm1_llm_only|MIG-d7c98f93-6e8c-598c-9c27-16c6045b2771|configs/train_config_meld_textmask1_llm_only_4bit.yaml|outputs/train_tm1_llm_only.log"
  "tm1_audio_only|MIG-eae605da-1627-5245-a3ac-77f400bffcd2|configs/train_config_meld_textmask1_audio_only_4bit.yaml|outputs/train_tm1_audio_only.log"
  "tm1_both|MIG-e9174e51-35ae-5f7a-8bd4-459c1d531517|configs/train_config_meld_textmask1_both_4bit.yaml|outputs/train_tm1_both.log"
  "esd_grounded|MIG-0d1a8717-3fd3-5772-805c-1657cf70fb4d|configs/train_config_esd.yaml|outputs/train_esd_grounded.log"
)

for spec in "${JOBS[@]}"; do
  IFS='|' read -r name uuid cfg log <<< "$spec"
  if tmux has-session -t "$name" 2>/dev/null; then
    echo "-- SKIP $name: a tmux session by that name already exists (kill it first to relaunch)."
    continue
  fi
  echo "-- launch $name on $uuid  ($cfg)"
  # tee keeps the log file AND lets `tmux attach` show live output. `; exec bash` keeps the pane
  # open after the run ends so you can read the final lines / exit status instead of it vanishing.
  tmux new-session -d -s "$name" \
    "CUDA_VISIBLE_DEVICES=$uuid '$PYBIN' scripts/train_lora.py --config '$cfg' 2>&1 | tee '$log'; echo; echo '[exit '\$?']'; exec bash"
done

echo
echo "Launched. Sessions:"
tmux ls
echo
echo "Attach:  tmux attach -t tm1_llm_only   (detach: Ctrl-b then d)"
echo "Tail:    tail -f outputs/train_tm1_llm_only.log"
