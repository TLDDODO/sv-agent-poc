#!/usr/bin/env bash
# Durable fix for OPERATIONS.md Playbook B: $HOME is a 58 GB partition and fills from
# checkpoints (238 MB each, 9-14 per run); /data is TBs. This moves each FINISHED or
# IDLE run directory under outputs/ to /data/user_dirs/$USER/outputs/ and replaces it
# with a symlink, so every script/config that writes to outputs/<run>/... keeps working
# completely unchanged (no config edits needed).
#
# Safe to run while a training job is actively writing checkpoints: any run directory
# without a final/ whose metrics.jsonl was touched in the last 10 minutes is treated as
# ACTIVE and skipped untouched. Re-run this after that run finishes to pick it up too.
#
#   ./scripts/migrate_outputs_to_data.sh                 # uses ~/outputs
#   ./scripts/migrate_outputs_to_data.sh /path/to/outputs # explicit path
set -euo pipefail

SRC="${1:-$HOME/outputs}"
DEST_BASE="/data/user_dirs/$USER/outputs"

if [ ! -d "$SRC" ]; then
  echo "No $SRC found, nothing to migrate." >&2
  exit 0
fi

mkdir -p "$DEST_BASE"

moved=0
skipped=0
for d in "$SRC"/*/; do
  [ -d "$d" ] || continue
  name=$(basename "$d")

  if [ -L "${d%/}" ]; then
    echo "SKIP $name (already a symlink, already migrated)"
    continue
  fi

  metrics="${d}metrics.jsonl"
  if [ ! -d "${d}final" ] && [ -f "$metrics" ] && [ -n "$(find "$metrics" -mmin -10)" ]; then
    echo "SKIP $name (looks ACTIVE: no final/ yet, metrics.jsonl touched <10 min ago)"
    skipped=$((skipped + 1))
    continue
  fi

  echo "MOVE $name -> $DEST_BASE/$name"
  mv "$d" "$DEST_BASE/$name"
  ln -s "$DEST_BASE/$name" "$SRC/$name"
  moved=$((moved + 1))
done

echo
echo "Moved $moved run dir(s), skipped $skipped active run(s)."
df -h ~ /data
