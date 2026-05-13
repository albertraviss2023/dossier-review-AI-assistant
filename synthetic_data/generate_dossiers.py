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
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

COUNTRIES = ["Tanzania", "Burkina Faso", "Uganda", "Botswana"]
DOSAGE_FORMS = ["tablet", "capsule", "suspension", "injectable", "cream", "inhaler", "eye drops", "syrup"]
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
    "Data were analyzed using a mixed-effects model for repeated measures, adjusting for baseline covariates.",
    "The analytical procedure was validated in accordance with ICH Q2(R1) guidelines, demonstrating acceptable accuracy, precision, and specificity.",
    "Adverse events were coded using the Medical Dictionary for Regulatory Activities (MedDRA) version 24.0.",
    "Pharmacokinetic parameters were derived using non-compartmental analysis from the concentration-time profiles.",
    "The risk management plan includes routine pharmacovigilance and proposed educational materials for healthcare professionals.",
    "Stability testing was conducted in climatic zones III and IV, reflecting the intended distribution markets.",
    "The container closure system consists of PVC/PVDC-Aluminum blisters, compliant with pharmacopoeial standards.",
    "A randomized, double-blind, parallel-group study design was employed to minimize selection and observer bias.",
    "Statistical significance was set at an alpha level of 0.05, and all tests were two-sided.",
    "The manufacturing site operates under a fully implemented Pharmaceutical Quality System (PQS) aligned with ICH Q10.",
]

SECTION_FILLER_SENTENCES = {
    "m1_application_admin": [
        "Administrative cover letters, declarations, and fee records were cross-checked against the submission index.",
        "Applicant authorization documents and legal attestations were reconciled against the named manufacturing parties.",
        "Regional administrative forms were checked for signature completeness and dossier version alignment.",
        "The proposed prescribing information and patient information leaflet have been translated into local languages.",
        "A comprehensive table of contents and glossary of abbreviations are provided to facilitate regulatory review.",
    ],
    "m1_manufacturer_gmp": [
        "Inspection history, CAPA closure records, and site responsibilities were reconciled across the manufacturing chain.",
        "The GMP evidence package includes certificate status, inspection scope, and manufacturing-site accountability records.",
        "Site quality-system commitments were compared against the proposed commercial manufacturing activities.",
        "Recent regulatory inspections yielded no critical observations, and all major findings have been effectively closed.",
        "Batch manufacturing records and standard operating procedures (SOPs) are maintained and archived on-site.",
    ],
    "m2_clinical_overview": [
        "Clinical interpretation focuses on whether efficacy, safety, and benefit-risk conclusions are supported by the submitted evidence.",
        "The clinical overview links the therapeutic rationale to the pivotal evidence package and the proposed indication.",
        "Benefit-risk language was reviewed for consistency with the submitted efficacy and safety summaries.",
        "The target population demographics are broadly representative of the intended commercial patient cohort.",
        "No new safety signals were identified during the extended open-label follow-up period.",
    ],
    "m3_api_quality": [
        "The API package links specification limits to validated analytical methods and impurity-control decisions.",
        "Critical material attributes and control strategy elements were reviewed for consistency across the quality dossier.",
        "Batch analysis, validation, and impurity management records support the proposed API quality framework.",
        "Residual solvents and elemental impurities are controlled well below ICH Q3C and Q3D permissible daily exposures.",
        "The synthetic route involves three well-characterized steps with defined starting materials and isolated intermediates.",
    ],
    "m5_pivotal_trial_reports": [
        "The pivotal study narratives align endpoint definitions, analysis populations, and outcome interpretation.",
        "Clinical study reports document protocol adherence, endpoint handling, and safety interpretation in the target population.",
        "The trial reports connect efficacy conclusions to the prespecified analysis framework and observed safety findings.",
        "The primary efficacy endpoint was met, demonstrating a statistically significant improvement over placebo (p < 0.001).",
        "Discontinuations due to treatment-emergent adverse events (TEAEs) were low and balanced across all study arms.",
    ],
}

INN_PRODUCT_PROFILES = {
    "abacavir": {"atc_code": "J05AF06", "forms": ["tablet"], "strengths": ["300 mg"]},
    "acyclovir": {"atc_code": "J05AB01", "forms": ["tablet", "suspension"], "strengths": ["200 mg", "400 mg"]},
    "albendazole": {"atc_code": "P02CA03", "forms": ["tablet", "suspension"], "strengths": ["200 mg", "400 mg"]},
    "amlodipine": {"atc_code": "C08CA01", "forms": ["tablet"], "strengths": ["5 mg", "10 mg"]},
    "artemether": {"atc_code": "P01BE01", "forms": ["tablet", "injectable"], "strengths": ["20 mg", "80 mg/mL"]},
    "atenolol": {"atc_code": "C07AB03", "forms": ["tablet"], "strengths": ["50 mg", "100 mg"]},
    "atorvastatin": {"atc_code": "C10AA05", "forms": ["tablet"], "strengths": ["10 mg", "20 mg", "40 mg"]},
    "beclometasone": {"atc_code": "R03BA01", "forms": ["inhaler", "cream"], "strengths": ["100 mcg/dose", "0.05%"]},
    "bisoprolol": {"atc_code": "C07AB07", "forms": ["tablet"], "strengths": ["2.5 mg", "5 mg", "10 mg"]},
    "budesonide": {"atc_code": "R03BA02", "forms": ["inhaler"], "strengths": ["100 mcg/dose", "200 mcg/dose"]},
    "carbamazepine": {"atc_code": "N03AF01", "forms": ["tablet", "suspension"], "strengths": ["200 mg", "400 mg"]},
    "cetirizine": {"atc_code": "R06AE07", "forms": ["tablet", "syrup"], "strengths": ["10 mg", "1 mg/mL"]},
    "clobetasol": {"atc_code": "D07AD01", "forms": ["cream"], "strengths": ["0.05%"]},
    "clopidogrel": {"atc_code": "B01AC04", "forms": ["tablet"], "strengths": ["75 mg"]},
    "clotrimazole": {"atc_code": "D01AC01", "forms": ["cream"], "strengths": ["1%"]},
    "dapagliflozin": {"atc_code": "A10BK01", "forms": ["tablet"], "strengths": ["5 mg", "10 mg"]},
    "dexamethasone": {"atc_code": "H02AB02", "forms": ["tablet", "injectable"], "strengths": ["4 mg", "4 mg/mL"]},
    "diclofenac": {"atc_code": "M01AB05", "forms": ["tablet", "injectable"], "strengths": ["50 mg", "75 mg/3 mL"]},
    "efavirenz": {"atc_code": "J05AG03", "forms": ["tablet"], "strengths": ["600 mg"]},
    "enalapril": {"atc_code": "C09AA02", "forms": ["tablet"], "strengths": ["5 mg", "10 mg", "20 mg"]},
    "enoxaparin": {"atc_code": "B01AB05", "forms": ["injectable"], "strengths": ["40 mg/0.4 mL", "60 mg/0.6 mL"]},
    "esomeprazole": {"atc_code": "A02BC05", "forms": ["capsule", "injectable"], "strengths": ["20 mg", "40 mg"]},
    "fluconazole": {"atc_code": "J02AC01", "forms": ["tablet", "suspension"], "strengths": ["150 mg", "200 mg", "50 mg/5 mL"]},
    "fluoxetine": {"atc_code": "N06AB03", "forms": ["capsule"], "strengths": ["20 mg"]},
    "fluticasone": {"atc_code": "R03BA05", "forms": ["inhaler"], "strengths": ["125 mcg/dose", "250 mcg/dose"]},
    "furosemide": {"atc_code": "C03CA01", "forms": ["tablet", "injectable"], "strengths": ["40 mg", "10 mg/mL"]},
    "hydrochlorothiazide": {"atc_code": "C03AA03", "forms": ["tablet"], "strengths": ["12.5 mg", "25 mg"]},
    "hydroxychloroquine": {"atc_code": "P01BA02", "forms": ["tablet"], "strengths": ["200 mg"]},
    "ibuprofen": {"atc_code": "M01AE01", "forms": ["tablet", "suspension"], "strengths": ["200 mg", "400 mg", "100 mg/5 mL"]},
    "imatinib": {"atc_code": "L01EA01", "forms": ["tablet"], "strengths": ["100 mg", "400 mg"]},
    "insulin glargine": {"atc_code": "A10AE04", "forms": ["injectable"], "strengths": ["100 units/mL"]},
    "isoniazid": {"atc_code": "J04AC01", "forms": ["tablet"], "strengths": ["100 mg", "300 mg"]},
    "ivermectin": {"atc_code": "P02CF01", "forms": ["tablet"], "strengths": ["3 mg", "6 mg"]},
    "ketoconazole": {"atc_code": "D01AC08", "forms": ["cream", "tablet"], "strengths": ["2%", "200 mg"]},
    "levothyroxine": {"atc_code": "H03AA01", "forms": ["tablet"], "strengths": ["50 mcg", "100 mcg"]},
    "loratadine": {"atc_code": "R06AX13", "forms": ["tablet", "syrup"], "strengths": ["10 mg", "1 mg/mL"]},
    "losartan": {"atc_code": "C09CA01", "forms": ["tablet"], "strengths": ["50 mg", "100 mg"]},
    "metformin": {"atc_code": "A10BA02", "forms": ["tablet"], "strengths": ["500 mg", "850 mg", "1000 mg"]},
    "metoprolol": {"atc_code": "C07AB02", "forms": ["tablet"], "strengths": ["50 mg", "100 mg"]},
    "naproxen": {"atc_code": "M01AE02", "forms": ["tablet"], "strengths": ["250 mg", "500 mg"]},
    "nifedipine": {"atc_code": "C08CA05", "forms": ["tablet"], "strengths": ["20 mg", "30 mg"]},
    "omeprazole": {"atc_code": "A02BC01", "forms": ["capsule"], "strengths": ["20 mg", "40 mg"]},
    "ondansetron": {"atc_code": "A04AA01", "forms": ["tablet", "injectable"], "strengths": ["4 mg", "8 mg"]},
    "oseltamivir": {"atc_code": "J05AH02", "forms": ["capsule", "suspension"], "strengths": ["30 mg", "75 mg"]},
    "paracetamol": {"atc_code": "N02BE01", "forms": ["tablet", "suspension"], "strengths": ["500 mg", "1000 mg", "120 mg/5 mL"]},
    "phenobarbital": {"atc_code": "N03AA02", "forms": ["tablet"], "strengths": ["30 mg", "60 mg"]},
    "praziquantel": {"atc_code": "P02BA01", "forms": ["tablet"], "strengths": ["600 mg"]},
    "prednisolone": {"atc_code": "H02AB06", "forms": ["tablet"], "strengths": ["5 mg", "20 mg"]},
    "propranolol": {"atc_code": "C07AA05", "forms": ["tablet"], "strengths": ["40 mg", "80 mg"]},
    "pyrazinamide": {"atc_code": "J04AK01", "forms": ["tablet"], "strengths": ["500 mg"]},
    "ritonavir": {"atc_code": "J05AE03", "forms": ["tablet"], "strengths": ["100 mg"]},
    "salbutamol": {"atc_code": "R03AC02", "forms": ["inhaler"], "strengths": ["100 mcg/dose"]},
    "sertraline": {"atc_code": "N06AB06", "forms": ["tablet"], "strengths": ["50 mg", "100 mg"]},
    "simvastatin": {"atc_code": "C10AA01", "forms": ["tablet"], "strengths": ["20 mg", "40 mg"]},
    "spironolactone": {"atc_code": "C03DA01", "forms": ["tablet"], "strengths": ["25 mg", "50 mg"]},
    "tamoxifen": {"atc_code": "L02BA01", "forms": ["tablet"], "strengths": ["20 mg"]},
    "tenofovir disoproxil": {"atc_code": "J05AF07", "forms": ["tablet"], "strengths": ["300 mg"]},
    "timolol": {"atc_code": "S01ED01", "forms": ["eye drops"], "strengths": ["0.25%", "0.5%"]},
    "tramadol": {"atc_code": "N02AX02", "forms": ["capsule", "injectable"], "strengths": ["50 mg", "100 mg/2 mL"]},
    "valaciclovir": {"atc_code": "J05AB11", "forms": ["tablet"], "strengths": ["500 mg"]},
    "valsartan": {"atc_code": "C09CA03", "forms": ["tablet"], "strengths": ["80 mg", "160 mg"]},
    "warfarin": {"atc_code": "B01AA03", "forms": ["tablet"], "strengths": ["5 mg"]},
    "zidovudine": {"atc_code": "J05AF01", "forms": ["tablet", "syrup"], "strengths": ["300 mg", "50 mg/5 mL"]},
}


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
    used_filler_sentences: set[str] = field(default_factory=set)


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


def generate_brand_name_for_inn(rng: random.Random, inn: str) -> str:
    stem = "".join(part[:4] for part in inn.split())[:6].capitalize()
    suffixes = ["ra", "via", "med", "care", "nova", "zen"]
    return f"{stem}{rng.choice(suffixes)}"


def resolve_non_antibacterial_profile(inn: str) -> dict[str, list[str] | str]:
    profile = INN_PRODUCT_PROFILES.get(inn)
    if profile:
        return profile

    topical_inns = {"clobetasol", "clotrimazole", "ketoconazole"}
    inhaled_inns = {"salbutamol", "budesonide", "fluticasone"}
    ophthalmic_inns = {"timolol"}
    injectable_inns = {"insulin glargine", "enoxaparin"}
    antihypertensives = {"captopril", "carvedilol", "diltiazem", "digoxin", "isosorbide mononitrate", "lisinopril"}
    analgesics = {"aceclofenac", "codeine", "etoricoxib"}
    psychiatric_neuro = {"baclofen", "diazepam", "donepezil", "gabapentin", "haloperidol"}
    endocrine_metabolic = {"allopurinol", "glibenclamide", "gliclazide"}
    oncology_immunology = {"abiraterone", "adalimumab", "azathioprine", "cyclophosphamide", "cyclosporine", "methotrexate"}
    antiviral_agents = {"lamivudine", "nevirapine", "dolutegravir"}
    gi_agents = {"famotidine"}

    if inn in topical_inns:
        return {"atc_code": "D01AC08", "forms": ["cream"], "strengths": ["1%"]}
    if inn in inhaled_inns:
        return {"atc_code": "R03AC02", "forms": ["inhaler"], "strengths": ["100 mcg/dose"]}
    if inn in ophthalmic_inns:
        return {"atc_code": "S01ED01", "forms": ["eye drops"], "strengths": ["0.5%"]}
    if inn in injectable_inns:
        return {"atc_code": "B01AB05", "forms": ["injectable"], "strengths": ["100 units/mL"]}
    if inn in antihypertensives:
        return {"atc_code": "C09AA02", "forms": ["tablet"], "strengths": ["5 mg", "10 mg", "20 mg"]}
    if inn in analgesics:
        return {"atc_code": "M01AE01", "forms": ["tablet", "capsule"], "strengths": ["50 mg", "100 mg", "200 mg"]}
    if inn in psychiatric_neuro:
        return {"atc_code": "N05BA01", "forms": ["tablet"], "strengths": ["5 mg", "10 mg", "25 mg", "100 mg"]}
    if inn in endocrine_metabolic:
        return {"atc_code": "A10BB12", "forms": ["tablet"], "strengths": ["5 mg", "80 mg", "100 mg", "300 mg"]}
    if inn in oncology_immunology:
        return {"atc_code": "L01XE01", "forms": ["tablet", "injectable"], "strengths": ["2.5 mg", "50 mg", "100 mg", "500 mg"]}
    if inn in antiviral_agents:
        return {"atc_code": "J05AF10", "forms": ["tablet"], "strengths": ["50 mg", "150 mg", "300 mg"]}
    if inn in gi_agents:
        return {"atc_code": "A02BA03", "forms": ["tablet"], "strengths": ["20 mg", "40 mg"]}
    return {"atc_code": "A10BA02", "forms": ["tablet"], "strengths": ["500 mg", "850 mg"]}


def resolve_antibacterial_form_strength(inn: str) -> tuple[list[str], list[str]]:
    injectable_only = {"amikacin", "benzylpenicillin", "ceftriaxone", "cefiderocol", "colistin", "gentamicin", "vancomycin", "piperacillin"}
    oral_and_injectable = {"linezolid", "metronidazole", "levofloxacin"}
    pediatric_oral = {"amoxicillin", "ampicillin", "azithromycin", "cefalexin", "cefixime", "cefpodoxime", "clarithromycin"}
    fluoroquinolones = {"ciprofloxacin", "levofloxacin", "moxifloxacin"}

    if inn in injectable_only:
        return ["injectable"], ["1 g/vial", "500 mg/vial"]
    if inn in oral_and_injectable:
        return ["tablet", "injectable"], ["500 mg", "600 mg", "400 mg/200 mL"]
    if inn in pediatric_oral:
        return ["tablet", "capsule", "suspension"], ["250 mg", "500 mg", "125 mg/5 mL"]
    if inn in fluoroquinolones:
        return ["tablet", "injectable"], ["500 mg", "750 mg", "5 mg/mL"]
    return ["tablet", "capsule"], ["250 mg", "500 mg"]


def strength_matches_form(dosage_form: str, strength: str) -> bool:
    lowered = strength.lower()
    if dosage_form in {"tablet", "capsule"}:
        return all(token not in lowered for token in ("/ml", "/5 ml", "/200 ml", "/0.4 ml", "/0.6 ml", "/vial", "%", "dose", "units/ml"))
    if dosage_form in {"suspension", "syrup"}:
        return any(token in lowered for token in ("/ml", "/5 ml"))
    if dosage_form == "injectable":
        return any(token in lowered for token in ("/ml", "/vial", "units/ml"))
    if dosage_form in {"cream", "eye drops"}:
        return "%" in lowered
    if dosage_form == "inhaler":
        return "dose" in lowered
    return True


def resolve_product_profile(rng: random.Random, inn: str) -> tuple[str, str, str, str]:
    antibacterial_profile = ANTIBIOTIC_PROFILES.get(inn)
    if antibacterial_profile:
        atc_code = str(antibacterial_profile["atc_code"])
        forms, strengths = resolve_antibacterial_form_strength(inn)
        dosage_form = rng.choice(forms)
        compatible_strengths = [strength for strength in strengths if strength_matches_form(dosage_form, strength)]
        strength = rng.choice(compatible_strengths or strengths)
        return atc_code, dosage_form, strength, generate_brand_name_for_inn(rng, inn)

    profile = resolve_non_antibacterial_profile(inn)
    dosage_form = rng.choice(list(profile["forms"]))
    strengths = list(profile["strengths"])
    compatible_strengths = [strength for strength in strengths if strength_matches_form(dosage_form, strength)]
    strength = rng.choice(compatible_strengths or strengths)
    return str(profile["atc_code"]), dosage_form, strength, generate_brand_name_for_inn(rng, inn)


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
    atc_code, dosage_form, strength, product_name = resolve_product_profile(rng, inn)
    antibacterial_profile = ANTIBIOTIC_PROFILES.get(inn)
    if antibacterial_profile:
        amr_profile = build_antibacterial_profile(rng, inn)
        therapeutic_area = str(amr_profile["therapeutic_area"])
        aware_category = str(amr_profile["aware_category"])
        amr_unmet_need = str(amr_profile["amr_unmet_need"])
        targets_mdr_pathogen = bool(amr_profile["targets_mdr_pathogen"])
        glass_resistance_trend = str(amr_profile["glass_resistance_trend"])
        similarity_to_existing_watch = str(amr_profile["similarity_to_existing_watch"])
        existing_watch_comparator = str(amr_profile["existing_watch_comparator"])
    else:
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
        product_name=product_name,
        inn_name=inn,
        atc_code=atc_code,
        dosage_form=dosage_form,
        strength=strength,
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
    filler_pool = list(FILLER_SENTENCES)
    while len(out) < target_length:
        unused = [sentence for sentence in filler_pool if sentence not in out]
        next_sentence = rng.choice(unused or filler_pool)
        out += " " + next_sentence
    return out[:target_length]


def pad_section_text(rng: random.Random, section_id: str, text: str, target_length: int) -> str:
    out = text.strip()
    section_fillers = SECTION_FILLER_SENTENCES.get(section_id, [])
    filler_pool = section_fillers + FILLER_SENTENCES
    while len(out) < target_length:
        unused = [sentence for sentence in filler_pool if sentence not in out]
        next_sentence = rng.choice(unused or filler_pool)
        out += " " + next_sentence
    return out[:target_length]


def compose_section_text(rng: random.Random, section_id: str, ctx: Context, target_length: int) -> str:
    templates = {
        "m1_application_admin": (
            f"This dossier constitutes a formal application for Marketing Authorization of {ctx.product_name} ({ctx.inn_name}) "
            f"submitted on {ctx.submission_date} to the national regulatory authority of {ctx.country}. "
            f"The applicant, {ctx.applicant}, formally requests approval for the commercial distribution of this medicinal product. "
            f"The proposed pharmaceutical form is {ctx.dosage_form} with a strength of {ctx.strength}, "
            f"classified under ATC code {ctx.atc_code}. All required administrative declarations, legal attestations, "
            f"letters of authorization, and regional application forms have been completed, signed by the responsible "
            f"Qualified Person, and appended to Module 1."
        ),
        "m1_manufacturer_gmp": (
            f"The primary commercial manufacturing site for the finished pharmaceutical product is {ctx.manufacturer}, "
            f"located in {ctx.facility_country}. The facility was subject to a comprehensive GMP inspection by a recognized "
            f"stringent regulatory authority. The latest inspection concluded on {ctx.gmp_last_inspection}, resulting in a "
            f"formal compliance status of '{ctx.gmp_status}'. The active GMP certificate number is {ctx.gmp_certificate_number}, "
            f"which remains valid until {ctx.gmp_certificate_expiry}. Site master files, a summary of recent inspection "
            f"observations, and evidence of completed Corrective and Preventive Actions (CAPA) are included in the annex."
        ),
        "m1_product_information": (
            f"The proposed proprietary name for this medicinal product is {ctx.product_name}, containing the active "
            f"pharmaceutical ingredient {ctx.inn_name}. The draft Summary of Product Characteristics (SmPC), Patient "
            f"Information Leaflet (PIL), and primary/secondary packaging labels are provided for review. These documents "
            f"detail the approved therapeutic indications, posology, contraindications, special warnings, and precautions "
            f"for use. A comprehensive risk management plan to minimize medication errors is also submitted. "
            f"{amr_product_statement(ctx)}"
        ),
        "m2_quality_overall_summary": (
            f"This Quality Overall Summary (QOS) provides a critical evaluation of the chemistry, manufacturing, and "
            f"controls (CMC) data for {ctx.inn_name}. The control strategy justifies the proposed specifications for both "
            f"the active substance and the finished product, emphasizing critical quality attributes (CQAs) and critical "
            f"process parameters (CPPs). Impurity profiles, including degradation products and potential genotoxic impurities, "
            f"have been thoroughly characterized. Batch analysis data from three commercial-scale validation batches "
            f"demonstrate consistent manufacturing performance and compliance with all release criteria."
        ),
        "m2_clinical_overview": (
            f"The Clinical Overview synthesizes the efficacy and safety data supporting the use of {ctx.product_name} "
            f"for the treatment of {ctx.indication}. The pivotal clinical development program comprised {ctx.pivotal_trial_count} "
            f"well-controlled studies. Based on the integrated analysis, the reported clinical outcome category is '{ctx.clinical_outcome}'. "
            f"The overall benefit-risk profile is considered highly favorable for the target patient population. "
            f"Safety findings were consistent with the known pharmacological class effects, and appropriate risk minimization "
            f"measures have been integrated into the proposed prescribing information. {amr_clinical_statement(ctx)}"
        ),
        "m3_api_quality": (
            f"The active pharmaceutical ingredient (API) section details the complete synthesis route, starting from "
            f"well-defined regulatory starting materials. Robust in-process controls and intermediate specifications "
            f"ensure the consistent quality of the final drug substance. The analytical procedures used for release and "
            f"stability testing have been fully validated for accuracy, precision, linearity, and robustness. "
            f"The impurity control strategy adequately addresses organic impurities, residual solvents, and elemental "
            f"impurities in accordance with current ICH guidelines. Forced degradation studies confirm the "
            f"stability-indicating nature of the assay methods."
        ),
        "m3_fpp_manufacturing": (
            f"The finished pharmaceutical product (FPP) manufacturing process utilizes standard, scalable unit operations. "
            f"A formal quality risk assessment (e.g., FMEA) was conducted to identify critical process parameters (CPPs) "
            f"that impact critical quality attributes (CQAs). Process performance qualification (PPQ) reports for three "
            f"consecutive commercial-scale batches verify that the process is maintained in a state of control. "
            f"In-process controls, intermediate hold-time studies, and packaging validation data are presented to "
            f"substantiate the robustness and reproducibility of the commercial manufacturing operations."
        ),
        "m3_stability": (
            f"A comprehensive stability program has been executed to justify the proposed shelf-life and storage conditions. "
            f"Data from both accelerated (40°C/75% RH for 6 months) and long-term storage conditions (spanning up to 36 months) "
            f"are presented for multiple primary stability batches. Statistical evaluation using linear regression and "
            f"poolability tests confirms that degradation trends remain well within the acceptable specification limits. "
            f"Photostability and freeze-thaw cycling studies demonstrate that the product does not require specific "
            f"handling precautions. A post-approval stability protocol commitment is included."
        ),
        "m4_nonclinical_summary": (
            f"The nonclinical testing program evaluated the primary pharmacodynamics, secondary pharmacodynamics, "
            f"safety pharmacology, and comprehensive toxicology profile of the compound. Repeat-dose toxicity studies "
            f"in two mammalian species established clear no-observed-adverse-effect levels (NOAELs). "
            f"Genotoxicity testing (Ames and in vivo micronucleus assays) yielded negative results. "
            f"Reproductive and developmental toxicity studies revealed no teratogenic signals at clinically relevant exposures. "
            f"The calculated safety margins support the proposed clinical dosing regimen without major safety concerns."
        ),
        "m5_trial_listing": (
            f"The tabular listing of clinical studies provides a comprehensive inventory of all trials conducted in support "
            f"of the proposed indication ({ctx.indication}). This includes Phase I pharmacokinetic/pharmacodynamic studies, "
            f"Phase II dose-finding studies, and the pivotal Phase III efficacy and safety trials. "
            f"For each study, the table details the protocol identifier, study design, randomization ratio, "
            f"number of enrolled subjects, study duration, and current completion status. {amr_clinical_statement(ctx)}"
        ),
        "m5_pivotal_trial_reports": (
            f"Detailed clinical study reports (CSRs) for the pivotal efficacy trials are provided. "
            f"These randomized, double-blind, actively-controlled trials evaluated the primary and secondary endpoints "
            f"in accordance with the pre-specified statistical analysis plan (SAP). "
            f"The trials resulted in a formal outcome category of '{ctx.clinical_outcome}', demonstrating robust "
            f"treatment effects in the intent-to-treat (ITT) and per-protocol populations. "
            f"Subgroup analyses across age, gender, and baseline disease severity strata were consistent with the "
            f"primary findings. Serious adverse events (SAEs) and discontinuations were systematically analyzed and adjudicated. "
            f"{amr_clinical_statement(ctx)}"
        ),
        "m5_bioequivalence": (
            f"Biopharmaceutics data substantiate the formulation development bridging between clinical trial materials "
            f"and the proposed commercial product. In vivo bioequivalence studies demonstrated that the 90% confidence "
            f"intervals for the geometric mean ratios of Cmax and AUC parameters fell entirely within the standard "
            f"acceptance criteria of 80.00% to 125.00%. "
            f"Additionally, multi-point comparative dissolution profiles across physiological pH ranges (pH 1.2, 4.5, and 6.8) "
            f"confirmed similarity (f2 > 50). The bioanalytical methods used for plasma quantification were fully validated."
        ),
    }
    base_text = templates[section_id]
    return pad_section_text(rng, section_id, base_text, target_length)


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
        text = pad_section_text(rng, section_id, text, target)
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
        return "approval_denied", 0.92

    if watch_similarity_guard:
        return "additional_information_required", 0.74

    if (not clinical_data_available) or (not gmp_recent) or incorrect_critical == 1:
        return "additional_information_required", 0.78

    if reserve_fast_track:
        return "approval_granted", 0.34

    if partial_sections >= 1:
        return "approval_granted", 0.64

    return "approval_granted", 0.28


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


def _render_ascii_table(header: List[str], rows: List[List[str]], col_widths: List[int]) -> List[str]:
    lines = []
    
    def format_row(cells):
        parts = []
        for cell, width in zip(cells, col_widths):
            cell_str = str(cell)[:width]
            parts.append(cell_str.ljust(width))
        return " | ".join(parts)

    separator = "-+-".join("-" * w for w in col_widths)
    lines.append(format_row(header))
    lines.append(separator)
    for row in rows:
        lines.append(format_row(row))
    return lines


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

        # Add realistic tabular data for specific sections
        if section["section_id"] == "m1_manufacturer_gmp" and section["labels"]["presence"] == "present":
            lines.append("Site Inspection History Summary:")
            gmp_header = ["Inspection Date", "Authority", "Scope", "Outcome"]
            gmp_rows = [
                [dossier["gmp_details"]["last_inspection_date"], "National Auth", "FPP/General", dossier["policy_signals"]["gmp_inspection_status"]],
                ["2022-05-12", "SRA Joint", "API/Sterile", "compliant"],
            ]
            lines.extend(_render_ascii_table(gmp_header, gmp_rows, [18, 15, 15, 12]))
            lines.append("")

        if section["section_id"] == "m5_trial_listing" and section["labels"]["presence"] == "present":
            lines.append("Pivotal Clinical Trial Inventory:")
            trial_header = ["Protocol ID", "Phase", "Enrollment", "Status"]
            trial_rows = []
            for i in range(dossier["clinical_details"]["pivotal_trial_count"]):
                trial_rows.append([f"PROT-00{i+1}", "III", random.randint(200, 800), "completed"])
            lines.extend(_render_ascii_table(trial_header, trial_rows, [15, 8, 12, 12]))
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
    f1_num = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2_num = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    page_nums: List[int] = []
    for page_lines in pages:
        stream_parts = ["BT"]
        y = top_start
        current_font = None
        for line in page_lines:
            # Use monospaced font for tables or headers
            is_table = any(c in line for c in ("|", "+-", "  ")) and len(line) > 10
            target_font = "/F2" if is_table else "/F1"
            
            if target_font != current_font:
                stream_parts.append(f"{target_font} 10 Tf")
                current_font = target_font
                
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
                f"/Resources << /Font << /F1 {f1_num} 0 R /F2 {f2_num} 0 R >> >> "
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
