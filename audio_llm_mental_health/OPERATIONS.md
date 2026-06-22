# OPERATIONS — debugging & runbook for the shared-MIG H100

A symptom→diagnosis→fix playbook for running this project on the cluster, written so a past
mistake is never debugged twice. Read the "Environment realities" section once; after that, jump
to the triage table and the per-symptom playbooks. The standing launch checklist at the bottom is
the thing to actually follow every time you start a run.

---

## Environment realities (the constraints that cause every failure below)

- **Shared, multi-tenant GPU host.** Other users run their own jobs on the same physical card
  (e.g. user `rfu` running AMBER MD, `pmemd.cuda`). You will see their processes in `nvidia-smi`.
  **Never kill a process you do not own** — always check the `user` column first.
- **The card is MIG-partitioned**: one `H100 80GB HBM3` split into seven `1g.10gb` instances
  (GI 7–13), each ~9.75 GiB. You get *one slice's* worth of memory and ~1/7 of the compute.
- **Everyone defaults to GI 7.** With `CUDA_VISIBLE_DEVICES` empty, a job lands on GI 7, so you
  collide with whoever else defaulted there. GI 8–13 are usually empty. Fix = pin an empty slice
  (see playbook A).
- **The model nearly fills a whole slice.** Qwen2-Audio-7B 4-bit QLoRA training occupies
  ~9.3–9.7 GiB of the 9.75 GiB slice. There is essentially **no room for a co-tenant** — sharing a
  slice with any other GPU process means OOM. You need a slice to yourself.
- **`$HOME` (`/`) is a small 58 GB partition** and fills easily. `/data` is 3+ TB. HF cache is
  already redirected to `/data` via `HF_HOME`. Training `outputs/` still lives under `$HOME`, and
  checkpoints (238 MB each, 9–14 per run) are what fill it.
- **~20 s per training step** on the slice (gradient checkpointing + 4-bit dequant + 1/7 compute).
  The first `metrics.jsonl` line only appears at step 10 (`logging_steps=10`), i.e. ~3 minutes in.
  "Nothing printed yet" right after launch is normal, not a hang.
- **`CUDA_VISIBLE_DEVICES` is per-shell.** It does not survive a reconnect or a new window. Re-export
  it every time, or you silently fall back to GI 7.

---

## Triage table

| Symptom (what you see) | Almost certainly | Go to |
|---|---|---|
| `torch.OutOfMemoryError: CUDA out of memory` | a co-tenant on your MIG slice (or you launched twice) | Playbook A |
| `No space left on device (os error 28)` (often inside `save_pretrained`/safetensors) | `$HOME` disk full from old checkpoints | Playbook B |
| `client_loop: send disconnect` / job vanished after SSH drop | ran in bare SSH, not tmux | Playbook C |
| "is it still running / did it finish?" | trust the filesystem, not scrollback | Playbook D |
| unknown PID holding GPU memory | identify before touching | Playbook E |
| crash mid-run, want to continue | resume — but validate the checkpoint first | Playbook F |

---

## Playbook A — CUDA OOM on the MIG slice

OOM here is almost never "the model is too big" (it has fit before) — it's **someone (or something)
sharing your slice**. The error line names the rival: `Process <pid> has <N> MiB memory in use`.

1. See who is on which slice, and who owns the rival PID:
   ```bash
   nvidia-smi                                   # per-MIG memory + the Processes table at the bottom
   ps -p <rival_pid> -o pid,ppid,user,etimes,cmd # CHECK THE user COLUMN
   ```
2. **If the rival is not yours** (e.g. `user=rfu`, `cmd=pmemd.cuda`): do **not** kill it. Move
   yourself to an empty slice instead:
   ```bash
   nvidia-smi -L                                # list MIG UUIDs; GI 7 is the first/usually-busy one
   export CUDA_VISIBLE_DEVICES=MIG-<uuid-of-an-empty-slice>
   python scripts/train_lora.py --config <config>
   nvidia-smi | grep python                     # CONFIRM you landed on a previously-empty slice
   ```
   (As of last check, GI 8 = `MIG-eae605da-1627-5245-a3ac-77f400bffcd2`. UUIDs can change if MIG is
   reconfigured — always re-list with `nvidia-smi -L` if a pin fails with "invalid device".)
3. **If the rival is your own stale process** (a killed-but-not-reaped eval/train): then and only
   then, `kill -9 <pid>` it, confirm memory frees with `nvidia-smi`, and relaunch.
4. **If every slice is occupied / you get a permission error opening another slice**: your account
   may be bound to GI 7. Wait for the co-tenant to finish or ask the admin. Don't fight over a slice.

> Cause of a *self-inflicted* OOM: launching `train_lora.py` a second time because the first looked
> idle. One run already fills the slice; two collide. Confirm with `nvidia-smi | grep python` (one
> python = fine) **before** relaunching anything.

## Playbook B — disk full (`No space left on device`)

The traceback points at `save_pretrained` / `safetensors` because the crash happens when writing a
checkpoint. The loss right before it is irrelevant — training was healthy; the disk filled.

1. Confirm and locate the hogs:
   ```bash
   df -h ~
   du -sh outputs/* 2>/dev/null | sort -h
   du -sh outputs/*/checkpoint-* 2>/dev/null | sort -h | tail
   du -sh ~/.cache/huggingface 2>/dev/null      # should be ~empty; HF_HOME points to /data
   ```
2. Safe cleanup — **self-protecting**: only delete intermediate checkpoints of runs that already
   have a `final/` (the completed-run adapter). Runs lacking a `final/` keep their checkpoints.
   ```bash
   rm -rf outputs/*_smoke                        # smoke tests are throwaway
   for d in outputs/*/; do
     if [ -d "${d}final" ]; then rm -rf "${d}"checkpoint-*; fi
   done
   df -h ~
   ```
   **Never delete** any `final/` (RP.md numbers depend on `meld_lora`, `meld_lora_4bit`,
   `meld_lora_grounded`, `esd_lora_plain` finals) or the checkpoints of an incomplete run.
3. Durable fix (do when not mid-crisis): point `output_dir` in the config to
   `/data/user_dirs/$USER/outputs/...`, or symlink `outputs` → `/data`. `$HOME` is 58 GB; `/data`
   is TBs. This recurs until outputs leave `$HOME`.

## Playbook C — SSH drop killed the job

A bare-SSH foreground process dies the instant the connection drops. `eval_accuracy.py` has **no
resume** without `--out`, so a killed eval restarts from scratch. Training can resume (Playbook F),
but only from the last `save_steps` checkpoint.

**Always run long jobs in tmux:**
```bash
tmux new -s <name>          # e.g. tm1 (digit one, not letter L — name typos cost time)
# ... launch the job, wait until it's visibly progressing ...
# detach:  Ctrl+B  then  D
tmux attach -t <name>       # reattach later
tmux ls                     # list sessions
```
Remember: `CUDA_VISIBLE_DEVICES` does not survive into a fresh tmux window — re-export before
launching inside it.

## Playbook D — "is it running / did it finish?" (filesystem > scrollback)

Scrollback lies (stale buffers, detached panes). The filesystem doesn't.

- **Finished?** `ls outputs/<run>/final/` — the `final/` adapter is written **only after all epochs
  complete**. Its presence = clean completion. Its absence = not done (or crashed).
- **Progressing?** `tail -3 outputs/<run>/metrics.jsonl`. **Append-only**: lines from a previous
  crashed run persist, so check the **timestamp** (is it recent?) and the **step** (a restarted run
  counts from a low step again, appended after the old high-step lines). Stale step-120 lines from
  yesterday are not progress.
- **Alive?** `nvidia-smi | grep python` (a python PID holding ~9 GiB on your slice) and/or
  `ps -o etimes= -p <pid>`. Growing GPU memory = active compute.
- Don't conclude "stuck" in the first ~3 minutes: first metrics line is at step 10 ≈ 3 min.

## Playbook E — unknown process holding GPU/identify before acting

```bash
ps -p <pid> -o pid,ppid,user,etimes,cmd     # user column decides everything
tr '\0' ' ' < /proc/<pid>/cmdline; echo      # full command line
pwdx <pid>                                   # working directory
```
If `user` is not you → leave it. If the commands report "No such process" → it already exited;
the concern is moot. Only act on processes you own.

## Playbook F — resume an interrupted training run

```bash
ls -la outputs/<run>/checkpoint-<N>/          # VALIDATE first
```
A valid checkpoint contains `adapter_model.safetensors` **and** `training_state.pt` at sane sizes.
An **empty** dir (only `.`/`..`, `total 16`) is a half-written shell from a crash *during* the save
— it cannot be resumed from. Then:
- valid checkpoint → `python scripts/train_lora.py --config <config> --resume-from outputs/<run>/checkpoint-<N>`
- crashed before the first `save_steps` (200) → no checkpoint exists → restart from scratch (you
  only lost <200 steps).

---

## Standing launch checklist (follow every time)

**Before a training run:**
1. `df -h ~` → need ≥ 3 GB free (a run writes ~2.2 GB of checkpoints). If not, Playbook B.
2. `nvidia-smi` → find an empty MIG slice (GI 8–13, ~12 MiB used).
3. `nvidia-smi -L` → get that slice's UUID.
4. `tmux new -s <name>`.
5. `export CUDA_VISIBLE_DEVICES=MIG-<empty-slice-uuid>` (inside the tmux window).
6. `python scripts/train_lora.py --config <config>`.
7. `nvidia-smi | grep python` → confirm exactly **one** python, on the slice you pinned, not shared.
8. Wait ~3 min, `tail -3 outputs/<run>/metrics.jsonl` → fresh timestamp + climbing step + falling loss.
9. Detach: `Ctrl+B` then `D`. **Do not relaunch** — to check later, attach or `tail`, never re-run.

**Before a multi-row eval** (`eval_accuracy.py` / `audio_ablation.py`):
- Same slice/tmux discipline (evals also need a free slice and die on SSH drop).
- For a `text_mask_prob=1.0` (audio-only-trained) adapter, evaluate with `--audio-only`, **not**
  `--hide-transcript` (the latter is a train/test mismatch for it). See RP.md "Core Finding".
- `eval_accuracy.py` has no resume — pass `--out <file>` if you want a per-row dump to survive.
