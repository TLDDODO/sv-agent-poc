#!/usr/bin/env bash
# Back up LoRA adapters (and optionally probe .npz dumps) to a PRIVATE Hugging Face repo.
#
# Run this ON THE GPU BOX, where /data is actually mounted -- NOT from a Claude Code web
# session (that container has no /data). It only PRESERVES data: it creates a private repo
# and uploads to it. It never deletes anything locally.
#
# Defaults are deliberately conservative:
#   * Repo is created PRIVATE. There is no flag here to make it public -- flip visibility
#     in the HF web UI later if you ever decide to, so it can never happen by accident.
#   * Only adapter weight folders (*_lora*) are uploaded by default.
#   * The probe .npz dumps are hidden-state extractions DERIVED FROM MELD / ESD audio.
#     Those datasets' licenses typically forbid redistributing derived data. They are
#     uploaded ONLY if you pass --with-npz, i.e. only after you've checked the licenses.
#
# Usage:
#   hf auth login                     # once, paste a WRITE token from hf.co/settings/tokens
#   bash backup_to_hf.sh <hf-user>/<repo-name>                 # adapters only (recommended first)
#   bash backup_to_hf.sh <hf-user>/<repo-name> --with-npz      # also upload probe .npz (license-gated)
#
# Override the source root if your layout differs:
#   DATA_ROOT=/data/user_dirs/ychen/outputs bash backup_to_hf.sh <hf-user>/<repo-name>
#
set -euo pipefail

REPO_ID="${1:-}"
WITH_NPZ="no"
[[ "${2:-}" == "--with-npz" ]] && WITH_NPZ="yes"

# Where the adapters live on the GPU box. Adjust if yours differ.
DATA_ROOT="${DATA_ROOT:-/data/user_dirs/ychen/outputs}"
# Where the 6 probe .npz dumps live (the narrative had them under .../outputs/outputs).
NPZ_ROOT="${NPZ_ROOT:-${DATA_ROOT}/outputs}"

if [[ -z "$REPO_ID" ]]; then
  echo "ERROR: pass a repo id, e.g.  bash backup_to_hf.sh myuser/audio-llm-mh-backup" >&2
  exit 2
fi

command -v hf >/dev/null 2>&1 || { echo "ERROR: 'hf' CLI not found (pip install -U huggingface_hub)" >&2; exit 2; }
hf auth whoami >/dev/null 2>&1 || { echo "ERROR: not logged in. Run: hf auth login" >&2; exit 2; }

echo "==> Source root : $DATA_ROOT"
echo "==> Target repo : $REPO_ID  (PRIVATE)"
echo "==> Include npz : $WITH_NPZ"
echo

# 1) Create the private repo if it does not exist (idempotent: --exist-ok).
hf repo create "$REPO_ID" --repo-type model --private --exist-ok

# 2) Upload each adapter folder. Skip empty dirs (e.g. the 0-byte esd_lora) so we don't
#    create misleading empty entries in the repo.
shopt -s nullglob
uploaded=0
for d in "$DATA_ROOT"/*_lora*/; do
  name="$(basename "$d")"
  if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then
    echo "-- skip (empty): $name"
    continue
  fi
  echo "-- upload adapter: $name ($(du -sh "$d" | cut -f1))"
  hf upload "$REPO_ID" "$d" "adapters/$name" --repo-type model
  uploaded=$((uploaded + 1))
done
echo "==> uploaded $uploaded adapter folder(s)"

# 3) Probe .npz dumps -- only with explicit opt-in (license check on MELD/ESD first).
if [[ "$WITH_NPZ" == "yes" ]]; then
  if compgen -G "$NPZ_ROOT/*.npz" >/dev/null; then
    echo "-- upload probe .npz from $NPZ_ROOT (you confirmed license allows this)"
    hf upload "$REPO_ID" "$NPZ_ROOT" "probes" --include="*.npz" --repo-type model
  else
    echo "-- no .npz found under $NPZ_ROOT (set NPZ_ROOT=... if elsewhere)"
  fi
else
  echo "==> skipped probe .npz (pass --with-npz after checking MELD/ESD licenses)"
fi

echo
echo "Done. Verify at: https://huggingface.co/$REPO_ID  (Settings shows it is Private)"
