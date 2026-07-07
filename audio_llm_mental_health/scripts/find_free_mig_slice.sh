#!/usr/bin/env bash
# Codifies the manual nvidia-smi + nvidia-smi -L cross-referencing from OPERATIONS.md
# Playbook A / the standing launch checklist into one command, so picking an empty MIG
# slice is one call instead of eyeballing two tables by hand every time.
#
# It ALWAYS prints the raw nvidia-smi / nvidia-smi -L output above its suggestion --
# picking the wrong slice here means colliding with another tenant's multi-hour job
# (it has happened: rfu's pmemd.cuda on GI 7), so don't trust the suggestion blindly.
# Sanity-check it against the raw tables the first few times you run it.
#
#   ./scripts/find_free_mig_slice.sh
#   export CUDA_VISIBLE_DEVICES=<uuid it suggests>
set -euo pipefail

echo "=== nvidia-smi (raw) ==="
smi=$(nvidia-smi)
echo "$smi"

echo
echo "=== nvidia-smi -L (raw) ==="
list=$(nvidia-smi -L)
echo "$list"

mapfile -t uuids < <(echo "$list" | grep -oE 'MIG-[0-9a-f-]+')
if [ "${#uuids[@]}" -eq 0 ]; then
  echo
  echo "No MIG UUIDs found in 'nvidia-smi -L' -- is this host MIG-partitioned?" >&2
  echo "This script only handles the MIG case; for a plain (non-MIG) GPU, use nvidia-smi directly." >&2
  exit 1
fi

echo
echo "=== GIs with a process on them (from the Processes table) ==="
occupied_gis=$(echo "$smi" | awk '/^\| Processes:/{f=1} f' | grep -E '^\|\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+' | awk '{print $3}' | sort -un)
if [ -n "$occupied_gis" ]; then
  echo "$occupied_gis"
else
  echo "(none -- every slice looks idle right now)"
fi

# GI numbering on this host has, every time it's been checked, started at 7 and run
# sequentially with the device order from `nvidia-smi -L` (device 0 = GI 7, device 1 =
# GI 8, ...). Re-derive the starting GI from the MIG-devices memory table each run
# instead of hardcoding 7, so a MIG reconfiguration doesn't silently produce a wrong
# answer.
first_gi=$(echo "$smi" | grep -E '^\|\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+\|' | head -1 | awk '{print $3}')
first_gi=${first_gi:-7}

echo
echo "=== suggestion ==="
# GI 7 (the first slice) is where every job with an empty CUDA_VISIBLE_DEVICES lands by
# default, so it's the highest-collision-risk slice even when it reads empty right now --
# someone else's un-pinned job will drop onto it without warning. So: prefer the
# HIGHEST-numbered empty slice (farthest from the default landing zone and from GI 8, the
# one most recently seen busy), and fall back to GI 7 only if it's the single empty slice
# left. Iterate descending; first empty wins; remember GI 7 separately as last resort.
free_uuid=""
free_gi=""
gi7_uuid=""
gi7_gi=""
for ((i = ${#uuids[@]} - 1; i >= 0; i--)); do
  gi=$((first_gi + i))
  if echo "$occupied_gis" | grep -qx "$gi"; then
    continue
  fi
  if [ "$gi" -eq "$first_gi" ]; then
    gi7_uuid="${uuids[$i]}"   # the default slice -- only used if nothing else is free
    gi7_gi="$gi"
    continue
  fi
  free_uuid="${uuids[$i]}"
  free_gi="$gi"
  break
done
if [ -z "$free_uuid" ] && [ -n "$gi7_uuid" ]; then
  echo "(only the default slice GI $gi7_gi is free -- nothing higher available, using it)"
  free_uuid="$gi7_uuid"
  free_gi="$gi7_gi"
fi

if [ -n "$free_uuid" ]; then
  echo "Empty slice: GI $free_gi -> $free_uuid"
  echo
  echo "  export CUDA_VISIBLE_DEVICES=$free_uuid"
  echo
  echo "After launching, confirm with: nvidia-smi | grep python  (exactly one process, on this slice)"
else
  echo "No empty slice found by this heuristic -- check the raw tables above by hand (OPERATIONS.md Playbook A)."
fi
