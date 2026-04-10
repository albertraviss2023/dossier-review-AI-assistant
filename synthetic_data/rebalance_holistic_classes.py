from __future__ import annotations

import argparse
import copy
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebalance holistic policy classes by targeted synthetic augmentation."
    )
    parser.add_argument(
        "--input-jsonl",
        default="synthetic_data/data/raw/v1_2026-04-03/dossiers.jsonl",
        help="Input dossier JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        default="synthetic_data/data/raw/balanced_v1_2026-04-05",
        help="Output directory for balanced dataset",
    )
    parser.add_argument(
        "--min-class-count",
        type=int,
        default=180,
        help="Minimum samples per holistic class after augmentation",
    )
    parser.add_argument("--seed", type=int, default=20260405, help="Random seed")
    parser.add_argument(
        "--copy-pdfs",
        action="store_true",
        help="Copy source PDFs to output dossiers_pdf directory (off by default for speed/storage)",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True))
            f.write("\n")


def holistic_label(dossier: dict[str, Any]) -> str:
    return str(dossier.get("labels", {}).get("holistic_policy_decision", "standard_review"))


def mutate_section_text(section: dict[str, Any], rng: random.Random) -> None:
    note = " Supplemental clarification added for balanced class augmentation."
    text = str(section.get("text", ""))
    constraints = section.get("constraints", {})
    min_chars = int(constraints.get("min_chars", 0))
    max_chars = int(constraints.get("max_chars", 1000000))

    if len(text) + len(note) <= max_chars:
        text = text + note
    else:
        text = text[:max(min_chars, max_chars - len(note))] + note
        text = text[:max_chars]

    section["text"] = text
    section.setdefault("metrics", {})["char_count"] = len(text)

    if len(text) < min_chars:
        length_status = "too_short"
    elif len(text) > max_chars:
        length_status = "too_long"
    else:
        length_status = "length_ok"
    section.setdefault("labels", {})["length_status"] = length_status


def write_holistic_csv(path: Path, dossiers: list[dict[str, Any]]) -> None:
    fieldnames = [
        "dossier_id",
        "country",
        "holistic_policy_decision",
        "risk_score",
        "compliant_submission",
        "inn_infringement",
        "gmp_inspection_status",
        "gmp_inspection_recent",
        "gmp_certificate_validity",
        "clinical_data_available",
        "pivotal_trial_outcome",
        "aware_category",
        "amr_unmet_need",
        "targets_mdr_pathogen",
        "glass_resistance_trend",
        "similarity_to_existing_watch",
        "existing_watch_comparator",
        "defect_modes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for dossier in dossiers:
            labels = dossier.get("labels", {})
            signals = dossier.get("policy_signals", {})
            provenance = dossier.get("provenance", {})
            defect_modes = provenance.get("defect_modes", [])
            writer.writerow(
                {
                    "dossier_id": dossier.get("dossier_id"),
                    "country": dossier.get("country"),
                    "holistic_policy_decision": labels.get("holistic_policy_decision"),
                    "risk_score": labels.get("risk_score"),
                    "compliant_submission": labels.get("compliant_submission"),
                    "inn_infringement": signals.get("inn_infringement"),
                    "gmp_inspection_status": signals.get("gmp_inspection_status"),
                    "gmp_inspection_recent": signals.get("gmp_inspection_recent"),
                    "gmp_certificate_validity": signals.get("gmp_certificate_validity"),
                    "clinical_data_available": signals.get("clinical_data_available"),
                    "pivotal_trial_outcome": signals.get("pivotal_trial_outcome"),
                    "aware_category": signals.get("aware_category"),
                    "amr_unmet_need": signals.get("amr_unmet_need"),
                    "targets_mdr_pathogen": signals.get("targets_mdr_pathogen"),
                    "glass_resistance_trend": signals.get("glass_resistance_trend"),
                    "similarity_to_existing_watch": signals.get("similarity_to_existing_watch"),
                    "existing_watch_comparator": signals.get("existing_watch_comparator"),
                    "defect_modes": ",".join(defect_modes),
                }
            )


def write_section_csv(path: Path, dossiers: list[dict[str, Any]]) -> None:
    fieldnames = [
        "dossier_id",
        "country",
        "section_id",
        "module",
        "presence",
        "length_status",
        "correctness",
        "error_tags",
        "char_count",
        "min_chars",
        "max_chars",
        "critical",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for dossier in dossiers:
            for section in dossier.get("sections", []):
                labels = section.get("labels", {})
                metrics = section.get("metrics", {})
                constraints = section.get("constraints", {})
                writer.writerow(
                    {
                        "dossier_id": dossier.get("dossier_id"),
                        "country": dossier.get("country"),
                        "section_id": section.get("section_id"),
                        "module": section.get("module"),
                        "presence": labels.get("presence", "missing"),
                        "length_status": labels.get("length_status", "missing"),
                        "correctness": labels.get("correctness", "incorrect"),
                        "error_tags": ",".join(labels.get("error_tags", [])),
                        "char_count": metrics.get("char_count", 0),
                        "min_chars": constraints.get("min_chars", 0),
                        "max_chars": constraints.get("max_chars", 0),
                        "critical": section.get("critical", False),
                    }
                )


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    input_jsonl = Path(args.input_jsonl)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dossiers = read_jsonl(input_jsonl)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for dossier in dossiers:
        groups[holistic_label(dossier)].append(dossier)

    original_distribution = {k: len(v) for k, v in groups.items()}

    existing_ids = {str(d["dossier_id"]) for d in dossiers}
    augmented: list[dict[str, Any]] = []
    augmentation_counts: Counter[str] = Counter()

    for label, rows in groups.items():
        needed = max(0, args.min_class_count - len(rows))
        for idx in range(needed):
            base = copy.deepcopy(rng.choice(rows))
            source_id = str(base["dossier_id"])

            counter = idx + 1
            new_id = f"{source_id}-AUG-{counter:05d}"
            while new_id in existing_ids:
                counter += 1
                new_id = f"{source_id}-AUG-{counter:05d}"
            existing_ids.add(new_id)

            base["dossier_id"] = new_id
            try:
                dt = datetime.fromisoformat(str(base.get("submission_date")))
            except ValueError:
                dt = datetime(2026, 1, 1)
            base["submission_date"] = (dt + timedelta(days=rng.randint(1, 120))).date().isoformat()

            provenance = base.setdefault("provenance", {})
            provenance["augmented"] = True
            provenance["augmented_from"] = source_id
            provenance["augmentation_target_label"] = label
            provenance["augmentation_version"] = "rebalance_v1_2026-04-05"

            sections = base.get("sections", [])
            if sections:
                target_section = rng.choice(sections)
                mutate_section_text(target_section, rng)

            augmented.append(base)
            augmentation_counts[label] += 1

    balanced = dossiers + augmented

    write_jsonl(output_dir / "dossiers.jsonl", balanced)
    write_holistic_csv(output_dir / "holistic_labels.csv", balanced)
    write_section_csv(output_dir / "section_labels.csv", balanced)

    if args.copy_pdfs:
        source_pdf_dir = input_jsonl.parent / "dossiers_pdf"
        target_pdf_dir = output_dir / "dossiers_pdf"
        target_pdf_dir.mkdir(parents=True, exist_ok=True)
        if source_pdf_dir.exists():
            for pdf in source_pdf_dir.glob("*.pdf"):
                target = target_pdf_dir / pdf.name
                if not target.exists():
                    target.write_bytes(pdf.read_bytes())

    defect_distribution: Counter[str] = Counter()
    for dossier in balanced:
        for defect in dossier.get("provenance", {}).get("defect_modes", []):
            defect_distribution[defect] += 1

    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "input_jsonl": str(input_jsonl),
        "num_dossiers": len(balanced),
        "seed": args.seed,
        "min_class_count": args.min_class_count,
        "original_distribution": original_distribution,
        "holistic_distribution": dict(Counter(holistic_label(d) for d in balanced)),
        "augmentation_counts": dict(augmentation_counts),
        "defect_distribution": dict(defect_distribution),
        "files": {
            "dossiers_jsonl": "dossiers.jsonl",
            "section_labels_csv": "section_labels.csv",
            "holistic_labels_csv": "holistic_labels.csv",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest["holistic_distribution"], indent=2))
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
