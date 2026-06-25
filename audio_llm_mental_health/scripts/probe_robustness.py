#!/usr/bin/env python
"""Fold-noise robustness check for the Accessibility-Delta Probe -- CPU-only, no GPU/model.

probe_accessibility.py reports ONE cross-validated AUC per (dump, location, layer) at the
hardcoded StratifiedKFold(random_state=42). A single such number carries real fold-to-fold
noise: with ~200 rows and 5 classes, which rows land in which fold shifts the macro-OVR AUC by
a few points on its own. This script holds the .npz fixed (SAME 200 rows -- so it isolates
fold noise, NOT sample noise; for sample noise re-run extract_hidden_states.py with a new
--seed) and refits the identical Standardize -> PCA(<=50) -> multinomial-LR pipeline across
many kfold seeds, reporting mean / std / min / max.

Use it to decide whether a gap BETWEEN dumps is real. Concretely, RP.md's MELD-only ladder
claims meld_lora_grounded's projector AUC (~0.644) sits above the baseline/textmask1 cluster
(~0.59-0.61). If that 0.05 gap is smaller than each dump's own fold-noise band here, the gap
is a fold-split artifact and the "richest mid-stack signal" reading must be downgraded; if the
bands are tight (~0.01) and don't overlap, fold noise is ruled out and only sample noise (the
GPU re-extract) remains to test.

    python scripts/probe_robustness.py \
        --in outputs/probe_meld_baseline.npz:3 \
        --in outputs/probe_meld_grounded.npz:7 \
        --in outputs/probe_meld_textmask1.npz:9 \
        --in outputs/probe_meld_textmask1_acoustic.npz:9 \
        --location projector --n-seeds 20

Pass --location llm_layer:21 to robustness-check a specific decoder layer (e.g. grounded's
mid-stack peak) instead of the projector. Default location is projector -- the one stage
RP.md line 29 confirms is untrained across all adapters, hence the clean cross-dump control.
"""

import argparse

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

N_FOLDS = 5
PCA_COMPONENTS = 50


def probe_auc(X: np.ndarray, y_enc: np.ndarray, seed: int) -> float:
    """Identical pipeline to probe_accessibility.probe_auc, but with the kfold seed exposed."""
    n_splits = min(N_FOLDS, int(np.bincount(y_enc).min()))
    if n_splits < 2:
        return float("nan")
    pipe = make_pipeline(
        StandardScaler(),
        PCA(n_components=min(PCA_COMPONENTS, X.shape[0] - 1, X.shape[1])),
        LogisticRegression(max_iter=2000, C=1.0),
    )
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    try:
        proba = cross_val_predict(pipe, X, y_enc, cv=skf, method="predict_proba")
        return roc_auc_score(y_enc, proba, multi_class="ovr", average="macro")
    except ValueError:
        return float("nan")


def resolve_matrix(data, location: str) -> np.ndarray:
    """'projector' / 'audio_tower' -> that array; 'llm_layer:21' -> llm_layers[:, 21, :]."""
    if location.startswith("llm_layer:"):
        idx = int(location.split(":", 1)[1])
        return data["llm_layers"][:, idx, :]
    return data[location]


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
    parser.add_argument("--in", dest="ins", action="append", required=True,
                        help="extract_hidden_states.py .npz dump, optionally ':<tracking>'. Repeatable.")
    parser.add_argument("--location", default="projector",
                        help="'projector' (default), 'audio_tower', or 'llm_layer:<idx>'.")
    parser.add_argument("--n-seeds", type=int, default=20, help="Number of kfold seeds (default 20).")
    args = parser.parse_args()

    print(f"Fold-noise robustness at location='{args.location}', {args.n_seeds} kfold seeds")
    print("(SAME rows per dump -- isolates fold noise, not sample noise)\n")
    print(f"{'dump':<42} {'track':>5} {'mean':>7} {'std':>6} {'min':>7} {'max':>7} {'range':>6}")

    rows = []
    for spec in args.ins:
        path, tracking = parse_spec(spec)
        data = np.load(path, allow_pickle=True)
        y = LabelEncoder().fit_transform(data["labels"])
        X = resolve_matrix(data, args.location)
        aucs = np.array([probe_auc(X, y, seed) for seed in range(args.n_seeds)])
        aucs = aucs[~np.isnan(aucs)]
        name = path.rsplit("/", 1)[-1]
        tag = f"{tracking:g}" if tracking is not None else "-"
        print(f"{name:<42} {tag:>5} {aucs.mean():>7.4f} {aucs.std():>6.4f} "
              f"{aucs.min():>7.4f} {aucs.max():>7.4f} {aucs.max() - aucs.min():>6.4f}")
        rows.append((name, tracking, aucs))

    print("\nRead it:")
    print("  * If a between-dump gap you care about is SMALLER than the per-dump max-min")
    print("    range here, that gap is within fold noise -- don't read it as a real")
    print("    difference. If the per-dump bands are tight (~0.01) and don't overlap the")
    print("    neighbour's band, fold noise is ruled out and only sample noise remains")
    print("    (re-run extract_hidden_states.py with a fresh --seed to test that).")


if __name__ == "__main__":
    main()
