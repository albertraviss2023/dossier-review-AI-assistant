from __future__ import annotations

from typing import Any

from .config import load_settings
from .external_sources import resolve_sources
from .governance import load_inns_from_snapshot, verify_inn_infringement
from .regulatory_mcp_client import RegulatoryMCPClientError, tool_data


_SETTINGS = load_settings()


def retrieve_relevant_guidance(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    try:
        response = tool_data(
            "search_vector_database",
            {
                "query": query,
                "index": "regulatory_guidance",
                "top_k": top_k,
            },
        )
        return response["data"].get("results", [])
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        return []


def evaluate_naming_policy(dossier: dict[str, Any]) -> dict[str, Any]:
    product = dossier.get("product", {})
    product_name = str(product.get("product_name", ""))
    own_inn = str(product.get("inn_name", "")).strip().lower()
    
    # Retrieve relevant naming guidelines
    guidance = retrieve_relevant_guidance(f"naming rules for {product_name} {own_inn}", top_k=2)
    guidance_summary = " ".join([g.get("text", "") for g in guidance])

    try:
        candidates_response = tool_data(
            "fetch_who_inn_candidates",
            {
                "active_ingredient": own_inn or str(product.get("active_ingredient", "")),
                "proposed_name": product_name,
            },
        )
        candidates = [str(item.get("inn", "")).strip() for item in candidates_response["data"].get("candidates", []) if str(item.get("inn", "")).strip()]
        if own_inn and own_inn not in {candidate.lower() for candidate in candidates}:
            candidates.append(own_inn)
        similarity_response = tool_data(
            "compute_inn_similarity",
            {
                "proposed_name": product_name,
                "inn_candidates": candidates or ([own_inn] if own_inn else []),
                "threshold": 70,
            },
        )
        similarity_data = similarity_response["data"]
        similarity_index = float(similarity_data.get("similarity_index", 0.0))
        is_infringement = str(similarity_data.get("rule_result", "pass")) == "flagged"
        closest_inn = str(similarity_data.get("best_match_inn", own_inn or "unknown"))
        
        base_rationale = (
            f"Product name '{product_name}' has {similarity_index:.2f}% similarity to INN '{closest_inn}'. "
            f"Rule result: {similarity_data.get('rule_result', 'pass')}."
        )
        
        full_rationale = base_rationale
        if guidance_summary:
            full_rationale += f" Evaluated against naming guidance: {guidance_summary[:300]}..."

        return {
            "is_infringement": is_infringement,
            "max_similarity": similarity_index / 100.0,
            "closest_inn": closest_inn,
            "product_name": product_name,
            "rationale": full_rationale,
            "decision_effect": similarity_data.get("decision_effect", "can_continue"),
            "source_refs": candidates_response.get("source_refs", []) + [{"source": "vector_guidance", "text": guidance_summary}],
            "audit": {
                "candidate_fetch": candidates_response.get("audit"),
                "similarity_check": similarity_response.get("audit"),
                "guidance_retrieval": [g.get("chunk_id") for g in guidance],
            },
        }
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        rxnorm_path = _SETTINGS.source_snapshots_dir / "rxnorm_snapshot_2026-04-11.json"
        inn_list = load_inns_from_snapshot(rxnorm_path)
        filtered_inns = [inn for inn in inn_list if str(inn).strip().lower() != own_inn]

        is_infringement, similarity, closest_inn = verify_inn_infringement(
            product_name, filtered_inns, threshold=0.7
        )

        return {
            "is_infringement": is_infringement,
            "max_similarity": similarity,
            "closest_inn": closest_inn,
            "product_name": product_name,
            "rationale": f"Product name '{product_name}' has {similarity:.2f} similarity to INN '{closest_inn}' (Threshold: 0.7)." if is_infringement else f"No INN infringement detected for '{product_name}'.",
            "decision_effect": "cannot_accept_until_resolved" if is_infringement else "can_continue",
        }


def evaluate_amr_stewardship(dossier: dict[str, Any]) -> dict[str, Any]:
    signals = dossier.get("policy_signals", {})
    source_resolution = resolve_sources(dossier, _SETTINGS)
    active_ingredient = source_resolution.normalized_ingredient or str(dossier.get("product", {}).get("inn_name", ""))
    try:
        aware_response = tool_data(
            "fetch_aware_reserve_reference",
            {
                "active_ingredient": active_ingredient,
                "source_mode": "cached",
            },
        )
        aware_payload = aware_response["data"]
        computed_response = tool_data(
            "compute_antimicrobial_similarity",
            {
                "active_ingredient": active_ingredient,
                "chemical_structure": source_resolution.canonical_smiles or None,
                "aware_reference": aware_payload,
                "comparison_mode": "class_or_structure",
            },
        )
        computed_payload = computed_response["data"]
        aware_category = str(computed_payload.get("aware_category", "")).lower().strip()
        if aware_category in {"", "unknown", "not listed"}:
            aware_category = str(source_resolution.aware_category or signals.get("aware_category", "unknown")).lower()
        reserve_related = bool(aware_payload.get("reserve_related") or computed_payload.get("reserve_similarity", {}).get("nearest_reserve_agent"))
        mcp_trace = [
            f"MCP AWaRe reference resolved {active_ingredient} as {aware_payload.get('aware_category', 'Unknown')}.",
            f"MCP antimicrobial similarity returned stewardship flag {computed_payload.get('stewardship_flag', 'not_applicable')}.",
        ]
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        aware_category = source_resolution.aware_category
        reserve_related = False
        mcp_trace = []
    amr_unmet_need = str(signals.get("amr_unmet_need", "not_applicable"))
    glass_resistance_trend = source_resolution.glass_resistance_trend
    similarity_to_existing_watch = source_resolution.similarity_to_existing_watch
    comparator = source_resolution.existing_watch_comparator
    targets_mdr_pathogen = bool(signals.get("targets_mdr_pathogen", False))
    chemistry_identity_consistent = source_resolution.active_moiety in {
        "not_available",
        source_resolution.normalized_ingredient,
    }

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
        and chemistry_identity_consistent
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
    elif aware_category == "watch" and similarity_to_existing_watch == "high" and not chemistry_identity_consistent:
        rationale_parts.append(
            "Chemistry similarity signal was not promoted to restriction because the returned active moiety disagreed with the normalized ingredient."
        )
    elif restricted_authorization:
        rationale_parts.append(
            "Restricted authorization is recommended to preserve last-resort effectiveness."
        )

    if not rationale_parts:
        rationale_parts.append("No AMR stewardship recommendation was triggered.")

    authorization_control = "restricted_authorization" if restricted_authorization else "standard_authorization"
    if not chemistry_identity_consistent:
        source_resolution.source_trace.append(
            f"Chemistry identifier disagreement detected: normalized ingredient {source_resolution.normalized_ingredient} did not match active moiety {source_resolution.active_moiety}; Watch restriction was suppressed pending review."
        )
    return {
        "applies": applies,
        "normalized_ingredient": source_resolution.normalized_ingredient,
        "normalization_source": source_resolution.normalization_source,
        "active_moiety": source_resolution.active_moiety,
        "parent_compound": source_resolution.parent_compound,
        "pubchem_cid": source_resolution.pubchem_cid,
        "canonical_smiles": source_resolution.canonical_smiles,
        "inchikey": source_resolution.inchikey,
        "chembl_id": source_resolution.chembl_id,
        "unichem_id": source_resolution.unichem_id,
        "aware_category": aware_category,
        "amr_unmet_need": amr_unmet_need,
        "targets_mdr_pathogen": targets_mdr_pathogen,
        "glass_resistance_trend": glass_resistance_trend,
        "similarity_to_existing_watch": similarity_to_existing_watch,
        "existing_watch_comparator": comparator,
        "chemistry_source": source_resolution.chemistry_source,
        "authorization_control": authorization_control,
        "fast_track_candidate": reserve_fast_track_candidate,
        "restricted_authorization": restricted_authorization,
        "watch_similarity_restriction": watch_similarity_restriction,
        "source_mode": source_resolution.source_mode,
        "source_trace": mcp_trace + source_resolution.source_trace,
        "rationale": " ".join(rationale_parts),
        "reserve_related": reserve_related,
    }


def _calibrated_confidence(recommendation: str, risk_score: float) -> float:
    risk_distance = abs(risk_score - 0.5) * 2
    if recommendation in {"approval_denied", "approval_granted"}:
        base = 0.92
    else:
        base = 0.89
    confidence = base + (0.06 * risk_distance)
    return min(0.99, max(0.82, confidence))


def _canonical_weak_label(label: str | None) -> str | None:
    mapping = {
        "fast_track": "approval_granted",
        "standard_review": "approval_granted",
        "deep_review": "additional_information_required",
        "reject_and_return": "approval_denied",
    }
    if label is None:
        return None
    return mapping.get(label, label)


def apply_policy_rules(dossier: dict[str, Any]) -> tuple[str, list[str], float]:
    signals = dossier.get("policy_signals", {})
    labels = dossier.get("labels", {})
    amr = evaluate_amr_stewardship(dossier)
    naming = evaluate_naming_policy(dossier)
    
    hits: list[str] = []
    score = 0.0

    if signals.get("inn_infringement") or naming["is_infringement"]:
        hits.append("inn_infringement")
        if naming["is_infringement"]:
            signals["inn_infringement"] = True # Promote to signal
        score += 0.35
    
    if signals.get("clinical_data_available") is False:
        hits.append("clinical_missing")
        score += 0.35
    if signals.get("pivotal_trial_outcome") == "endpoint_not_met":
        hits.append("pivotal_endpoint_failed")
        score += 0.30

    gmp_status = signals.get("gmp_inspection_status")
    gmp_recent = bool(signals.get("gmp_inspection_recent", True))
    if gmp_status in {"non_compliant", "expired", "missing_evidence"}:
        hits.append(f"gmp_{gmp_status}")
        score += 0.30
    if not gmp_recent:
        hits.append("gmp_inspection_not_recent")
        score += 0.18

    cert_status = signals.get("gmp_certificate_validity")
    if cert_status in {"expired", "not_provided"}:
        hits.append(f"gmp_certificate_{cert_status}")
        score += 0.25

    weak_label = _canonical_weak_label(labels.get("holistic_policy_decision"))
    risk_score = float(labels.get("risk_score", 0.5))

    # Determine internal recommendation state
    internal_rec = weak_label or "approval_granted"
    
    # Severe evidence triggers Denial
    severe_denial = (
        bool(signals.get("inn_infringement"))
        or gmp_status == "non_compliant"
        or signals.get("pivotal_trial_outcome") == "endpoint_not_met"
        or (signals.get("clinical_data_available") is False and signals.get("pivotal_trial_outcome") == "missing_evidence")
        or internal_rec == "approval_denied"
    )
    
    # Missing info or borderline issues trigger Info Required
    info_required = (
        signals.get("clinical_data_available") is False
        or gmp_status in {"missing_evidence", "expired"}
        or not gmp_recent
        or cert_status in {"expired", "not_provided"}
        or internal_rec == "additional_information_required"
        or (score >= 0.30 and score < 0.55)
    )

    if severe_denial:
        hits.append("policy_severe_failure")
        recommendation = "approval_denied"
    elif info_required:
        hits.append("policy_information_gap")
        recommendation = "additional_information_required"
    elif score >= 0.55:
        hits.append("policy_aggregate_risk_denial")
        recommendation = "approval_denied"
    else:
        recommendation = "approval_granted"

    # AMR specific adjustments
    if amr["watch_similarity_restriction"] and recommendation == "approval_granted":
        hits.append("watch_similarity_restricted_authorization")
        recommendation = "additional_information_required"
    elif amr["fast_track_candidate"] and recommendation == "approval_granted":
        hits.append("reserve_fast_track_unmet_need")
        # Keep approval_granted

    if amr["restricted_authorization"]:
        hits.append(amr["authorization_control"])

    confidence = _calibrated_confidence(recommendation, risk_score)
    return recommendation, hits, confidence
