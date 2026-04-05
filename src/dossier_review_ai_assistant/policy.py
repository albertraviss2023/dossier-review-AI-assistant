from __future__ import annotations

from typing import Any


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
    severe_evidence = score >= 0.55
    if severe_evidence and recommendation != "reject_and_return":
        hits.append("safety_override_reject")
        recommendation = "reject_and_return"

    confidence = _calibrated_confidence(recommendation, risk_score)
    return recommendation, hits, confidence
