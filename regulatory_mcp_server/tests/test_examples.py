from __future__ import annotations

from regulatory_mcp_server.tools.examples import (
    compare_current_section_to_examples,
    get_section_examples,
)


def test_get_section_examples_returns_correct_and_incorrect_examples():
    result = get_section_examples(
        section_type="patient_information_leaflet",
        example_type="both",
        product_type="generic",
        top_k=4,
    )
    assert result["status"] == "success"
    assert result["data"]["examples"]
    labels = {item["label"] for item in result["data"]["examples"]}
    assert {"correct", "incorrect"} <= labels


def test_compare_current_section_classifies_good_section_as_compliant():
    result = compare_current_section_to_examples(
        current_section={
            "section_id": "pil-1",
            "section_type": "patient_information_leaflet",
            "title": "Patient Information Leaflet",
            "text": "The leaflet states the indication, dosage instructions, contraindications, warnings, side effects, and storage conditions clearly.",
        },
        comparison_dimensions=[
            "completeness",
            "safety wording",
            "contraindications",
            "dosage clarity",
        ],
    )
    assert result["data"]["classification"] == "compliant"
    assert result["data"]["matched_bad_patterns"] == []


def test_compare_current_section_flags_deficient_section():
    result = compare_current_section_to_examples(
        current_section={
            "section_id": "pil-2",
            "section_type": "patient_information_leaflet",
            "title": "Patient Information Leaflet",
            "text": "The leaflet gives the indication only and a vague dose statement.",
        },
        comparison_dimensions=[
            "completeness",
            "safety wording",
            "contraindications",
            "dosage clarity",
        ],
    )
    assert result["data"]["classification"] in {"partially_compliant", "non_compliant"}
    assert result["data"]["evidence"]
    first = result["data"]["evidence"][0]
    assert {"dimension", "finding", "severity", "evidence_excerpt"} <= set(first)
