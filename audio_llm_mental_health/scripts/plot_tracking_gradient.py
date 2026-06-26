#!/usr/bin/env python
"""Summary figure for the decoupling gradient -- no training, no data files, no GPU.

Every number here is a logged result transcribed from RP.md (Core Finding); the script
just plots them, so it reproduces anywhere matplotlib is installed. Two panels:

  A. Donor-swap TRACKING (/15) across the decoupling gradient -- the one behavioural
     ruler measured identically (same fixed 15-row donor-swap set) in every condition,
     so it is the apples-to-apples axis. Chance for a 7-way match is 1/7 -> ~2.14/15.

  B. Linear-probe AUC at three stages (audio_tower / multi_modal_projector / final LLM
     layer) across the four-corpus gradient, plotted against that corpus's tracking. The
     three stages rise together and audio_tower (pre-LLM) already carries most of the
     spread -- the re-arbitration signature (RP.md lines 27-31).

    python scripts/plot_tracking_gradient.py --out tracking_gradient.png
"""

import argparse

import matplotlib.pyplot as plt

# --- Panel A: donor-swap tracking, ordered by decoupling strength (RP.md lines 11-39) ---
COND_LABELS = ["MELD\nbaseline", "MELD\ngrounded\n(tm0.3)", "MELD\ntm1.0",
               "MELD tm1.0\n+acoustic", "LIME\nPart B", "ESD\nplain"]
TRACKING = [3, 7, 9, 9, 13, 15]            # /15, donor-swap matches
CHANCE = 15 / 7                            # 7-way match null ~ 2.14/15

# --- Panel B: probe AUC by stage across the 4-point corpus gradient (RP.md lines 27, 31) ---
PROBE_TRACKING = [3, 9, 13, 15]            # meld_4bit, meld_tm1.0, lime_partB, esd_plain
AUDIO_TOWER = [0.6035, 0.6167, 0.9211, 0.9958]
PROJECTOR = [0.5844, 0.6150, 0.9159, 0.9975]
FINAL_LAYER = [0.6439, 0.6807, 0.9226, 0.9841]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tracking_gradient.png")
    args = ap.parse_args()

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(13, 5))

    # Panel A -- tracking gradient
    x = range(len(COND_LABELS))
    colors = ["#b0413e" if t <= 3 else "#d98c3f" if t < 13 else "#2e7d4f" for t in TRACKING]
    axA.bar(x, TRACKING, color=colors)
    axA.axhline(CHANCE, ls="--", color="gray", lw=1)
    axA.text(len(COND_LABELS) - 0.5, CHANCE + 0.25, f"chance ~{CHANCE:.1f}/15",
             ha="right", va="bottom", color="gray", fontsize=9)
    for xi, t in zip(x, TRACKING):
        axA.text(xi, t + 0.2, f"{t}/15", ha="center", va="bottom", fontsize=10, fontweight="bold")
    axA.set_xticks(list(x))
    axA.set_xticklabels(COND_LABELS, fontsize=8)
    axA.set_ylabel("donor-swap tracking (/15)")
    axA.set_ylim(0, 16)
    axA.set_title("A. Audio grounding rises with decoupling strength", fontsize=11)

    # Panel B -- probe AUC by stage vs tracking
    axB.plot(PROBE_TRACKING, AUDIO_TOWER, "o-", label="audio_tower (pre-LLM)")
    axB.plot(PROBE_TRACKING, PROJECTOR, "s--", label="projector (untrained)")
    axB.plot(PROBE_TRACKING, FINAL_LAYER, "^-", label="final LLM layer")
    axB.set_xlabel("donor-swap tracking (/15)")
    axB.set_ylabel("linear-probe AUC")
    axB.set_ylim(0.55, 1.0)
    axB.set_title("B. Probe AUC: spread is already present pre-LLM\n(re-arbitration signature)",
                  fontsize=11)
    axB.legend(fontsize=9, loc="lower right")
    axB.grid(True, alpha=0.3)

    fig.suptitle("Decoupling the transcript shortcut forces audio grounding "
                 "(MELD -> LIME -> ESD)", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
