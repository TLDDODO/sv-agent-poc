#!/usr/bin/env python
"""CPU half of the Accessibility-Delta Probe: cross-validated linear probes from
extract_hidden_states.py's .npz dumps -- no GPU, no model, sklearn only.

For each --in dump (one per trained adapter, i.e. one point on RP.md's grounding gradient),
fits a linear probe at every location/layer cached by extract_hidden_states.py and reports
its cross-validated macro one-vs-rest ROC-AUC for predicting emotion. Standardize -> PCA(<=50
components) -> multinomial logistic regression, k-fold (k = min(5, smallest class count)):
PCA keeps a linear probe from memorizing a few hundred rows in a 1280-4096-d space, which would
read as "information available" when it's really "model has more parameters than data points".

Pass each dump's RP.md donor-swap tracking score after a colon (e.g. ':13' for 13/15) purely
so the printed summary lines up probe AUC against behavioral grounding without you having to
cross-reference RP.md by hand; it changes nothing about the fit.

    python scripts/probe_accessibility.py \
        --in outputs/probe_meld_baseline.npz:3 \
        --in outputs/probe_meld_textmask1.npz:9 \
        --in outputs/probe_lime_plain.npz:13 \
        --in outputs/probe_esd_plain.npz:15 \
        --out outputs/accessibility_probe_results.csv

Read the result (see the printed "Read it" block for the full version):
  * AUC flat across the gradient while tracking rises 3 -> 15: the information was already
    linearly readable in the COLLAPSED model -- training changed arbitration, not representation.
  * AUC rises in step with tracking: the representation itself changed -- re-representation.
  * Compare across llm layers too: a peak-then-decay shape specifically in low-tracking adapters
    (info present mid-stack, discarded by the final layer) is the layer-local signature of
    Billa's (arXiv 2602.23136) "available but not accessible" claim -- tested here across this
    project's OWN trained gradient instead of on one fixed model, which is what neither Billa
    nor VoxParadox (arXiv 2605.27772, which probes+fixes via PCLM/DPO on fixed off-the-shelf
    models, never across a controlled training-intervention gradient) can do.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

N_FOLDS = 5
PCA_COMPONENTS = 50


def probe_auc(X: np.ndarray, y_enc: np.ndarray) -> float:
    """k-fold cross-validated macro OVR ROC-AUC. NaN means "too few rows of some class for
    even a 2-fold split", not "AUC is zero" -- treat it as missing, not as a result."""
    n_splits = min(N_FOLDS, int(np.bincount(y_enc).min()))
    if n_splits < 2:
        return float("nan")
    pipe = make_pipeline(
        StandardScaler(),
        PCA(n_components=min(PCA_COMPONENTS, X.shape[0] - 1, X.shape[1])),
        LogisticRegression(max_iter=2000, C=1.0),
    )
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    try:
        proba = cross_val_predict(pipe, X, y_enc, cv=skf, method="predict_proba")
        return roc_auc_score(y_enc, proba, multi_class="ovr", average="macro")
    except ValueError:
        return float("nan")


def parse_spec(spec: str) -> tuple[str, float | None]:
    """'path.npz' or 'path.npz:13' -> (path, tracking_score_or_None)."""
    if ":" in spec:
        path, _, tail = spec.rpartition(":")
        try:
            return path, float(tail)
        except ValueError:
            pass
    return spec, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in", dest="ins", action="append", required=True,
        help="extract_hidden_states.py .npz dump, optionally suffixed ':<tracking>/15' "
        "(e.g. outputs/probe_lime_plain.npz:13). Repeatable, one per adapter.",
    )
    parser.add_argument("--out", default=None, help="Optional CSV of dump/location/layer -> AUC.")
    args = parser.parse_args()

    rows_out = []
    for spec in args.ins:
        path, tracking = parse_spec(spec)
        data = np.load(path, allow_pickle=True)
        labels = data["labels"]
        y = LabelEncoder().fit_transform(labels)
        n_classes = len(np.unique(y))
        tag = f", tracking={tracking:g}/15" if tracking is not None else ""
        print(f"\n=== {path} ({len(labels)} rows, {n_classes} classes{tag}) ===")

        auc_audio_tower = probe_auc(data["audio_tower"], y)
        auc_projector = probe_auc(data["projector"], y)
        print(f"  audio_tower (pre-LLM, semantic-tower output):  AUC={auc_audio_tower:.3f}")
        print(f"  projector   (post-projection, pre-LLM):        AUC={auc_projector:.3f}")
        rows_out.append([path, tracking, "audio_tower", -1, auc_audio_tower])
        rows_out.append([path, tracking, "projector", -1, auc_projector])

        llm_layers = data["llm_layers"]  # (N, n_layers+1, D)
        n_layers = llm_layers.shape[1]
        print(f"  llm layers (0=embedding .. {n_layers - 1}=final), pooled over audio-token positions:")
        for layer_idx in range(n_layers):
            auc = probe_auc(llm_layers[:, layer_idx, :], y)
            print(f"    layer {layer_idx:>2}: AUC={auc:.3f}")
            rows_out.append([path, tracking, "llm_layer", layer_idx, auc])

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["dump", "tracking_score", "location", "layer_idx", "auc"])
            writer.writerows(rows_out)
        print(f"\nWrote {len(rows_out)} (location, layer) AUC rows to {out_path}")

    print("\nRead it:")
    print("  * AUC roughly FLAT across the gradient (baseline included) while tracking itself")
    print("    rises 3 -> 15: emotion was already linearly readable pre-training -- the trained")
    print("    intervention changed what the LLM DOES with the audio channel (re-arbitration),")
    print("    not what's encoded in it.")
    print("  * AUC clearly RISING in step with tracking (e.g. ~0.35 at baseline -> ~0.85 at the")
    print("    grounded end): the representation itself changed (re-representation).")
    print("  * Compare the SHAPE across llm layers, not just the final one: a peak-then-decay")
    print("    specific to low-tracking adapters (info present mid-stack, gone by the final")
    print("    layer) is the layer-local version of 'available but not accessible' -- now shown")
    print("    across a trained gradient instead of one fixed model.")


if __name__ == "__main__":
    main()
