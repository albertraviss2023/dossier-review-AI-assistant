from __future__ import annotations

from dossier_review_ai_assistant.policy import apply_policy_rules, evaluate_amr_stewardship


def _base_dossier() -> dict:
    return {
        "policy_signals": {
            "inn_infringement": False,
            "gmp_inspection_status": "compliant",
            "gmp_inspection_recent": True,
            "gmp_certificate_validity": "valid",
            "clinical_data_available": True,
            "pivotal_trial_outcome": "endpoint_met",
            "aware_category": "not_applicable",
            "amr_unmet_need": "not_applicable",
            "targets_mdr_pathogen": False,
            "glass_resistance_trend": "not_applicable",
            "similarity_to_existing_watch": "not_applicable",
            "existing_watch_comparator": "not_applicable",
        },
        "labels": {
            "holistic_policy_decision": "standard_review",
            "risk_score": 0.42,
        },
    }


def test_reserve_antibiotic_can_fast_track_with_restricted_authorization():
    dossier = _base_dossier()
    dossier["policy_signals"].update(
        {
            "aware_category": "reserve",
            "amr_unmet_need": "critical",
            "targets_mdr_pathogen": True,
            "glass_resistance_trend": "rising",
        }
    )

    amr = evaluate_amr_stewardship(dossier)
    recommendation, hits, _ = apply_policy_rules(dossier)

    assert amr["fast_track_candidate"] is True
    assert amr["authorization_control"] == "restricted_authorization"
    assert recommendation == "fast_track"
    assert "reserve_fast_track_unmet_need" in hits
    assert "restricted_authorization" in hits


def test_watch_similarity_with_rising_resistance_escalates_to_deep_review():
    dossier = _base_dossier()
    dossier["labels"]["holistic_policy_decision"] = "fast_track"
    dossier["policy_signals"].update(
        {
            "aware_category": "watch",
            "glass_resistance_trend": "rising",
            "similarity_to_existing_watch": "high",
            "existing_watch_comparator": "ciprofloxacin",
        }
    )

    amr = evaluate_amr_stewardship(dossier)
    recommendation, hits, _ = apply_policy_rules(dossier)

    assert amr["watch_similarity_restriction"] is True
    assert recommendation == "deep_review"
    assert "watch_similarity_restricted_authorization" in hits
    assert "watch_similarity_deep_review" in hits


def test_severe_safety_findings_still_override_reserve_fast_track():
    dossier = _base_dossier()
    dossier["policy_signals"].update(
        {
            "aware_category": "reserve",
            "amr_unmet_need": "critical",
            "targets_mdr_pathogen": True,
            "gmp_inspection_status": "non_compliant",
        }
    )

    recommendation, hits, _ = apply_policy_rules(dossier)

    assert recommendation == "reject_and_return"
    assert "safety_override_reject" in hits
