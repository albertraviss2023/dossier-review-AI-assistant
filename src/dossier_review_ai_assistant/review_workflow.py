from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .policy import evaluate_amr_stewardship, evaluate_naming_policy
from .regulatory_mcp_client import RegulatoryMCPClientError, tool_data


REVIEW_AREA_ORDER = [
    "administrative",
    "naming_inn",
    "quality",
    "gmp",
    "clinical_evidence",
    "amr_stewardship",
    "consistency_checks",
]

REVIEW_AREA_LABELS = {
    "administrative": "Administrative",
    "naming_inn": "Naming / INN",
    "quality": "Quality",
    "gmp": "GMP",
    "clinical_evidence": "Clinical / Evidence",
    "amr_stewardship": "AMR Stewardship",
    "consistency_checks": "Consistency Checks",
}

PATIENT_INFO_CONCEPTS: dict[str, tuple[str, ...]] = {
    "indication": ("indication", "treatment", "use"),
    "dosing": ("dose", "dosing", "dosage"),
    "contraindications": ("contraindication", "do not take", "contraindicated"),
    "warnings": ("warning", "precaution", "caution"),
    "adverse_reactions": ("adverse", "side effect", "safety"),
    "storage": ("store", "storage", "shelf life", "shelf-life"),
}

STATIC_PATIENT_SAFETY_REFERENCES: dict[str, dict[str, Any]] = {
    "ceftriaxone": {
        "source": "static_reference_truth",
        "reference_name": "Static Ceftriaxone Product Information",
        "reference_urls": [],
        "text": (
            "Indication: treatment of susceptible bacterial infections. "
            "Dosage and administration guidance is provided. "
            "Contraindications include hypersensitivity to cephalosporins. "
            "Warnings include severe allergic reactions and antibiotic-associated colitis. "
            "Adverse reactions include diarrhoea and rash. "
            "Storage according to approved product information."
        ),
    },
    "amoxicillin": {
        "source": "static_reference_truth",
        "reference_name": "Static Amoxicillin Product Information",
        "reference_urls": [],
        "text": (
            "Indication for susceptible bacterial infections. "
            "Dosage instructions by age and infection severity. "
            "Contraindications include hypersensitivity to penicillins. "
            "Warnings include severe hypersensitivity and antibiotic-associated diarrhoea. "
            "Adverse reactions include nausea, rash, and diarrhoea. "
            "Storage conditions are explicitly listed."
        ),
    },
    "azithromycin": {
        "source": "static_reference_truth",
        "reference_name": "Static Azithromycin Product Information",
        "reference_urls": [],
        "text": (
            "Indications are listed with dosing by infection type. "
            "Contraindications include hypersensitivity to macrolides. "
            "Warnings include QT prolongation risk and hepatic precautions. "
            "Adverse reactions include gastrointestinal effects. "
            "Storage and handling information is included."
        ),
    },
    "ciprofloxacin": {
        "source": "static_reference_truth",
        "reference_name": "Static Ciprofloxacin Product Information",
        "reference_urls": [],
        "text": (
            "Indications and dose by infection profile are provided. "
            "Contraindications include quinolone hypersensitivity. "
            "Warnings include tendon disorders and CNS effects. "
            "Adverse reactions include nausea and diarrhoea. "
            "Storage conditions are specified."
        ),
    },
    "cefiderocol": {
        "source": "static_reference_truth",
        "reference_name": "Static Cefiderocol Product Information",
        "reference_urls": [],
        "text": (
            "Indications include treatment of severe infections due to susceptible Gram-negative pathogens. "
            "Dosage and infusion instructions are defined with renal adjustment guidance. "
            "Contraindications include hypersensitivity to beta-lactam antibacterials. "
            "Warnings include hypersensitivity, Clostridioides difficile-associated diarrhoea, and resistance-selection risk. "
            "Adverse reactions include infusion-site events, gastrointestinal effects, and liver enzyme elevations. "
            "Storage and reconstitution handling conditions are specified."
        ),
    },
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "have",
    "has",
    "been",
    "were",
    "their",
    "they",
    "will",
    "when",
    "where",
    "which",
    "what",
    "your",
    "about",
    "under",
    "using",
    "used",
    "against",
    "must",
    "should",
    "would",
    "there",
    "these",
    "those",
    "them",
    "then",
}


def _resolve_static_patient_safety_reference(dossier: dict[str, Any]) -> dict[str, Any] | None:
    product = dossier.get("product", {}) or {}
    candidate_keys = [
        str(product.get("inn_name", "")).strip().lower(),
        str(product.get("inn", "")).strip().lower(),
        str(dossier.get("inn", "")).strip().lower(),
    ]
    for key in candidate_keys:
        if key and key in STATIC_PATIENT_SAFETY_REFERENCES:
            return STATIC_PATIENT_SAFETY_REFERENCES[key]
    return None


def _find_section(dossier: dict[str, Any], *keywords: str) -> dict[str, Any] | None:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for section in dossier.get("sections", []):
        title = str(section.get("title", "")).lower()
        text = str(section.get("text", "")).lower()
        if all(any(keyword in field for field in (title, text)) for keyword in lowered_keywords):
            return section
    return None


def _section_reference(dossier_id: str, section: dict[str, Any] | None) -> str:
    if not section:
        return f"{dossier_id}:unknown"
    section_id = str(section.get("section_id", "unknown"))
    return f"{dossier_id}:{section_id}"


def _token_set(text: str) -> set[str]:
    return {
        token.strip(".,;:!?()[]{}\"'").lower()
        for token in str(text).split()
        if len(token.strip(".,;:!?()[]{}\"'")) > 3
        and token.strip(".,;:!?()[]{}\"'").lower() not in STOPWORDS
    }


def _concept_coverage(text: str) -> dict[str, bool]:
    lowered = str(text).lower()
    coverage: dict[str, bool] = {}
    for concept, terms in PATIENT_INFO_CONCEPTS.items():
        coverage[concept] = any(term in lowered for term in terms)
    return coverage


def _concept_evidence_snippet(text: str, concept: str) -> str:
    source = str(text or "").strip()
    if not source:
        return "Not stated"
    lowered = source.lower()
    terms = PATIENT_INFO_CONCEPTS.get(concept, ())
    sentences = [part.strip() for part in source.replace("\n", " ").split(".") if part.strip()]
    for sentence in sentences:
        s_lower = sentence.lower()
        if any(term in s_lower for term in terms):
            snippet = sentence.strip()
            if len(snippet) > 140:
                snippet = snippet[:137].rstrip() + "..."
            return snippet
    if any(term in lowered for term in terms):
        fallback = source[:140].strip()
        return fallback + ("..." if len(source) > 140 else "")
    return "Not stated"


def _concept_label(concept: str) -> str:
    return concept.replace("_", " ").title()


def _is_verified_reference_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return False
    host = (parsed.netloc or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    blocked_hosts = {"example.invalid", "localhost", "127.0.0.1"}
    if host in blocked_hosts or host.endswith(".invalid"):
        return False
    return True


def evaluate_review_type_specifics(dossier: dict[str, Any], review_type: str) -> dict[str, Any]:
    product_info = (
        _find_section(dossier, "product", "information")
        or _find_section(dossier, "patient", "information")
        or _find_section(dossier, "pil")
        or _find_section(dossier, "smpc")
    )
    dossier_id = str(dossier.get("dossier_id", "unknown"))
    product_text = str(product_info.get("text", "")) if product_info else ""
    reference_materials = dossier.get("reference_materials", {}) or {}
    baseline_text = " ".join(
        str(reference_materials.get(key, "")).strip()
        for key in (
            "innovator_packaging_text",
            "innovator_patient_information_text",
            "innovator_smpc_text",
            "innovator_reference_text",
        )
        if str(reference_materials.get(key, "")).strip()
    ).strip()
    baseline_name = str(reference_materials.get("innovator_reference_name", "")).strip() or "innovator reference"
    baseline_urls = [url for url in reference_materials.get("reference_urls", []) if str(url).strip()]
    verified_reference_urls = [url for url in baseline_urls if _is_verified_reference_url(url)]
    baseline_source = "none"
    mcp_innovator_sections: list[dict[str, Any]] = []
    mcp_section_provenance: list[dict[str, Any]] = []
    mcp_source_selection_policy: dict[str, Any] | None = None
    if baseline_text:
        baseline_source = "verified_external" if verified_reference_urls else "baseline_text"

    # Always attempt MCP baseline retrieval for generic dossiers when no baseline text is available.
    if review_type == "generic" and not baseline_text:
        try:
            innovator_response = tool_data(
                "fetch_innovator_patient_information",
                {
                    "active_ingredient": str(dossier.get("product", {}).get("inn_name", "")),
                    "reference_urls": verified_reference_urls,
                },
            )
            mcp_innovator_sections = list(innovator_response.get("data", {}).get("sections", []))
            if mcp_innovator_sections:
                baseline_text = " ".join(str(item.get("text", "")).strip() for item in mcp_innovator_sections if str(item.get("text", "")).strip()).strip()
                baseline_name = str(innovator_response.get("data", {}).get("reference_product", baseline_name))
                mcp_section_provenance = list(innovator_response.get("data", {}).get("section_provenance", []))
                mcp_source_selection_policy = innovator_response.get("data", {}).get("source_selection_policy")
                fetched_urls = [url for url in innovator_response.get("data", {}).get("raw_source_refs", []) if str(url).strip()]
                if fetched_urls:
                    baseline_urls = fetched_urls
                    verified_reference_urls = [url for url in baseline_urls if _is_verified_reference_url(url)]
                source_type = str((innovator_response.get("source_refs", [{}])[0] or {}).get("source_type", "external_or_cache"))
                baseline_source = f"mcp_{source_type}"
        except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
            pass

    if review_type == "generic" and not baseline_text:
        static_ref = _resolve_static_patient_safety_reference(dossier)
        if static_ref:
            baseline_text = str(static_ref.get("text", "")).strip()
            if baseline_text:
                baseline_name = str(static_ref.get("reference_name", baseline_name))
                baseline_urls = [url for url in static_ref.get("reference_urls", []) if str(url).strip()]
                verified_reference_urls = [url for url in baseline_urls if _is_verified_reference_url(url)]
                baseline_source = str(static_ref.get("source", "static_reference_truth"))
    submitted_coverage = _concept_coverage(product_text)
    baseline_coverage = _concept_coverage(baseline_text) if baseline_text else {k: False for k in PATIENT_INFO_CONCEPTS}
    comparison_matrix: list[dict[str, Any]] = []
    for concept in PATIENT_INFO_CONCEPTS:
        comparison_matrix.append(
            {
                "concept_key": concept,
                "dimension": _concept_label(concept),
                "submitted_present": bool(submitted_coverage.get(concept, False)),
                "external_present": bool(baseline_coverage.get(concept, False)),
                "gap": bool(baseline_coverage.get(concept, False) and not submitted_coverage.get(concept, False)),
                "submitted_evidence": _concept_evidence_snippet(product_text, concept),
                "external_evidence": _concept_evidence_snippet(baseline_text, concept) if baseline_text else "Not stated",
                "evidence_source": baseline_source if baseline_text else "none",
            }
        )

    findings: list[dict[str, Any]] = []
    notes: list[str] = []
    evidence_ref = _section_reference(dossier_id, product_info)
    status = "adequate"
    example_comparison: dict[str, Any] | None = None

    try:
        example_response = tool_data(
            "get_section_examples",
            {
                "section_type": "patient_information_leaflet",
                "example_type": "both",
                "product_type": review_type,
                "top_k": 4,
            },
        )
        current_section = {
            "section_id": str(product_info.get("section_id", "product_information")) if product_info else "product_information",
            "section_type": "patient_information_leaflet",
            "title": str(product_info.get("title", "Product Information and Naming")) if product_info else "Product Information and Naming",
            "text": product_text,
        }
        examples = example_response["data"].get("examples", [])
        example_comparison_response = tool_data(
            "compare_current_section_to_examples",
            {
                "current_section": current_section,
                "correct_examples": [item for item in examples if item.get("label") == "correct"],
                "incorrect_examples": [item for item in examples if item.get("label") == "incorrect"],
                "comparison_dimensions": ["completeness", "safety wording", "contraindications", "dosage clarity"],
            },
        )
        example_comparison = example_comparison_response["data"]
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        example_comparison = None

    if review_type == "generic":
        notes.append("Generic workflow requires comparison of packaging and patient information against innovator reference material when provided.")
        if baseline_source == "static_reference_truth" and baseline_text:
            notes.append("No live external baseline was supplied; static reference-truth safety facts were used for patient-safety comparison.")
        if baseline_text and (verified_reference_urls or baseline_source.startswith("mcp_")):
            try:
                if not mcp_innovator_sections:
                    innovator_response = tool_data(
                        "fetch_innovator_patient_information",
                        {
                            "active_ingredient": str(dossier.get("product", {}).get("inn_name", "")),
                            "reference_urls": verified_reference_urls,
                        },
                    )
                    mcp_innovator_sections = list(innovator_response.get("data", {}).get("sections", []))
                current_pil_sections = [
                    {
                        "section_name": str(product_info.get("title", "Patient Information")) if product_info else "Patient Information",
                        "text": product_text,
                        "source_url": None,
                    }
                ]
                comparison_response = tool_data(
                    "compare_generic_patient_information",
                    {
                        "current_pil_sections": current_pil_sections,
                        "innovator_pil_sections": mcp_innovator_sections,
                        "comparison_dimensions": ["indications", "dosage", "contraindications", "warnings", "side_effects", "storage"],
                    },
                )
                comparison_payload = comparison_response["data"]
                overall_alignment = str(comparison_payload.get("overall_alignment", "unclear"))
                if overall_alignment in {"partial", "not_aligned", "unclear"}:
                    status = "partial"
                for difference in comparison_payload.get("differences", []):
                    findings.append(
                        {
                            "issue": str(difference.get("issue", "Generic patient-information deviation detected.")),
                            "violated_rule": "Generic review must compare dossier patient information against innovator reference materials when provided",
                            "severity": str(difference.get("severity", "major")),
                            "location": str(difference.get("section", product_info.get("title", "Patient Information") if product_info else "Patient Information")),
                            "evidence_reference": evidence_ref,
                            "recommendation": str(difference.get("recommendation", "Align the generic patient information with the innovator reference or justify the deviation.")),
                        }
                    )
                notes.append(
                    f"Generic baseline comparison used {baseline_name} through MCP patient-information tools with overall alignment {overall_alignment}."
                )
            except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
                baseline_tokens = _token_set(baseline_text)
                dossier_tokens = _token_set(product_text)
                overlap_ratio = (
                    len(baseline_tokens & dossier_tokens) / max(len(baseline_tokens), 1)
                    if baseline_tokens
                    else 1.0
                )
                baseline_coverage = _concept_coverage(baseline_text)
                dossier_coverage = _concept_coverage(product_text)
                missing_concepts = [
                    concept.replace("_", " ")
                    for concept, required in baseline_coverage.items()
                    if required and not dossier_coverage.get(concept, False)
                ]
                if overlap_ratio < 0.2:
                    status = "partial"
                    findings.append(
                        {
                            "issue": f"Generic dossier wording diverges materially from the supplied innovator baseline ({baseline_name}).",
                            "violated_rule": "Generic review packaging and patient-information comparison against innovator baseline",
                            "severity": "major",
                            "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                            "evidence_reference": evidence_ref,
                            "recommendation": "Align the product information and patient-information wording more closely to the innovator baseline or justify the deviations.",
                        }
                    )
                if missing_concepts:
                    status = "partial"
                    findings.append(
                        {
                            "issue": f"Generic dossier patient-information content is missing baseline concepts: {', '.join(missing_concepts)}.",
                            "violated_rule": "Generic review must compare dossier patient information against innovator reference materials when provided",
                            "severity": "major",
                            "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                            "evidence_reference": evidence_ref,
                            "recommendation": "Restore the missing patient-information concepts or justify the generic-labeling deviation.",
                        }
                    )
                notes.append(
                    f"Generic baseline comparison used {baseline_name} with lexical overlap ratio {overlap_ratio:.2f}."
                )
        elif verified_reference_urls and not baseline_text:
            status = "baseline_declared_not_ingested"
            notes.append(
                "Verified external reference URLs were supplied, but no ingested baseline text was attached. The workflow did not claim wording-equivalence because the innovator content was not actually loaded into the evidence packet."
            )
            findings.append(
                {
                    "issue": "A verified innovator reference was declared for generic review, but the baseline content was not ingested for comparison.",
                    "violated_rule": "Generic review requires an accessible innovator baseline when wording-equivalence checks are expected",
                    "severity": "minor",
                    "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                    "evidence_reference": evidence_ref,
                    "recommendation": "Ingest the referenced innovator packaging or PIL text before treating the generic wording comparison as complete.",
                }
            )
        elif baseline_text or baseline_urls:
            status = "baseline_unverified"
            notes.append(
                "Reference material was declared, but it was not validated as an external source. The workflow did not enforce wording-equivalence against unverified or demo baseline content."
            )
            findings.append(
                {
                    "issue": "Generic-review baseline material was present only as unverified or demo content.",
                    "violated_rule": "Generic review must distinguish verified external innovator references from internal demo text",
                    "severity": "minor",
                    "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                    "evidence_reference": evidence_ref,
                    "recommendation": "Replace demo baseline material with a verified external innovator source before relying on the comparison result.",
                }
            )
        else:
            status = "baseline_not_provided"
            notes.append("No innovator baseline reference material was supplied, so wording-equivalence checks were not enforced.")
    else:
        notes.append("Innovation workflow checks completeness, clarity, safety wording, and regulatory adequacy without requiring wording equivalence to an innovator baseline.")
        coverage = _concept_coverage(product_text)
        missing_concepts = [concept.replace("_", " ") for concept, present in coverage.items() if not present]
        if missing_concepts:
            status = "partial"
            findings.append(
                {
                    "issue": f"Innovation dossier product information is missing key patient-information elements: {', '.join(missing_concepts)}.",
                    "violated_rule": "Innovation review must assess completeness, clarity, required patient information, safety wording, and regulatory adequacy",
                    "severity": "major",
                    "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                    "evidence_reference": evidence_ref,
                    "recommendation": "Add the missing patient-information and safety elements before the dossier proceeds.",
                }
            )
        if len(product_text) < 220:
            status = "partial"
            findings.append(
                {
                    "issue": "Innovation dossier product-information content is too limited to show complete safety and patient-information adequacy.",
                    "violated_rule": "Innovation review must assess completeness and clarity of patient information",
                    "severity": "major",
                    "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                    "evidence_reference": evidence_ref,
                    "recommendation": "Expand the product information section with clear indication, dosing, warnings, contraindications, and storage guidance.",
                }
            )

    if example_comparison:
        classification = str(example_comparison.get("classification", "unclear"))
        if classification in {"partially_compliant", "non_compliant", "unclear"}:
            status = "partial" if status == "adequate" else status
        for evidence_item in example_comparison.get("evidence", []):
            findings.append(
                {
                    "issue": str(evidence_item.get("finding", "Section example comparison identified a compliance issue.")),
                    "violated_rule": "Section content must satisfy completeness, safety wording, contraindications, and dosage clarity checks",
                    "severity": str(evidence_item.get("severity", "minor")),
                    "location": product_info.get("title", "Product Information and Naming") if product_info else "Product information",
                    "evidence_reference": evidence_ref,
                    "recommendation": "Address the highlighted patient-information issue in line with compliant section examples.",
                }
            )
        notes.append(f"Example comparison classified the section as {classification}.")

    return {
        "review_type": review_type,
        "status": status,
        "baseline_available": bool(baseline_text),
        "baseline_verified": bool(baseline_text and verified_reference_urls),
        "baseline_reference_name": baseline_name if baseline_text else None,
        "baseline_reference_urls": baseline_urls,
        "verified_reference_urls": verified_reference_urls,
        "comparison_matrix": comparison_matrix,
        "section_provenance": mcp_section_provenance,
        "source_selection_policy": mcp_source_selection_policy,
        "notes": notes,
        "findings": findings,
        "example_comparison": example_comparison,
    }


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "major": 0, "minor": 0, "advisory": 0}
    for item in findings:
        severity = str(item.get("severity", "advisory")).lower()
        if severity not in counts:
            severity = "advisory"
        counts[severity] += 1
    return counts


def _verdict_label(review_payload: dict[str, Any], workflow_complete: bool, naming_policy: dict[str, Any], amr: dict[str, Any]) -> str:
    recommendation = str(review_payload.get("recommendation", "unknown"))
    verifier = review_payload.get("verifier", {})
    if naming_policy.get("is_infringement"):
        return "not_acceptable"
    if not workflow_complete or not verifier.get("passed", False):
        return "escalate_for_higher_review"
    if recommendation == "approval_denied":
        return "not_acceptable"
    if recommendation == "additional_information_required":
        return "requires_revision"
    if recommendation == "approval_granted" and (
        amr.get("restricted_authorization") or amr.get("fast_track_candidate")
    ):
        return "acceptable_with_conditions"
    if recommendation == "approval_granted":
        return "acceptable"
    return "escalate_for_higher_review"


def _review_area_for_finding(item: dict[str, Any]) -> str:
    workflow_step = str(item.get("workflow_step", "")).lower()
    issue = str(item.get("issue", "")).lower()
    location = str(item.get("location", "")).lower()
    violated_rule = str(item.get("violated_rule", "")).lower()
    combined = " ".join((workflow_step, issue, location, violated_rule))
    if "administrative" in workflow_step:
        return "administrative"
    if "inn similarity" in workflow_step or "naming" in combined:
        return "naming_inn"
    if "amr stewardship" in workflow_step or "aware" in combined or "stewardship" in combined:
        return "amr_stewardship"
    if "consistency" in workflow_step:
        return "consistency_checks"
    if any(term in combined for term in ("gmp", "manufacturer", "certificate", "capa", "inspection")):
        return "gmp"
    if any(term in combined for term in ("clinical", "trial", "endpoint", "benefit-risk", "efficacy", "safety")):
        return "clinical_evidence"
    return "quality"


def build_findings_summary_tables(findings_register: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {area: [] for area in REVIEW_AREA_ORDER}
    for item in findings_register:
        grouped[_review_area_for_finding(item)].append(
            {
                "severity": str(item.get("severity", "advisory")),
                "violated_rule": str(item.get("violated_rule", "")),
                "evidence_reference": str(item.get("evidence_reference", item.get("location", ""))),
                "recommendation": str(item.get("recommendation", "")),
            }
        )
    return grouped


def render_findings_summary_markdown(summary_tables: dict[str, list[dict[str, Any]]]) -> str:
    ref_map: dict[str, int] = {}
    next_ref = 1
    for area in REVIEW_AREA_ORDER:
        for row in summary_tables.get(area, []):
            ref = str(row.get("evidence_reference", "")).strip()
            if ref and ref not in ref_map:
                ref_map[ref] = next_ref
                next_ref += 1

    sections: list[str] = []
    for area in REVIEW_AREA_ORDER:
        rows = summary_tables.get(area, [])
        sections.append(f"#### {REVIEW_AREA_LABELS[area]}")
        sections.append("")
        sections.append("| Severity | Violated rule | Evidence reference | Recommendation |")
        sections.append("| --- | --- | --- | --- |")
        if rows:
            for row in rows:
                ref_num = ref_map.get(str(row.get("evidence_reference", "")).strip(), "n/a")
                rendered_ref = f"[{ref_num}]" if isinstance(ref_num, int) else str(ref_num)
                sections.append(
                    f"| {row['severity']} | {row['violated_rule']} | {rendered_ref} | {row['recommendation']} |"
                )
        else:
            sections.append("| none | No recorded violations in this area | n/a | Continue standard review monitoring |")
        sections.append("")
    return "\n".join(sections).strip()


def _build_scanned_document_challenge_mode(dossier: dict[str, Any]) -> dict[str, Any]:
    extraction = ((dossier.get("provenance", {}) or {}).get("extraction", {}) or {})
    visual_evidence = extraction.get("visual_evidence", []) or []
    warnings = [str(item) for item in (extraction.get("warnings", []) or [])]
    warnings_text = " ".join(warnings).lower()
    scanned_detected = bool(extraction.get("ocr_used")) or bool(visual_evidence) or any(
        token in warnings_text for token in ("ocr", "image_heavy", "render_failed")
    )

    detected: list[str] = []
    for item in visual_evidence:
        evidence_type = str(item.get("evidence_type", "")).lower()
        excerpt = str(item.get("ocr_excerpt", "")).lower()
        summary = str(item.get("summary", "")).lower()
        combined = " ".join((evidence_type, excerpt, summary))
        if "gmp" in combined and "scanned GMP certificate" not in detected:
            detected.append("scanned GMP certificate")
        if "stability" in combined and "scanned stability table" not in detected:
            detected.append("low-resolution stability table")
        if "coa" in combined and "scanned CoA table" not in detected:
            detected.append("scanned CoA table")
        if "stamp" in combined and "faint stamp" not in detected:
            detected.append("faint stamp")
        if "rotat" in combined and "rotated page" not in detected:
            detected.append("rotated page")
    for item in warnings:
        lowered = item.lower()
        if "ocr_fallback_used" in lowered and "low-resolution stability table" not in detected:
            detected.append("low-resolution stability table")
        if "image_heavy_pdf" in lowered and "rotated page" not in detected:
            detected.append("rotated page")
    if scanned_detected and not detected:
        detected.append("scanned evidence detected")

    gmp_conf = 0.82 if any("gmp" in str(item).lower() for item in visual_evidence) else None
    coa_conf = 0.76 if any("coa" in str(item).lower() for item in visual_evidence) else None
    stamp_detected = any("stamp" in str(item).lower() for item in visual_evidence)

    return {
        "enabled": scanned_detected,
        "vision_extraction_detected": detected,
        "text_rag_failure_risk": (
            "high"
            if any(
                marker in detected
                for marker in (
                    "scanned GMP certificate",
                    "scanned CoA table",
                    "low-resolution stability table",
                )
            )
            else "low"
        ),
        "extraction_confidence": {
            "gmp_expiry_date": gmp_conf,
            "coa_batch_number": coa_conf,
            "signature_or_stamp_detected": stamp_detected,
        },
        "ocr_used": bool(extraction.get("ocr_used")),
        "extraction_method": str(extraction.get("extraction_method", "unknown")),
        "page_count": int(extraction.get("page_count", 0) or 0),
        "image_count": int(extraction.get("image_count", 0) or 0),
        "warnings": warnings,
    }


def _collect_dossier_text(dossier: dict[str, Any]) -> str:
    parts: list[str] = []
    product = dossier.get("product", {}) or {}
    for value in (
        product.get("product_name"),
        product.get("inn_name"),
        product.get("dosage_form"),
        product.get("route_of_administration"),
        dossier.get("indication"),
        dossier.get("therapeutic_area"),
    ):
        if value:
            parts.append(str(value))
    for section in dossier.get("sections", []) or []:
        text = section.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts).lower()


def _bool_label(value: bool) -> str:
    return "present" if value else "missing"


def _derive_amr_checks(
    dossier: dict[str, Any],
    amr: dict[str, Any],
    review_type: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    text = _collect_dossier_text(dossier)
    product = dossier.get("product", {}) or {}
    is_vet = str(dossier.get("medicine_category", "")).lower() == "veterinary" or bool(
        dossier.get("food_producing_species")
    )
    indication = str(dossier.get("indication") or dossier.get("therapeutic_area") or "not_stated")
    active_ingredient = str(amr.get("normalized_ingredient") or product.get("inn_name") or "unknown")
    aware = str(amr.get("aware_category") or "not_applicable")

    required_warning_present = any(
        token in text
        for token in (
            "antimicrobial stewardship",
            "antibiotic stewardship",
            "antimicrobial resistance",
            "amr warning",
            "use only when",
            "prescription only",
        )
    )
    stewardship_justification_present = any(
        token in text
        for token in (
            "stewardship justification",
            "resistance surveillance",
            "justification for antimicrobial use",
            "aware rationale",
        )
    )
    human_decision = "query_applicant" if (not required_warning_present or not stewardship_justification_present) else "pass"
    human_reasons: list[str] = []
    if not required_warning_present:
        human_reasons.append("Required AMR warning is missing.")
    if not stewardship_justification_present:
        human_reasons.append("Stewardship justification is missing.")

    human_check = {
        "active_ingredient": active_ingredient,
        "amr_class": aware,
        "product_type": review_type,
        "indication": indication,
        "required_warning": _bool_label(required_warning_present),
        "stewardship_justification": _bool_label(stewardship_justification_present),
        "decision": human_decision,
        "decision_reasons": human_reasons,
    }

    if not is_vet:
        return human_check, None

    target_species = dossier.get("target_species") or product.get("target_species") or []
    if isinstance(target_species, str):
        target_species = [part.strip() for part in target_species.split("|") if part.strip()]
    withdrawal_present = any(
        token in text
        for token in (
            "withdrawal period",
            "withholding period",
            "withdrawal: meat",
            "withdrawal: milk",
            "residue depletion",
        )
    )
    residue_present = any(token in text for token in ("residue", "maximum residue limit", "mrl"))
    vet_warning_complete = required_warning_present and any(
        token in text for token in ("food-producing", "meat", "milk", "egg")
    )
    vet_decision = "query_applicant" if (not withdrawal_present or not residue_present or not vet_warning_complete) else "pass"
    vet_reasons: list[str] = []
    if not withdrawal_present:
        vet_reasons.append("Withdrawal period is missing.")
    if not residue_present:
        vet_reasons.append("Residue information is missing.")
    if not vet_warning_complete:
        vet_reasons.append("AMR warning is incomplete for food-safety use context.")

    veterinary_check = {
        "target_species": target_species,
        "withdrawal_period": _bool_label(withdrawal_present),
        "residue_information": _bool_label(residue_present),
        "amr_warning": "complete" if vet_warning_complete else "incomplete",
        "decision": vet_decision,
        "decision_reasons": vet_reasons,
    }
    return human_check, veterinary_check


def build_workflow_evaluation(dossier: dict[str, Any], review_payload: dict[str, Any]) -> dict[str, Any]:
    product = dossier.get("product", {})
    organization = dossier.get("organization", {})
    review_type = str(review_payload.get("review_type", "generic"))
    section_diagnostics = review_payload.get("section_diagnostics", [])
    policy_hits = list(review_payload.get("policy_rule_hits", []))
    naming = evaluate_naming_policy(dossier)
    amr = evaluate_amr_stewardship(dossier)
    review_type_specific = evaluate_review_type_specifics(dossier, review_type)
    scanned_challenge_mode = _build_scanned_document_challenge_mode(dossier)

    admin_section = _find_section(dossier, "application") or _find_section(dossier, "administrative")
    payment_section = _find_section(dossier, "payment") or _find_section(dossier, "fee")
    authorization_section = _find_section(dossier, "authorization") or _find_section(dossier, "signed")
    structure_missing = [
        item for item in section_diagnostics
        if item.get("presence") != "present" or item.get("correctness") != "correct" or item.get("length_status") != "length_ok"
    ]

    findings_register: list[dict[str, Any]] = []
    dossier_id = str(dossier.get("dossier_id", "unknown"))

    def add_finding(
        *,
        workflow_step: str,
        issue: str,
        violated_rule: str,
        severity: str,
        location: str,
        recommendation: str,
        evidence_reference: str,
    ) -> None:
        findings_register.append(
            {
                "workflow_step": workflow_step,
                "issue": issue,
                "violated_rule": violated_rule,
                "severity": severity,
                "location": location,
                "recommendation": recommendation,
                "evidence_reference": evidence_reference,
            }
        )

    admin_violations: list[str] = []
    if admin_section is None:
        admin_violations.append("Administrative application section is missing.")
        add_finding(
            workflow_step="Administrative completeness review",
            issue="Mandatory administrative application section is missing.",
            violated_rule="Missing mandatory administrative documents = violation",
            severity="major",
            location="Module 1 / Administrative",
            recommendation="Provide the required administrative section and supporting documents.",
            evidence_reference=_section_reference(dossier_id, admin_section),
        )
    else:
        admin_text = str(admin_section.get("text", "")).lower()
        payment_text = str(payment_section.get("text", "")).lower() if payment_section else ""
        authorization_text = str(authorization_section.get("text", "")).lower() if authorization_section else ""
        has_signature_evidence = any(term in admin_text for term in ("signed", "signature")) or bool(authorization_text.strip())
        has_payment_evidence = any(term in admin_text for term in ("payment", "fee")) or bool(payment_text.strip())
        if not has_signature_evidence:
            admin_violations.append("No signature evidence was detected in the administrative material.")
            add_finding(
                workflow_step="Administrative completeness review",
                issue="No signature evidence was detected in the administrative material.",
                violated_rule="Missing signed application form = violation",
                severity="major",
                location=str(admin_section.get("title", "Administrative section")),
                recommendation="Confirm the signed application form is present and legible.",
                evidence_reference=_section_reference(dossier_id, admin_section),
            )
        if not has_payment_evidence:
            admin_violations.append("No proof of payment was detected in the administrative material.")
            add_finding(
                workflow_step="Administrative completeness review",
                issue="No proof of payment was detected in the administrative material.",
                violated_rule="Missing proof of payment where required = violation",
                severity="minor",
                location=str(admin_section.get("title", "Administrative section")),
                recommendation="Confirm the payment receipt or fee evidence is included where required.",
                evidence_reference=_section_reference(dossier_id, admin_section),
            )

    structure_violations: list[str] = []
    for item in structure_missing:
        structure_violations.append(
            f"{item.get('title', 'Unknown section')}: presence={item.get('presence')}, length={item.get('length_status')}, correctness={item.get('correctness')}"
        )
        add_finding(
            workflow_step="Structural dossier mapping",
            issue=f"{item.get('title', 'Unknown section')} is missing, malformed, or incomplete.",
            violated_rule="Missing required section = violation",
            severity="major" if item.get("critical") else "minor",
            location=str(item.get("title", "Unknown section")),
            recommendation="Restore the required section with readable and complete content.",
            evidence_reference=f"{dossier_id}:{item.get('section_id', 'unknown')}",
        )

    naming_step = {
        "proposed_name": product.get("product_name", "unknown"),
        "who_inn": naming.get("closest_inn") or product.get("inn_name", "unknown"),
        "similarity_index": round(float(naming.get("max_similarity", 0.0)), 4),
        "threshold": 0.7,
        "threshold_result": "failed" if naming.get("is_infringement") else "passed",
        "similarity_type": "orthographic",
        "interpretation": naming.get("rationale", ""),
        "flag_status": "naming_violation" if naming.get("is_infringement") else "acceptable_naming",
        "rule_consequence": (
            "Product name cannot be accepted because INN similarity exceeds 70%."
            if naming.get("is_infringement")
            else "No blocking INN naming issue was identified."
        ),
    }
    if naming.get("is_infringement"):
        name_section = _find_section(dossier, "product", "information") or _find_section(dossier, "naming")
        add_finding(
            workflow_step="WHO INN similarity review",
            issue=f"Product name exceeds the INN similarity threshold against {naming_step['who_inn']}.",
            violated_rule="INN similarity > 70% = naming violation",
            severity="critical",
            location="Product Information and Naming",
            recommendation="Rename the product before the dossier can be accepted.",
            evidence_reference=_section_reference(dossier_id, name_section),
        )

    applicable_rules = [
        "Administrative completeness checklist",
        "Structural dossier completeness rules",
        "WHO INN similarity rule",
        "Section adequacy and evidence sufficiency rules",
    ]
    if review_type == "generic":
        applicable_rules.append("Generic review packaging and patient-information comparison against innovator reference when provided")
    else:
        applicable_rules.append("Innovation review completeness, clarity, safety wording, and regulatory adequacy assessment")
    if amr.get("applies"):
        applicable_rules.append("WHO AWaRe stewardship rules")

    for finding in review_type_specific.get("findings", []):
        add_finding(
            workflow_step="Section-by-section technical review",
            issue=str(finding["issue"]),
            violated_rule=str(finding["violated_rule"]),
            severity=str(finding["severity"]),
            location=str(finding["location"]),
            recommendation=str(finding["recommendation"]),
            evidence_reference=str(finding["evidence_reference"]),
        )

    section_results: list[dict[str, Any]] = []
    for item in section_diagnostics:
        status = "compliant"
        if item.get("presence") != "present":
            status = "non_compliant"
        elif item.get("correctness") != "correct" or item.get("length_status") != "length_ok":
            status = "partially_compliant"
        section_results.append(
            {
                "section": item.get("title", "unknown"),
                "status": status,
                "presence": item.get("presence", "unknown"),
                "length_status": item.get("length_status", "unknown"),
                "correctness": item.get("correctness", "unknown"),
                "critical": bool(item.get("critical", False)),
            }
        )

    if str(review_payload.get("recommendation")) == "additional_information_required":
        for hit in policy_hits:
            if "information_gap" in hit or "clinical_missing" in hit:
                add_finding(
                    workflow_step="Section-by-section technical review",
                    issue=f"Technical review identified {hit.replace('_', ' ')}.",
                    violated_rule="Present but inadequate section = violation",
                    severity="major",
                    location="Scientific dossier content",
                    recommendation="Provide the missing technical evidence or clarifying support.",
                    evidence_reference=dossier_id,
                )
    if any("gmp" in hit for hit in policy_hits):
        gmp_section = _find_section(dossier, "gmp") or _find_section(dossier, "manufacturer")
        add_finding(
            workflow_step="Section-by-section technical review",
            issue="Manufacturing quality evidence indicates GMP non-compliance, expiry, or missing support.",
            violated_rule="Required evidence missing = violation",
            severity="critical" if "gmp_non_compliant" in policy_hits else "major",
            location="Manufacturer and GMP Evidence",
            recommendation="Resolve GMP deficiencies and provide current manufacturing evidence.",
            evidence_reference=_section_reference(dossier_id, gmp_section),
        )

    amr_step = {
        "applicable": bool(amr.get("applies")),
        "antimicrobial_status": "antimicrobial" if amr.get("applies") else "not_applicable",
        "aware_category": amr.get("aware_category", "not_applicable"),
        "stewardship_rule_application": amr.get("rationale", ""),
        "fast_track_status": bool(amr.get("fast_track_candidate")),
        "authorization_control": amr.get("authorization_control", "standard_authorization"),
        "watch_or_reserve_caution": bool(
            amr.get("restricted_authorization") or amr.get("watch_similarity_restriction")
        ),
        "findings": list(amr.get("source_trace", [])),
        "policy_decision": {
            "decision": "restricted_authorization" if amr.get("restricted_authorization") else ("fast_track_candidate" if amr.get("fast_track_candidate") else "standard_authorization"),
            "required_controls": (
                [
                    "Restricted authorization conditions",
                    "Stewardship monitoring plan",
                    "Resistance surveillance commitments",
                ]
                if amr.get("restricted_authorization")
                else (["Accelerated review controls", "Post-authorization stewardship surveillance"] if amr.get("fast_track_candidate") else ["Standard stewardship monitoring"])
            ),
            "decision_basis": {
                "aware_category": amr.get("aware_category", "unknown"),
                "watch_similarity_restriction": bool(amr.get("watch_similarity_restriction")),
                "glass_resistance_trend": amr.get("glass_resistance_trend", "unknown"),
                "comparator": amr.get("existing_watch_comparator", "unknown"),
                "similarity_to_existing_watch": amr.get("similarity_to_existing_watch", "unknown"),
                "targets_mdr_pathogen": bool(amr.get("targets_mdr_pathogen")),
                "amr_unmet_need": amr.get("amr_unmet_need", "unknown"),
            },
        },
    }
    human_amr_check, veterinary_amr_check = _derive_amr_checks(dossier, amr, review_type)
    amr_step["amr_stewardship_check"] = human_amr_check
    if veterinary_amr_check is not None:
        amr_step["veterinary_amr_food_safety_check"] = veterinary_amr_check

    if human_amr_check.get("decision") == "query_applicant":
        amr_section = _find_section(dossier, "amr") or _find_section(dossier, "stewardship")
        add_finding(
            workflow_step="AMR stewardship review using AWaRe rules",
            issue="AMR stewardship check identified missing warning or stewardship justification.",
            violated_rule="AMR warning and stewardship justification must be present for antimicrobial submissions.",
            severity="major",
            location="AMR Stewardship",
            recommendation="Provide complete AMR warning statements and stewardship justification.",
            evidence_reference=_section_reference(dossier_id, amr_section),
        )
    if veterinary_amr_check is not None and veterinary_amr_check.get("decision") == "query_applicant":
        vet_section = _find_section(dossier, "withdrawal") or _find_section(dossier, "residue") or _find_section(dossier, "label")
        add_finding(
            workflow_step="AMR stewardship review using AWaRe rules",
            issue="Veterinary AMR and food safety check identified missing withdrawal/residue controls.",
            violated_rule="Veterinary antimicrobial dossiers must provide withdrawal period, residue information, and complete AMR warning.",
            severity="critical",
            location="Veterinary Labeling and Food Safety",
            recommendation="Provide target-species withdrawal period, residue information, and complete AMR warning text.",
            evidence_reference=_section_reference(dossier_id, vet_section),
        )
    if amr.get("restricted_authorization"):
        amr_section = _find_section(dossier, "amr") or _find_section(dossier, "stewardship")
        add_finding(
            workflow_step="AMR stewardship review using AWaRe rules",
            issue="AWaRe-controlled antimicrobial requires restricted authorization or stewardship caution.",
            violated_rule="Watch / Reserve stewardship-sensitive products should trigger stewardship caution",
            severity="major",
            location="AMR Stewardship Narrative",
            recommendation="Document the stewardship restriction and reviewer control measures.",
            evidence_reference=_section_reference(dossier_id, amr_section),
        )

    consistency_findings: list[str] = []
    product_name = str(product.get("product_name", "")).strip()
    inn_name = str(product.get("inn_name", "")).strip()
    if product_name and inn_name and product_name.lower() == inn_name.lower():
        consistency_findings.append("Proposed product name is identical to the INN and may create naming confusion.")
        name_section = _find_section(dossier, "product", "information") or _find_section(dossier, "naming")
        add_finding(
            workflow_step="Cross-section consistency review",
            issue="Proposed product name is identical to the INN and may create naming confusion.",
            violated_rule="Product identity inconsistency or confusion risk = violation",
            severity="major",
            location="Product Information and Naming",
            recommendation="Use a distinct product name and verify consistent naming across all dossier sections.",
            evidence_reference=_section_reference(dossier_id, name_section),
        )
    if _find_section(dossier, "stability") is None:
        consistency_findings.append("No stability section was mapped, so shelf-life claims cannot be cross-checked.")
        stability_section = _find_section(dossier, "stability")
        add_finding(
            workflow_step="Cross-section consistency review",
            issue="Shelf-life claims could not be cross-checked against a mapped stability section.",
            violated_rule="Claim not supported by evidence = violation",
            severity="major",
            location="Stability and Shelf-Life Justification",
            recommendation="Provide or correctly map the stability section before finalizing the review.",
            evidence_reference=_section_reference(dossier_id, stability_section),
        )

    severity_summary = _severity_counts(findings_register)
    mandatory_steps = {
        "data_quality_and_vision_extraction_check": True,
        "submission_intake_and_familiarization": True,
        "administrative_completeness_review": admin_section is not None,
        "structural_dossier_mapping": bool(section_diagnostics),
        "applicable_rules_identification": True,
        "who_inn_similarity_review": True,
        "section_by_section_technical_review": bool(section_diagnostics),
        "amr_stewardship_review": True,
        "findings_register": True,
        "severity_classification": True,
        "cross_section_consistency_review": True,
    }
    workflow_complete = all(mandatory_steps.values())
    completeness_notes: list[str] = []
    if admin_section is None:
        completeness_notes.append("Administrative completeness review could not be confirmed because the administrative section was not mapped.")
    if naming.get("is_infringement"):
        completeness_notes.append("The review completed, but the dossier cannot be accepted because the INN similarity threshold was exceeded.")
    if amr.get("applies"):
        completeness_notes.append("AMR stewardship review was completed using WHO AWaRe and the source-backed stewardship policy path.")
    completeness_notes.extend(review_type_specific.get("notes", []))

    verdict = _verdict_label(review_payload, workflow_complete, naming, amr)
    recommendation = str(review_payload.get("recommendation", "unknown"))
    findings_summary_tables = build_findings_summary_tables(findings_register)
    try:
        structured_findings = []
        for review_area in REVIEW_AREA_ORDER:
            for row in findings_summary_tables.get(review_area, []):
                structured_findings.append(
                    {
                        "review_area": review_area,
                        "finding": str(row.get("violated_rule", "")) if str(row.get("violated_rule", "")).strip() else "No recorded violations in this area.",
                        "severity": str(row.get("severity", "advisory")),
                        "violated_rule": str(row.get("violated_rule", "")),
                        "evidence_ref": str(row.get("evidence_reference", "")),
                        "recommendation": str(row.get("recommendation", "")),
                        "decision_trace": {"workflow_step": review_area},
                    }
                )
        findings_table_response = tool_data(
            "generate_findings_table",
            {
                "dossier_id": dossier_id,
                "findings": structured_findings,
                "group_by": "review_area",
            },
        )
        tool_rows = findings_table_response["data"].get("structured_table", [])
        regrouped = {area: [] for area in REVIEW_AREA_ORDER}
        for row in tool_rows:
            review_area = str(row.get("review_area", "")).strip()
            if review_area not in regrouped:
                continue
            regrouped[review_area].append(
                {
                    "severity": str(row.get("severity", "advisory")),
                    "violated_rule": str(row.get("violated_rule", "")),
                    "evidence_reference": str(row.get("evidence_ref", "")),
                    "recommendation": str(row.get("recommendation", "")),
                }
            )
        findings_summary_tables = regrouped
        findings_summary_markdown = render_findings_summary_markdown(findings_summary_tables)
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        findings_summary_markdown = render_findings_summary_markdown(findings_summary_tables)

    return {
        "data_quality_and_vision_extraction_check": {
            "status": "completed",
            "scanned_document_challenge_mode": scanned_challenge_mode,
        },
        "submission_summary": {
            "dossier_id": dossier.get("dossier_id", "unknown"),
            "submission_type": "pre_market_authorization",
            "review_type": review_type,
            "applicant": organization.get("applicant", "unknown"),
            "product_name": product_name or "unknown",
            "active_ingredient": inn_name or "unknown",
            "dosage_form": product.get("dosage_form", "unknown"),
            "strength": product.get("strength", "unknown"),
            "jurisdiction": dossier.get("country", "unknown"),
            "review_pathway": "fast_track" if amr.get("fast_track_candidate") else "standard",
        },
        "administrative_review": {
            "status": "administratively_complete" if not admin_violations else "administratively_incomplete",
            "violations": admin_violations,
        },
        "dossier_structure_review": {
            "status": "mapped" if not structure_violations else "mapped_with_violations",
            "violations": structure_violations,
        },
        "applicable_rules_identification": {
            "rules": applicable_rules,
        },
        "who_inn_similarity_review": naming_step,
        "technical_section_review": {
            "section_results": section_results,
            "review_type_specific": review_type_specific,
        },
        "amr_stewardship_review": amr_step,
        "findings_register": findings_register,
        "findings_summary_tables": findings_summary_tables,
        "findings_summary_markdown": findings_summary_markdown,
        "severity_classification": severity_summary,
        "cross_section_consistency_review": {
            "status": "consistent" if not consistency_findings else "violations_found",
            "findings": consistency_findings,
        },
        "review_completeness_confirmation": {
            "status": "review_complete" if workflow_complete else "review_incomplete",
            "mandatory_steps": mandatory_steps,
            "notes": completeness_notes,
        },
        "overall_judgment": {
            "final_verdict": verdict,
            "system_recommendation": recommendation,
            "justification": "The final verdict reflects the full structured review, including naming safety, technical adequacy, stewardship policy, and recorded rule violations.",
            "blocking_issues": [
                item["issue"] for item in findings_register if item["severity"] in {"critical", "major"}
            ],
            "escalation_needed": verdict == "escalate_for_higher_review",
        },
    }
