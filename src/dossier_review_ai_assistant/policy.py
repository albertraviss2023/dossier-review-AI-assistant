from __future__ import annotations

from typing import Any


def evaluate_amr_stewardship(dossier: dict[str, Any]) -> dict[str, Any]:
    signals = dossier.get("policy_signals", {})
    aware_category = str(signals.get("aware_category", "not_applicable"))
    amr_unmet_need = str(signals.get("amr_unmet_need", "not_applicable"))
    glass_resistance_trend = str(signals.get("glass_resistance_trend", "not_applicable"))
    similarity_to_existing_watch = str(signals.get("similarity_to_existing_watch", "not_applicable"))
    comparator = str(signals.get("existing_watch_comparator", "not_applicable"))
    targets_mdr_pathogen = bool(signals.get("targets_mdr_pathogen", False))

    applies = aware_category in {"access", "watch", "reserve"}
    reserve_fast_track_candidate = (
        aware_category == "reserve"
        and targets_mdr_pathogen
        and amr_unmet_need in {"high", "critical"}
    )
    watch_similarity_restriction = (
        aware_category == "watch"
        and similarity_to_existing_watch == "high"
        and glass_resistance_trend == "rising"
    )
    restricted_authorization = aware_category == "reserve" or watch_similarity_restriction

    rationale_parts: list[str] = []
    if not applies:
        rationale_parts.append("AMR stewardship lifecycle rules do not apply to this dossier.")
    elif reserve_fast_track_candidate:
        rationale_parts.append(
            "Reserve antibiotic targets a critical MDR unmet need and is eligible for accelerated review."
        )
    elif aware_category == "watch":
        rationale_parts.append("Watch-category antibiotic requires stewardship review for resistance risk.")
    elif aware_category == "access":
        rationale_parts.append("Access-category antibiotic remains under standard stewardship monitoring.")

    if watch_similarity_restriction:
        rationale_parts.append(
            f"High similarity to existing Watch comparator {comparator} plus rising GLASS resistance supports restricted authorization."
        )
    elif restricted_authorization:
        rationale_parts.append(
            "Restricted authorization is recommended to preserve last-resort effectiveness."
        )

    if not rationale_parts:
        rationale_parts.append("No AMR stewardship recommendation was triggered.")

    authorization_control = "restricted_authorization" if restricted_authorization else "standard_authorization"

    return {
        "applies": applies,
        "aware_category": aware_category,
        "amr_unmet_need": amr_unmet_need,
        "targets_mdr_pathogen": targets_mdr_pathogen,
        "glass_resistance_trend": glass_resistance_trend,
        "similarity_to_existing_watch": similarity_to_existing_watch,
        "existing_watch_comparator": comparator,
        "authorization_control": authorization_control,
        "fast_track_candidate": reserve_fast_track_candidate,
        "restricted_authorization": restricted_authorization,
        "watch_similarity_restriction": watch_similarity_restriction,
        "rationale": " ".join(rationale_parts),
    }


def _calibrated_confidence(recommendation: str, risk_score: float) -> float:
    risk_distance = abs(risk_score - 0.5) * 2
    if recommendation in {"reject_and_return", "fast_track"}:
        base = 0.92
    else:
        base = 0.89
    confidence = base + (0.06 * risk_distance)
    return min(0.99, max(0.82, confidence))


def apply_policy_rules(dossier: dict[str, Any]) -> tuple[str, list[str], float]:
    signals = dossier.get("policy_signals", {})
    labels = dossier.get("labels", {})
    amr = evaluate_amr_stewardship(dossier)
    hits: list[str] = []
    score = 0.0

    if signals.get("inn_infringement"):
        hits.append("inn_infringement")
        score += 0.35
    if signals.get("clinical_data_available") is False:
        hits.append("clinical_missing")
        score += 0.35
    if signals.get("pivotal_trial_outcome") == "endpoint_not_met":
        hits.append("pivotal_endpoint_failed")
        score += 0.30

    gmp_status = signals.get("gmp_inspection_status")
    if gmp_status in {"non_compliant", "expired", "missing_evidence"}:
        hits.append(f"gmp_{gmp_status}")
        score += 0.30

    cert_status = signals.get("gmp_certificate_validity")
    if cert_status in {"expired", "not_provided"}:
        hits.append(f"gmp_certificate_{cert_status}")
        score += 0.25

    weak_label = labels.get("holistic_policy_decision")
    risk_score = float(labels.get("risk_score", 0.5))

    # Baseline for the synthetic phase: follow weak labels, then apply safety override on severe evidence.
    recommendation = weak_label or "fast_track"
    severe_evidence = (
        score >= 0.55
        or gmp_status == "non_compliant"
        or signals.get("pivotal_trial_outcome") == "endpoint_not_met"
    )
    if severe_evidence and recommendation != "reject_and_return":
        hits.append("safety_override_reject")
        recommendation = "reject_and_return"
    elif amr["watch_similarity_restriction"] and recommendation in {"fast_track", "standard_review"}:
        hits.append("watch_similarity_restricted_authorization")
        hits.append("watch_similarity_deep_review")
        recommendation = "deep_review"
    elif amr["fast_track_candidate"]:
        hits.append("reserve_fast_track_unmet_need")
        recommendation = "fast_track"

    if amr["restricted_authorization"]:
        hits.append(amr["authorization_control"])

    confidence = _calibrated_confidence(recommendation, risk_score)
    return recommendation, hits, confidence
