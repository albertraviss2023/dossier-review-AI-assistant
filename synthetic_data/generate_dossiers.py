#!/usr/bin/env python3
"""Synthetic dossier generator for Dossier Review AI Assistant (Regulatory Dossier Policy Copilot).

This script creates CTD-aligned dossiers with section-level labels and policy-level labels.
It generates both compliant and non-compliant submissions, including key failure modes:
- INN infringement risk
- Missing or failed pivotal clinical trials
- GMP non-compliance or outdated inspections
- Section-level missing/length/correctness issues
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import textwrap
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

COUNTRIES = ["Tanzania", "Burkina Faso", "Uganda", "Botswana"]
DOSAGE_FORMS = ["tablet", "capsule", "suspension", "injectable", "cream"]
APPLICANT_PREFIXES = ["Alpha", "Prime", "National", "Global", "United"]
ATC_CODES = [
    "A02BC01",
    "A10AE04",
    "A10BA02",
    "A10BB12",
    "A10BK01",
    "B01AB05",
    "B01AC04",
    "C03CA01",
    "C07AB07",
    "C08CA01",
    "C09AA02",
    "C09CA01",
    "C10AA01",
    "D01AC08",
    "D07AC15",
    "H02AB06",
    "J01CA04",
    "J01CR02",
    "J01DB01",
    "J01DD04",
    "J01FA10",
    "J01MA02",
    "J01XA01",
    "J04AB02",
    "J05AF07",
    "J05AF10",
    "J05AG03",
    "L01XE01",
    "M01AB05",
    "M01AE01",
    "N02BE01",
    "N03AX12",
    "N05BA01",
    "N06AB06",
    "P01BA02",
    "P01BF01",
    "P02BA01",
    "R03AC02",
    "S01ED01",
]
NON_ANTIBACTERIAL_ATC_CODES = [code for code in ATC_CODES if not code.startswith("J01")]
INN_POOL = [
    "abacavir",
    "abiraterone",
    "aceclofenac",
    "acyclovir",
    "adalimumab",
    "albendazole",
    "allopurinol",
    "amikacin",
    "amiodarone",
    "amlodipine",
    "amoxicillin",
    "ampicillin",
    "artemether",
    "ceftriaxone",
    "artesunate",
    "atenolol",
    "atorvastatin",
    "azathioprine",
    "baclofen",
    "beclometasone",
    "benzylpenicillin",
    "bisoprolol",
    "budesonide",
    "captopril",
    "carbamazepine",
    "carvedilol",
    "cefalexin",
    "cefixime",
    "cefpodoxime",
    "cetirizine",
    "chloramphenicol",
    "ciprofloxacin",
    "clarithromycin",
    "clindamycin",
    "clobetasol",
    "clopidogrel",
    "clotrimazole",
    "codeine",
    "cyclophosphamide",
    "cyclosporine",
    "dapagliflozin",
    "dexamethasone",
    "diazepam",
    "diclofenac",
    "digoxin",
    "diltiazem",
    "donepezil",
    "doxycycline",
    "efavirenz",
    "enalapril",
    "enoxaparin",
    "erythromycin",
    "esomeprazole",
    "etoricoxib",
    "famotidine",
    "fluconazole",
    "fluoxetine",
    "fluticasone",
    "furosemide",
    "gabapentin",
    "gentamicin",
    "glibenclamide",
    "gliclazide",
    "haloperidol",
    "hydrochlorothiazide",
    "hydroxychloroquine",
    "imatinib",
    "insulin glargine",
    "isoniazid",
    "isosorbide mononitrate",
    "ivermectin",
    "ketoconazole",
    "levofloxacin",
    "levothyroxine",
    "linezolid",
    "lisinopril",
    "loratadine",
    "losartan",
    "metformin",
    "methotrexate",
    "metoprolol",
    "metronidazole",
    "moxifloxacin",
    "naproxen",
    "nevirapine",
    "nifedipine",
    "nitrofurantoin",
    "omeprazole",
    "ondansetron",
    "oseltamivir",
    "paracetamol",
    "phenobarbital",
    "piperacillin",
    "praziquantel",
    "prednisolone",
    "propranolol",
    "pyrazinamide",
    "ritonavir",
    "salbutamol",
    "sertraline",
    "simvastatin",
    "spironolactone",
    "sulfamethoxazole",
    "tamoxifen",
    "tenofovir disoproxil",
    "timolol",
    "tramadol",
    "trimethoprim",
    "valaciclovir",
    "valsartan",
    "vancomycin",
    "warfarin",
    "zidovudine",
    "azithromycin",
    "rifampicin",
    "lamivudine",
    "dolutegravir",
    "ibuprofen",
    "colistin",
    "cefiderocol",
]
PROTECTED_NAME_POOL = [
    "Panadoll",
    "Amoxacil",
    "MetforMax",
    "RifaSafe",
    "Ceftrax",
    "Artesunex",
]
MANUFACTURERS = [
    "Kampala Biopharma Ltd",
    "Dodoma Pharma Works",
    "Gaborone Life Sciences",
    "Ouagadougou Therapeutics",
    "Nile Generic Medicines",
    "Kagera Formulations",
    "Mwanza Pharma Industries",
    "Bukoba Therapeutics",
    "Kilimanjaro Formulations",
    "Dar Medica Labs",
    "Uganda Essential Medicines Plant",
    "Entebbe Pharma Solutions",
    "Jinja Bioactive Manufacturing",
    "Bobo-Dioulasso Pharma SA",
    "Sahel Essential Drugs Company",
    "Ouaga Public Health Formulations",
    "Botswana Clinical Manufacturing",
    "Gaborone Sterile Products",
    "Francistown Pharma Ventures",
    "Kalahari Generics",
    "EastAfrica Health Products",
    "AfriCure Therapeutics",
    "Global Access Generics",
    "PanRegional Pharma Holdings",
]
STUDY_INDICATIONS = [
    "uncomplicated malaria",
    "community acquired pneumonia",
    "type 2 diabetes",
    "moderate pain",
    "bacterial skin infection",
]
ANTIBIOTIC_PROFILES = {
    "amikacin": {
        "atc_code": "J01GB06",
        "aware_category": "watch",
        "watch_comparator": "gentamicin",
    },
    "amoxicillin": {
        "atc_code": "J01CA04",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "ampicillin": {
        "atc_code": "J01CA01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "azithromycin": {
        "atc_code": "J01FA10",
        "aware_category": "watch",
        "watch_comparator": "clarithromycin",
    },
    "benzylpenicillin": {
        "atc_code": "J01CE01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "cefalexin": {
        "atc_code": "J01DB01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "cefiderocol": {
        "atc_code": "J01DI02",
        "aware_category": "reserve",
        "watch_comparator": "not_applicable",
    },
    "cefixime": {
        "atc_code": "J01DD08",
        "aware_category": "watch",
        "watch_comparator": "ceftriaxone",
    },
    "cefpodoxime": {
        "atc_code": "J01DD13",
        "aware_category": "watch",
        "watch_comparator": "ceftriaxone",
    },
    "ceftriaxone": {
        "atc_code": "J01DD04",
        "aware_category": "watch",
        "watch_comparator": "cefotaxime",
    },
    "chloramphenicol": {
        "atc_code": "J01BA01",
        "aware_category": "watch",
        "watch_comparator": "thiamphenicol",
    },
    "ciprofloxacin": {
        "atc_code": "J01MA02",
        "aware_category": "watch",
        "watch_comparator": "ofloxacin",
    },
    "clarithromycin": {
        "atc_code": "J01FA09",
        "aware_category": "watch",
        "watch_comparator": "erythromycin",
    },
    "clindamycin": {
        "atc_code": "J01FF01",
        "aware_category": "watch",
        "watch_comparator": "lincomycin",
    },
    "colistin": {
        "atc_code": "J01XB01",
        "aware_category": "reserve",
        "watch_comparator": "not_applicable",
    },
    "doxycycline": {
        "atc_code": "J01AA02",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "erythromycin": {
        "atc_code": "J01FA01",
        "aware_category": "watch",
        "watch_comparator": "azithromycin",
    },
    "gentamicin": {
        "atc_code": "J01GB03",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "levofloxacin": {
        "atc_code": "J01MA12",
        "aware_category": "watch",
        "watch_comparator": "ciprofloxacin",
    },
    "linezolid": {
        "atc_code": "J01XX08",
        "aware_category": "reserve",
        "watch_comparator": "not_applicable",
    },
    "metronidazole": {
        "atc_code": "J01XD01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "moxifloxacin": {
        "atc_code": "J01MA14",
        "aware_category": "watch",
        "watch_comparator": "levofloxacin",
    },
    "nitrofurantoin": {
        "atc_code": "J01XE01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "piperacillin": {
        "atc_code": "J01CA12",
        "aware_category": "watch",
        "watch_comparator": "ampicillin",
    },
    "sulfamethoxazole": {
        "atc_code": "J01EC01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "trimethoprim": {
        "atc_code": "J01EA01",
        "aware_category": "access",
        "watch_comparator": "not_applicable",
    },
    "vancomycin": {
        "atc_code": "J01XA01",
        "aware_category": "reserve",
        "watch_comparator": "not_applicable",
    },
}

SECTION_SPECS = [
    {
        "id": "m1_application_admin",
        "module": "1",
        "title": "Application Form and Administrative Information",
        "min_chars": 900,
        "max_chars": 2200,
        "critical": True,
    },
    {
        "id": "m1_manufacturer_gmp",
        "module": "1",
        "title": "Manufacturer and GMP Evidence",
        "min_chars": 700,
        "max_chars": 1800,
        "critical": True,
    },
    {
        "id": "m1_product_information",
        "module": "1",
        "title": "Product Information and Naming",
        "min_chars": 600,
        "max_chars": 1600,
        "critical": True,
    },
    {
        "id": "m2_quality_overall_summary",
        "module": "2",
        "title": "Quality Overall Summary",
        "min_chars": 1200,
        "max_chars": 3000,
        "critical": True,
    },
    {
        "id": "m2_clinical_overview",
        "module": "2",
        "title": "Clinical Overview and Benefit-Risk Summary",
        "min_chars": 900,
        "max_chars": 2500,
        "critical": True,
    },
    {
        "id": "m3_api_quality",
        "module": "3",
        "title": "API Quality and Control Strategy",
        "min_chars": 1300,
        "max_chars": 3200,
        "critical": True,
    },
    {
        "id": "m3_fpp_manufacturing",
        "module": "3",
        "title": "FPP Manufacturing Process and Controls",
        "min_chars": 1200,
        "max_chars": 3000,
        "critical": True,
    },
    {
        "id": "m3_stability",
        "module": "3",
        "title": "Stability and Shelf-Life Justification",
        "min_chars": 900,
        "max_chars": 2600,
        "critical": True,
    },
    {
        "id": "m4_nonclinical_summary",
        "module": "4",
        "title": "Nonclinical Study Summary",
        "min_chars": 700,
        "max_chars": 2000,
        "critical": False,
    },
    {
        "id": "m5_trial_listing",
        "module": "5",
        "title": "Tabular Listing of Clinical Studies",
        "min_chars": 700,
        "max_chars": 1800,
        "critical": True,
    },
    {
        "id": "m5_pivotal_trial_reports",
        "module": "5",
        "title": "Pivotal Clinical Trial Reports",
        "min_chars": 1500,
        "max_chars": 3800,
        "critical": True,
    },
    {
        "id": "m5_bioequivalence",
        "module": "5",
        "title": "Biopharmaceutics and Bioequivalence Evidence",
        "min_chars": 600,
        "max_chars": 1800,
        "critical": False,
    },
]
SECTION_SPEC_MAP = {s["id"]: s for s in SECTION_SPECS}

MAJOR_ERROR_TAGS = {
    "inn_infringement",
    "clinical_missing",
    "clinical_failed",
    "gmp_non_compliant",
    "gmp_certificate_expired",
    "missing_critical_section",
    "cross_section_inconsistency",
}

DEFECT_WEIGHTS = {
    "inn_infringement": 0.16,
    "clinical_missing": 0.16,
    "clinical_failed": 0.14,
    "gmp_non_compliant": 0.16,
    "gmp_outdated": 0.12,
    "gmp_certificate_expired": 0.10,
    "missing_section": 0.10,
    "short_section": 0.06,
}

FILLER_SENTENCES = [
    "All referenced documents are available in the dossier annex and traceable by section identifier.",
    "The applicant confirms alignment with applicable technical guidance and regional submission standards.",
    "Method validation records and quality controls were reviewed for internal consistency.",
    "Risk mitigation activities are documented with ownership, timelines, and follow-up checkpoints.",
    "Where applicable, protocol deviations were assessed for impact on interpretation of outcomes.",
]


@dataclass
class Context:
    dossier_id: str
    country: str
    submission_date: str
    product_name: str
    inn_name: str
    atc_code: str
    dosage_form: str
    strength: str
    applicant: str
    manufacturer: str
    facility_country: str
    gmp_status: str
    gmp_last_inspection: str
    gmp_certificate_number: str
    gmp_certificate_expiry: str
    clinical_outcome: str
    clinical_data_available: bool
    pivotal_trial_count: int
    indication: str
    therapeutic_area: str
    aware_category: str
    amr_unmet_need: str
    targets_mdr_pathogen: bool
    glass_resistance_trend: str
    similarity_to_existing_watch: str
    existing_watch_comparator: str
    defects: List[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic CTD-style dossiers with labels")
    parser.add_argument("--num-dossiers", type=int, default=1200)
    parser.add_argument("--compliant-rate", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dossier-review-AI-assistant/synthetic_data/output"),
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--emit-section-text",
        action="store_true",
        help="Write one text file per dossier for parser and retrieval testing",
    )
    parser.add_argument(
        "--emit-pdf",
        dest="emit_pdf",
        action="store_true",
        default=True,
        help="Write one PDF dossier per record (default: enabled)",
    )
    parser.add_argument(
        "--no-emit-pdf",
        dest="emit_pdf",
        action="store_false",
        help="Disable PDF generation",
    )
    return parser.parse_args()


def weighted_sample_without_replacement(rng: random.Random, weights: Dict[str, float], k: int) -> List[str]:
    pool = list(weights.items())
    selected: List[str] = []
    remaining = dict(pool)
    for _ in range(min(k, len(remaining))):
        total = sum(remaining.values())
        pick = rng.uniform(0, total)
        upto = 0.0
        chosen = None
        for key, weight in remaining.items():
            upto += weight
            if upto >= pick:
                chosen = key
                break
        if chosen is None:
            chosen = next(iter(remaining.keys()))
        selected.append(chosen)
        remaining.pop(chosen)
    return selected


def random_date_in_past(rng: random.Random, years_back_min: int, years_back_max: int) -> date:
    days = rng.randint(years_back_min * 365, years_back_max * 365)
    return date.today() - timedelta(days=days)


def generate_brand_name(rng: random.Random) -> str:
    prefixes = ["Nova", "Cura", "Vita", "Medi", "Thera", "Heal", "Pharma"]
    suffixes = ["line", "plus", "care", "med", "fex", "zyme", "aid"]
    return f"{rng.choice(prefixes)}{rng.choice(suffixes)}"


def build_antibacterial_profile(rng: random.Random, inn: str) -> Dict[str, str | bool]:
    profile = ANTIBIOTIC_PROFILES[inn]
    aware_category = str(profile["aware_category"])
    comparator = str(profile["watch_comparator"])

    if aware_category == "reserve":
        return {
            "therapeutic_area": "antibacterial",
            "atc_code": str(profile["atc_code"]),
            "aware_category": aware_category,
            "amr_unmet_need": rng.choices(["critical", "high"], weights=[0.75, 0.25], k=1)[0],
            "targets_mdr_pathogen": True,
            "glass_resistance_trend": rng.choices(["rising", "stable"], weights=[0.8, 0.2], k=1)[0],
            "similarity_to_existing_watch": "not_applicable",
            "existing_watch_comparator": comparator,
        }

    if aware_category == "watch":
        similarity = rng.choices(["high", "moderate", "low"], weights=[0.35, 0.35, 0.30], k=1)[0]
        if similarity == "high":
            glass_trend = rng.choices(["rising", "stable"], weights=[0.8, 0.2], k=1)[0]
        else:
            glass_trend = rng.choices(["rising", "stable", "declining"], weights=[0.4, 0.45, 0.15], k=1)[0]
        return {
            "therapeutic_area": "antibacterial",
            "atc_code": str(profile["atc_code"]),
            "aware_category": aware_category,
            "amr_unmet_need": rng.choices(["routine", "moderate"], weights=[0.75, 0.25], k=1)[0],
            "targets_mdr_pathogen": False,
            "glass_resistance_trend": glass_trend,
            "similarity_to_existing_watch": similarity,
            "existing_watch_comparator": comparator,
        }

    return {
        "therapeutic_area": "antibacterial",
        "atc_code": str(profile["atc_code"]),
        "aware_category": aware_category,
        "amr_unmet_need": "routine",
        "targets_mdr_pathogen": False,
        "glass_resistance_trend": rng.choices(["stable", "declining", "rising"], weights=[0.55, 0.25, 0.20], k=1)[0],
        "similarity_to_existing_watch": "low",
        "existing_watch_comparator": comparator,
    }


def amr_product_statement(ctx: Context) -> str:
    if ctx.aware_category == "reserve":
        return (
            " WHO AWaRe category: Reserve. Indication is restricted to suspected or confirmed MDR infections "
            "after Access options have failed or are not suitable. The dossier proposes specialist-only use "
            "under restricted authorization controls."
        )
    if ctx.aware_category == "watch":
        return (
            f" WHO AWaRe category: Watch. Similarity to existing Watch comparator {ctx.existing_watch_comparator} "
            f"is assessed as {ctx.similarity_to_existing_watch}. Stewardship materials describe controlled use "
            "to limit cross-resistance pressure."
        )
    if ctx.aware_category == "access":
        return (
            " WHO AWaRe category: Access. Product is positioned for routine antibacterial use with standard "
            "stewardship monitoring and local resistance surveillance."
        )
    return ""


def amr_clinical_statement(ctx: Context) -> str:
    if ctx.aware_category == "reserve":
        return (
            f" The clinical program addresses a {ctx.amr_unmet_need} unmet need in MDR infections. "
            f"GLASS-aligned surveillance trend is {ctx.glass_resistance_trend}, and enrollment focused on "
            "patients with limited remaining treatment options."
        )
    if ctx.aware_category == "watch":
        return (
            f" GLASS-aligned surveillance trend is {ctx.glass_resistance_trend}, and cross-resistance risk "
            f"relative to {ctx.existing_watch_comparator} is assessed as {ctx.similarity_to_existing_watch}."
        )
    if ctx.aware_category == "access":
        return (
            f" GLASS-aligned surveillance trend is {ctx.glass_resistance_trend}, supporting continued first-line "
            "or second-line use with routine monitoring."
        )
    return ""


def build_base_context(rng: random.Random) -> Context:
    inn = rng.choice(INN_POOL)
    antibacterial_profile = ANTIBIOTIC_PROFILES.get(inn)
    if antibacterial_profile:
        amr_profile = build_antibacterial_profile(rng, inn)
        atc_code = str(amr_profile["atc_code"])
        therapeutic_area = str(amr_profile["therapeutic_area"])
        aware_category = str(amr_profile["aware_category"])
        amr_unmet_need = str(amr_profile["amr_unmet_need"])
        targets_mdr_pathogen = bool(amr_profile["targets_mdr_pathogen"])
        glass_resistance_trend = str(amr_profile["glass_resistance_trend"])
        similarity_to_existing_watch = str(amr_profile["similarity_to_existing_watch"])
        existing_watch_comparator = str(amr_profile["existing_watch_comparator"])
    else:
        atc_code = rng.choice(NON_ANTIBACTERIAL_ATC_CODES)
        therapeutic_area = "non_antibacterial"
        aware_category = "not_applicable"
        amr_unmet_need = "not_applicable"
        targets_mdr_pathogen = False
        glass_resistance_trend = "not_applicable"
        similarity_to_existing_watch = "not_applicable"
        existing_watch_comparator = "not_applicable"
    inspection_date = random_date_in_past(rng, 0, 2)
    certificate_expiry = inspection_date + timedelta(days=rng.randint(500, 1000))
    submission = random_date_in_past(rng, 0, 1)
    ctx = Context(
        dossier_id=f"DOS-{uuid.uuid4().hex[:10].upper()}",
        country=rng.choice(COUNTRIES),
        submission_date=submission.isoformat(),
        product_name=generate_brand_name(rng),
        inn_name=inn,
        atc_code=atc_code,
        dosage_form=rng.choice(DOSAGE_FORMS),
        strength=f"{rng.choice([125, 250, 500, 850, 1000])} mg",
        applicant=f"{rng.choice(APPLICANT_PREFIXES)} Therapeutics",
        manufacturer=rng.choice(MANUFACTURERS),
        facility_country=rng.choice(COUNTRIES),
        gmp_status="compliant",
        gmp_last_inspection=inspection_date.isoformat(),
        gmp_certificate_number=f"GMP-{rng.randint(100000, 999999)}",
        gmp_certificate_expiry=certificate_expiry.isoformat(),
        clinical_outcome="endpoint_met",
        clinical_data_available=True,
        pivotal_trial_count=rng.randint(2, 4),
        indication=rng.choice(STUDY_INDICATIONS),
        therapeutic_area=therapeutic_area,
        aware_category=aware_category,
        amr_unmet_need=amr_unmet_need,
        targets_mdr_pathogen=targets_mdr_pathogen,
        glass_resistance_trend=glass_resistance_trend,
        similarity_to_existing_watch=similarity_to_existing_watch,
        existing_watch_comparator=existing_watch_comparator,
        defects=[],
    )
    return ctx


def pad_to_target_length(rng: random.Random, text: str, target_length: int) -> str:
    out = text.strip()
    while len(out) < target_length:
        out += " " + rng.choice(FILLER_SENTENCES)
    return out[:target_length]


def compose_section_text(rng: random.Random, section_id: str, ctx: Context, target_length: int) -> str:
    templates = {
        "m1_application_admin": (
            f"Application dossier for {ctx.product_name} ({ctx.inn_name}) submitted on {ctx.submission_date} "
            f"to the {ctx.country} authority. Applicant: {ctx.applicant}. Proposed dosage form: {ctx.dosage_form}; "
            f"strength: {ctx.strength}; ATC: {ctx.atc_code}. Administrative declarations, legal attestations, and "
            "regional forms are complete and signed."
        ),
        "m1_manufacturer_gmp": (
            f"Primary manufacturing site: {ctx.manufacturer} in {ctx.facility_country}. Latest GMP inspection date: "
            f"{ctx.gmp_last_inspection}. GMP status: {ctx.gmp_status}. GMP certificate number: {ctx.gmp_certificate_number}; "
            f"certificate expiry: {ctx.gmp_certificate_expiry}. CAPA evidence and inspection observations are attached."
        ),
        "m1_product_information": (
            f"Proposed product name is {ctx.product_name}. INN is {ctx.inn_name}. Labeling, SmPC/PIL content, contraindications, "
            "dosing information, and medication error mitigation statements are included with linguistic review notes."
            f"{amr_product_statement(ctx)}"
        ),
        "m2_quality_overall_summary": (
            f"Quality Overall Summary for API {ctx.inn_name} describes specification strategy, control points, impurity profile, "
            "batch analysis, and release criteria. Manufacturing process validation confirms consistency and quality attributes."
        ),
        "m2_clinical_overview": (
            f"Clinical overview summarizes therapeutic rationale for {ctx.indication}. Pivotal program includes "
            f"{ctx.pivotal_trial_count} studies. Reported outcome category: {ctx.clinical_outcome}. Benefit-risk narrative, "
            f"safety findings, and subgroup considerations are included.{amr_clinical_statement(ctx)}"
        ),
        "m3_api_quality": (
            f"API quality section provides synthesis route, material controls, specification limits, analytical validation, "
            "stability profile, and impurity control strategy. Data support batch-to-batch consistency and quality assurance."
        ),
        "m3_fpp_manufacturing": (
            "FPP process includes critical process parameters, in-process controls, hold time studies, packaging validation, "
            "and process performance qualification reports with traceability to quality risk management outputs."
        ),
        "m3_stability": (
            "Stability program includes accelerated and long-term conditions, trend analysis, protocol adherence, and "
            "shelf-life assignment justification with out-of-trend management records."
        ),
        "m4_nonclinical_summary": (
            "Nonclinical data summarize pharmacology, toxicology, local tolerance, and safety margins. Study quality and "
            "species relevance are discussed with limitations and translational considerations."
        ),
        "m5_trial_listing": (
            f"Clinical study table lists pivotal and supportive studies for {ctx.indication}, including protocol IDs, trial phase, "
            "sample sizes, randomization details, and completion status."
            f"{amr_clinical_statement(ctx)}"
        ),
        "m5_pivotal_trial_reports": (
            f"Pivotal trial reports document primary and secondary endpoints, statistical analysis plan adherence, "
            f"and outcome category {ctx.clinical_outcome}. Safety outcomes, serious adverse events, and subgroup analyses are included."
            f"{amr_clinical_statement(ctx)}"
        ),
        "m5_bioequivalence": (
            "Biopharmaceutics section includes comparative dissolution, bioequivalence evidence, analytical method validation, "
            "and protocol deviations with impact assessment."
        ),
    }
    base_text = templates[section_id]
    return pad_to_target_length(rng, base_text, target_length)


def create_base_sections(rng: random.Random, ctx: Context) -> Dict[str, Dict]:
    sections: Dict[str, Dict] = {}
    for spec in SECTION_SPECS:
        target = rng.randint(spec["min_chars"], spec["max_chars"])
        text = compose_section_text(rng, spec["id"], ctx, target)
        sections[spec["id"]] = {
            "section_id": spec["id"],
            "module": spec["module"],
            "title": spec["title"],
            "text": text,
            "error_tags": [],
            "critical": spec["critical"],
            "min_chars": spec["min_chars"],
            "max_chars": spec["max_chars"],
        }
    return sections


def set_section_text(
    rng: random.Random,
    sections: Dict[str, Dict],
    section_id: str,
    text: str,
    keep_within_length_bounds: bool = True,
) -> None:
    spec = SECTION_SPEC_MAP[section_id]
    if keep_within_length_bounds:
        target = rng.randint(spec["min_chars"], spec["max_chars"])
        text = pad_to_target_length(rng, text, target)
    sections[section_id]["text"] = text


def mark_error(sections: Dict[str, Dict], section_id: str, error_tag: str) -> None:
    if section_id not in sections:
        return
    if error_tag not in sections[section_id]["error_tags"]:
        sections[section_id]["error_tags"].append(error_tag)


def apply_inn_infringement(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    ctx.product_name = rng.choice(PROTECTED_NAME_POOL)
    ctx.defects.append("inn_infringement")
    set_section_text(
        rng,
        sections,
        "m1_product_information",
        f"Proposed product name is {ctx.product_name}, with INN listed as {ctx.inn_name}. "
        "Name similarity review indicates potential confusion with protected and existing nomenclature classes. "
        "The submission did not include a sufficient differentiation and risk mitigation plan for look-alike and "
        "sound-alike naming concerns."
    )
    set_section_text(
        rng,
        sections,
        "m1_application_admin",
        f"Application dossier for {ctx.product_name} ({ctx.inn_name}) submitted on {ctx.submission_date} "
        f"to the {ctx.country} authority. Applicant: {ctx.applicant}. Proposed dosage form: {ctx.dosage_form}; "
        f"strength: {ctx.strength}; ATC: {ctx.atc_code}. Administrative declarations are present but naming "
        "conflict remediation documents are incomplete.",
    )
    mark_error(sections, "m1_product_information", "inn_infringement")


def apply_clinical_missing(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    ctx.clinical_data_available = False
    ctx.clinical_outcome = "missing_evidence"
    ctx.pivotal_trial_count = 0
    ctx.defects.append("clinical_missing")
    sections["m5_pivotal_trial_reports"]["text"] = ""
    mark_error(sections, "m5_pivotal_trial_reports", "clinical_missing")
    set_section_text(
        rng,
        sections,
        "m2_clinical_overview",
        f"Clinical overview for {ctx.indication} indicates pivotal efficacy data are not available at submission time. "
        "Benefit-risk cannot be concluded pending full clinical study reports and verified endpoint analyses.",
    )
    set_section_text(
        rng,
        sections,
        "m5_trial_listing",
        "Tabular listing indicates planned or ongoing studies, but no completed pivotal study reports were provided "
        "in this submission package.",
    )
    mark_error(sections, "m2_clinical_overview", "clinical_missing")


def apply_clinical_failed(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    ctx.clinical_data_available = True
    ctx.clinical_outcome = "endpoint_not_met"
    ctx.defects.append("clinical_failed")
    set_section_text(
        rng,
        sections,
        "m5_pivotal_trial_reports",
        "Pivotal trial analysis indicates primary endpoint was not met in the intent-to-treat population. "
        "Estimated treatment effect did not reach pre-specified significance and sensitivity analyses were inconsistent.",
    )
    set_section_text(
        rng,
        sections,
        "m2_clinical_overview",
        f"Clinical overview for {ctx.indication} indicates pivotal efficacy outcomes did not meet the primary endpoint. "
        "Current evidence does not support a favorable benefit-risk conclusion for authorization.",
    )
    mark_error(sections, "m5_pivotal_trial_reports", "clinical_failed")
    mark_error(sections, "m2_clinical_overview", "clinical_failed")


def apply_gmp_non_compliant(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    ctx.gmp_status = "non_compliant"
    old_date = random_date_in_past(rng, 2, 5)
    ctx.gmp_last_inspection = old_date.isoformat()
    ctx.defects.append("gmp_non_compliant")
    set_section_text(
        rng,
        sections,
        "m1_manufacturer_gmp",
        f"Inspection findings for {ctx.manufacturer} identified critical GMP deficiencies. "
        f"Inspection date: {ctx.gmp_last_inspection}. Status: non_compliant. "
        "CAPA package is incomplete and verification of closure is pending.",
    )
    mark_error(sections, "m1_manufacturer_gmp", "gmp_non_compliant")


def apply_gmp_outdated(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    old_date = random_date_in_past(rng, 4, 7)
    ctx.gmp_last_inspection = old_date.isoformat()
    ctx.defects.append("gmp_outdated")
    set_section_text(
        rng,
        sections,
        "m1_manufacturer_gmp",
        f"Latest GMP inspection date is {ctx.gmp_last_inspection}. "
        "No recent inspection evidence was provided for the required review window.",
    )
    mark_error(sections, "m1_manufacturer_gmp", "gmp_outdated")


def apply_gmp_certificate_expired(rng: random.Random, ctx: Context, sections: Dict[str, Dict]) -> None:
    expired = random_date_in_past(rng, 1, 3)
    ctx.gmp_certificate_expiry = expired.isoformat()
    ctx.defects.append("gmp_certificate_expired")
    set_section_text(
        rng,
        sections,
        "m1_manufacturer_gmp",
        f"Primary manufacturing site: {ctx.manufacturer} in {ctx.facility_country}. Latest GMP inspection date: "
        f"{ctx.gmp_last_inspection}. GMP status: {ctx.gmp_status}. GMP certificate number: {ctx.gmp_certificate_number}; "
        f"certificate expiry: {ctx.gmp_certificate_expiry}. Certificate has expired and requires renewal before authorization.",
    )
    mark_error(sections, "m1_manufacturer_gmp", "gmp_certificate_expired")


def apply_missing_section(
    rng: random.Random, sections: Dict[str, Dict], blocked_section_ids: set[str] | None = None
) -> None:
    blocked = blocked_section_ids or set()
    candidates = [s["id"] for s in SECTION_SPECS if s["id"] not in blocked]
    if not candidates:
        candidates = [s["id"] for s in SECTION_SPECS]
    missing_section_id = rng.choice(candidates)
    sections[missing_section_id]["text"] = ""
    if sections[missing_section_id]["critical"]:
        mark_error(sections, missing_section_id, "missing_critical_section")
    else:
        mark_error(sections, missing_section_id, "missing_section")


def apply_short_section(rng: random.Random, sections: Dict[str, Dict]) -> None:
    # Restrict short-section defects to non-critical or lower-risk sections to avoid implausible extreme stacking.
    candidates = ["m4_nonclinical_summary", "m5_bioequivalence", "m2_quality_overall_summary"]
    section_id = rng.choice(candidates)
    sections[section_id]["text"] = "Insufficient detail provided in this section."
    mark_error(sections, section_id, "insufficient_detail")


def normalize_defect_selection(rng: random.Random, selected: List[str]) -> List[str]:
    selected_set = set(selected)

    # Clinical missing and clinical failed are mutually exclusive states.
    if "clinical_missing" in selected_set and "clinical_failed" in selected_set:
        selected_set.remove(rng.choice(["clinical_missing", "clinical_failed"]))

    # If a site is non-compliant, outdated status is redundant in this synthetic policy profile.
    if "gmp_non_compliant" in selected_set and "gmp_outdated" in selected_set:
        selected_set.remove("gmp_outdated")

    return list(selected_set)


def apply_defects(rng: random.Random, ctx: Context, sections: Dict[str, Dict], compliant: bool) -> None:
    if compliant:
        return

    defect_count = rng.randint(1, 3)
    selected = weighted_sample_without_replacement(rng, DEFECT_WEIGHTS, defect_count)
    selected = normalize_defect_selection(rng, selected)
    protected_for_missing: set[str] = set()
    if "inn_infringement" in selected:
        protected_for_missing.add("m1_product_information")
    if "clinical_missing" in selected or "clinical_failed" in selected:
        protected_for_missing.update({"m2_clinical_overview", "m5_trial_listing", "m5_pivotal_trial_reports"})
    if any(k in selected for k in ("gmp_non_compliant", "gmp_outdated", "gmp_certificate_expired")):
        protected_for_missing.add("m1_manufacturer_gmp")

    for defect in selected:
        if defect == "inn_infringement":
            apply_inn_infringement(rng, ctx, sections)
        elif defect == "clinical_missing":
            apply_clinical_missing(rng, ctx, sections)
        elif defect == "clinical_failed":
            apply_clinical_failed(rng, ctx, sections)
        elif defect == "gmp_non_compliant":
            apply_gmp_non_compliant(rng, ctx, sections)
        elif defect == "gmp_outdated":
            apply_gmp_outdated(rng, ctx, sections)
        elif defect == "gmp_certificate_expired":
            apply_gmp_certificate_expired(rng, ctx, sections)
        elif defect == "missing_section":
            apply_missing_section(rng, sections, blocked_section_ids=protected_for_missing)
            ctx.defects.append("missing_section")
        elif defect == "short_section":
            apply_short_section(rng, sections)
            ctx.defects.append("short_section")


def section_correctness(presence: str, length_status: str, error_tags: List[str], critical: bool) -> str:
    if presence == "missing":
        return "incorrect"

    if any(tag in MAJOR_ERROR_TAGS for tag in error_tags):
        return "incorrect"

    if length_status in {"too_short", "too_long"}:
        return "incorrect" if critical else "partial"

    if error_tags:
        return "partial"

    return "correct"


def compute_section_metadata(section: Dict) -> Dict:
    text = section["text"]
    char_count = len(text)
    if text.strip() == "":
        presence = "missing"
        length_status = "missing"
    elif char_count < section["min_chars"]:
        presence = "present"
        length_status = "too_short"
    elif char_count > section["max_chars"]:
        presence = "present"
        length_status = "too_long"
    else:
        presence = "present"
        length_status = "length_ok"

    correctness = section_correctness(presence, length_status, section["error_tags"], section["critical"])
    return {
        "presence": presence,
        "length_status": length_status,
        "correctness": correctness,
        "char_count": char_count,
    }


def is_recent_inspection(last_inspection_iso: str) -> bool:
    last_date = date.fromisoformat(last_inspection_iso)
    return (date.today() - last_date).days <= 3 * 365


def certificate_valid(expiry_iso: str) -> str:
    expiry = date.fromisoformat(expiry_iso)
    return "valid" if expiry >= date.today() else "expired"


def validate_internal_consistency(ctx: Context, sections: Dict[str, Dict]) -> List[str]:
    issues: List[str] = []
    clinical_text = sections["m5_pivotal_trial_reports"]["text"].strip()

    if ctx.clinical_data_available and ctx.clinical_outcome == "missing_evidence":
        issues.append("clinical_data_available=true but clinical_outcome=missing_evidence")
    if (not ctx.clinical_data_available) and ctx.clinical_outcome != "missing_evidence":
        issues.append("clinical_data_available=false but clinical_outcome is not missing_evidence")
    if (not ctx.clinical_data_available) and clinical_text != "":
        issues.append("clinical_data_available=false but pivotal report section is not empty")
    if "clinical_missing" in ctx.defects and "clinical_failed" in ctx.defects:
        issues.append("mutually exclusive clinical defects both present")

    if ctx.gmp_status == "non_compliant" and "gmp_non_compliant" not in ctx.defects:
        issues.append("gmp_status=non_compliant without gmp_non_compliant defect tag")
    if ctx.gmp_status == "compliant" and "gmp_non_compliant" in ctx.defects:
        issues.append("gmp_status=compliant but gmp_non_compliant defect tag present")

    if "inn_infringement" in ctx.defects:
        if "inn_infringement" not in sections["m1_product_information"]["error_tags"]:
            issues.append("inn_infringement defect missing on product information section")

    if ctx.aware_category == "reserve" and not ctx.targets_mdr_pathogen:
        issues.append("reserve AWaRe category requires targets_mdr_pathogen=true")
    if ctx.aware_category == "watch" and ctx.similarity_to_existing_watch == "high":
        if ctx.existing_watch_comparator == "not_applicable":
            issues.append("watch high-similarity dossier missing comparator")
    if ctx.aware_category == "not_applicable":
        if ctx.glass_resistance_trend != "not_applicable":
            issues.append("non-antibacterial dossier has AMR resistance trend")
        if ctx.amr_unmet_need != "not_applicable":
            issues.append("non-antibacterial dossier has AMR unmet need")

    return issues


def holistic_decision(
    sections: Dict[str, Dict],
    inn_infringement: bool,
    clinical_outcome: str,
    clinical_data_available: bool,
    gmp_status: str,
    gmp_recent: bool,
    gmp_cert_validity: str,
    aware_category: str,
    amr_unmet_need: str,
    targets_mdr_pathogen: bool,
    glass_resistance_trend: str,
    similarity_to_existing_watch: str,
) -> Tuple[str, float]:
    incorrect_critical = 0
    partial_sections = 0
    for section in sections.values():
        md = section["metadata"]
        if section["critical"] and md["correctness"] == "incorrect":
            incorrect_critical += 1
        if md["correctness"] == "partial":
            partial_sections += 1

    high_risk = (
        inn_infringement
        or gmp_status == "non_compliant"
        or gmp_cert_validity == "expired"
        or clinical_outcome == "endpoint_not_met"
    )
    reserve_fast_track = (
        aware_category == "reserve"
        and targets_mdr_pathogen
        and amr_unmet_need in {"high", "critical"}
    )
    watch_similarity_guard = (
        aware_category == "watch"
        and similarity_to_existing_watch == "high"
        and glass_resistance_trend == "rising"
    )

    if high_risk or incorrect_critical >= 2:
        return "reject_and_return", 0.92

    if watch_similarity_guard:
        return "deep_review", 0.74

    if (not clinical_data_available) or (not gmp_recent) or incorrect_critical == 1:
        return "deep_review", 0.78

    if reserve_fast_track:
        return "fast_track", 0.34

    if partial_sections >= 1:
        return "standard_review", 0.64

    return "fast_track", 0.28


def build_dossier_record(rng: random.Random, compliant: bool) -> Dict:
    ctx = build_base_context(rng)
    sections = create_base_sections(rng, ctx)

    apply_defects(rng, ctx, sections, compliant)
    consistency_issues = validate_internal_consistency(ctx, sections)
    if consistency_issues:
        raise ValueError(f"Inconsistent synthetic dossier state: {', '.join(consistency_issues)}")

    for sec in sections.values():
        sec["metadata"] = compute_section_metadata(sec)

    gmp_recent = is_recent_inspection(ctx.gmp_last_inspection)
    gmp_cert_validity = certificate_valid(ctx.gmp_certificate_expiry)
    inn_infringement = "inn_infringement" in ctx.defects

    policy_label, risk_score = holistic_decision(
        sections=sections,
        inn_infringement=inn_infringement,
        clinical_outcome=ctx.clinical_outcome,
        clinical_data_available=ctx.clinical_data_available,
        gmp_status=ctx.gmp_status,
        gmp_recent=gmp_recent,
        gmp_cert_validity=gmp_cert_validity,
        aware_category=ctx.aware_category,
        amr_unmet_need=ctx.amr_unmet_need,
        targets_mdr_pathogen=ctx.targets_mdr_pathogen,
        glass_resistance_trend=ctx.glass_resistance_trend,
        similarity_to_existing_watch=ctx.similarity_to_existing_watch,
    )

    section_items = []
    for spec in SECTION_SPECS:
        sec = sections[spec["id"]]
        section_items.append(
            {
                "section_id": sec["section_id"],
                "module": sec["module"],
                "title": sec["title"],
                "text": sec["text"],
                "critical": sec["critical"],
                "constraints": {
                    "min_chars": sec["min_chars"],
                    "max_chars": sec["max_chars"],
                },
                "labels": {
                    "presence": sec["metadata"]["presence"],
                    "length_status": sec["metadata"]["length_status"],
                    "correctness": sec["metadata"]["correctness"],
                    "error_tags": sec["error_tags"],
                },
                "metrics": {
                    "char_count": sec["metadata"]["char_count"],
                },
            }
        )

    section_summary = {
        "correct": sum(1 for s in section_items if s["labels"]["correctness"] == "correct"),
        "partial": sum(1 for s in section_items if s["labels"]["correctness"] == "partial"),
        "incorrect": sum(1 for s in section_items if s["labels"]["correctness"] == "incorrect"),
    }

    return {
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
        "policy_signals": {
            "inn_infringement": inn_infringement,
            "gmp_inspection_status": ctx.gmp_status,
            "gmp_inspection_recent": gmp_recent,
            "gmp_certificate_validity": gmp_cert_validity,
            "clinical_data_available": ctx.clinical_data_available,
            "pivotal_trial_outcome": ctx.clinical_outcome,
            "aware_category": ctx.aware_category,
            "amr_unmet_need": ctx.amr_unmet_need,
            "targets_mdr_pathogen": ctx.targets_mdr_pathogen,
            "glass_resistance_trend": ctx.glass_resistance_trend,
            "similarity_to_existing_watch": ctx.similarity_to_existing_watch,
            "existing_watch_comparator": ctx.existing_watch_comparator,
        },
        "gmp_details": {
            "last_inspection_date": ctx.gmp_last_inspection,
            "certificate_number": ctx.gmp_certificate_number,
            "certificate_expiry": ctx.gmp_certificate_expiry,
        },
        "clinical_details": {
            "pivotal_trial_count": ctx.pivotal_trial_count,
            "indication": ctx.indication,
            "outcome": ctx.clinical_outcome,
        },
        "sections": section_items,
        "labels": {
            "holistic_policy_decision": policy_label,
            "risk_score": round(risk_score, 3),
            "compliant_submission": compliant,
        },
        "quality_summary": section_summary,
        "provenance": {
            "synthetic": True,
            "defect_modes": sorted(set(ctx.defects)),
        },
    }


def write_section_labels_csv(path: Path, dossiers: List[Dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dossier_id",
                "country",
                "section_id",
                "module",
                "presence",
                "length_status",
                "correctness",
                "error_tags",
                "char_count",
                "min_chars",
                "max_chars",
                "critical",
            ]
        )
        for dossier in dossiers:
            for sec in dossier["sections"]:
                writer.writerow(
                    [
                        dossier["dossier_id"],
                        dossier["country"],
                        sec["section_id"],
                        sec["module"],
                        sec["labels"]["presence"],
                        sec["labels"]["length_status"],
                        sec["labels"]["correctness"],
                        "|".join(sec["labels"]["error_tags"]),
                        sec["metrics"]["char_count"],
                        sec["constraints"]["min_chars"],
                        sec["constraints"]["max_chars"],
                        sec["critical"],
                    ]
                )


def write_holistic_labels_csv(path: Path, dossiers: List[Dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dossier_id",
                "country",
                "holistic_policy_decision",
                "risk_score",
                "compliant_submission",
                "inn_infringement",
                "gmp_inspection_status",
                "gmp_inspection_recent",
                "gmp_certificate_validity",
                "clinical_data_available",
                "pivotal_trial_outcome",
                "aware_category",
                "amr_unmet_need",
                "targets_mdr_pathogen",
                "glass_resistance_trend",
                "similarity_to_existing_watch",
                "existing_watch_comparator",
                "defect_modes",
            ]
        )
        for dossier in dossiers:
            p = dossier["policy_signals"]
            writer.writerow(
                [
                    dossier["dossier_id"],
                    dossier["country"],
                    dossier["labels"]["holistic_policy_decision"],
                    dossier["labels"]["risk_score"],
                    dossier["labels"]["compliant_submission"],
                    p["inn_infringement"],
                    p["gmp_inspection_status"],
                    p["gmp_inspection_recent"],
                    p["gmp_certificate_validity"],
                    p["clinical_data_available"],
                    p["pivotal_trial_outcome"],
                    p["aware_category"],
                    p["amr_unmet_need"],
                    p["targets_mdr_pathogen"],
                    p["glass_resistance_trend"],
                    p["similarity_to_existing_watch"],
                    p["existing_watch_comparator"],
                    "|".join(dossier["provenance"]["defect_modes"]),
                ]
            )


def write_jsonl(path: Path, dossiers: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for dossier in dossiers:
            f.write(json.dumps(dossier, ensure_ascii=True) + "\n")


def write_manifest(path: Path, dossiers: List[Dict], args: argparse.Namespace) -> None:
    holistic_counts: Dict[str, int] = {}
    defect_counts: Dict[str, int] = {}
    for dossier in dossiers:
        label = dossier["labels"]["holistic_policy_decision"]
        holistic_counts[label] = holistic_counts.get(label, 0) + 1
        for defect in dossier["provenance"]["defect_modes"]:
            defect_counts[defect] = defect_counts.get(defect, 0) + 1

    manifest = {
        "num_dossiers": len(dossiers),
        "seed": args.seed,
        "compliant_rate_target": args.compliant_rate,
        "countries": COUNTRIES,
        "holistic_distribution": holistic_counts,
        "defect_distribution": defect_counts,
        "files": {
            "dossiers_jsonl": "dossiers.jsonl",
            "section_labels_csv": "section_labels.csv",
            "holistic_labels_csv": "holistic_labels.csv",
            "dossiers_pdf_dir": "dossiers_pdf" if args.emit_pdf else None,
        },
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_text_exports(output_dir: Path, dossiers: List[Dict]) -> None:
    text_dir = output_dir / "dossiers_txt"
    text_dir.mkdir(parents=True, exist_ok=True)
    for dossier in dossiers:
        out = [
            f"DOSSIER ID: {dossier['dossier_id']}",
            f"COUNTRY: {dossier['country']}",
            f"PRODUCT: {dossier['product']['product_name']} ({dossier['product']['inn_name']})",
            f"HOLISTIC LABEL: {dossier['labels']['holistic_policy_decision']}",
            "",
        ]
        for section in dossier["sections"]:
            out.append(f"## {section['section_id']} - {section['title']}")
            out.append(section["text"] if section["text"].strip() else "[MISSING SECTION]")
            out.append("")
        (text_dir / f"{dossier['dossier_id']}.txt").write_text("\n".join(out), encoding="utf-8")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _split_lines_for_pdf(lines: List[str], max_chars: int = 95) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(line, width=max_chars, break_long_words=True, replace_whitespace=False))
    return wrapped


def _dossier_to_pdf_lines(dossier: Dict) -> List[str]:
    lines: List[str] = []
    lines.append("REGULATORY DOSSIER SUBMISSION")
    lines.append(f"Dossier ID: {dossier['dossier_id']}")
    lines.append(f"Country: {dossier['country']}")
    lines.append(f"Submission Date: {dossier['submission_date']}")
    lines.append(
        f"Product: {dossier['product']['product_name']} ({dossier['product']['inn_name']}) | "
        f"ATC: {dossier['product']['atc_code']} | Strength: {dossier['product']['strength']}"
    )
    lines.append(
        f"Applicant: {dossier['organization']['applicant']} | "
        f"Manufacturer: {dossier['organization']['manufacturer']}"
    )
    lines.append(
        f"Policy Label: {dossier['labels']['holistic_policy_decision']} | "
        f"Risk Score: {dossier['labels']['risk_score']}"
    )
    policy_signals = dossier["policy_signals"]
    lines.append(
        "AMR Stewardship: "
        f"AWaRe={policy_signals['aware_category']} | "
        f"Unmet Need={policy_signals['amr_unmet_need']} | "
        f"GLASS Trend={policy_signals['glass_resistance_trend']} | "
        f"Watch Similarity={policy_signals['similarity_to_existing_watch']}"
    )
    lines.append("")
    lines.append("SECTION CONTENT")
    lines.append("")
    for section in dossier["sections"]:
        lines.append(f"[{section['module']}] {section['section_id']} - {section['title']}")
        lines.append(
            f"Labels: presence={section['labels']['presence']}; "
            f"length={section['labels']['length_status']}; "
            f"correctness={section['labels']['correctness']}"
        )
        if section["labels"]["error_tags"]:
            lines.append(f"Error tags: {', '.join(section['labels']['error_tags'])}")
        content = section["text"].strip() if section["text"].strip() else "[MISSING SECTION]"
        lines.append(content)
        lines.append("")
    return _split_lines_for_pdf(lines)


def _write_basic_pdf(path: Path, lines: List[str]) -> None:
    page_width = 612
    page_height = 792
    left_margin = 50
    top_start = 760
    bottom_margin = 50
    leading = 14
    max_lines_per_page = max(1, (top_start - bottom_margin) // leading)

    pages: List[List[str]] = [
        lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)
    ] or [[]]

    objects: List[str] = []

    def add_obj(content: str) -> int:
        objects.append(content)
        return len(objects)

    catalog_num = add_obj("<< /Type /Catalog /Pages 2 0 R >>")
    pages_num = add_obj("<< /Type /Pages /Count 0 /Kids [] >>")
    font_num = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_nums: List[int] = []
    for page_lines in pages:
        stream_parts = ["BT", "/F1 10 Tf"]
        y = top_start
        for line in page_lines:
            escaped = _pdf_escape(line)
            stream_parts.append(f"1 0 0 1 {left_margin} {y} Tm ({escaped}) Tj")
            y -= leading
        stream_parts.append("ET")
        stream = "\n".join(stream_parts)
        stream_bytes = stream.encode("latin-1", errors="replace")
        content_num = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream"
        )
        page_num = add_obj(
            (
                f"<< /Type /Page /Parent {pages_num} 0 R "
                f"/MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
                f"/Contents {content_num} 0 R >>"
            )
        )
        page_nums.append(page_num)

    kids = " ".join(f"{num} 0 R" for num in page_nums)
    objects[pages_num - 1] = f"<< /Type /Pages /Count {len(page_nums)} /Kids [{kids}] >>"
    objects[catalog_num - 1] = f"<< /Type /Catalog /Pages {pages_num} 0 R >>"

    header = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = ""
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(header.encode("latin-1")) + len(body.encode("latin-1")))
        body += f"{i} 0 obj\n{obj}\nendobj\n"

    xref_offset = len(header.encode("latin-1")) + len(body.encode("latin-1"))
    xref = [f"xref\n0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n")
    xref_blob = "".join(xref)
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_num} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf_bytes = (header + body + xref_blob + trailer).encode("latin-1", errors="replace")
    path.write_bytes(pdf_bytes)


def write_pdf_exports(output_dir: Path, dossiers: List[Dict]) -> None:
    pdf_dir = output_dir / "dossiers_pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for dossier in dossiers:
        lines = _dossier_to_pdf_lines(dossier)
        _write_basic_pdf(pdf_dir / f"{dossier['dossier_id']}.pdf", lines)


def main() -> None:
    args = parse_args()
    if args.num_dossiers <= 0:
        raise ValueError("--num-dossiers must be > 0")
    if not 0.0 <= args.compliant_rate <= 1.0:
        raise ValueError("--compliant-rate must be between 0 and 1")

    rng = random.Random(args.seed)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    dossiers: List[Dict] = []
    for _ in range(args.num_dossiers):
        compliant = rng.random() < args.compliant_rate
        dossier = None
        for _attempt in range(10):
            try:
                dossier = build_dossier_record(rng, compliant=compliant)
                break
            except ValueError:
                continue
        if dossier is None:
            raise RuntimeError("Failed to generate a consistent dossier after 10 attempts")
        dossiers.append(dossier)

    write_jsonl(output_dir / "dossiers.jsonl", dossiers)
    write_section_labels_csv(output_dir / "section_labels.csv", dossiers)
    write_holistic_labels_csv(output_dir / "holistic_labels.csv", dossiers)
    write_manifest(output_dir / "manifest.json", dossiers, args)

    if args.emit_pdf:
        write_pdf_exports(output_dir, dossiers)

    if args.emit_section_text:
        write_text_exports(output_dir, dossiers)

    print(f"Generated {len(dossiers)} dossiers at: {output_dir}")


if __name__ == "__main__":
    main()
