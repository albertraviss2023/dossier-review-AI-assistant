from __future__ import annotations

import random

from synthetic_data.generate_dossiers import (
    Context,
    compose_section_text,
    resolve_product_profile,
)


def test_resolve_product_profile_returns_plausible_pairs():
    rng = random.Random(7)

    losartan = resolve_product_profile(rng, "losartan")
    clotrimazole = resolve_product_profile(rng, "clotrimazole")
    timolol = resolve_product_profile(rng, "timolol")
    salbutamol = resolve_product_profile(rng, "salbutamol")
    ceftriaxone = resolve_product_profile(rng, "ceftriaxone")

    assert losartan[0] == "C09CA01"
    assert losartan[1] == "tablet"
    assert losartan[2] in {"50 mg", "100 mg"}

    assert clotrimazole[1] == "cream"
    assert clotrimazole[2] == "1%"

    assert timolol[1] == "eye drops"
    assert timolol[2] in {"0.25%", "0.5%"}

    assert salbutamol[1] == "inhaler"
    assert salbutamol[2] == "100 mcg/dose"

    assert ceftriaxone[0] == "J01DD04"
    assert ceftriaxone[1] == "injectable"


def test_compose_section_text_avoids_repeating_same_filler_sentence_within_one_section():
    rng = random.Random(11)
    ctx = Context(
        dossier_id="DOS-REALISM-001",
        country="Uganda",
        submission_date="2026-04-13",
        product_name="Losaracare",
        inn_name="losartan",
        atc_code="C09CA01",
        dosage_form="tablet",
        strength="50 mg",
        applicant="Prime Therapeutics",
        manufacturer="Kampala Biopharma Ltd",
        facility_country="Uganda",
        gmp_status="compliant",
        gmp_last_inspection="2026-01-10",
        gmp_certificate_number="GMP-123456",
        gmp_certificate_expiry="2028-01-10",
        clinical_outcome="endpoint_met",
        clinical_data_available=True,
        pivotal_trial_count=2,
        indication="hypertension",
        therapeutic_area="non_antibacterial",
        aware_category="not_applicable",
        amr_unmet_need="not_applicable",
        targets_mdr_pathogen=False,
        glass_resistance_trend="not_applicable",
        similarity_to_existing_watch="not_applicable",
        existing_watch_comparator="not_applicable",
        defects=[],
    )

    text = compose_section_text(rng, "m1_application_admin", ctx, 1500)

    assert text.count("All referenced documents are available in the dossier annex and traceable by section identifier.") <= 1
    assert text.count("The applicant confirms alignment with applicable technical guidance and regional submission standards.") <= 1
