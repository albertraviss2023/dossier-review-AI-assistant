from __future__ import annotations

from dataclasses import replace

from dossier_review_ai_assistant.policy import apply_policy_rules, evaluate_amr_stewardship
import dossier_review_ai_assistant.external_sources as external_sources
import dossier_review_ai_assistant.policy as policy


def _base_dossier() -> dict:
    return {
        "product": {
            "inn_name": "unknown-molecule",
        },
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
            "holistic_policy_decision": "approval_granted",
            "risk_score": 0.42,
        },
    }


def test_reserve_antibiotic_can_fast_track_with_restricted_authorization():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "cefiderocol"
    dossier["policy_signals"].update(
        {
            "amr_unmet_need": "critical",
            "targets_mdr_pathogen": True,
        }
    )

    amr = evaluate_amr_stewardship(dossier)
    recommendation, hits, _ = apply_policy_rules(dossier)

    assert amr["aware_category"] == "reserve"
    assert amr["glass_resistance_trend"] == "rising"
    assert amr["source_mode"] == "snapshot_backed"
    assert amr["fast_track_candidate"] is True
    assert amr["authorization_control"] == "restricted_authorization"
    assert recommendation == "approval_granted"
    assert "reserve_fast_track_unmet_need" in hits
    assert "restricted_authorization" in hits


def test_watch_similarity_with_rising_resistance_escalates_to_deep_review():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "levofloxacin"
    dossier["labels"]["holistic_policy_decision"] = "approval_granted"
    dossier["policy_signals"].update(
        {
            "similarity_to_existing_watch": "low",
            "existing_watch_comparator": "not_applicable",
        }
    )

    amr = evaluate_amr_stewardship(dossier)
    recommendation, hits, _ = apply_policy_rules(dossier)

    assert amr["similarity_to_existing_watch"] == "high"
    assert amr["existing_watch_comparator"] == "ciprofloxacin"
    assert amr["active_moiety"] == "levofloxacin"
    assert amr["parent_compound"] == "levofloxacin"
    assert amr["pubchem_cid"] == "149096"
    assert amr["chembl_id"] == "CHEMBL1433"
    assert amr["unichem_id"] == "UC149096"
    assert amr["chemistry_source"].startswith("chemistry_snapshot:")
    assert amr["watch_similarity_restriction"] is True
    assert recommendation == "additional_information_required"
    assert "watch_similarity_restricted_authorization" in hits


def test_snapshot_fallback_preserves_signal_when_no_snapshot_match():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "novelcin"
    dossier["policy_signals"].update(
        {
            "aware_category": "watch",
            "glass_resistance_trend": "stable",
        }
    )

    amr = evaluate_amr_stewardship(dossier)

    assert amr["aware_category"] == "watch"
    assert amr["glass_resistance_trend"] == "stable"
    assert amr["source_mode"] == "signals_fallback"
    assert any("fell back" in item.lower() for item in amr["source_trace"])


def test_rxnorm_snapshot_normalizes_brand_or_variant_before_source_lookup():
    dossier = _base_dossier()
    dossier["product"]["product_name"] = "Respivox"
    dossier["product"]["inn_name"] = "levofloxacin hemihydrate"
    dossier["policy_signals"].update(
        {
            "similarity_to_existing_watch": "high",
            "existing_watch_comparator": "ciprofloxacin",
        }
    )

    amr = evaluate_amr_stewardship(dossier)

    assert amr["normalized_ingredient"] == "levofloxacin"
    assert amr["normalization_source"].startswith("rxnorm_snapshot:")
    assert amr["aware_category"] == "watch"
    assert amr["glass_resistance_trend"] == "rising"
    assert any("normalized product identity to levofloxacin" in item.lower() for item in amr["source_trace"])


def test_chemistry_snapshot_fallback_preserves_dossier_similarity_when_uncovered():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "novelcin"
    dossier["policy_signals"].update(
        {
            "similarity_to_existing_watch": "moderate",
            "existing_watch_comparator": "ciprofloxacin",
        }
    )

    amr = evaluate_amr_stewardship(dossier)

    assert amr["similarity_to_existing_watch"] == "moderate"
    assert amr["existing_watch_comparator"] == "ciprofloxacin"
    assert amr["active_moiety"] == "not_available"
    assert amr["pubchem_cid"] == "not_available"
    assert amr["chemistry_source"] == "signals_fallback"
    assert any("chemistry snapshot had no entry" in item.lower() for item in amr["source_trace"])


def test_expanded_snapshot_coverage_resolves_previously_uncovered_watch_antibiotic():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "moxifloxacin"
    dossier["policy_signals"].update(
        {
            "aware_category": "watch",
            "glass_resistance_trend": "rising",
            "similarity_to_existing_watch": "high",
        }
    )

    amr = evaluate_amr_stewardship(dossier)

    assert amr["source_mode"] == "snapshot_backed"
    assert amr["aware_category"] == "watch"
    assert amr["glass_resistance_trend"] == "rising"
    assert amr["pubchem_cid"] == "152946"
    assert amr["chembl_id"] == "CHEMBL1587"


def test_severe_safety_findings_still_override_reserve_fast_track():
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "cefiderocol"
    dossier["policy_signals"].update(
        {
            "amr_unmet_need": "critical",
            "targets_mdr_pathogen": True,
            "gmp_inspection_status": "non_compliant",
        }
    )

    recommendation, hits, _ = apply_policy_rules(dossier)

    assert recommendation == "approval_denied"
    assert "policy_severe_failure" in hits


def test_live_source_mode_prefers_live_values_when_configured(monkeypatch):
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "levofloxacin"

    live_settings = replace(
        policy._SETTINGS,
        external_source_mode="live_prefer",
        rxnorm_live_url="https://example.test/rxnorm?query={query}",
        who_aware_live_url="https://example.test/aware?inn_name={inn_name}",
        who_glass_live_url="https://example.test/glass?inn_name={inn_name}",
        chemistry_similarity_live_url="https://example.test/chemistry?ingredient={ingredient}",
    )

    def fake_fetch(url: str, timeout_seconds: float) -> dict:
        if "rxnorm" in url:
            return {"normalized_ingredient": "levofloxacin", "source_version": "rxnorm-live-v1"}
        if "aware" in url:
            return {"aware_category": "watch", "source_version": "aware-live-v1"}
        if "glass" in url:
            return {"glass_resistance_trend": "stable", "source_version": "glass-live-v1"}
        if "chemistry" in url:
            return {
                "similarity_to_existing_watch": "moderate",
                "existing_watch_comparator": "ofloxacin",
                "active_moiety": "levofloxacin",
                "parent_compound": "levofloxacin",
                "pubchem_cid": "149096",
                "canonical_smiles": "LIVE_SMILES",
                "inchikey": "LIVEINCHIKEY",
                "chembl_id": "CHEMBL1433",
                "unichem_id": "UC149096",
                "source_version": "chem-live-v1",
            }
        raise AssertionError(f"Unexpected url {url}")

    monkeypatch.setattr(policy, "_SETTINGS", live_settings)
    monkeypatch.setattr(external_sources, "_fetch_json", fake_fetch)

    amr = evaluate_amr_stewardship(dossier)

    assert amr["source_mode"] == "live_backed"
    assert amr["glass_resistance_trend"] == "stable"
    assert amr["similarity_to_existing_watch"] == "moderate"
    assert amr["existing_watch_comparator"] == "ofloxacin"
    assert amr["canonical_smiles"] == "LIVE_SMILES"
    assert amr["inchikey"] == "LIVEINCHIKEY"
    assert amr["watch_similarity_restriction"] is False
    assert amr["chemistry_source"] == "chemistry_live:chem-live-v1"
    assert any("live who glass adapter resolved" in item.lower() for item in amr["source_trace"])


def test_chemistry_identifier_disagreement_disables_watch_restriction(monkeypatch):
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "levofloxacin"
    dossier["labels"]["holistic_policy_decision"] = "approval_granted"

    live_settings = replace(
        policy._SETTINGS,
        external_source_mode="live_prefer",
        chemistry_similarity_live_url="https://example.test/chemistry?ingredient={ingredient}",
    )

    def chemistry_only_fetch(url: str, timeout_seconds: float) -> dict:
        if "chemistry" not in url:
            raise TimeoutError("other live sources intentionally unavailable")
        return {
            "similarity_to_existing_watch": "high",
            "existing_watch_comparator": "ciprofloxacin",
            "active_moiety": "moxifloxacin",
            "parent_compound": "moxifloxacin",
            "pubchem_cid": "152946",
            "canonical_smiles": "DIFFERENT_SMILES",
            "inchikey": "DIFFERENTKEY",
            "chembl_id": "CHEMBL999999",
            "unichem_id": "UC152946",
            "source_version": "chem-live-v2",
        }

    monkeypatch.setattr(policy, "_SETTINGS", live_settings)
    monkeypatch.setattr(external_sources, "_fetch_json", chemistry_only_fetch)

    amr = evaluate_amr_stewardship(dossier)
    recommendation, hits, _ = apply_policy_rules(dossier)

    assert amr["active_moiety"] == "moxifloxacin"
    assert amr["watch_similarity_restriction"] is False
    assert recommendation == "approval_granted"
    assert any("disagreement" in item.lower() for item in amr["source_trace"])
    assert "watch_similarity_restricted_authorization" not in hits


def test_live_source_failures_fall_back_to_snapshot_data(monkeypatch):
    dossier = _base_dossier()
    dossier["product"]["inn_name"] = "cefiderocol"

    live_settings = replace(
        policy._SETTINGS,
        external_source_mode="live_prefer",
        rxnorm_live_url="https://example.test/rxnorm?query={query}",
        who_aware_live_url="https://example.test/aware?inn_name={inn_name}",
        who_glass_live_url="https://example.test/glass?inn_name={inn_name}",
        chemistry_similarity_live_url="https://example.test/chemistry?ingredient={ingredient}",
    )

    def broken_fetch(url: str, timeout_seconds: float) -> dict:
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(policy, "_SETTINGS", live_settings)
    monkeypatch.setattr(external_sources, "_fetch_json", broken_fetch)

    amr = evaluate_amr_stewardship(dossier)

    assert amr["source_mode"] == "snapshot_backed"
    assert amr["aware_category"] == "reserve"
    assert amr["glass_resistance_trend"] == "rising"
    assert any("failed" in item.lower() for item in amr["source_trace"])
