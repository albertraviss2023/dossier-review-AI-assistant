from __future__ import annotations

from dossier_review_ai_assistant.intake import build_dossier_from_raw_text
from dossier_review_ai_assistant.review_workflow import build_workflow_evaluation


def _base_review_payload(*, review_type: str) -> dict:
    return {
        "recommendation": "approval_granted",
        "review_type": review_type,
        "confidence": 0.91,
        "route": "fallback",
        "rationale": "The dossier is adequate on the available evidence.",
        "policy_rule_hits": [],
        "section_diagnostics": [],
        "citations": [],
        "verifier": {"grounded_claim_rate": 1.0, "passed": True},
        "amr_stewardship": {
            "applies": False,
            "aware_category": "not_applicable",
            "glass_resistance_trend": "not_applicable",
            "authorization_control": "standard_authorization",
            "fast_track_candidate": False,
            "restricted_authorization": False,
            "watch_similarity_restriction": False,
            "source_trace": [],
            "rationale": "AMR stewardship is not applicable.",
        },
    }


def test_generic_review_uses_innovator_reference_when_provided():
    dossier = build_dossier_from_raw_text(
        dossier_id="GENERIC-WORKFLOW-001",
        country="Uganda",
        submission_date="2026-04-20",
        product_name="Paraclear",
        inn_name="paracetamol",
        applicant="Generic Applicant",
        manufacturer="Generic Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Application Form and Administrative Information\n\n"
            "Signed application form included. Proof of payment attached.\n\n"
            "Product Information and Naming\n\n"
            "The proposed prescribing information includes indication, dosing, contraindications, warnings, adverse reactions, and storage conditions.\n\n"
            "Manufacturer and GMP Evidence\n\n"
            "GMP certificate remains valid.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study.\n"
        ),
    )
    dossier["reference_materials"] = {
        "innovator_reference_name": "Reference Paracetamol PIL",
        "innovator_patient_information_text": (
            "The patient information leaflet includes indication, dosing, contraindications, warnings, adverse reactions, and storage conditions."
        ),
        "reference_urls": ["https://www.medicines.org.uk/emc/product/5164/pil"],
    }
    review_payload = _base_review_payload(review_type="generic")
    review_payload["section_diagnostics"] = [
        {
            "section_id": section["section_id"],
            "title": section["title"],
            "presence": "present",
            "length_status": "length_ok",
            "correctness": "correct",
            "critical": section["critical"],
        }
        for section in dossier["sections"]
    ]

    workflow = build_workflow_evaluation(dossier, review_payload)
    specific = workflow["technical_section_review"]["review_type_specific"]

    assert specific["review_type"] == "generic"
    assert specific["baseline_available"] is True
    assert specific["baseline_verified"] is True
    assert specific["baseline_reference_name"] == "Reference Paracetamol PIL"
    assert "Generic workflow requires comparison" in specific["notes"][0]
    assert "#### Naming / INN" in workflow["findings_summary_markdown"]


def test_innovation_review_checks_completeness_without_baseline_matching():
    dossier = build_dossier_from_raw_text(
        dossier_id="INNOVATION-WORKFLOW-001",
        country="Uganda",
        submission_date="2026-04-20",
        product_name="Novathera",
        inn_name="novathera",
        applicant="Innovation Applicant",
        manufacturer="Innovation Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Application Form and Administrative Information\n\n"
            "Signed application form included. Proof of payment attached.\n\n"
            "Product Information and Naming\n\n"
            "The product information gives the indication and dose but omits storage details and contraindications.\n\n"
            "Manufacturer and GMP Evidence\n\n"
            "GMP certificate remains valid.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study.\n"
        ),
    )
    review_payload = _base_review_payload(review_type="innovation")
    review_payload["section_diagnostics"] = [
        {
            "section_id": section["section_id"],
            "title": section["title"],
            "presence": "present",
            "length_status": "length_ok",
            "correctness": "correct",
            "critical": section["critical"],
        }
        for section in dossier["sections"]
    ]

    workflow = build_workflow_evaluation(dossier, review_payload)
    specific = workflow["technical_section_review"]["review_type_specific"]

    assert specific["review_type"] == "innovation"
    assert specific["baseline_available"] is False
    assert specific["status"] == "partial"
    assert any("missing key patient-information elements" in item["issue"] for item in specific["findings"])
    assert "| Severity | Violated rule | Evidence reference | Recommendation |" in workflow["findings_summary_markdown"]


def test_generic_review_marks_demo_reference_as_unverified():
    dossier = build_dossier_from_raw_text(
        dossier_id="GENERIC-WORKFLOW-UNVERIFIED-001",
        country="Uganda",
        submission_date="2026-04-20",
        product_name="Paraclear",
        inn_name="paracetamol",
        applicant="Generic Applicant",
        manufacturer="Generic Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Application Form and Administrative Information\n\n"
            "Signed application form included. Proof of payment attached.\n\n"
            "Product Information and Naming\n\n"
            "The proposed prescribing information includes indication, dosing, contraindications, warnings, adverse reactions, and storage conditions.\n\n"
            "Manufacturer and GMP Evidence\n\n"
            "GMP certificate remains valid.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study.\n"
        ),
    )
    dossier["reference_materials"] = {
        "innovator_reference_name": "Demo PIL",
        "innovator_patient_information_text": "Demo baseline text only.",
        "reference_urls": ["https://example.invalid/reference-pil"],
    }
    review_payload = _base_review_payload(review_type="generic")
    review_payload["section_diagnostics"] = [
        {
            "section_id": section["section_id"],
            "title": section["title"],
            "presence": "present",
            "length_status": "length_ok",
            "correctness": "correct",
            "critical": section["critical"],
        }
        for section in dossier["sections"]
    ]

    workflow = build_workflow_evaluation(dossier, review_payload)
    specific = workflow["technical_section_review"]["review_type_specific"]

    assert specific["baseline_available"] is True
    assert specific["baseline_verified"] is False
    assert specific["status"] == "baseline_unverified"
    assert any("not validated as an external source" in note for note in specific["notes"])
