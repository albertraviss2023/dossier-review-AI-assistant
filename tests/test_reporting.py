from __future__ import annotations

from dossier_review_ai_assistant.intake import build_dossier_from_raw_text
from dossier_review_ai_assistant.reporting import build_review_report


def test_workflow_report_flags_naming_violation_and_blocks_acceptance():
    dossier = build_dossier_from_raw_text(
        dossier_id="REPORT-NAMING-001",
        country="Uganda",
        submission_date="2026-04-18",
        product_name="amoxicillin",
        inn_name="amoxicillin",
        applicant="Naming Applicant",
        manufacturer="Naming Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Application Form and Administrative Information\n\n"
            "Signed application form included. Proof of payment attached.\n\n"
            "Product Information and Naming\n\n"
            "The proposed product name is amoxicillin.\n\n"
            "Manufacturer and GMP Evidence\n\n"
            "GMP certificate remains valid.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study.\n"
        ),
    )
    review_payload = {
        "recommendation": "approval_denied",
        "confidence": 0.95,
        "route": "fallback",
        "rationale": "The dossier cannot be accepted because the proposed name is too similar to the WHO INN.",
        "policy_rule_hits": ["inn_infringement"],
        "section_diagnostics": [
            {"title": section["title"], "presence": "present", "length_status": "length_ok", "correctness": "correct", "critical": section["critical"]}
            for section in dossier["sections"]
        ],
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

    bundle = build_review_report(dossier=dossier, review_payload=review_payload, report_title="Naming Review Report")
    workflow = bundle["json"]["workflow_report"]

    assert workflow["who_inn_similarity_review"]["threshold_result"] == "failed"
    assert workflow["overall_judgment"]["final_verdict"] == "not_acceptable"
    assert any(item["workflow_step"] == "WHO INN similarity review" for item in workflow["findings_register"])
    assert "Applicable Rules And Requirements" in bundle["html"]
    assert "AMR Stewardship Review" in bundle["html"]
    assert "Findings Summary Tables" in bundle["html"]
    assert "summary-table-card" in bundle["html"]
    assert "Severity Classification" in bundle["text"]
    assert "Findings Summary Tables" in bundle["text"]
    assert "| Severity | Violated rule | Evidence reference | Recommendation |" not in bundle["text"]
    assert "findings_summary_markdown" in bundle["json"]
    assert "WHO INN Similarity Review" in bundle["text"]
    assert bundle["docx_bytes"].startswith(b"PK")
