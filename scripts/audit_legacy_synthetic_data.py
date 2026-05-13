from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


KNOWN_INNS = {
    "amoxicillin",
    "ampicillin",
    "ceftriaxone",
    "cefotaxime",
    "doxycycline",
    "azithromycin",
    "ciprofloxacin",
    "metformin",
    "amlodipine",
    "paracetamol",
    "cefiderocol",
}

CORE_SECTION_HINTS = {
    "m1_application_admin",
    "m1_manufacturer_gmp",
    "m1_product_information",
    "m2_quality_overall_summary",
    "m3_stability",
    "m3_api_quality",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _extract_inn_tokens(text: str) -> set[str]:
    lowered = text.lower()
    hits = set()
    for inn in KNOWN_INNS:
        if re.search(rf"\b{re.escape(inn)}\b", lowered):
            hits.add(inn)
    return hits


def audit_dataset(dossiers: list[dict[str, Any]]) -> dict[str, Any]:
    issue_counts = Counter()
    issues_by_dossier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    examples: dict[str, list[str]] = defaultdict(list)

    for dossier in dossiers:
        did = str(dossier.get("dossier_id", "unknown"))
        product = dossier.get("product", {}) or {}
        declared_inn = _norm(product.get("inn_name") or product.get("inn"))
        sections = dossier.get("sections", []) or []
        section_ids = {str(s.get("section_id", "")) for s in sections}
        section_text = "\n".join(str(s.get("text", "")) for s in sections)

        for required in CORE_SECTION_HINTS:
            if required not in section_ids:
                issue_counts["missing_core_section"] += 1
                msg = f"Missing core section: {required}"
                issues_by_dossier[did].append({"type": "missing_core_section", "detail": msg})
                if len(examples["missing_core_section"]) < 8:
                    examples["missing_core_section"].append(f"{did}: {required}")

        if not declared_inn:
            issue_counts["missing_declared_inn"] += 1
            issues_by_dossier[did].append({"type": "missing_declared_inn", "detail": "No declared INN in product metadata."})
            if len(examples["missing_declared_inn"]) < 8:
                examples["missing_declared_inn"].append(did)

        text_inns = _extract_inn_tokens(section_text)
        if declared_inn and text_inns:
            alien = {token for token in text_inns if token != declared_inn}
            if alien:
                issue_counts["cross_product_inn_leakage"] += 1
                detail = f"Declared INN '{declared_inn}' but sections contain other INNs: {sorted(alien)}"
                issues_by_dossier[did].append({"type": "cross_product_inn_leakage", "detail": detail})
                if len(examples["cross_product_inn_leakage"]) < 8:
                    examples["cross_product_inn_leakage"].append(f"{did}: {detail}")

        policy = dossier.get("policy_signals", {}) or {}
        aware = _norm(policy.get("aware_category", "not_applicable"))
        if aware in {"access", "watch", "reserve"}:
            for key in ("glass_resistance_trend", "similarity_to_existing_watch", "existing_watch_comparator"):
                value = _norm(policy.get(key, "not_applicable"))
                if value in {"", "unknown"}:
                    issue_counts["incomplete_amr_policy_signals"] += 1
                    detail = f"AMR dossier missing {key}"
                    issues_by_dossier[did].append({"type": "incomplete_amr_policy_signals", "detail": detail})
                    if len(examples["incomplete_amr_policy_signals"]) < 8:
                        examples["incomplete_amr_policy_signals"].append(f"{did}: {detail}")

        labels = dossier.get("labels", {}) or {}
        holistic = _norm(labels.get("holistic_policy_decision"))
        if holistic in {"fast_track", "standard_review", "deep_review", "reject_and_return"}:
            if "reference_materials" not in dossier:
                issue_counts["missing_reference_materials_block"] += 1
                detail = "No reference_materials block (generic baseline likely unavailable for patient-safety comparison)."
                issues_by_dossier[did].append({"type": "missing_reference_materials_block", "detail": detail})
                if len(examples["missing_reference_materials_block"]) < 8:
                    examples["missing_reference_materials_block"].append(f"{did}: {detail}")

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "num_dossiers": len(dossiers),
        "issue_counts": dict(issue_counts),
        "examples": dict(examples),
        "issues_by_dossier": issues_by_dossier,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Legacy Synthetic Data Integrity Audit",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Dossiers scanned: `{report['num_dossiers']}`",
        "",
        "## Issue Counts",
        "",
    ]
    for key, value in sorted(report["issue_counts"].items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Examples")
    lines.append("")
    for key, rows in report.get("examples", {}).items():
        lines.append(f"### {key}")
        for row in rows:
            lines.append(f"- {row}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit legacy synthetic dossier dataset integrity.")
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=Path("synthetic_data/data/raw/balanced_v1_2026-04-05/dossiers.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("synthetic_data/legacy_archive/latest_audit"),
    )
    args = parser.parse_args()
    rows = _read_jsonl(args.input_jsonl)
    report = audit_dataset(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "legacy_integrity_audit.json"
    md_path = args.output_dir / "legacy_integrity_audit.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, md_path)
    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")
    print(json.dumps(report["issue_counts"], indent=2))


if __name__ == "__main__":
    main()
