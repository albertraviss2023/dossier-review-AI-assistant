#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import textwrap
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from pypdf import PdfReader, PdfWriter


MODULE_SECTIONS = [
    ("Module 1", "m1_application_form", "Application Form"),
    ("Module 1", "m1_cover_letter", "Cover Letter"),
    ("Module 1", "m1_authorization_letter", "Letter of Authorization"),
    ("Module 1", "m1_gmp_certificate", "GMP Certificate"),
    ("Module 1", "m1_cpp_certificates", "CPP / Certificate Documents"),
    ("Module 1", "m1_product_label", "Product Label"),
    ("Module 1", "m1_pil", "Patient Information Leaflet"),
    ("Module 1", "m1_smpc", "SmPC"),
    ("Module 1", "m1_payment_proof", "Proof of Payment"),
    ("Module 2", "m2_qos", "Quality Overall Summary"),
    ("Module 2", "m2_clinical_overview", "Clinical Overview / Justification"),
    ("Module 2", "m2_be_summary", "Bioequivalence Summary"),
    ("Module 3", "m3_drug_substance", "Drug Substance Information"),
    ("Module 3", "m3_drug_product", "Drug Product Information"),
    ("Module 3", "m3_manufacturing_process", "Manufacturing Process"),
    ("Module 3", "m3_batch_formula", "Batch Formula"),
    ("Module 3", "m3_specifications", "Specifications"),
    ("Module 3", "m3_analytical_procedures", "Analytical Procedures"),
    ("Module 3", "m3_method_validation", "Method Validation"),
    ("Module 3", "m3_coa", "Certificate of Analysis"),
    ("Module 3", "m3_stability", "Stability Data"),
    ("Module 3", "m3_container_closure", "Container Closure System"),
    ("Module 4", "m4_nonclinical", "Nonclinical Study Reports / Justification"),
    ("Module 5", "m5_be_or_clinical", "Bioequivalence / Clinical Study Reports"),
    ("Module 5", "m5_reference_comparator", "Reference / Comparator Product Evidence"),
]

RENEWAL_EXTRA_SECTIONS = [
    ("Module 1", "m1_renewal_history", "Renewal Product History"),
    ("Module 1", "m1_renewal_declaration", "Renewal Declaration"),
    ("Module 1", "m1_variation_history", "Variation History"),
    ("Module 1", "m1_pv_recall_summary", "Pharmacovigilance / Complaint / Recall Summary"),
]

VET_EXTRA_SECTIONS = [
    ("Module 1", "m1_vet_target_species", "Target Species and Posology"),
    ("Module 1", "m1_vet_withdrawal_periods", "Withdrawal / Residue Information"),
    ("Module 1", "m1_vet_user_safety", "Veterinary User Safety and Environmental Risk"),
]

SCAN_EFFECTS = [
    "skew_rotation",
    "blur_low_resolution",
    "grayscale_photocopy",
    "uneven_brightness",
    "noise_speckles",
    "compression_artifacts",
    "faint_stamp_low_resolution",
    "synthetic_signature_shadow",
    "cropped_margin",
    "scanned_table_low_contrast",
]

MUTATION_TYPES = [
    "missing_pil",
    "missing_smpc",
    "inconsistent_route",
    "inconsistent_strength",
    "expired_gmp_certificate",
    "gmp_site_mismatch",
    "missing_coa_batch_number",
    "coa_result_out_of_specification",
    "stability_data_missing",
    "unsupported_shelf_life",
    "missing_be_report",
    "missing_reference_product",
    "wrong_reference_product",
    "missing_renewal_product_history",
    "missing_variation_history",
    "missing_pharmacovigilance_summary",
    "missing_veterinary_target_species",
    "missing_withdrawal_period",
    "missing_amr_classification",
    "missing_antimicrobial_use_warning",
    "unreadable_scanned_certificate",
    "scanned_coa_not_extractable",
]

REALISTIC_MANUFACTURER_PREFIXES = [
    "Lakeview",
    "NileBridge",
    "Kampala",
    "Eastland",
    "Savanna",
    "PrimeCrest",
    "MedCore",
    "AtlasBio",
    "BlueRidge",
    "Sterling",
    "NovaCare",
    "GrandOak",
]

REALISTIC_MANUFACTURER_SUFFIXES = [
    "Pharmaceuticals Ltd",
    "Lifesciences Ltd",
    "Biopharma Ltd",
    "Healthcare Ltd",
    "Therapeutics Ltd",
    "Formulations Ltd",
]

REALISTIC_APPLICANT_PREFIXES = [
    "Regent",
    "Horizon",
    "Crestline",
    "Aster",
    "WellSpring",
    "MediAxis",
    "BridgePoint",
    "SummitCare",
    "TrueNorth",
    "Pioneer",
]

REALISTIC_APPLICANT_SUFFIXES = [
    "Healthcare (EA) Ltd",
    "Medicines Agency Ltd",
    "Pharma Distributors Ltd",
    "Lifesciences Uganda Ltd",
    "Regulatory Services Ltd",
]

REFERENCE_FACTS_BY_INN: dict[str, dict[str, Any]] = {
    "ceftriaxone": {
        "reference_product_name": "Ceftriaxone 1 g Powder for Injection",
        "pil_route": "intravenous or intramuscular",
        "pil_warnings": [
            "hypersensitivity to cephalosporins",
            "serious allergic reactions",
            "antibiotic-associated diarrhoea",
        ],
        "pil_storage": "Store below 30C and protect from light.",
        "smpc_contraindications": [
            "hypersensitivity to ceftriaxone or other cephalosporins",
        ],
        "smpc_warnings": [
            "serious hypersensitivity reactions",
            "antibiotic-associated colitis",
        ],
    },
    "metformin": {
        "reference_product_name": "Metformin 500 mg Film-coated Tablets",
        "pil_route": "oral",
        "pil_warnings": [
            "risk of lactic acidosis in predisposed patients",
            "renal impairment requires clinical monitoring",
        ],
        "pil_storage": "Store below 25C in original package.",
        "smpc_contraindications": [
            "severe renal impairment",
            "metabolic acidosis including diabetic ketoacidosis",
        ],
        "smpc_warnings": [
            "lactic acidosis risk",
            "renal function monitoring requirements",
        ],
    },
    "oxytetracycline": {
        "reference_product_name": "Oxytetracycline 200 mg/mL Injectable Solution",
        "pil_route": "intramuscular",
        "pil_warnings": [
            "observe prudent antimicrobial use",
            "do not exceed labelled dose in food-producing animals",
        ],
        "pil_storage": "Store below 30C and protect from direct sunlight.",
        "smpc_contraindications": [
            "hypersensitivity to tetracyclines",
        ],
        "smpc_warnings": [
            "withdrawal periods must be observed",
            "antimicrobial stewardship precautions apply",
        ],
    },
}

REALISTIC_SITE_ADDRESSES = [
    "Kampala Industrial Area, Plot 14",
    "Namanve Industrial Park, Block C",
    "Athi River Export Processing Zone, Unit 7",
    "Addis Manufacturing Corridor, Sector B",
    "Ruiru Pharma Estate, Plot 22",
    "Dar es Salaam Logistics Zone, Lot 9",
]

def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _split_lines_for_pdf(lines: list[str], max_chars: int = 95) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(line, width=max_chars, break_long_words=True, replace_whitespace=False))
    return wrapped


def _write_basic_pdf(path: Path, lines: list[str]) -> None:
    page_width = 612
    page_height = 792
    left_margin = 50
    top_start = 760
    bottom_margin = 50
    leading = 14
    max_lines_per_page = max(1, (top_start - bottom_margin) // leading)
    pages: list[list[str]] = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)] or [[]]
    objects: list[str] = []

    def add_obj(content: str) -> int:
        objects.append(content)
        return len(objects)

    catalog_num = add_obj("<< /Type /Catalog /Pages 2 0 R >>")
    pages_num = add_obj("<< /Type /Pages /Count 0 /Kids [] >>")
    f1_num = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2_num = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    page_nums: list[int] = []

    for page_lines in pages:
        stream_parts = ["BT"]
        y = top_start
        current_font = None
        for line in page_lines:
            is_table = any(c in line for c in ("|", "+-", "  ")) and len(line) > 10
            target_font = "/F2" if is_table else "/F1"
            if target_font != current_font:
                stream_parts.append(f"{target_font} 10 Tf")
                current_font = target_font
            stream_parts.append(f"1 0 0 1 {left_margin} {y} Tm ({_pdf_escape(line)}) Tj")
            y -= leading
        stream_parts.append("ET")
        stream = "\n".join(stream_parts)
        stream_bytes = stream.encode("latin-1", errors="replace")
        content_num = add_obj(f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream")
        page_num = add_obj(
            f"<< /Type /Page /Parent {pages_num} 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {f1_num} 0 R /F2 {f2_num} 0 R >> >> /Contents {content_num} 0 R >>"
        )
        page_nums.append(page_num)

    kids = " ".join(f"{n} 0 R" for n in page_nums)
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
    trailer = f"trailer\n<< /Size {len(objects)+1} /Root {catalog_num} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    path.write_bytes((header + body + "".join(xref) + trailer).encode("latin-1", errors="replace"))


@dataclass
class DatasetConfig:
    seed: int
    query_ratio: float
    stress_test_ratio: float
    matrix: dict[str, list[str]]
    default_context: dict[str, Any]
    split_ratios: dict[str, float]

    @classmethod
    def load(cls, path: Path) -> "DatasetConfig":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            seed=int(payload.get("seed", 20260508)),
            query_ratio=float(payload.get("query_ratio", 0.5)),
            stress_test_ratio=float(payload.get("stress_test_ratio", 0.1)),
            matrix=dict(payload["matrix"]),
            default_context=dict(payload["default_context"]),
            split_ratios=dict(payload["split_ratios"]),
        )


class ProductSampler:
    def __init__(self, rng: random.Random, products: list[dict[str, Any]]) -> None:
        self.rng = rng
        self.products = products

    @staticmethod
    def default_products() -> list[dict[str, Any]]:
        return [
            {"product_key": "hum_gen_amr_cef", "medicine_category": "human", "application_pathway_options": "generic|line_extension", "is_antimicrobial": True, "amr_class": "Watch", "inn": "ceftriaxone", "active_ingredients": "ceftriaxone", "dosage_form": "powder for injection", "route_of_administration": "intravenous", "strength": "1 g", "therapeutic_area": "infectious_disease", "target_species": "", "food_producing_species": False, "requires_withdrawal_period": False, "reference_required": True, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "hum_gen_nonamr_met", "medicine_category": "human", "application_pathway_options": "generic|fixed_dose_combination", "is_antimicrobial": False, "amr_class": "not_applicable", "inn": "metformin", "active_ingredients": "metformin", "dosage_form": "tablet", "route_of_administration": "oral", "strength": "500 mg", "therapeutic_area": "endocrine", "target_species": "", "food_producing_species": False, "requires_withdrawal_period": False, "reference_required": True, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "hum_innov_amr_syn", "medicine_category": "human", "application_pathway_options": "innovator|biosimilar_or_biological", "is_antimicrobial": True, "amr_class": "Reserve", "inn": "synteromycin", "active_ingredients": "synteromycin", "dosage_form": "oral suspension", "route_of_administration": "oral", "strength": "250 mg/5 mL", "therapeutic_area": "infectious_disease", "target_species": "", "food_producing_species": False, "requires_withdrawal_period": False, "reference_required": False, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "hum_innov_nonamr_syn", "medicine_category": "human", "application_pathway_options": "innovator|line_extension", "is_antimicrobial": False, "amr_class": "not_applicable", "inn": "cardiovex", "active_ingredients": "cardiovex", "dosage_form": "tablet", "route_of_administration": "oral", "strength": "20 mg", "therapeutic_area": "cardiovascular", "target_species": "", "food_producing_species": False, "requires_withdrawal_period": False, "reference_required": False, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "vet_gen_amr_oxy", "medicine_category": "veterinary", "application_pathway_options": "generic|line_extension", "is_antimicrobial": True, "amr_class": "Watch", "inn": "oxytetracycline", "active_ingredients": "oxytetracycline", "dosage_form": "injectable solution", "route_of_administration": "intramuscular", "strength": "200 mg/mL", "therapeutic_area": "infectious_disease", "target_species": "cattle|goats|sheep", "food_producing_species": True, "requires_withdrawal_period": True, "reference_required": True, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "vet_gen_nonamr_multi", "medicine_category": "veterinary", "application_pathway_options": "generic|fixed_dose_combination", "is_antimicrobial": False, "amr_class": "not_applicable", "inn": "multivitamin blend", "active_ingredients": "vitamin a|vitamin d3|vitamin e", "dosage_form": "oral solution", "route_of_administration": "oral", "strength": "label claim", "therapeutic_area": "nutrition", "target_species": "cattle|goats|sheep", "food_producing_species": True, "requires_withdrawal_period": False, "reference_required": False, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "vet_innov_amr_im", "medicine_category": "veterinary", "application_pathway_options": "innovator|line_extension", "is_antimicrobial": True, "amr_class": "Reserve", "inn": "lactomaxin", "active_ingredients": "lactomaxin", "dosage_form": "intramammary infusion", "route_of_administration": "intramammary", "strength": "100 mg/syringe", "therapeutic_area": "mastitis", "target_species": "dairy cattle", "food_producing_species": True, "requires_withdrawal_period": True, "reference_required": False, "suitable_for_new_submission": True, "suitable_for_renewal": True},
            {"product_key": "vet_innov_nonamr_antiinf", "medicine_category": "veterinary", "application_pathway_options": "innovator|biosimilar_or_biological", "is_antimicrobial": False, "amr_class": "not_applicable", "inn": "antiinflamox", "active_ingredients": "antiinflamox", "dosage_form": "injectable suspension", "route_of_administration": "subcutaneous", "strength": "50 mg/mL", "therapeutic_area": "anti-inflammatory", "target_species": "cattle|dogs", "food_producing_species": True, "requires_withdrawal_period": True, "reference_required": False, "suitable_for_new_submission": True, "suitable_for_renewal": True},
        ]

    def sample(self, medicine_category: str, application_pathway: str, product_class: str, submission_type: str) -> dict[str, Any]:
        filtered = []
        for product in self.products:
            if product["medicine_category"] != medicine_category:
                continue
            if application_pathway not in str(product["application_pathway_options"]).split("|"):
                continue
            if product_class == "antimicrobial" and not bool(product["is_antimicrobial"]):
                continue
            if product_class == "non_antimicrobial" and bool(product["is_antimicrobial"]):
                continue
            if submission_type == "new_submission" and not bool(product["suitable_for_new_submission"]):
                continue
            if submission_type == "renewal" and not bool(product["suitable_for_renewal"]):
                continue
            filtered.append(product)
        if not filtered:
            # Fallback: preserve category + product class, relax pathway constraint.
            for product in self.products:
                if product["medicine_category"] != medicine_category:
                    continue
                if product_class == "antimicrobial" and not bool(product["is_antimicrobial"]):
                    continue
                if product_class == "non_antimicrobial" and bool(product["is_antimicrobial"]):
                    continue
                filtered.append(product)
        if not filtered:
            raise ValueError("No product candidates for requested matrix point, even after fallback.")
        return dict(self.rng.choice(filtered))


class RequirementMatrix:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requirements: dict[str, list[dict[str, Any]]] = {}

    def write_defaults(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        workflow_steps = [
            {"step_id": 1, "step_key": "submission_intake_and_familiarization", "step_label": "Submission intake and familiarization"},
            {"step_id": 2, "step_key": "administrative_completeness_review", "step_label": "Administrative completeness review"},
            {"step_id": 3, "step_key": "structural_dossier_mapping", "step_label": "Structural dossier mapping"},
            {"step_id": 4, "step_key": "applicable_rules_identification", "step_label": "Applicable rules and requirements identification"},
            {"step_id": 5, "step_key": "who_inn_similarity_review", "step_label": "WHO INN similarity review"},
            {"step_id": 6, "step_key": "section_by_section_technical_review", "step_label": "Section-by-section technical review"},
            {"step_id": 7, "step_key": "amr_stewardship_review", "step_label": "AMR stewardship review using AWaRe rules (conditional)"},
            {"step_id": 8, "step_key": "findings_register", "step_label": "Identification and recording of findings"},
            {"step_id": 9, "step_key": "severity_classification", "step_label": "Severity classification"},
            {"step_id": 10, "step_key": "cross_section_consistency_review", "step_label": "Cross-section consistency review"},
            {"step_id": 11, "step_key": "review_completeness_confirmation", "step_label": "Review completeness confirmation"},
            {"step_id": 12, "step_key": "overall_judgment", "step_label": "Overall judgment"},
        ]
        (self.root / "workflow_steps.json").write_text(json.dumps(workflow_steps, indent=2), encoding="utf-8")
        payloads = {
            "common_requirements.json": [
                self._req("COM-APP-001", "Module 1", "Application Form", ["product_name", "inn", "strength", "dosage_form", "route_of_administration", "applicant_name", "manufacturer_name"], "Missing mandatory product identity fields in application form."),
                self._req("COM-GMP-001", "Module 1", "GMP Certificate", ["certificate_number", "expiry_date", "site_address"], "GMP certificate missing or invalid evidence."),
                self._req("COM-LABEL-001", "Module 1", "Product Label", ["product_name", "strength", "dosage_form", "route_of_administration", "storage_conditions"], "Label fields missing or inconsistent."),
                self._req("COM-COA-001", "Module 3", "Certificate of Analysis", ["batch_number", "specification_limits", "results", "conclusion", "signature"], "CoA missing required fields."),
                self._req("COM-STABILITY-001", "Module 3", "Stability Data", ["storage_conditions", "shelf_life", "timepoints"], "Stability evidence insufficient for shelf-life."),
            ],
            "human_requirements.json": [
                self._req("HUM-PIL-001", "Module 1", "Patient Information Leaflet", ["route_of_administration", "dosage_form", "patient_instructions", "warnings"], "PIL incomplete for human medicine."),
                self._req("HUM-SMPC-001", "Module 1", "SmPC", ["contraindications", "warnings", "adverse_reactions"], "SmPC mandatory safety fields incomplete."),
            ],
            "veterinary_requirements.json": [
                self._req("VET-SPECIES-001", "Module 1", "Target Species and Posology", ["target_species", "species_dosing"], "Target species/dosing missing."),
                self._req("VET-WITHDRAWAL-001", "Module 1", "Withdrawal / Residue Information", ["withdrawal_period_meat", "withdrawal_period_milk"], "Withdrawal periods missing for food species."),
            ],
            "new_submission_requirements.json": [
                self._req("NEW-QUALITY-001", "Module 3", "Drug Product Information", ["composition", "manufacturing_process", "specifications"], "Full quality package required for new submission."),
                self._req("NEW-CLINICAL-001", "Module 5", "Bioequivalence / Clinical Study Reports", ["study_design", "effect_size", "safety_summary"], "Clinical/BE evidence missing."),
            ],
            "renewal_requirements.json": [
                self._req("REN-HISTORY-001", "Module 1", "Renewal Product History", ["authorization_number", "renewal_period", "product_history"], "Renewal history incomplete."),
                self._req("REN-VARIATION-001", "Module 1", "Variation History", ["variation_history"], "Variation history missing."),
                self._req("REN-PV-001", "Module 1", "Pharmacovigilance / Complaint / Recall Summary", ["pv_summary", "recall_summary"], "PV/recall summary missing."),
            ],
            "antimicrobial_requirements.json": [
                self._req("AMR-CLASS-001", "Module 1", "Product Label", ["amr_classification", "antimicrobial_warning"], "AMR classification/warnings missing."),
            ],
            "pathway_requirements.json": [
                self._req("PATH-GEN-001", "Module 5", "Reference / Comparator Product Evidence", ["reference_product_name", "comparator_evidence"], "Generic pathway requires valid reference/comparator evidence."),
                self._req("PATH-INNOV-001", "Module 4", "Nonclinical Study Reports / Justification", ["nonclinical_or_justification"], "Innovator/new active requires nonclinical evidence or valid justification."),
            ],
        }
        for name, data in payloads.items():
            (self.root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.requirements[name] = data

    @staticmethod
    def _req(requirement_id: str, module: str, section: str, required_information: list[str], query_condition: str) -> dict[str, Any]:
        return {
            "requirement_id": requirement_id,
            "module": module,
            "section": section,
            "required_for_medicine_category": ["human", "veterinary"],
            "required_for_submission_type": ["new_submission", "renewal"],
            "required_for_pathway": ["generic", "innovator", "fixed_dose_combination", "line_extension", "biosimilar_or_biological"],
            "required_when": {"is_antimicrobial": None, "medicine_category": None, "food_producing_species": None},
            "required_information": required_information,
            "pass_condition": "Required information is present, extractable, and consistent with supporting sections.",
            "query_condition": query_condition,
        }


class DossierPlanner:
    def __init__(self, config: DatasetConfig, rng: random.Random) -> None:
        self.config = config
        self.rng = rng

    def plan(self, num_dossiers: int) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        matrix = self.config.matrix
        combos = []
        for mc in matrix["medicine_categories"]:
            for st in matrix["submission_types"]:
                for ap in matrix["application_pathways"]:
                    for pc in matrix["product_classes"]:
                        combos.append((mc, st, ap, pc))
        self.rng.shuffle(combos)
        by_mc: dict[str, list[tuple[str, str, str, str]]] = {"human": [], "veterinary": []}
        for combo in combos:
            by_mc[combo[0]].append(combo)
        families = max(1, num_dossiers // 2)
        for i in range(families):
            target_mc = "human" if i % 2 == 0 else "veterinary"
            pool = by_mc.get(target_mc) or combos
            mc, st, ap, pc = pool[i % len(pool)]
            plans.append({"family_id": f"FAM-{i+1:04d}", "medicine_category": mc, "submission_type": st, "application_pathway": ap, "product_class": pc, "submission_status": "correct"})
            plans.append({"family_id": f"FAM-{i+1:04d}", "medicine_category": mc, "submission_type": st, "application_pathway": ap, "product_class": pc, "submission_status": "query"})
        if len(plans) < num_dossiers:
            for i in range(num_dossiers - len(plans)):
                mc, st, ap, pc = combos[(families + i) % len(combos)]
                plans.append({"family_id": f"FAM-EXTRA-{i+1:04d}", "medicine_category": mc, "submission_type": st, "application_pathway": ap, "product_class": pc, "submission_status": "correct"})
        return plans[:num_dossiers]


class SectionGenerator:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def sections_for(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        sections = list(MODULE_SECTIONS)
        if manifest["submission_type"] == "renewal":
            sections.extend(RENEWAL_EXTRA_SECTIONS)
        if manifest["medicine_category"] == "veterinary":
            sections.extend(VET_EXTRA_SECTIONS)
        rendered = []
        for module, section_id, name in sections:
            rendered.append({"module": module, "section_id": section_id, "section_name": name, "text": self._build_text(manifest, section_id, name)})
        return rendered

    def _build_text(self, m: dict[str, Any], sid: str, name: str) -> str:
        ref_facts = REFERENCE_FACTS_BY_INN.get(str(m.get("inn", "")).lower())
        reference_required = bool(m.get("reference_required", False))
        base = [
            f"{name} for dossier {m['dossier_id']}.",
            f"Product: {m['product_name']} ({m['inn']}); strength {m['strength']}; route {m['route_of_administration']}.",
            f"Applicant: {m['applicant_name']} ({m['applicant_country']}); Manufacturer: {m['manufacturer_name']} ({m['manufacturer_country']}).",
        ]
        if sid == "m1_pil":
            warnings = [
                "Do not use if you are allergic to the active ingredient or related medicines.",
                "Seek immediate medical care for rash, breathing difficulty, or severe diarrhoea.",
                "Use exactly as prescribed; complete the full treatment course where applicable.",
            ]
            if not m.get("is_antimicrobial", False):
                warnings = [
                    "Do not stop treatment abruptly unless advised by a healthcare professional.",
                    "Tell your doctor about kidney, liver, or heart conditions before use.",
                    "Report dizziness, fainting, severe abdominal pain, or persistent vomiting immediately.",
                ]
            if m.get("medicine_category") == "veterinary":
                species = ", ".join(m.get("target_species", [])) or "target species as approved"
                warnings.append(f"For veterinary use in {species} only.")
            if reference_required and ref_facts:
                warnings = [f"Reference-aligned warning: {w}." for w in ref_facts["pil_warnings"]]
                route_text = ref_facts["pil_route"]
                storage_text = ref_facts["pil_storage"]
            else:
                route_text = m["route_of_administration"]
                storage_text = "Store below 30C, protect from moisture/light, keep out of reach of children."
            base.extend(
                [
                    "PIL Section: What this medicine is and what it is used for.",
                    f"PIL Route and Form: Route={route_text}; Dosage form={m['dosage_form']}; Strength={m['strength']}.",
                    "PIL Instructions: Follow the prescribed dose schedule. Do not exceed recommended dose.",
                    f"PIL Warnings: {' '.join(warnings)}",
                    f"PIL Storage: {storage_text}",
                    "PIL Adverse Effects: Common effects include gastrointestinal upset and headache; serious effects require urgent review.",
                ]
            )
        if sid == "m1_smpc":
            contraindications = ["Known hypersensitivity to active ingredient or excipients", "Severe allergy to related therapeutic class where applicable"]
            warnings_line = "monitor organ function and hypersensitivity risks."
            if reference_required and ref_facts:
                contraindications = list(ref_facts["smpc_contraindications"])
                warnings_line = "; ".join(ref_facts["smpc_warnings"]) + "."
            base.extend(
                [
                    "SmPC 4.1 Therapeutic indications: As approved in the application form.",
                    "SmPC 4.2 Posology and method of administration: Dose by age/weight and clinical condition as approved.",
                    f"SmPC 4.3 Contraindications: {', '.join(contraindications)}.",
                    f"SmPC 4.4 Special warnings and precautions: {warnings_line}",
                    "SmPC 4.8 Undesirable effects: nausea, diarrhoea, rash, dizziness; serious adverse reactions listed.",
                    "SmPC 6.4 Special precautions for storage: store according to label and stability commitments.",
                ]
            )
        if sid == "m1_gmp_certificate":
            site_address = m.get("manufacturing_site_address", "Kampala Industrial Area, Plot 14")
            base.append(f"GMP Certificate No: GMP-{m['dossier_id'][-6:]}; Site Address: {site_address}; Expiry Date: {m['gmp_expiry_date']}.")
        if sid == "m3_coa":
            base.append("CoA Table: Batch Number=BCH-24011; Specification Limits=Conforms; Results=Within limits; Conclusion=Pass; Authorized Signature=Present.")
        if sid == "m3_stability":
            base.append("Stability Table: 0, 3, 6, 9, 12 months; Conditions=30C/75%RH; Conclusion supports shelf life.")
        if sid == "m5_be_or_clinical":
            base.append("Clinical Summary: Endpoint met where applicable; Effect size and safety summary included.")
        if sid == "m5_reference_comparator" and reference_required and ref_facts:
            base.append(
                f"Reference Product Evidence: Comparator is {ref_facts['reference_product_name']}; submitted PIL/SmPC statements are aligned to reference safety facts."
            )
        if m["submission_type"] == "renewal" and sid == "m1_renewal_history":
            base.append("Renewal Context: Previous authorization number present; product quality and safety trend documented.")
        if m["medicine_category"] == "veterinary" and sid == "m1_vet_withdrawal_periods":
            base.append(f"Withdrawal Periods: Meat={m.get('withdrawal_period_meat', 'not_applicable')}; Milk={m.get('withdrawal_period_milk', 'not_applicable')}.")
        if m["is_antimicrobial"]:
            base.append(f"Antimicrobial Classification: {m['amr_class']}; stewardship warning and prudent-use statement included.")
        return "\n".join(base)


class MutationEngine:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def apply(self, dossier: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        mutated = json.loads(json.dumps(dossier))
        options = self._options_for(mutated)
        mutation = self.rng.choice(options)
        issue = self._mutate(mutated, mutation)
        mutated["submission_status"] = "query"
        mutated["expected_sop_outcome"] = "query_applicant"
        return mutated, issue

    def _options_for(self, d: dict[str, Any]) -> list[str]:
        opts = list(MUTATION_TYPES)
        if d["medicine_category"] != "veterinary":
            opts = [o for o in opts if "veterinary" not in o and "withdrawal" not in o]
        if not d["is_antimicrobial"]:
            opts = [o for o in opts if "amr" not in o and "antimicrobial" not in o]
        if d["submission_type"] != "renewal":
            opts = [o for o in opts if "renewal" not in o and "variation_history" not in o and "pharmacovigilance" not in o]
        return opts or ["missing_pil"]

    def _mutate(self, d: dict[str, Any], mutation: str) -> dict[str, Any]:
        section_lookup = {s["section_id"]: s for s in d["sections"]}
        expected_query = "Applicant should provide the missing or corrected evidence."
        section_id = "m1_application_form"
        requirement_id = "COM-APP-001"
        if mutation == "missing_pil":
            section_id, requirement_id = "m1_pil", "HUM-PIL-001"
            section_lookup[section_id]["text"] = ""
            expected_query = "Applicant should provide a complete Patient Information Leaflet."
        elif mutation == "missing_smpc":
            section_id, requirement_id = "m1_smpc", "HUM-SMPC-001"
            section_lookup[section_id]["text"] = ""
            expected_query = "Applicant should provide a complete SmPC."
        elif mutation == "expired_gmp_certificate":
            section_id, requirement_id = "m1_gmp_certificate", "COM-GMP-001"
            d["gmp_expiry_date"] = "2022-02-01"
            section_lookup[section_id]["text"] += "\nCertificate Expiry Date: 2022-02-01."
            expected_query = "Applicant should provide a valid current GMP certificate."
        elif mutation == "missing_withdrawal_period":
            section_id, requirement_id = "m1_vet_withdrawal_periods", "VET-WITHDRAWAL-001"
            section_lookup[section_id]["text"] = section_lookup[section_id]["text"].replace("Withdrawal Periods:", "Withdrawal Periods: missing")
            d["withdrawal_period_meat"] = ""
            d["withdrawal_period_milk"] = ""
            expected_query = "Applicant should provide withdrawal periods for meat and milk."
        elif mutation == "missing_amr_classification":
            section_id, requirement_id = "m1_product_label", "AMR-CLASS-001"
            section_lookup[section_id]["text"] += "\nAMR classification: not stated."
            d["amr_class"] = ""
            expected_query = "Applicant should provide AMR classification and antimicrobial-use warning."
        else:
            section_id = "m3_coa"
            requirement_id = "COM-COA-001"
            section_lookup[section_id]["text"] += f"\nMutation injected: {mutation}."
            expected_query = f"Applicant should address the issue: {mutation.replace('_', ' ')}."
        return {"mutation_type": mutation, "section_id": section_id, "requirement_id": requirement_id, "expected_query": expected_query}


class LabelGenerator:
    def build(self, dossier: dict[str, Any], issue: dict[str, Any] | None, page_lookup: dict[str, list[int]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        section_labels: list[dict[str, Any]] = []
        chunk_labels: list[dict[str, Any]] = []
        issue_labels: list[dict[str, Any]] = []
        idx = 1
        for section in dossier["sections"]:
            sid = section["section_id"]
            text = section["text"]
            presence = "present" if text.strip() else "missing"
            query_hit = issue and issue["section_id"] == sid
            sec_outcome = "query" if query_hit else ("pass" if presence == "present" else "query")
            section_label = {
                "dossier_id": dossier["dossier_id"],
                "section_id": sid,
                "module": section["module"],
                "section_name": section["section_name"],
                "applicable": True,
                "required": True,
                "labels": {
                    "presence": presence,
                    "completeness": "incomplete" if query_hit or presence == "missing" else "complete",
                    "length": "too_short" if (query_hit and presence == "present") else ("not_applicable" if presence == "missing" else "length_ok"),
                    "extractability": "partially_extractable" if query_hit and issue["mutation_type"].startswith("scanned_") else ("not_applicable" if presence == "missing" else "extractable"),
                    "correctness": "incorrect" if query_hit else ("not_applicable" if presence == "missing" else "correct"),
                    "consistency": "inconsistent" if query_hit else "consistent",
                    "sop_outcome": sec_outcome,
                },
                "sop_requirement_ids": [issue["requirement_id"]] if query_hit else [],
                "evidence_location": {"page_range": [page_lookup[sid][0], page_lookup[sid][-1]], "chunk_ids": [f"{dossier['dossier_id']}_{sid}_CHUNK_{idx:03d}"]},
                "expected_action": "query_applicant" if query_hit else "accept_requirement",
            }
            section_labels.append(section_label)
            chunk_id = section_label["evidence_location"]["chunk_ids"][0]
            chunk_labels.append(
                {
                    "chunk_id": chunk_id,
                    "dossier_id": dossier["dossier_id"],
                    "module": section["module"],
                    "section": sid,
                    "page_range": section_label["evidence_location"]["page_range"],
                    "text_type": "searchable_text",
                    "sop_requirement_ids": section_label["sop_requirement_ids"],
                    "section_status": sec_outcome,
                    "issue_type": issue["mutation_type"] if query_hit else None,
                    "expected_llm_action": "query_applicant" if query_hit else "accept_requirement",
                }
            )
            idx += 1
        if issue:
            issue_labels.append(
                {
                    "issue_id": f"ISSUE-{hashlib.sha1((dossier['dossier_id'] + issue['mutation_type']).encode()).hexdigest()[:8].upper()}",
                    "dossier_id": dossier["dossier_id"],
                    "requirement_id": issue["requirement_id"],
                    "issue_type": issue["mutation_type"],
                    "module": next(s["module"] for s in dossier["sections"] if s["section_id"] == issue["section_id"]),
                    "section": issue["section_id"],
                    "severity": "major",
                    "expected_query": issue["expected_query"],
                    "affected_pages": page_lookup[issue["section_id"]],
                    "affected_chunks": [c["chunk_id"] for c in chunk_labels if c["section"] == issue["section_id"]],
                }
            )
        return section_labels, chunk_labels, issue_labels


class ManifestGenerator:
    def __init__(self, rng: random.Random, quality_cfg: dict[str, Any]) -> None:
        self.rng = rng
        self.quality_cfg = quality_cfg

    def build_page_and_scan_manifests(self, dossier: dict[str, Any], sections: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[int]]]:
        pages = []
        scans = []
        page_index = 1
        page_lookup: dict[str, list[int]] = {}
        profile = dossier["document_quality_profile"]
        cfg = self.quality_cfg[profile]
        frac = self.rng.uniform(float(cfg["scanned_min"]), float(cfg["scanned_max"]))
        n_scanned_targets = max(0, int(round(frac * len(sections))))
        scanned_sections = set(self.rng.sample([s["section_id"] for s in sections], k=min(n_scanned_targets, len(sections))))
        for section in sections:
            sid = section["section_id"]
            page_count = 1 if len(section["text"]) < 500 else 2
            page_lookup[sid] = list(range(page_index, page_index + page_count))
            for p in range(page_count):
                scanned = sid in scanned_sections
                scan_profile = self.rng.choice(SCAN_EFFECTS) if scanned else None
                pages.append(
                    {
                        "dossier_id": dossier["dossier_id"],
                        "page": page_index,
                        "module": section["module"],
                        "section_id": sid,
                        "section_name": section["section_name"],
                        "page_type": "scanned_image" if scanned else "searchable_text",
                        "scan_profile": scan_profile,
                        "contains_tables": sid in {"m3_coa", "m3_stability", "m3_specifications", "m2_be_summary"},
                        "contains_signature": sid in {"m1_authorization_letter", "m1_payment_proof", "m1_gmp_certificate"},
                        "contains_stamp": sid in {"m1_gmp_certificate", "m1_cpp_certificates"},
                        "expected_entities": ["product_name", "inn", "strength"],
                        "sop_requirement_ids": [],
                    }
                )
                if scanned:
                    scans.append(
                        {
                            "dossier_id": dossier["dossier_id"],
                            "page": page_index,
                            "section_id": sid,
                            "scan_effect": scan_profile,
                            "text_type": "scanned_table" if sid in {"m3_coa", "m3_stability"} else "scanned_text",
                        }
                    )
                page_index += 1
        return pages, scans, page_lookup


class PdfRenderer:
    def render(
        self,
        dossier: dict[str, Any],
        out_pdf: Path,
        page_manifest: list[dict[str, Any]],
        scan_artifact_by_page: dict[int, Path] | None = None,
    ) -> None:
        scan_artifact_by_page = scan_artifact_by_page or {}
        section_by_id = {section["section_id"]: section for section in dossier["sections"]}
        writer = PdfWriter()
        out_pdf.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="synthetic_pdf_pages_") as temp_dir:
            temp_root = Path(temp_dir)
            for page in sorted(page_manifest, key=lambda row: int(row["page"])):
                page_no = int(page["page"])
                artifact = scan_artifact_by_page.get(page_no)
                if page.get("page_type") == "scanned_image" and artifact and artifact.exists():
                    img = Image.open(artifact).convert("RGB")
                    page_pdf = temp_root / f"page_{page_no:04d}_scan.pdf"
                    img.save(page_pdf, "PDF", resolution=150.0)
                    writer.add_page(PdfReader(str(page_pdf)).pages[0])
                    continue

                section = section_by_id.get(str(page["section_id"]), {})
                lines = [
                    "SYNTHETIC PRE-MARKET AUTHORIZATION DOSSIER",
                    f"Dossier ID: {dossier['dossier_id']}",
                    f"Page: {page_no}",
                    f"Module/Section: {page['module']} / {page['section_id']} - {page['section_name']}",
                    f"Page Type: {page.get('page_type', 'searchable_text')}",
                    "",
                    section.get("text", "[MISSING SECTION]"),
                ]
                page_pdf = temp_root / f"page_{page_no:04d}_text.pdf"
                _write_basic_pdf(page_pdf, _split_lines_for_pdf(lines))
                writer.add_page(PdfReader(str(page_pdf)).pages[0])

        with out_pdf.open("wb") as handle:
            writer.write(handle)


class ScanSimulator:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def render_scan_artifact(self, out_path: Path, dossier_id: str, page: int, section_id: str, effect: str) -> None:
        img = Image.new("L", (1654, 2339), color=245)
        draw = ImageDraw.Draw(img)
        y = 120
        lines = [
            "SYNTHETIC SCANNED PAGE",
            f"Dossier: {dossier_id}",
            f"Section: {section_id}",
            f"Page: {page}",
            f"Effect: {effect}",
            "This artifact is generated for OCR/vision stress testing.",
        ]
        for line in lines:
            draw.text((120, y), line, fill=30)
            y += 56
        for _ in range(28):
            noise_x = self.rng.randint(0, img.width - 20)
            noise_y = self.rng.randint(0, img.height - 20)
            draw.rectangle((noise_x, noise_y, noise_x + self.rng.randint(2, 16), noise_y + self.rng.randint(2, 16)), fill=self.rng.randint(100, 240))

        if "blur" in effect:
            img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
        if "low_resolution" in effect:
            img = img.resize((900, 1270), resample=Image.Resampling.BILINEAR).resize((1654, 2339), resample=Image.Resampling.BILINEAR)
        if "grayscale" in effect:
            img = ImageOps.autocontrast(img, cutoff=2)
        if "uneven_brightness" in effect:
            overlay = Image.new("L", img.size, color=0)
            od = ImageDraw.Draw(overlay)
            for i in range(0, img.height, 20):
                shade = int(10 + 35 * (i / max(1, img.height)))
                od.rectangle((0, i, img.width, min(img.height, i + 20)), fill=shade)
            img = Image.blend(img, overlay, alpha=0.08)
        if "cropped_margin" in effect:
            img = ImageOps.expand(img.crop((40, 50, img.width - 70, img.height - 90)), border=30, fill=255)
        if "rotation" in effect or "skew" in effect:
            img = img.rotate(self.rng.uniform(-2.8, 2.8), fillcolor=255)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)


class SplitGenerator:
    def __init__(self, rng: random.Random, ratios: dict[str, float], stress_ratio: float) -> None:
        self.rng = rng
        self.ratios = ratios
        self.stress_ratio = stress_ratio

    def generate(self, manifests: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
        family_groups: dict[str, list[dict[str, Any]]] = {}
        for m in manifests:
            family_groups.setdefault(m["family_id"], []).append(m)
        families = list(family_groups.keys())
        self.rng.shuffle(families)
        n = len(families)
        n_train = int(n * self.ratios["train"])
        n_val = int(n * self.ratios["validation"])
        train_f = set(families[:n_train])
        val_f = set(families[n_train:n_train + n_val])
        test_f = set(families[n_train + n_val:])
        split_map: dict[str, list[str]] = {"train": [], "validation": [], "test": [], "stress_test": []}
        split_meta: list[dict[str, Any]] = []
        difficult = [m for m in manifests if m["document_quality_profile"] == "difficult_scan_stress_test" or m["submission_status"] == "query"]
        stress_count = max(1, int(len(manifests) * self.stress_ratio)) if manifests else 0
        stress_ids = {m["dossier_id"] for m in difficult[:stress_count]}
        for m in manifests:
            fam = m["family_id"]
            split = "train" if fam in train_f else ("validation" if fam in val_f else "test")
            split_map[split].append(m["dossier_id"])
            if m["dossier_id"] in stress_ids:
                split_map["stress_test"].append(m["dossier_id"])
            split_meta.append({"dossier_id": m["dossier_id"], "split": split, "family_id": fam, "is_base_gold": m["submission_status"] == "correct", "mutation_id": m.get("mutation_id")})
        return split_map, split_meta


class DatasetValidator:
    def validate(
        self,
        manifests: list[dict[str, Any]],
        section_labels: list[dict[str, Any]],
        chunk_labels: list[dict[str, Any]],
        issue_labels: list[dict[str, Any]],
        page_manifests: list[dict[str, Any]],
        scan_manifests: list[dict[str, Any]],
        split_map: dict[str, list[str]],
    ) -> dict[str, Any]:
        errors: list[str] = []
        manifest_ids = {m["dossier_id"] for m in manifests}
        for sid in split_map["train"] + split_map["validation"] + split_map["test"]:
            if sid not in manifest_ids:
                errors.append(f"Split references missing dossier {sid}.")
        if len(set(split_map["train"]) & set(split_map["validation"])) > 0 or len(set(split_map["train"]) & set(split_map["test"])) > 0 or len(set(split_map["validation"]) & set(split_map["test"])) > 0:
            errors.append("A dossier appears in more than one split.")
        for m in manifests:
            did = m["dossier_id"]
            secs = [s for s in section_labels if s["dossier_id"] == did]
            chs = [c for c in chunk_labels if c["dossier_id"] == did]
            if not secs:
                errors.append(f"No section labels for {did}.")
            if not chs:
                errors.append(f"No chunk labels for {did}.")
            if m["submission_status"] == "correct":
                if any(s["labels"]["sop_outcome"] == "query" for s in secs):
                    errors.append(f"Correct dossier has query section outcome: {did}.")
            if m["submission_status"] == "query":
                if not any(i["dossier_id"] == did for i in issue_labels):
                    errors.append(f"Query dossier has no issue labels: {did}.")
        if any(pm["page_type"] == "scanned_image" for pm in page_manifests) and not scan_manifests:
            errors.append("Scanned pages exist but scan manifest is empty.")
        return {"valid": len(errors) == 0, "errors": errors, "counts": {"dossiers": len(manifests), "section_labels": len(section_labels), "chunk_labels": len(chunk_labels), "issue_labels": len(issue_labels), "pages": len(page_manifests), "scanned_pages": len(scan_manifests)}}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _today_minus(days_back: int) -> str:
    return (date.today() - timedelta(days=days_back)).isoformat()


def _make_dossier_id(plan: dict[str, Any], product: dict[str, Any], idx: int) -> str:
    mc = "HUM" if plan["medicine_category"] == "human" else "VET"
    st = "NEW" if plan["submission_type"] == "new_submission" else "REN"
    ap = {"generic": "GEN", "innovator": "INNOV", "fixed_dose_combination": "FDC", "line_extension": "LINE", "biosimilar_or_biological": "BIO"}[plan["application_pathway"]]
    pc = "AMR" if plan["product_class"] == "antimicrobial" else "NONAMR"
    inn = str(product["inn"]).replace(" ", "")[:4].upper()
    return f"{mc}-{st}-{ap}-{pc}-{inn}-{idx:04d}"


def _realistic_org_name(rng: random.Random, prefixes: list[str], suffixes: list[str]) -> str:
    return f"{rng.choice(prefixes)} {rng.choice(suffixes)}"


def _build_realistic_product_name(product: dict[str, Any]) -> str:
    inn = str(product["inn"]).strip()
    strength = str(product["strength"]).strip()
    form = str(product["dosage_form"]).strip()
    return f"{inn.title()} {strength} {form}".replace("  ", " ")


def _build_reference_truth_files(root: Path) -> None:
    (root / "human").mkdir(parents=True, exist_ok=True)
    (root / "veterinary").mkdir(parents=True, exist_ok=True)
    (root / "pil_smpc_reference").mkdir(parents=True, exist_ok=True)
    (root / "amr_classification").mkdir(parents=True, exist_ok=True)
    (root / "comparator_products").mkdir(parents=True, exist_ok=True)
    ref = {
        "reference_id": "REF-HUM-CEFTRIAXONE-001",
        "inn": "ceftriaxone",
        "dosage_form": "powder for injection",
        "route_of_administration": "intravenous",
        "reference_product_name": "Ceftriaxone 1 g Powder for Injection",
        "source_type": "official_product_information_static",
        "required_pil_facts": {"route": "intravenous or intramuscular depending on product presentation", "key_warnings": ["hypersensitivity to cephalosporins", "serious allergic reactions", "antibiotic-associated diarrhoea"], "storage": "store according to approved product information"},
        "required_smpc_facts": {"contraindications": ["hypersensitivity to ceftriaxone or cephalosporins"], "warnings": ["serious hypersensitivity reactions", "antibiotic-associated colitis"]},
    }
    (root / "pil_smpc_reference" / "ceftriaxone_reference.json").write_text(json.dumps(ref, indent=2), encoding="utf-8")


def _write_section_bank_examples(root: Path) -> None:
    correct_dir = root / "correct_sections"
    defective_dir = root / "defective_sections"
    correct_dir.mkdir(parents=True, exist_ok=True)
    defective_dir.mkdir(parents=True, exist_ok=True)
    correct_pil = {
        "section_id": "m1_pil",
        "section_name": "Patient Information Leaflet",
        "quality": "correct",
        "required_fields_present": [
            "route_of_administration",
            "dosage_form",
            "strength",
            "patient_instructions",
            "warnings",
            "storage_conditions",
            "adverse_effects",
        ],
        "text": "\n".join(
            [
                "Patient Information Leaflet",
                "Product: Synthetic Ceftriaxone Product 1 g powder for injection.",
                "Route and form: Intravenous / intramuscular powder for injection.",
                "Instructions: Reconstitute and administer only by trained healthcare professionals.",
                "Warnings: Hypersensitivity to cephalosporins; severe allergic reactions; antibiotic-associated diarrhoea.",
                "Storage: Store below 30C. Protect from moisture and light.",
                "Adverse effects: diarrhoea, rash, nausea; serious reactions require urgent medical attention.",
            ]
        ),
    }
    defective_pil = {
        "section_id": "m1_pil",
        "section_name": "Patient Information Leaflet",
        "quality": "defective",
        "known_issues": ["missing_route", "missing_warnings", "missing_storage"],
        "text": "\n".join(
            [
                "Patient leaflet attached.",
                "Use medicine as directed.",
                "No detailed warnings provided.",
            ]
        ),
    }
    (correct_dir / "pil_human_correct_example.json").write_text(json.dumps(correct_pil, indent=2), encoding="utf-8")
    (defective_dir / "pil_human_defective_example.json").write_text(json.dumps(defective_pil, indent=2), encoding="utf-8")


def _write_output_readme(root: Path) -> None:
    content = """# Synthetic Dossier Dataset

This dataset is generated for regulatory LLM+vision+RAG benchmarking.

## Run
```powershell
python synthetic_data/generate_dataset.py --config synthetic_data/dataset_config.yaml --num-dossiers 192 --output synthetic_dossier_dataset
```

Smoke:
```powershell
python synthetic_data/generate_dataset.py --config synthetic_data/dataset_config.yaml --num-dossiers 16 --output synthetic_dossier_dataset_smoke
```

## Label interpretation
- `dossier_labels.jsonl`: dossier-level benchmark targets and expected SOP outcomes.
- `section_labels.jsonl`: module/section quality + SOP pass/query expectations.
- `chunk_labels.jsonl`: chunk-level text type and expected LLM action.
- `issue_labels.jsonl`: controlled known-query failure records.
"""
    (root / "README.md").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic CTD/eCTD benchmark dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--num-dossiers", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = DatasetConfig.load(args.config)
    rng = random.Random(config.seed)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    for rel in [
        "human/new_submissions", "human/renewals", "veterinary/new_submissions", "veterinary/renewals",
        "raw/human/new_submissions", "raw/human/renewals", "raw/veterinary/new_submissions", "raw/veterinary/renewals",
        "gold/human/new_submissions", "gold/human/renewals", "gold/veterinary/new_submissions", "gold/veterinary/renewals",
        "rendered_pdfs/human/new_submissions", "rendered_pdfs/human/renewals", "rendered_pdfs/veterinary/new_submissions", "rendered_pdfs/veterinary/renewals",
        "labels", "manifests", "splits", "evaluation", "section_bank/correct_sections", "section_bank/defective_sections", "section_bank/scanned_section_templates",
    ]:
        (out / rel).mkdir(parents=True, exist_ok=True)
    _write_output_readme(out)
    (out / "dataset_config.yaml").write_text(args.config.read_text(encoding="utf-8"), encoding="utf-8")

    req = RequirementMatrix(out / "sop_requirement_matrix")
    req.write_defaults()
    _build_reference_truth_files(out / "reference_truth")
    _write_section_bank_examples(out / "section_bank")

    products = ProductSampler.default_products()
    with (out / "products_master.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(products[0].keys()))
        w.writeheader()
        w.writerows(products)
    sampler = ProductSampler(rng, products)
    planner = DossierPlanner(config, rng)
    section_gen = SectionGenerator(rng)
    mutator = MutationEngine(rng)
    manifest_gen = ManifestGenerator(rng, config.default_context["document_quality_profiles"])
    label_gen = LabelGenerator()
    renderer = PdfRenderer()
    scan_sim = ScanSimulator(rng)

    dossier_manifests: list[dict[str, Any]] = []
    dossier_labels: list[dict[str, Any]] = []
    section_labels: list[dict[str, Any]] = []
    chunk_labels: list[dict[str, Any]] = []
    issue_labels: list[dict[str, Any]] = []
    page_manifests: list[dict[str, Any]] = []
    scan_manifests: list[dict[str, Any]] = []
    expected_sop_rows: list[dict[str, Any]] = []
    extraction_targets: list[dict[str, Any]] = []

    plans = planner.plan(args.num_dossiers)
    family_base: dict[str, dict[str, Any]] = {}
    for idx, plan in enumerate(plans, start=1):
        product = sampler.sample(plan["medicine_category"], plan["application_pathway"], plan["product_class"], plan["submission_type"])
        if plan["submission_status"] == "query" and plan["family_id"] in family_base:
            base = json.loads(json.dumps(family_base[plan["family_id"]]))
            dossier = base
            dossier["dossier_id"] = f"{base['dossier_id']}-Q"
            dossier["mutation_id"] = None
            dossier, issue = mutator.apply(dossier)
            dossier["mutation_id"] = issue["mutation_type"]
        else:
            dossier_id = _make_dossier_id(plan, product, idx)
            is_amr = bool(product["is_antimicrobial"])
            path = "new_submissions" if plan["submission_type"] == "new_submission" else "renewals"
            quality_profile = rng.choice(list(config.default_context["document_quality_profiles"].keys()))
            dossier = {
                "dossier_id": dossier_id,
                "family_id": plan["family_id"],
                "medicine_category": plan["medicine_category"],
                "submission_type": plan["submission_type"],
                "application_pathway": plan["application_pathway"],
                "product_class": plan["product_class"],
                "is_antimicrobial": is_amr,
                "amr_class": product["amr_class"] if is_amr else "not_applicable",
                "therapeutic_area": product["therapeutic_area"],
                "product_name": _build_realistic_product_name(product),
                "inn": product["inn"],
                "active_ingredients": str(product["active_ingredients"]).split("|"),
                "strength": product["strength"],
                "dosage_form": product["dosage_form"],
                "route_of_administration": product["route_of_administration"],
                "manufacturer_country": rng.choice(config.default_context["manufacturer_countries"]),
                "applicant_country": rng.choice(config.default_context["applicant_countries"]),
                "manufacturer_name": _realistic_org_name(rng, REALISTIC_MANUFACTURER_PREFIXES, REALISTIC_MANUFACTURER_SUFFIXES),
                "applicant_name": _realistic_org_name(rng, REALISTIC_APPLICANT_PREFIXES, REALISTIC_APPLICANT_SUFFIXES),
                "manufacturing_site_address": rng.choice(REALISTIC_SITE_ADDRESSES),
                "document_quality_profile": quality_profile,
                "submission_status": "correct",
                "expected_sop_outcome": "pass",
                "reference_required": bool(product["reference_required"]),
                "reference_source_type": "official_product_information_static" if bool(product["reference_required"]) else "not_required",
                "known_queries": [],
                "target_species": str(product["target_species"]).split("|") if plan["medicine_category"] == "veterinary" and product["target_species"] else [],
                "food_producing_species": bool(product["food_producing_species"]) if plan["medicine_category"] == "veterinary" else False,
                "requires_withdrawal_period": bool(product["requires_withdrawal_period"]) if plan["medicine_category"] == "veterinary" else False,
                "withdrawal_period_meat": "28 days" if plan["medicine_category"] == "veterinary" and bool(product["requires_withdrawal_period"]) else "",
                "withdrawal_period_milk": "7 days" if plan["medicine_category"] == "veterinary" and bool(product["requires_withdrawal_period"]) else "",
                "gmp_expiry_date": _today_minus(-600),
                "submission_date": _today_minus(rng.randint(2, 540)),
            }
            dossier["sections"] = section_gen.sections_for(dossier)
            issue = None
            family_base[plan["family_id"]] = json.loads(json.dumps(dossier))
        if plan["submission_status"] == "query" and issue:
            dossier["known_queries"] = [issue["mutation_type"]]
        path = "new_submissions" if dossier["submission_type"] == "new_submission" else "renewals"
        cat = dossier["medicine_category"]
        pages, scans, page_lookup = manifest_gen.build_page_and_scan_manifests(dossier, dossier["sections"])
        page_to_scan_artifact: dict[int, Path] = {}
        for scan in scans:
            image_name = f"{scan['dossier_id']}_p{scan['page']:04d}_{scan['section_id']}.png"
            image_path = out / "section_bank" / "scanned_section_templates" / image_name
            scan_sim.render_scan_artifact(
                out_path=image_path,
                dossier_id=scan["dossier_id"],
                page=scan["page"],
                section_id=scan["section_id"],
                effect=scan["scan_effect"],
            )
            scan["artifact_path"] = str(Path("section_bank/scanned_section_templates") / image_name)
            page_to_scan_artifact[int(scan["page"])] = image_path
        sec_labels, ch_labels, iss_labels = label_gen.build(dossier, issue, page_lookup)
        page_manifests.extend(pages)
        scan_manifests.extend(scans)
        section_labels.extend(sec_labels)
        chunk_labels.extend(ch_labels)
        issue_labels.extend(iss_labels)
        raw_obj = {"dossier_id": dossier["dossier_id"], "manifest": dossier, "sections": dossier["sections"], "mutation_log": issue}
        (out / "raw" / cat / path / f"{dossier['dossier_id']}.json").write_text(json.dumps(raw_obj, indent=2), encoding="utf-8")
        (out / "gold" / cat / path / f"{dossier['dossier_id']}.json").write_text(json.dumps(dossier, indent=2), encoding="utf-8")
        renderer.render(
            dossier,
            out / "rendered_pdfs" / cat / path / f"{dossier['dossier_id']}.pdf",
            pages,
            scan_artifact_by_page=page_to_scan_artifact,
        )
        dossier_manifests.append(dossier)
        dossier_labels.append({"dossier_id": dossier["dossier_id"], "submission_status": dossier["submission_status"], "expected_sop_outcome": dossier["expected_sop_outcome"], "known_queries": dossier["known_queries"]})
        req_result = []
        if issue:
            req_result.append(
                {
                    "requirement_id": issue["requirement_id"],
                    "status": "query",
                    "reason": issue["mutation_type"].replace("_", " "),
                    "affected_sections": [issue["section_id"]],
                    "affected_chunks": [c["chunk_id"] for c in ch_labels if c["section"] == issue["section_id"]],
                    "expected_query": issue["expected_query"],
                }
            )
        expected_sop_rows.append(
            {
                "dossier_id": dossier["dossier_id"],
                "expected_sop_outcome": dossier["expected_sop_outcome"],
                "requirement_results": req_result or [{"requirement_id": "ALL-APPLICABLE", "status": "pass", "reason": "All applicable requirements pass.", "affected_sections": [], "affected_chunks": [], "expected_query": ""}],
                "overall_expected_action": "query_applicant" if issue else "accept_requirement",
            }
        )
        extraction_targets.append({"dossier_id": dossier["dossier_id"], "targets": ["product_name", "inn", "strength", "dosage_form", "route_of_administration", "manufacturer_name", "applicant_name"]})

    split_map, split_meta = SplitGenerator(rng, config.split_ratios, config.stress_test_ratio).generate(dossier_manifests)
    _write_jsonl(out / "labels" / "dossier_labels.jsonl", dossier_labels)
    _write_jsonl(out / "labels" / "section_labels.jsonl", section_labels)
    _write_jsonl(out / "labels" / "chunk_labels.jsonl", chunk_labels)
    _write_jsonl(out / "labels" / "issue_labels.jsonl", issue_labels)
    _write_jsonl(out / "manifests" / "dossier_manifests.jsonl", dossier_manifests)
    _write_jsonl(out / "manifests" / "page_manifests.jsonl", page_manifests)
    _write_jsonl(out / "manifests" / "scan_manifests.jsonl", scan_manifests)
    _write_jsonl(out / "evaluation" / "extraction_targets.jsonl", extraction_targets)
    _write_jsonl(out / "evaluation" / "expected_sop_assessments.jsonl", expected_sop_rows)
    (out / "evaluation" / "scoring_config.yaml").write_text("scoring:\n  sop_weight: 0.6\n  extraction_weight: 0.4\n", encoding="utf-8")
    (out / "splits" / "train.json").write_text(json.dumps({"split": "train", "dossier_ids": split_map["train"]}, indent=2), encoding="utf-8")
    (out / "splits" / "validation.json").write_text(json.dumps({"split": "validation", "dossier_ids": split_map["validation"]}, indent=2), encoding="utf-8")
    (out / "splits" / "test.json").write_text(json.dumps({"split": "test", "dossier_ids": split_map["test"]}, indent=2), encoding="utf-8")
    (out / "splits" / "stress_test.json").write_text(json.dumps({"split": "stress_test", "dossier_ids": split_map["stress_test"], "split_metadata": split_meta}, indent=2), encoding="utf-8")

    validation = DatasetValidator().validate(dossier_manifests, section_labels, chunk_labels, issue_labels, page_manifests, scan_manifests, split_map)
    (out / "evaluation" / "dataset_validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")

    def count_by(key: str) -> dict[str, int]:
        hist: dict[str, int] = {}
        for row in dossier_manifests:
            hist[str(row[key])] = hist.get(str(row[key]), 0) + 1
        return hist

    summary = {
        "total_dossiers": len(dossier_manifests),
        "count_by_medicine_category": count_by("medicine_category"),
        "count_by_submission_type": count_by("submission_type"),
        "count_by_application_pathway": count_by("application_pathway"),
        "count_by_product_class": count_by("product_class"),
        "count_by_submission_status": count_by("submission_status"),
        "count_by_document_quality_profile": count_by("document_quality_profile"),
        "count_by_split": {k: len(v) for k, v in split_map.items()},
        "number_of_scanned_pages": len(scan_manifests),
        "number_of_known_query_issues": len(issue_labels),
        "number_of_section_labels": len(section_labels),
        "number_of_chunk_labels": len(chunk_labels),
        "validation_status": validation["valid"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
