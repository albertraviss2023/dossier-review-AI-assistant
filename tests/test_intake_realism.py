from __future__ import annotations

from dossier_review_ai_assistant.intake import build_dossier_from_raw_text


def test_raw_intake_infers_fast_track_for_reserve_mdr_case():
    dossier = build_dossier_from_raw_text(
        dossier_id="INTAKE-FAST-001",
        country="Uganda",
        submission_date="2026-04-13",
        product_name="Cefidera",
        inn_name="cefiderocol",
        applicant="Demo Applicant",
        manufacturer="Demo Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Manufacturer and GMP Evidence\n\n"
            "GMP certificate remains valid and no critical findings were reported.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study for multidrug-resistant infection.\n\n"
            "AMR Stewardship Narrative\n\n"
            "This is a last-resort option for MDR infection and the dossier includes stewardship controls."
        ),
    )
    assert dossier["policy_signals"]["aware_category"] == "reserve"
    assert dossier["labels"]["holistic_policy_decision"] == "approval_granted"


def test_raw_intake_infers_reject_for_expired_gmp_case():
    dossier = build_dossier_from_raw_text(
        dossier_id="INTAKE-REJECT-001",
        country="Uganda",
        submission_date="2026-04-13",
        product_name="QualityFail",
        inn_name="amoxicillin",
        applicant="Demo Applicant",
        manufacturer="Demo Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "Manufacturer and GMP Evidence\n\n"
            "Certificate expired and inspection evidence missing.\n\n"
            "Clinical Overview and Benefit-Risk Summary\n\n"
            "Primary endpoint was met in the pivotal study."
        ),
    )
    assert dossier["policy_signals"]["gmp_certificate_validity"] in {"expired", "not_provided"}
    assert dossier["labels"]["holistic_policy_decision"] == "additional_information_required"


def test_raw_intake_appends_visual_evidence_sections_when_present():
    dossier = build_dossier_from_raw_text(
        dossier_id="INTAKE-VISUAL-001",
        country="Uganda",
        submission_date="2026-04-13",
        product_name="VisualCase",
        inn_name="amoxicillin",
        applicant="Demo Applicant",
        manufacturer="Demo Manufacturer",
        facility_country="Uganda",
        raw_text="Manufacturer and GMP Evidence\n\nGMP certificate remains valid.",
        extraction_metadata={
            "extraction_method": "pdf_text_plus_ocr",
            "page_count": 2,
            "image_count": 2,
            "ocr_used": True,
            "visual_evidence": [
                {
                    "page_number": 1,
                    "evidence_type": "gmp_certificate_or_site_evidence",
                    "summary": "Visual evidence suggests GMP documentation with no critical findings identified.",
                    "ocr_excerpt": "GMP certificate remains valid and no critical findings were reported.",
                }
            ],
        },
    )
    titles = [section["title"] for section in dossier["sections"]]
    assert any(title.startswith("Visual Evidence Summary - Page 1") for title in titles)


def test_raw_intake_splits_structured_export_into_named_sections():
    dossier = build_dossier_from_raw_text(
        dossier_id="INTAKE-STRUCTURED-001",
        country="Uganda",
        submission_date="2026-04-13",
        product_name="StructuredCase",
        inn_name="nitrofurantoin",
        applicant="Demo Applicant",
        manufacturer="Demo Manufacturer",
        facility_country="Uganda",
        raw_text=(
            "REGULATORY DOSSIER SUBMISSION\n\n"
            "[1] m1_manufacturer_gmp - Manufacturer and GMP Evidence\n"
            "Labels: presence=present; length=length_ok; correctness=correct\n"
            "The GMP certificate remains valid and inspection findings were closed.\n"
            "[2] m3_stability - Stability and Shelf-Life Justification\n"
            "Labels: presence=present; length=length_ok; correctness=correct\n"
            "A comprehensive stability program supports the proposed shelf life.\n"
        ),
    )

    titles = [section["title"] for section in dossier["sections"]]
    assert "Manufacturer and GMP Evidence" in titles
    assert "Stability and Shelf-Life Justification" in titles
