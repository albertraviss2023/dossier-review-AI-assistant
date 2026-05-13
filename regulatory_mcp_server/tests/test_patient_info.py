from __future__ import annotations

from regulatory_mcp_server.tools.patient_info import (
    compare_generic_patient_information,
    fetch_innovator_patient_information,
)


def test_fetch_innovator_patient_information_returns_cached_sections():
    result = fetch_innovator_patient_information(
        active_ingredient="amoxicillin",
        reference_urls=["https://www.medicines.org.uk/emc/product/541/pil"],
    )
    assert result["status"] == "success"
    assert result["data"]["sections"]


def test_compare_generic_patient_information_flags_missing_warning():
    result = compare_generic_patient_information(
        current_pil_sections=[
            {
                "section_name": "indications",
                "text": "This leaflet explains what the medicine is for and how much to take.",
                "source_url": None,
            }
        ],
        innovator_pil_sections=[
            {
                "section_name": "warnings",
                "text": "The leaflet includes warnings and precautions for safe use.",
                "source_url": None,
            }
        ],
        comparison_dimensions=["warnings"],
    )
    assert result["data"]["overall_alignment"] in {"partial", "not_aligned"}
    assert result["data"]["differences"]


def test_compare_generic_patient_information_passes_aligned_sections():
    result = compare_generic_patient_information(
        current_pil_sections=[
            {
                "section_name": "warnings",
                "text": "The leaflet includes warnings and precautions for safe use.",
                "source_url": None,
            },
            {
                "section_name": "storage",
                "text": "The leaflet explains how to store the medicine safely.",
                "source_url": None,
            },
        ],
        innovator_pil_sections=[
            {
                "section_name": "warnings",
                "text": "The leaflet includes warnings and precautions for safe use.",
                "source_url": None,
            },
            {
                "section_name": "storage",
                "text": "The leaflet explains how to store the medicine safely.",
                "source_url": None,
            },
        ],
        comparison_dimensions=["warnings", "storage"],
    )
    assert result["data"]["overall_alignment"] == "aligned"
    assert result["data"]["differences"] == []
