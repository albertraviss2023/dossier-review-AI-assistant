#!/usr/bin/env python3
"""Create a machine-adjudicated gold set from synthetic dossier records.

This script replaces manual labeling for the current phase by producing:
- Reviewer-style section labels (presence/length/correctness)
- Final human-like holistic decision labels
- Override metadata (model label vs adjudicated label)
- Evidence section references and reviewer notes

The output is intended for evaluation and release-gating, not legal decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

DECISIONS = ["fast_track", "standard_review", "deep_review", "reject_and_return"]
DECISION_SEVERITY = {
    "fast_track": 0,
    "standard_review": 1,
    "deep_review": 2,
    "reject_and_return": 3,
}
MAJOR_ERROR_TAGS = {
    "inn_infringement",
    "clinical_missing",
    "clinical_failed",
    "gmp_non_compliant",
    "gmp_certificate_expired",
    "missing_critical_section",
    "cross_section_inconsistency",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create machine-adjudicated gold set.")
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=Path("dossier-review-AI-assistant/synthetic_data/data/raw/v1_2026-04-03/dossiers.jsonl"),
        help="Input dossier JSONL path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dossier-review-AI-assistant/synthetic_data/data/gold/strict_v1_2026-04-03"),
        help="Output directory",
    )
    parser.add_argument("--sample-size", type=int, default=240, help="Target number of gold records")
    parser.add_argument("--seed", type=int, default=20260402)
    parser.add_argument(
        "--target-dist",
        type=str,
        default="fast_track:0.25,standard_review:0.25,deep_review:0.25,reject_and_return:0.25",
        help="Target class distribution for sampled gold set",
    )
    parser.add_argument(
        "--reviewer-id",
        type=str,
        default="senior_reviewer_sim_v1",
        help="Reviewer identifier to stamp in output metadata",
    )
    parser.add_argument(
        "--adjudication-profile",
        type=str,
        choices=["standard", "strict"],
        default="standard",
        help="Adjudication strictness profile",
    )
    return parser.parse_args()


def parse_target_dist(value: str) -> Dict[str, float]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    parsed: Dict[str, float] = {}
    for item in items:
        key, raw = item.split(":")
        key = key.strip()
        if key not in DECISIONS:
            raise ValueError(f"Invalid decision class in target-dist: {key}")
        parsed[key] = float(raw)
    total = sum(parsed.values())
    if total <= 0:
        raise ValueError("target-dist total must be > 0")
    return {k: v / total for k, v in parsed.items()}


def load_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def adjudicate_section(section: Dict) -> Dict:
    text = section.get("text", "")
    char_count = len(text)
    min_chars = section["constraints"]["min_chars"]
    max_chars = section["constraints"]["max_chars"]
    error_tags = list(section["labels"].get("error_tags", []))
    critical = bool(section.get("critical", False))

    if not text.strip():
        presence = "missing"
        length_status = "missing"
    elif char_count < min_chars:
        presence = "present"
        length_status = "too_short"
    elif char_count > max_chars:
        presence = "present"
        length_status = "too_long"
    else:
        presence = "present"
        length_status = "length_ok"

    if presence == "missing":
        correctness = "incorrect"
    elif any(tag in MAJOR_ERROR_TAGS for tag in error_tags):
        correctness = "incorrect"
    elif length_status in {"too_short", "too_long"}:
        correctness = "incorrect" if critical else "partial"
    elif error_tags:
        correctness = "partial"
    else:
        correctness = "correct"

    return {
        "presence": presence,
        "length_status": length_status,
        "correctness": correctness,
        "error_tags": error_tags,
        "char_count": char_count,
    }


def adjudicate_holistic(
    dossier: Dict, section_labels: Dict[str, Dict], profile: str
) -> Tuple[str, float, List[str], List[str]]:
    policy = dossier["policy_signals"]
    clinical = dossier.get("clinical_details", {})
    reasons: List[str] = []
    evidence_sections: List[str] = []

    incorrect_critical = 0
    incorrect_noncritical = 0
    partial_sections = 0
    missing_sections = 0
    aware_category = str(policy.get("aware_category", "not_applicable"))
    amr_unmet_need = str(policy.get("amr_unmet_need", "not_applicable"))
    targets_mdr_pathogen = bool(policy.get("targets_mdr_pathogen", False))
    glass_resistance_trend = str(policy.get("glass_resistance_trend", "not_applicable"))
    similarity_to_existing_watch = str(policy.get("similarity_to_existing_watch", "not_applicable"))
    existing_watch_comparator = str(policy.get("existing_watch_comparator", "not_applicable"))

    for sec in dossier["sections"]:
        sid = sec["section_id"]
        lbl = section_labels[sid]
        if sec["critical"] and lbl["correctness"] == "incorrect":
            incorrect_critical += 1
            evidence_sections.append(sid)
        if (not sec["critical"]) and lbl["correctness"] == "incorrect":
            incorrect_noncritical += 1
            evidence_sections.append(sid)
        if lbl["correctness"] == "partial":
            partial_sections += 1
            evidence_sections.append(sid)
        if lbl["presence"] == "missing":
            missing_sections += 1
            evidence_sections.append(sid)

    if policy["inn_infringement"]:
        reasons.append("INN naming conflict risk detected.")
        evidence_sections.append("m1_product_information")
    if policy["gmp_inspection_status"] == "non_compliant":
        reasons.append("Manufacturer GMP status is non-compliant.")
        evidence_sections.append("m1_manufacturer_gmp")
    if policy["gmp_certificate_validity"] == "expired":
        reasons.append("GMP certificate is expired.")
        evidence_sections.append("m1_manufacturer_gmp")
    if not policy["gmp_inspection_recent"]:
        reasons.append("GMP inspection is not recent enough for policy window.")
        evidence_sections.append("m1_manufacturer_gmp")
    if not policy["clinical_data_available"]:
        reasons.append("Pivotal clinical data are missing.")
        evidence_sections.append("m5_pivotal_trial_reports")
    if policy["pivotal_trial_outcome"] == "endpoint_not_met":
        reasons.append("Pivotal trial failed to meet primary endpoint.")
        evidence_sections.append("m5_pivotal_trial_reports")
    if aware_category in {"access", "watch", "reserve"}:
        reasons.append(f"WHO AWaRe category is {aware_category}.")
        evidence_sections.append("m1_product_information")
        evidence_sections.append("m2_clinical_overview")

    high_risk = (
        policy["inn_infringement"]
        or policy["gmp_inspection_status"] == "non_compliant"
        or policy["gmp_certificate_validity"] == "expired"
        or policy["pivotal_trial_outcome"] == "endpoint_not_met"
    )
    moderate_risk = (not policy["clinical_data_available"]) or (not policy["gmp_inspection_recent"])
    reserve_fast_track = (
        aware_category == "reserve"
        and targets_mdr_pathogen
        and amr_unmet_need in {"high", "critical"}
    )
    watch_similarity_guard = (
        aware_category == "watch"
        and similarity_to_existing_watch == "high"
        and glass_resistance_trend == "rising"
    )
    pivotal_trial_count = int(clinical.get("pivotal_trial_count", 0))

    if reserve_fast_track:
        reasons.append(
            "Reserve antibiotic addresses an MDR unmet need and is eligible for accelerated review with restricted authorization."
        )
        evidence_sections.append("m5_pivotal_trial_reports")
    if watch_similarity_guard:
        reasons.append(
            f"High similarity to Watch comparator {existing_watch_comparator} plus rising GLASS resistance supports restricted authorization."
        )
        evidence_sections.append("m1_product_information")
        evidence_sections.append("m5_pivotal_trial_reports")

    if profile == "strict":
        if high_risk or incorrect_critical >= 1:
            decision, confidence = "reject_and_return", 0.97
        elif watch_similarity_guard or moderate_risk or missing_sections >= 1:
            decision, confidence = "deep_review", 0.88
        elif pivotal_trial_count < 3 and not reserve_fast_track:
            decision, confidence = "deep_review", 0.82
            reasons.append("Strict profile requires >= 3 pivotal studies for non-escalated review.")
            evidence_sections.append("m5_trial_listing")
        elif reserve_fast_track:
            decision, confidence = "fast_track", 0.94
        elif partial_sections >= 1 or incorrect_noncritical >= 1:
            decision, confidence = "standard_review", 0.76
        else:
            decision, confidence = "fast_track", 0.93
    else:
        if high_risk or incorrect_critical >= 2:
            decision, confidence = "reject_and_return", 0.95
        elif watch_similarity_guard or moderate_risk or incorrect_critical == 1 or missing_sections >= 1:
            decision, confidence = "deep_review", 0.83
        elif reserve_fast_track:
            decision, confidence = "fast_track", 0.92
        elif partial_sections >= 1 or incorrect_noncritical >= 1:
            decision, confidence = "standard_review", 0.73
        else:
            decision, confidence = "fast_track", 0.91

    if incorrect_critical > 0:
        reasons.append(f"{incorrect_critical} critical section(s) marked incorrect.")
    if partial_sections > 0:
        reasons.append(f"{partial_sections} section(s) marked partial.")
    if missing_sections > 0:
        reasons.append(f"{missing_sections} section(s) missing from submission.")
    if not reasons:
        reasons.append("Submission meets completeness and correctness checks.")

    evidence_sections = sorted(set(evidence_sections))
    return decision, confidence, reasons, evidence_sections


def build_override_reason(model_decision: str, human_decision: str) -> str:
    if model_decision == human_decision:
        return "none"
    if DECISION_SEVERITY[human_decision] > DECISION_SEVERITY[model_decision]:
        return "policy_guardrail_escalation"
    return "evidence_sufficiency_downgrade"


def stratified_sample(
    records: List[Dict], sample_size: int, target_dist: Dict[str, float], rng: random.Random
) -> List[Dict]:
    by_label: Dict[str, List[Dict]] = defaultdict(list)
    for rec in records:
        by_label[rec["gold"]["final_human_decision"]].append(rec)
    for k in by_label:
        rng.shuffle(by_label[k])

    if sample_size >= len(records):
        out = list(records)
        rng.shuffle(out)
        return out

    target_counts: Dict[str, int] = {k: int(sample_size * target_dist.get(k, 0.0)) for k in DECISIONS}
    while sum(target_counts.values()) < sample_size:
        # Add remainder to classes with available data and biggest target deficit.
        best = max(DECISIONS, key=lambda c: target_dist.get(c, 0.0))
        target_counts[best] += 1

    selected: List[Dict] = []
    leftovers: List[Dict] = []
    for decision in DECISIONS:
        pool = by_label.get(decision, [])
        need = target_counts[decision]
        selected.extend(pool[:need])
        leftovers.extend(pool[need:])

    if len(selected) < sample_size:
        rng.shuffle(leftovers)
        selected.extend(leftovers[: sample_size - len(selected)])
    elif len(selected) > sample_size:
        rng.shuffle(selected)
        selected = selected[:sample_size]

    rng.shuffle(selected)
    return selected


def write_outputs(output_dir: Path, records: List[Dict], args: argparse.Namespace) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_dir / "gold_set.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")

    holistic_path = output_dir / "gold_holistic_labels.csv"
    with holistic_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "dossier_id",
                "country",
                "model_decision",
                "final_human_decision",
                "reviewer_confidence",
                "override_of_model",
                "override_reason",
                "label_source",
                "aware_category",
                "amr_unmet_need",
                "targets_mdr_pathogen",
                "glass_resistance_trend",
                "similarity_to_existing_watch",
                "existing_watch_comparator",
            ]
        )
        for rec in records:
            policy = rec["policy_signals"]
            w.writerow(
                [
                    rec["dossier_id"],
                    rec["country"],
                    rec["model_labels"]["holistic_policy_decision"],
                    rec["gold"]["final_human_decision"],
                    rec["gold"]["reviewer_confidence"],
                    rec["gold"]["override_of_model"],
                    rec["gold"]["override_reason"],
                    rec["gold"]["label_source"],
                    policy.get("aware_category"),
                    policy.get("amr_unmet_need"),
                    policy.get("targets_mdr_pathogen"),
                    policy.get("glass_resistance_trend"),
                    policy.get("similarity_to_existing_watch"),
                    policy.get("existing_watch_comparator"),
                ]
            )

    section_path = output_dir / "gold_section_labels.csv"
    with section_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "dossier_id",
                "section_id",
                "module",
                "presence",
                "length_status",
                "correctness",
                "error_tags",
                "corrected_from_model",
            ]
        )
        for rec in records:
            for s in rec["gold"]["section_labels"]:
                w.writerow(
                    [
                        rec["dossier_id"],
                        s["section_id"],
                        s["module"],
                        s["presence"],
                        s["length_status"],
                        s["correctness"],
                        "|".join(s["error_tags"]),
                        s["corrected_from_model"],
                    ]
                )

    dist = defaultdict(int)
    model_dist = defaultdict(int)
    overrides = 0
    for rec in records:
        dist[rec["gold"]["final_human_decision"]] += 1
        model_dist[rec["model_labels"]["holistic_policy_decision"]] += 1
        if rec["gold"]["override_of_model"]:
            overrides += 1

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": args.reviewer_id,
        "adjudication_profile": args.adjudication_profile,
        "input_jsonl": str(args.input_jsonl),
        "num_records": len(records),
        "target_dist": parse_target_dist(args.target_dist),
        "gold_distribution": dict(dist),
        "model_distribution_in_sample": dict(model_dist),
        "override_count": overrides,
        "override_rate": round(overrides / len(records), 4) if records else 0.0,
        "files": {
            "gold_set_jsonl": "gold_set.jsonl",
            "gold_holistic_labels_csv": "gold_holistic_labels.csv",
            "gold_section_labels_csv": "gold_section_labels.csv",
        },
    }
    (output_dir / "gold_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.sample_size <= 0:
        raise ValueError("--sample-size must be > 0")
    target_dist = parse_target_dist(args.target_dist)
    rng = random.Random(args.seed)

    dossiers = load_jsonl(args.input_jsonl)
    adjudicated_records: List[Dict] = []
    reviewed_at = datetime.now(timezone.utc).isoformat()

    for dossier in dossiers:
        section_labels: Dict[str, Dict] = {}
        section_output: List[Dict] = []
        for sec in dossier["sections"]:
            adjudicated = adjudicate_section(sec)
            section_labels[sec["section_id"]] = adjudicated
            section_output.append(
                {
                    "section_id": sec["section_id"],
                    "module": sec["module"],
                    "presence": adjudicated["presence"],
                    "length_status": adjudicated["length_status"],
                    "correctness": adjudicated["correctness"],
                    "error_tags": adjudicated["error_tags"],
                    "corrected_from_model": (
                        adjudicated["presence"] != sec["labels"]["presence"]
                        or adjudicated["length_status"] != sec["labels"]["length_status"]
                        or adjudicated["correctness"] != sec["labels"]["correctness"]
                    ),
                }
            )

        final_decision, confidence, reasons, evidence_sections = adjudicate_holistic(
            dossier, section_labels, profile=args.adjudication_profile
        )
        model_decision = dossier["labels"]["holistic_policy_decision"]
        override = model_decision != final_decision

        record = {
            "dossier_id": dossier["dossier_id"],
            "country": dossier["country"],
            "submission_date": dossier["submission_date"],
            "model_labels": {
                "holistic_policy_decision": model_decision,
                "risk_score": dossier["labels"]["risk_score"],
            },
            "gold": {
                "final_human_decision": final_decision,
                "reviewer_confidence": confidence,
                "decision_reasons": reasons,
                "evidence_section_ids": evidence_sections,
                "override_of_model": override,
                "override_reason": build_override_reason(model_decision, final_decision),
                "review_notes": " ; ".join(reasons),
                "reviewed_by": args.reviewer_id,
                "reviewed_at": reviewed_at,
                "label_source": "machine_adjudicated",
                "adjudication_profile": args.adjudication_profile,
                "section_labels": section_output,
            },
            "policy_signals": dossier["policy_signals"],
            "provenance": dossier["provenance"],
        }
        adjudicated_records.append(record)

    sampled = stratified_sample(adjudicated_records, args.sample_size, target_dist, rng)
    write_outputs(args.output_dir, sampled, args)
    print(f"Created gold set with {len(sampled)} records at: {args.output_dir}")


if __name__ == "__main__":
    main()
