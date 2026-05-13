from __future__ import annotations

from regulatory_mcp_server.tools.aware_amr import (
    compute_antimicrobial_similarity,
    fetch_aware_reserve_reference,
)


def test_fetch_aware_reference_for_access_antimicrobial():
    result = fetch_aware_reserve_reference(
        active_ingredient="amoxicillin",
        source_mode="cached",
    )
    assert result["status"] == "success"
    assert result["data"]["aware_category"] == "Access"


def test_compute_antimicrobial_similarity_for_reserve_product():
    result = compute_antimicrobial_similarity(
        active_ingredient="colistin",
        aware_reference={
            "active_ingredient": "colistin",
            "is_antimicrobial": True,
            "aware_category": "Reserve",
            "reserve_related": True,
            "nearest_reserve_agent": "colistin",
        },
        comparison_mode="class_or_structure",
    )
    assert result["data"]["stewardship_flag"] == "required_control"
    assert result["data"]["reserve_similarity"]["nearest_reserve_agent"] == "colistin"


def test_compute_antimicrobial_similarity_for_non_antimicrobial():
    result = compute_antimicrobial_similarity(
        active_ingredient="paracetamol",
        aware_reference={
            "active_ingredient": "paracetamol",
            "is_antimicrobial": False,
            "aware_category": "Not listed",
            "reserve_related": False,
        },
        comparison_mode="class_or_structure",
    )
    assert result["data"]["stewardship_flag"] == "not_applicable"
