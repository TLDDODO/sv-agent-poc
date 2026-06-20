#!/usr/bin/env python
"""JSON-only probe of LIME-440K's claimed text/emotion decoupling (RP.md "Open premises").

Confirms or refutes, by direct read rather than by trusting the paper's prose: within each
group, is the text genuinely identical while the emotion label varies? Only reads the JSON
annotation files (text/emotion/group), never the audio .tar.gz archives, so this is cheap to
run from the login/transfer node.

Real repo layout, confirmed by a direct `HfApi.list_repo_files` + `json.load()` read (see
RP.md "Open premises") -- annotations live under two language-coded prefixes, not as a single
HF `datasets` split with a language column:

    PartA_json_CN/*.json   Chinese, Part A (223,884 utterances)
    PartB_json_EN/*.json   English, Part B (96,000 utterances)  <- the one RP.md trains/evals on

Each *.json file is a single dict keyed by utterance id (e.g. "4_5_surprise"), not JSON-Lines,
so `datasets.load_dataset(..., streaming=True)` cannot read it directly -- it mis-detects the
file as line-delimited JSON and throws a pyarrow parse error ("Column() changed from object to
string" / "Expected object or value"). This script downloads each matching file with
`hf_hub_download` and parses it as one JSON object instead.

Confirmed sample record (PartA_json_CN/10.json):
    {"10_1_surprise": {"text": "...", "emotion": "SURPRISE", "scenario": "...",
                        "group": "10_g_0", "wav_path": "/10/medium/10_1_surprise.wav"}}
Part B's schema is the same fields per the dataset card; only the language of "text" differs.

Note: within a group, "identical text" has so far held for the wording but not always for
punctuation (e.g. "...订好了？！" vs "...订好了......" vs "...订好了！" across three emotions in
the same group) -- this script does an exact-string compare, deliberately not normalizing
punctuation away, so that effect shows up in the non_identical_text count below rather than
being hidden.

    python scripts/probe_lime_partB.py --dump-schema
    python scripts/probe_lime_partB.py --prefix PartB_json_EN/
"""

import argparse
import json
from collections import defaultdict

from huggingface_hub import HfApi, hf_hub_download

DEFAULT_DATASET = "zhaoxiaoxian/LIME-440K_CogAudio-LLM"
DEFAULT_PREFIX = "PartB_json_EN/"  # RP.md's Data-level intervention trains/evals on Part B only.


def list_json_files(api: HfApi, dataset: str, prefix: str) -> list[str]:
    files = api.list_repo_files(dataset, repo_type="dataset")
    matches = sorted(f for f in files if f.startswith(prefix) and f.endswith(".json"))
    if not matches:
        raise SystemExit(
            f"No .json files under prefix {prefix!r} in {dataset}. "
            f"Other top-level prefixes found: {sorted({f.split('/')[0] for f in files if '/' in f})}"
        )
    return matches


def iter_records(dataset: str, json_files: list[str], limit: int | None):
    n = 0
    for rel_path in json_files:
        local_path = hf_hub_download(dataset, rel_path, repo_type="dataset")
        with open(local_path, encoding="utf-8") as f:
            data = json.load(f)
        for utt_id, record in data.items():
            yield rel_path, utt_id, record
            n += 1
            if limit and n >= limit:
                return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Repo path prefix to scan, e.g. PartB_json_EN/")
    parser.add_argument("--text-field", default="text")
    parser.add_argument("--emotion-field", default="emotion")
    parser.add_argument("--group-field", default="group")
    parser.add_argument("--limit", type=int, default=None, help="Cap records scanned (omit to scan every matching file)")
    parser.add_argument(
        "--dump-schema", action="store_true",
        help="Print one file's record count, keys, and a sample record, then exit",
    )
    args = parser.parse_args()

    api = HfApi()
    json_files = list_json_files(api, args.dataset, args.prefix)
    print(f"{len(json_files)} json files under prefix {args.prefix!r} (first 10): {json_files[:10]}")

    if args.dump_schema:
        local_path = hf_hub_download(args.dataset, json_files[0], repo_type="dataset")
        with open(local_path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n{json_files[0]}: {len(data)} records")
        print(f"keys across first 5 records: {[set(v.keys()) for v in list(data.values())[:5]]}")
        sample_id, sample_record = next(iter(data.items()))
        print(f"sample record ({sample_id!r}):")
        print(json.dumps(sample_record, indent=2, ensure_ascii=False))
        return

    groups = defaultdict(list)
    n_scanned = 0
    n_missing_field = 0
    for _rel_path, _utt_id, record in iter_records(args.dataset, json_files, args.limit):
        text = record.get(args.text_field)
        emotion = record.get(args.emotion_field)
        group = record.get(args.group_field)
        if text is None or emotion is None or group is None:
            n_missing_field += 1
            continue
        groups[group].append((text, emotion))
        n_scanned += 1

    if n_scanned == 0:
        raise SystemExit(
            f"0 usable records (missing-field skips: {n_missing_field}). "
            f"Check --*-field names with --dump-schema."
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
    print(f"\nrecords scanned: {n_scanned} (skipped for missing fields: {n_missing_field})")
    print(f"groups found: {n_groups}")
    print(
        f"  identical text, >1 emotion (claimed decoupling holds): "
        f"{identical_text_multi_emotion} ({identical_text_multi_emotion / n_groups:.1%})"
    )
    print(f"  identical text, 1 emotion only: {identical_text_single_emotion}")
    print(f"  non-identical text within group (claim violated, incl. punctuation-only diffs): {non_identical_text}")


if __name__ == "__main__":
    main()
