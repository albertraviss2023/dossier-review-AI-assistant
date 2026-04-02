#!/usr/bin/env python3
"""Create reproducible train/val/test splits for dossier JSONL records.

Stratification key: country + holistic_policy_decision
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create stratified splits for dossier dataset.")
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=Path("dossier-review-AI-assistant/synthetic_data/data/raw/v1_2026-04-03/dossiers.jsonl"),
        help="Input dossier JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dossier-review-AI-assistant/synthetic_data/data/splits/v1_2026-04-03"),
        help="Output directory",
    )
    parser.add_argument("--seed", type=int, default=20260403)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    return parser.parse_args()


def load_rows(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def strat_key(row: Dict) -> str:
    return f"{row['country']}|{row['labels']['holistic_policy_decision']}"


def split_bucket(bucket: List[Dict], train_ratio: float, val_ratio: float) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    n = len(bucket)
    n_train = int(round(n * train_ratio))
    n_val = int(round(n * val_ratio))
    if n_train + n_val > n:
        n_val = max(0, n - n_train)
    n_test = n - n_train - n_val

    if n >= 3:
        if n_train == 0:
            n_train, n_test = 1, max(0, n_test - 1)
        if n_val == 0:
            n_val, n_test = 1, max(0, n_test - 1)
        if n_test == 0:
            n_test = 1
            if n_train > 1:
                n_train -= 1
            elif n_val > 1:
                n_val -= 1
    train = bucket[:n_train]
    val = bucket[n_train : n_train + n_val]
    test = bucket[n_train + n_val :]
    return train, val, test


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_ids(path: Path, rows: List[Dict]) -> None:
    ids = [row["dossier_id"] for row in rows]
    path.write_text("\n".join(ids), encoding="utf-8")


def dist(rows: List[Dict]) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for row in rows:
        out[row["labels"]["holistic_policy_decision"]] += 1
    return dict(out)


def main() -> None:
    args = parse_args()
    total_ratio = args.train_ratio + args.val_ratio + args.test_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError("train/val/test ratios must sum to 1.0")

    rows = load_rows(args.input_jsonl)
    rng = random.Random(args.seed)

    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        buckets[strat_key(row)].append(row)
    for key in buckets:
        rng.shuffle(buckets[key])

    train_rows: List[Dict] = []
    val_rows: List[Dict] = []
    test_rows: List[Dict] = []

    for key in sorted(buckets.keys()):
        tr, va, te = split_bucket(buckets[key], args.train_ratio, args.val_ratio)
        train_rows.extend(tr)
        val_rows.extend(va)
        test_rows.extend(te)

    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    rng.shuffle(test_rows)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "train.jsonl", train_rows)
    write_jsonl(out_dir / "val.jsonl", val_rows)
    write_jsonl(out_dir / "test.jsonl", test_rows)
    write_ids(out_dir / "train_ids.txt", train_rows)
    write_ids(out_dir / "val_ids.txt", val_rows)
    write_ids(out_dir / "test_ids.txt", test_rows)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_jsonl": str(args.input_jsonl),
        "seed": args.seed,
        "ratios": {
            "train": args.train_ratio,
            "val": args.val_ratio,
            "test": args.test_ratio,
        },
        "counts": {
            "total": len(rows),
            "train": len(train_rows),
            "val": len(val_rows),
            "test": len(test_rows),
        },
        "label_distribution": {
            "train": dist(train_rows),
            "val": dist(val_rows),
            "test": dist(test_rows),
        },
        "files": {
            "train_jsonl": "train.jsonl",
            "val_jsonl": "val.jsonl",
            "test_jsonl": "test.jsonl",
            "train_ids": "train_ids.txt",
            "val_ids": "val_ids.txt",
            "test_ids": "test_ids.txt",
        },
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Created splits in {out_dir} (train={len(train_rows)}, val={len(val_rows)}, test={len(test_rows)})")


if __name__ == "__main__":
    main()

