#!/usr/bin/env python
"""JSON-only probe of LIME-440K's claimed text/emotion decoupling (RP.md "Open premises").

Confirms or refutes, by direct read rather than by trusting the paper's prose: within each
grouping field, is the text genuinely identical while the emotion label varies? Only reads
text + label columns and drops any audio column before iterating, so it does not require
downloading the 52 GB audio payload -- run this on the login/transfer node, not on a GPU node.

The real schema (column names for the group/text/emotion fields, split names, and whether
Part A/Part B are separate configs or a row-level field) is not yet known -- the HF dataset
viewer is blocked from this sandbox (see ../README.md "Why this can't run in this sandbox").
First run with --dump-schema to see the real column names, then rerun with --group-field /
--text-field / --emotion-field (and --language-field / --language-value if Part A and Part B
share one split) set to whatever --dump-schema reports.

    python scripts/probe_lime_partB.py --dataset zhaoxiaoxian/LIME-440K_CogAudio-LLM --dump-schema
    python scripts/probe_lime_partB.py --dataset zhaoxiaoxian/LIME-440K_CogAudio-LLM \
        --group-field group_id --text-field text --emotion-field emotion
"""

import argparse
import json
from collections import defaultdict

from datasets import load_dataset

TEXT_FIELD_CANDIDATES = ["text", "transcript", "sentence", "content", "utterance"]
EMOTION_FIELD_CANDIDATES = ["emotion", "label", "emotion_label", "emo"]
GROUP_FIELD_CANDIDATES = ["group", "group_id", "text_id", "sentence_id", "cluster_id", "pair_id"]
AUDIO_FIELD_CANDIDATES = ["audio", "audio_path", "wav", "speech"]


def pick_field(columns, candidates, kind):
    for c in candidates:
        if c in columns:
            return c
    raise SystemExit(
        f"Could not auto-detect the {kind} field among columns {columns}. "
        f"Pass --{kind}-field explicitly (run with --dump-schema first to see a sample row)."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="zhaoxiaoxian/LIME-440K_CogAudio-LLM")
    parser.add_argument("--config", default=None, help="HF dataset config name, if Part A/B are separate configs")
    parser.add_argument("--split", default="train")
    parser.add_argument("--language-field", default=None, help="Column to filter on, if Part A/B share one split")
    parser.add_argument("--language-value", default="English")
    parser.add_argument("--group-field", default=None)
    parser.add_argument("--text-field", default=None)
    parser.add_argument("--emotion-field", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Cap rows scanned (omit to scan the full split)")
    parser.add_argument("--dump-schema", action="store_true", help="Print column names and one sample row, then exit")
    args = parser.parse_args()

    ds = load_dataset(args.dataset, name=args.config, split=args.split, streaming=True)
    sample = next(iter(ds.take(1)))
    columns = list(sample.keys())

    if args.dump_schema:
        printable = {k: v for k, v in sample.items() if k not in AUDIO_FIELD_CANDIDATES}
        print("columns:", columns)
        print("sample row (audio field(s) omitted):")
        print(json.dumps(printable, indent=2, default=str))
        return

    group_field = args.group_field or pick_field(columns, GROUP_FIELD_CANDIDATES, "group")
    text_field = args.text_field or pick_field(columns, TEXT_FIELD_CANDIDATES, "text")
    emotion_field = args.emotion_field or pick_field(columns, EMOTION_FIELD_CANDIDATES, "emotion")

    drop_cols = [c for c in AUDIO_FIELD_CANDIDATES if c in columns]
    if drop_cols:
        ds = ds.remove_columns(drop_cols)

    groups = defaultdict(list)
    n_scanned = 0
    n_filtered_out = 0
    for row in ds:
        if args.language_field and row.get(args.language_field) != args.language_value:
            n_filtered_out += 1
            continue
        groups[row[group_field]].append((row[text_field], row[emotion_field]))
        n_scanned += 1
        if args.limit and n_scanned >= args.limit:
            break

    if n_scanned == 0:
        raise SystemExit(
            f"0 rows matched (filtered out {n_filtered_out}). "
            f"--language-field {args.language_field!r} / --language-value {args.language_value!r} "
            "likely doesn't match this dataset's actual values -- rerun --dump-schema and check."
        )

    identical_text_multi_emotion = 0
    identical_text_single_emotion = 0
    non_identical_text = 0
    for members in groups.values():
        texts = {t for t, _ in members}
        emotions = {e for _, e in members}
        if len(texts) > 1:
            non_identical_text += 1
        elif len(emotions) > 1:
            identical_text_multi_emotion += 1
        else:
            identical_text_single_emotion += 1

    n_groups = len(groups)
    print(f"rows scanned: {n_scanned} (filtered out: {n_filtered_out})")
    print(f"groups found: {n_groups}")
    print(
        f"  identical text, >1 emotion (claimed decoupling holds): "
        f"{identical_text_multi_emotion} ({identical_text_multi_emotion / n_groups:.1%})"
    )
    print(f"  identical text, 1 emotion only: {identical_text_single_emotion}")
    print(f"  non-identical text within group (claim violated): {non_identical_text}")


if __name__ == "__main__":
    main()
