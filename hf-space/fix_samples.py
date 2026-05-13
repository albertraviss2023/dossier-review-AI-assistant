import json
import random
from pathlib import Path
import sys

# Add synthetic_data to path to import generate_dossiers
sys.path.append("synthetic_data")
import generate_dossiers
from generate_dossiers import Context, _dossier_to_pdf_lines, _write_basic_pdf

def update_text(section, ctx, rng):
    section_id = section["section_id"]
    if section_id == "m1_gmp":
        base = generate_dossiers.compose_section_text(rng, "m1_manufacturer_gmp", ctx, 1200)
    elif section_id == "m2_clinical":
        base = generate_dossiers.compose_section_text(rng, "m2_clinical_overview", ctx, 1200)
    elif section_id == "m5_stewardship":
        base = generate_dossiers.compose_section_text(rng, "m5_trial_listing", ctx, 1200)
    else:
        # Fallback to the first matching section template or generic
        base = section.get("text", "")
        if "clinical" in section_id:
            base = generate_dossiers.compose_section_text(rng, "m2_clinical_overview", ctx, 1200)
        elif "gmp" in section_id:
            base = generate_dossiers.compose_section_text(rng, "m1_manufacturer_gmp", ctx, 1200)
        elif "admin" in section_id:
            base = generate_dossiers.compose_section_text(rng, "m1_application_admin", ctx, 1200)
        else:
            base += " " + " ".join(rng.choices(generate_dossiers.FILLER_SENTENCES, k=4))

    # Append error signals to the text to keep tests/examples working
    original_text = section.get("text", "")
    if "compliant" in original_text.lower():
        base += " The manufacturing site remains compliant and the GMP certificate is valid."
    if "expired" in original_text.lower():
        base += " Note: The GMP certificate has expired and requires renewal."
    if "reject" in original_text.lower() or "missing" in original_text.lower() or "endpoint not met" in original_text.lower() or "did not meet" in original_text.lower() or "failure" in original_text.lower():
        base += " Reviewers should note that " + original_text

    section["text"] = base
    section["metrics"]["char_count"] = len(base)
    return section

def main():
    rng = random.Random(42)
    sample_dir = Path("sample_dossiers")
    incoming_dir = sample_dir / "incoming_files"
    
    # Update root JSONs
    for json_path in sample_dir.glob("*.json"):
        with json_path.open() as f:
            data = json.load(f)
        
        ctx = Context(
            dossier_id=data["dossier_id"],
            country=data["country"],
            submission_date=data["submission_date"],
            product_name=data["product"]["product_name"],
            inn_name=data["product"]["inn_name"],
            atc_code=data["product"]["atc_code"],
            dosage_form=data["product"]["dosage_form"],
            strength=data["product"]["strength"],
            applicant=data["organization"]["applicant"],
            manufacturer=data["organization"]["manufacturer"],
            facility_country=data["organization"]["facility_country"],
            gmp_status=data["policy_signals"]["gmp_inspection_status"],
            gmp_last_inspection="2025-01-01",
            gmp_certificate_number="GMP-123456",
            gmp_certificate_expiry="2027-01-01" if data["policy_signals"]["gmp_certificate_validity"] == "valid" else "2023-01-01",
            clinical_outcome=data["policy_signals"]["pivotal_trial_outcome"],
            clinical_data_available=data["policy_signals"]["clinical_data_available"],
            pivotal_trial_count=2,
            indication="infections",
            therapeutic_area="antibacterial" if data["policy_signals"]["aware_category"] != "not_applicable" else "general",
            aware_category=data["policy_signals"]["aware_category"],
            amr_unmet_need=data["policy_signals"]["amr_unmet_need"],
            targets_mdr_pathogen=data["policy_signals"]["targets_mdr_pathogen"],
            glass_resistance_trend=data["policy_signals"]["glass_resistance_trend"],
            similarity_to_existing_watch=data["policy_signals"]["similarity_to_existing_watch"],
            existing_watch_comparator=data["policy_signals"]["existing_watch_comparator"],
            defects=[]
        )

        for sec in data.get("sections", []):
            update_text(sec, ctx, rng)

        with json_path.open("w") as f:
            json.dump(data, f, indent=2)

    # Process incoming files JSONs
    for json_path in incoming_dir.glob("*.json"):
        if json_path.name == "catalog.json":
            continue
            
        with json_path.open() as f:
            data = json.load(f)
            
        ctx = Context(
            dossier_id=data.get("dossier_id", "INCOMING"),
            country=data.get("country", "Unknown"),
            submission_date=data.get("submission_date", "2026-01-01"),
            product_name=data.get("product", {}).get("product_name", "TestProd"),
            inn_name=data.get("product", {}).get("inn_name", "testinn"),
            atc_code=data.get("product", {}).get("atc_code", "A01"),
            dosage_form=data.get("product", {}).get("dosage_form", "tablet"),
            strength=data.get("product", {}).get("strength", "100mg"),
            applicant=data.get("organization", {}).get("applicant", "App"),
            manufacturer=data.get("organization", {}).get("manufacturer", "Mfg"),
            facility_country=data.get("organization", {}).get("facility_country", "Country"),
            gmp_status=data.get("policy_signals", {}).get("gmp_inspection_status", "compliant"),
            gmp_last_inspection="2025-01-01",
            gmp_certificate_number="GMP-123456",
            gmp_certificate_expiry="2027-01-01",
            clinical_outcome=data.get("policy_signals", {}).get("pivotal_trial_outcome", "endpoint_met"),
            clinical_data_available=data.get("policy_signals", {}).get("clinical_data_available", True),
            pivotal_trial_count=2,
            indication="test",
            therapeutic_area="test",
            aware_category=data.get("policy_signals", {}).get("aware_category", "not_applicable"),
            amr_unmet_need=data.get("policy_signals", {}).get("amr_unmet_need", "not_applicable"),
            targets_mdr_pathogen=data.get("policy_signals", {}).get("targets_mdr_pathogen", False),
            glass_resistance_trend=data.get("policy_signals", {}).get("glass_resistance_trend", "not_applicable"),
            similarity_to_existing_watch=data.get("policy_signals", {}).get("similarity_to_existing_watch", "not_applicable"),
            existing_watch_comparator=data.get("policy_signals", {}).get("existing_watch_comparator", "not_applicable"),
            defects=[]
        )

        for sec in data.get("sections", []):
            update_text(sec, ctx, rng)

        with json_path.open("w") as f:
            json.dump(data, f, indent=2)

    # Recreate the PDFs in incoming_files by re-using the synthetic generator's output mechanism
    # I'll just write an arbitrary detailed PDF for each existing pdf
    for pdf_path in incoming_dir.glob("*.pdf"):
        if "scanned" in pdf_path.name:
            continue # Skip the specific scanned PDF as it's meant to be an image/scan

        # Generate a fake dossier structure
        ctx = generate_dossiers.build_base_context(rng)
        
        # Override some flags based on file name to preserve testing intent
        if "expired" in pdf_path.name:
            ctx.gmp_certificate_expiry = "2020-01-01"
            ctx.gmp_status = "non_compliant"
        if "clinical" in pdf_path.name and "failure" in pdf_path.name:
            ctx.clinical_outcome = "endpoint_not_met"
        if "watch" in pdf_path.name:
            ctx.aware_category = "watch"
        if "fast_track" in pdf_path.name:
            ctx.aware_category = "reserve"
            ctx.targets_mdr_pathogen = True
            ctx.amr_unmet_need = "critical"

        sections = generate_dossiers.create_base_sections(rng, ctx)
        dossier_data = {
            "dossier_id": ctx.dossier_id,
            "country": ctx.country,
            "submission_date": ctx.submission_date,
            "product": {
                "product_name": ctx.product_name,
                "inn_name": ctx.inn_name,
                "atc_code": ctx.atc_code,
                "dosage_form": ctx.dosage_form,
                "strength": ctx.strength,
            },
            "organization": {
                "applicant": ctx.applicant,
                "manufacturer": ctx.manufacturer,
                "facility_country": ctx.facility_country,
            },
            "labels": {
                "holistic_policy_decision": "standard_review",
                "risk_score": 0.5
            },
            "policy_signals": {
                "aware_category": ctx.aware_category,
                "amr_unmet_need": ctx.amr_unmet_need,
                "glass_resistance_trend": ctx.glass_resistance_trend,
                "similarity_to_existing_watch": ctx.similarity_to_existing_watch,
                "gmp_inspection_status": ctx.gmp_status,
                "pivotal_trial_outcome": ctx.clinical_outcome,
            },
            "gmp_details": {
                "last_inspection_date": ctx.gmp_last_inspection,
                "certificate_number": ctx.gmp_certificate_number,
                "certificate_expiry": ctx.gmp_certificate_expiry,
            },
            "clinical_details": {
                "pivotal_trial_count": ctx.pivotal_trial_count,
            },
            "sections": [
                {"module": s["module"], "section_id": s["section_id"], "title": s["title"], "labels": {"presence": "present", "length_status": "length_ok", "correctness": "correct", "error_tags": []}, "error_tags": [], "text": s["text"]} 
                for s in sections.values()
            ]
        }
        lines = _dossier_to_pdf_lines(dossier_data)
        _write_basic_pdf(pdf_path, lines)

if __name__ == "__main__":
    main()
