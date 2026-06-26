# Cloud-GPU Runbook — reproducing the dual-encoder (objective-level) cell

Goal: produce the one missing result — the **dual-encoder + disentanglement** run on MELD
(`outputs/dual_meld`), its donor-swap **tracking** number, and slot it into RP.md's gradient
table next to the data-level cells (baseline 3/15, textmask1 9/15, LIME 13/15, ESD 15/15).

This runs on **any single GPU with ≥16 GB** (it's 4-bit QLoRA; designed for a 9.75 GB MIG
slice). A 24 GB card (RTX 4090 / A100-40GB) gives comfortable headroom. On a *full* GPU the
3-epoch run finishes in roughly **1–1.5 h**, versus ~7 h on the 1/7 MIG slice it was built for.

**Keep it 4-bit.** The other cells in the table were trained 4-bit; the config here already is.
Do NOT switch to bf16 "because the card is bigger" — that breaks apples-to-apples comparability.

---

## 0. Rent the box

- RunPod / Vast.ai / Lambda. Pick a **PyTorch** template (torch + CUDA preinstalled), **≥24 GB**
  GPU, **≥60 GB** disk (MELD.Raw is ~10 GB and extracts larger).
- You are root in these containers, so `apt-get` works. Network is on by default.
- Cost: ~$1.5–3/hr; the whole job is 1–2 h. Budget a few dollars.

## 1. Code

```bash
git clone <your repo url> sv-agent-poc
cd sv-agent-poc
git checkout claude/audio-llm-mental-health-setup-pjrkc0
cd audio_llm_mental_health
```

## 2. Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
# If the template already ships torch, skip the torch line. Otherwise match the box's CUDA
# (see `nvidia-smi` "CUDA Version"), e.g. cu121:
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
# Audio extraction needs ffmpeg:
apt-get update && apt-get install -y ffmpeg
# HF auth (to pull the base model + back up the result):
hf auth login        # paste a token with write scope
```

## 3. Data — MELD (public, no license gate)

```bash
# Download MELD.Raw.tar.gz from https://affective-meld.github.io/ (grab the current link off the
# site; the long-standing mirror below has worked but VERIFY it resolves before trusting it):
wget -O MELD.Raw.tar.gz https://web.eecs.umich.edu/~mihalcea/downloads/MELD.Raw.tar.gz
tar xzf MELD.Raw.tar.gz                 # -> MELD.Raw/
tar xzf MELD.Raw/train.tar.gz -C MELD.Raw/   # produces train_splits/ + train_sent_emo.csv
tar xzf MELD.Raw/dev.tar.gz   -C MELD.Raw/   # produces dev_splits_complete/

# Video clips -> per-utterance 16 kHz wav (needs ffmpeg):
python scripts/extract_meld_audio.py --video-dir MELD.Raw/train_splits         --out-dir MELD.Raw/train_audio
python scripts/extract_meld_audio.py --video-dir MELD.Raw/dev_splits_complete  --out-dir MELD.Raw/dev_audio

# Build the plain manifests dual_meld trains/evals on (NO acoustic priors needed for this cell):
python scripts/prepare_meld_manifest.py --csv MELD.Raw/train_sent_emo.csv \
    --audio-dir MELD.Raw/train_audio --out data/meld_train_manifest.jsonl
python scripts/prepare_meld_manifest.py --csv MELD.Raw/dev_sent_emo.csv \
    --audio-dir MELD.Raw/dev_audio   --out data/meld_dev_manifest.jsonl
```

`dev_sent_emo.csv` ships at the top of MELD.Raw; `train_sent_emo.csv` comes out of `train.tar.gz`.

## 4. Smoke-test the dual-encoder loop FIRST (a few minutes)

This is the gate that caught nothing on the dead box only because the box's checkout was broken —
on a clean clone it validates the whole mechanism before you commit an hour to the full run.

```bash
python scripts/train_dual_encoder.py --config configs/train_config_dual_smoke.yaml
```

PASS = three `step N loss ... (lm ... dis ...)` lines with finite numbers + a
`saved adapter + emotion projection` line, no traceback. If it OOMs, drop
`per_device_train_batch_size` to 1 in the smoke config.

## 5. Full run (λ=100, already set)

```bash
tmux new -s dual_meld \
  "python scripts/train_dual_encoder.py --config configs/train_config_dual_meld_4bit.yaml 2>&1 | tee outputs/dual_meld_train.log; echo EXIT=\$?; exec bash"
# detach: Ctrl-b then d.  reattach: tmux attach -t dual_meld
# watch loss: tail -f outputs/dual_meld/metrics.jsonl   (dis_loss should now be on the same
#   order as lm_loss and falling — at λ=1 it was ~0.0001, negligible; λ=100 is why we raised it)
```

## 6. Eval — the headline tracking number

dual_meld trains with the transcript PRESENT (`text_mask_prob=0.0`), so eval the **with-transcript**
ruler (do NOT pass `--audio-only`) to stay comparable to baseline/textmask1's with-transcript cell:

```bash
python scripts/eval_dual_encoder.py --adapter outputs/dual_meld/final \
    --manifest data/meld_dev_manifest.jsonl \
    --indices 228,51,563,501,457,285,209,178,864,65,61,191,447,476,1034 \
    --out outputs/ablation_dual_meld.jsonl
```

The printed `tracking: N/15` is the cell. Compare against baseline 3/15, textmask1 9/15,
LIME 13/15, ESD 15/15. That single number is the objective-level-vs-data-level comparison the
paper turns on.

## 7. Back up the result immediately (don't lose it to a reclaimed pod)

```bash
R=Avery11/audio-llm-mh-backup
hf upload "$R" outputs/dual_meld/final           adapters/dual_meld/final --repo-type=model
hf upload "$R" outputs/ablation_dual_meld.jsonl  results/ablation_dual_meld.jsonl --repo-type=model
```

Then write the tracking number into RP.md's gradient table and commit.

---

## Optional, same box, while you're paying for it

- **LoRA-placement attribution** (already trained on the dead box, adapters backed up to HF under
  `adapters/meld_tm1_{llm_only,audio_only,both}`): if you re-pull those adapters, run
  `scripts/audio_ablation.py --audio-only` with the fixed 15-row indices on each to see which
  tower's LoRA is responsible for using the audio.
- **ESD grounded** (`adapters/esd_lora_grounded`) eval, same ruler.
- Re-running these from the HF-backed adapters needs only the manifests + audio, no retraining.
