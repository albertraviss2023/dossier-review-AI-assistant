from __future__ import annotations

import re
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR


PDF_TEXT_PATTERN = re.compile(rb"\((.*?)\)\s*Tj")
PDF_ARRAY_PATTERN = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
PDF_ARRAY_TEXT_PATTERN = re.compile(rb"\((.*?)\)")
MIN_DIRECT_PDF_TEXT_CHARS = 180
MAX_OCR_PAGES = 8
MAX_VISUAL_SUMMARY_PAGES = 6
STRUCTURED_SECTION_PATTERN = re.compile(
    r"^\[(?P<index>\d+)\]\s+(?P<section_code>[A-Za-z0-9_]+)\s*-\s*(?P<title>[^\n]+)\n"
    r"Labels:\s*(?P<labels>[^\n]*)\n"
    r"(?P<body>.*?)(?=^\[\d+\]\s+[A-Za-z0-9_]+\s*-|\Z)",
    re.MULTILINE | re.DOTALL,
)

HEADING_ALIASES = {
    "application form and administrative information": ("m1_application_admin", "1", "Application Form and Administrative Information", True),
    "manufacturer and gmp evidence": ("m1_manufacturer_gmp", "1", "Manufacturer and GMP Evidence", True),
    "product information and naming": ("m1_product_information", "1", "Product Information and Naming", True),
    "quality overall summary": ("m2_quality_overall_summary", "2", "Quality Overall Summary", True),
    "clinical overview and benefit-risk summary": ("m2_clinical_overview", "2", "Clinical Overview and Benefit-Risk Summary", True),
    "api quality and control strategy": ("m3_api_quality", "3", "API Quality and Control Strategy", True),
    "fpp manufacturing process and controls": ("m3_fpp_manufacturing", "3", "FPP Manufacturing Process and Controls", True),
    "stability and shelf-life justification": ("m3_stability", "3", "Stability and Shelf-Life Justification", True),
    "nonclinical study summary": ("m4_nonclinical_summary", "4", "Nonclinical Study Summary", False),
    "tabular listing of clinical studies": ("m5_trial_listing", "5", "Tabular Listing of Clinical Studies", True),
    "pivotal clinical trial reports": ("m5_pivotal_trial_reports", "5", "Pivotal Clinical Trial Reports", True),
    "biopharmaceutics and bioequivalence evidence": ("m5_bioequivalence", "5", "Biopharmaceutics and Bioequivalence Evidence", False),
    "amr stewardship narrative": ("m5_stewardship", "5", "AMR Stewardship Narrative", True),
}

_OCR_ENGINE: RapidOCR | None = None


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    extraction_method: str
    page_count: int | None = None
    image_count: int = 0
    ocr_used: bool = False
    warnings: tuple[str, ...] = ()
    visual_evidence: tuple[dict[str, Any], ...] = ()


def parse_uploaded_text(filename: str, payload: bytes) -> str:
    return parse_uploaded_document(filename, payload).text


def parse_uploaded_document(filename: str, payload: bytes) -> ParsedDocument:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "txt":
        text = payload.decode("utf-8", errors="ignore")
        return ParsedDocument(text=text, extraction_method="plain_text")
    if suffix == "docx":
        return ParsedDocument(text=_extract_docx_text(payload), extraction_method="docx_xml")
    if suffix == "pdf":
        return _extract_pdf_document(payload)
    raise ValueError(f"Unsupported intake file type: .{suffix or 'unknown'}")


def _extract_docx_text(payload: bytes) -> str:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        runs = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _decode_pdf_fragment(fragment: bytes) -> str:
    text = fragment.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\")
    return text.decode("latin-1", errors="ignore")


def _legacy_extract_pdf_text(payload: bytes) -> str:
    chunks: list[str] = []
    for match in PDF_TEXT_PATTERN.finditer(payload):
        text = _decode_pdf_fragment(match.group(1)).strip()
        if text:
            chunks.append(text)
    for match in PDF_ARRAY_PATTERN.finditer(payload):
        inner = match.group(1)
        parts = [_decode_pdf_fragment(item).strip() for item in PDF_ARRAY_TEXT_PATTERN.findall(inner)]
        joined = " ".join(part for part in parts if part)
        if joined:
            chunks.append(joined)
    return "\n\n".join(chunks)


def _extract_pdf_document(payload: bytes) -> ParsedDocument:
    warnings: list[str] = []
    direct_texts: list[str] = []
    image_count = 0
    page_count: int | None = None
    rendered_pages: list[Image.Image] = []

    try:
        reader = PdfReader(BytesIO(payload))
        page_count = len(reader.pages)
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            if extracted:
                direct_texts.append(extracted)
            try:
                image_count += len(page.images)
            except Exception:
                pass
    except Exception as exc:
        warnings.append(f"structured_pdf_reader_failed:{exc.__class__.__name__}")

    legacy_text = _legacy_extract_pdf_text(payload).strip()
    direct_text = _merge_text_parts(direct_texts + ([legacy_text] if legacy_text else []))

    should_render_pages = bool(image_count) or len(_normalize_for_merge(direct_text)) < MIN_DIRECT_PDF_TEXT_CHARS
    if should_render_pages:
        try:
            rendered_pages = _render_pdf_pages(payload, max_pages=min(page_count or MAX_OCR_PAGES, MAX_OCR_PAGES))
        except Exception as exc:
            warnings.append(f"pdf_render_failed:{exc.__class__.__name__}")

    visual_evidence = _summarize_visual_evidence(rendered_pages, direct_texts)

    if len(_normalize_for_merge(direct_text)) >= MIN_DIRECT_PDF_TEXT_CHARS:
        return ParsedDocument(
            text=direct_text,
            extraction_method="pdf_text_layer",
            page_count=page_count,
            image_count=image_count,
            ocr_used=False,
            warnings=tuple(warnings),
            visual_evidence=tuple(asdict(item) for item in visual_evidence),
        )

    ocr_text = _ocr_pages(rendered_pages)
    merged = _merge_text_parts([direct_text, ocr_text])
    if ocr_text:
        warnings.append("ocr_fallback_used")
        return ParsedDocument(
            text=merged,
            extraction_method="pdf_text_plus_ocr" if direct_text else "pdf_ocr",
            page_count=page_count,
            image_count=image_count,
            ocr_used=True,
            warnings=tuple(warnings),
            visual_evidence=tuple(asdict(item) for item in visual_evidence),
        )

    return ParsedDocument(
        text=direct_text,
        extraction_method="pdf_text_layer_fallback",
        page_count=page_count,
        image_count=image_count,
        ocr_used=False,
        warnings=tuple(warnings),
        visual_evidence=tuple(asdict(item) for item in visual_evidence),
    )


def _merge_text_parts(parts: list[str]) -> str:
    seen: set[str] = set()
    merged: list[str] = []
    for part in parts:
        normalized = _normalize_for_merge(part)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(part.strip())
    return "\n\n".join(merged)


def _normalize_for_merge(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _ocr_engine() -> RapidOCR:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _ocr_pages(rendered_pages: list[Image.Image]) -> str:
    page_text: list[str] = []
    engine = _ocr_engine()
    for image in rendered_pages:
        result, _ = engine(np.array(image))
        if not result:
            continue
        lines = [str(item[1]).strip() for item in result if len(item) >= 2 and str(item[1]).strip()]
        if lines:
            page_text.append("\n".join(lines))
    return "\n\n".join(page_text)


def _render_pdf_pages(payload: bytes, *, max_pages: int) -> list[Image.Image]:
    document = pdfium.PdfDocument(BytesIO(payload))
    total_pages = min(len(document), max_pages)
    images: list[Image.Image] = []
    for page_index in range(total_pages):
        page = document[page_index]
        bitmap = page.render(scale=2.0)
        images.append(bitmap.to_pil())
    return images


@dataclass(frozen=True)
class VisualEvidenceItem:
    page_number: int
    evidence_type: str
    summary: str
    ocr_excerpt: str


def _classify_visual_evidence(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("gmp", "certificate", "inspection", "capa", "manufacturer")):
        return "gmp_certificate_or_site_evidence"
    if any(term in lowered for term in ("label", "carton", "pil", "smcp", "pack", "brand name")):
        return "labeling_or_packaging_artifact"
    if any(term in lowered for term in ("stability", "trend", "months", "shelf-life", "shelf life")):
        return "stability_chart_or_table"
    if any(term in lowered for term in ("endpoint", "study", "trial", "benefit-risk", "efficacy", "safety")):
        return "clinical_chart_or_summary"
    if any(term in lowered for term in ("signature", "stamp", "signed")):
        return "signed_regulatory_document"
    return "general_visual_attachment"


def _summarize_visual_text(text: str) -> str:
    compact = " ".join(text.split())
    if not compact:
        return "Visual content was detected, but no reliable OCR text summary was produced."
    lowered = compact.lower()
    if "certificate expired" in lowered:
        return "Visual evidence suggests an expired GMP certificate or expired quality evidence."
    if "no critical findings" in lowered and "gmp" in lowered:
        return "Visual evidence suggests GMP documentation with no critical findings identified."
    if "primary endpoint was not met" in lowered or "endpoint not met" in lowered:
        return "Visual evidence suggests the pivotal study did not meet its primary endpoint."
    if "primary endpoint was met" in lowered or "endpoint met" in lowered:
        return "Visual evidence suggests the pivotal study met its primary endpoint."
    if "high similarity" in lowered and "rising resistance" in lowered:
        return "Visual evidence suggests a stewardship concern involving high comparator similarity and rising resistance."
    return f"Visual evidence OCR highlights: {compact[:180]}{'' if len(compact) <= 180 else '...'}"


def _summarize_visual_evidence(rendered_pages: list[Image.Image], direct_texts: list[str]) -> list[VisualEvidenceItem]:
    if not rendered_pages:
        return []
    engine = _ocr_engine()
    items: list[VisualEvidenceItem] = []
    for idx, image in enumerate(rendered_pages[:MAX_VISUAL_SUMMARY_PAGES], start=1):
        result, _ = engine(np.array(image))
        lines = [str(item[1]).strip() for item in result or [] if len(item) >= 2 and str(item[1]).strip()]
        page_text = " ".join(lines).strip()
        if not page_text and idx - 1 < len(direct_texts):
            page_text = " ".join(str(direct_texts[idx - 1]).split()).strip()
        if not page_text:
            continue
        excerpt = page_text[:220]
        items.append(
            VisualEvidenceItem(
                page_number=idx,
                evidence_type=_classify_visual_evidence(page_text),
                summary=_summarize_visual_text(page_text),
                ocr_excerpt=excerpt,
            )
        )
    return items


def _infer_policy_signals_from_text(text: str, inn_name: str) -> dict[str, Any]:
    lowered = text.lower()
    inn_lower = inn_name.lower()
    endpoint_not_met = (
        "endpoint not met" in lowered
        or "primary endpoint was not met" in lowered
        or "reported outcome category: endpoint_not_met" in lowered
    )
    endpoint_met = (
        "endpoint met" in lowered
        or "primary endpoint was met" in lowered
        or "reported outcome category: endpoint_met" in lowered
    )
    endpoint_inconclusive = (
        "endpoint was inconclusive" in lowered
        or "results were inconclusive" in lowered
        or "reported outcome category: inconclusive" in lowered
    )
    clinical_missing_phrases = (
        "clinical evidence not provided",
        "pivotal reports were not provided",
        "pivotal efficacy data are not available",
        "benefit-risk cannot be concluded",
        "pending full clinical study reports",
        "full clinical study reports are pending",
        "efficacy data are not available",
    )
    gmp_expired = (
        "gmp expired" in lowered
        or "certificate expired" in lowered
        or "gmp status: expired" in lowered
        or "gmp certificate validity: expired" in lowered
    )
    gmp_non_compliant = (
        "gmp non-compliant" in lowered
        or "gmp status: non_compliant" in lowered
        or "gmp status: non-compliant" in lowered
        or "status: non_compliant" in lowered
        or "status: non-compliant" in lowered
        or "critical gmp deficiencies" in lowered
        or ("critical findings" in lowered and "no critical findings" not in lowered)
    )
    gmp_missing = (
        "gmp evidence not provided" in lowered
        or "inspection evidence missing" in lowered
        or "gmp certificate not provided" in lowered
    )
    gmp_not_recent = (
        "no recent inspection evidence was provided" in lowered
        or "latest inspection date is" in lowered and "no recent inspection evidence" in lowered
    )
    reserve_hint = any(term in inn_lower for term in ("cefiderocol", "linezolid"))
    watch_hint = any(term in inn_lower for term in ("levofloxacin", "ciprofloxacin", "moxifloxacin"))
    access_hint = any(term in inn_lower for term in ("amoxicillin", "ampicillin", "doxycycline", "nitrofurantoin", "metronidazole"))
    mdr_hint = "mdr" in lowered or "multidrug-resistant" in lowered or "last-resort" in lowered
    aware_match = re.search(r"who aware category:\s*(access|watch|reserve)", lowered)
    explicit_aware = aware_match.group(1) if aware_match else None
    high_similarity_hint = (
        "high similarity" in lowered
        or "close similarity" in lowered
        or "assessed as high" in lowered
    )
    moderate_similarity_hint = "assessed as moderate" in lowered or "moderate similarity" in lowered
    low_similarity_hint = "assessed as low" in lowered or "low similarity" in lowered
    rising_resistance_hint = (
        "rising resistance" in lowered
        or "glass trend rising" in lowered
        or "glass-aligned surveillance trend is rising" in lowered
    )
    stable_resistance_hint = (
        "glass-aligned surveillance trend is stable" in lowered
        or "glass trend stable" in lowered
        or "resistance trend is stable" in lowered
    )
    comparator_match = re.search(r"comparator\s+([a-z0-9\\-]+)\s+is assessed", lowered)
    if not comparator_match:
        comparator_match = re.search(r"relative to\s+([a-z0-9\\-]+)\s+is assessed", lowered)
    missing_clinical_hint = any(phrase in lowered for phrase in clinical_missing_phrases)
    naming_risk_hint = (
        "name similarity review indicates potential confusion" in lowered
        or "look-alike and sound-alike naming concerns" in lowered
        or "insufficient differentiation and risk mitigation plan for look-alike" in lowered
    )

    return {
        "inn_infringement": naming_risk_hint,
        "gmp_inspection_status": "missing_evidence" if gmp_missing else ("non_compliant" if gmp_non_compliant else ("expired" if gmp_expired else "compliant")),
        "gmp_inspection_recent": not gmp_not_recent,
        "gmp_certificate_validity": "not_provided" if gmp_missing else ("expired" if gmp_expired else "valid"),
        "clinical_data_available": ("clinical" in lowered or "endpoint" in lowered) and not missing_clinical_hint,
        "pivotal_trial_outcome": "endpoint_not_met" if endpoint_not_met else ("endpoint_met" if endpoint_met else ("inconclusive" if endpoint_inconclusive else "missing_evidence" if missing_clinical_hint else "inconclusive")),
        "aware_category": explicit_aware if explicit_aware else ("reserve" if reserve_hint else ("watch" if watch_hint else ("access" if access_hint else "not_applicable"))),
        "amr_unmet_need": "critical" if mdr_hint and reserve_hint else ("moderate" if watch_hint else "not_applicable"),
        "targets_mdr_pathogen": mdr_hint,
        "glass_resistance_trend": "rising" if rising_resistance_hint else ("stable" if stable_resistance_hint or watch_hint or reserve_hint or access_hint else "not_applicable"),
        "similarity_to_existing_watch": "high" if high_similarity_hint else ("moderate" if moderate_similarity_hint else ("low" if low_similarity_hint or watch_hint else "not_applicable")),
        "existing_watch_comparator": comparator_match.group(1) if comparator_match else ("ciprofloxacin" if "ciprofloxacin" in lowered else ("levofloxacin" if "levofloxacin" in lowered else ("cefotaxime" if "cefotaxime" in lowered else ("ceftriaxone" if "ceftriaxone" in lowered else "not_applicable")))),
    }


def build_dossier_from_raw_text(
    *,
    dossier_id: str,
    country: str,
    submission_date: str,
    product_name: str,
    inn_name: str,
    applicant: str,
    manufacturer: str,
    facility_country: str,
    raw_text: str,
    review_program: str = "marketing_authorization",
    source_filename: str | None = None,
    extraction_metadata: dict[str, Any] | None = None,
    extractor: Any | None = None,
) -> dict[str, Any]:
    sections = _segment_sections(raw_text)
    if extraction_metadata and extraction_metadata.get("visual_evidence"):
        sections.extend(_visual_evidence_sections(extraction_metadata["visual_evidence"]))

    if extractor:
        policy_signals = extractor(raw_text, inn_name)
    else:
        policy_signals = _infer_policy_signals_from_text(raw_text, inn_name)

    dossier = {
        "dossier_id": dossier_id,
        "country": country,
        "submission_date": submission_date,
        "product": {
            "product_name": product_name,
            "inn_name": inn_name,
            "atc_code": "unknown",
            "dosage_form": "unknown",
            "strength": "unknown",
        },
        "organization": {
            "applicant": applicant,
            "manufacturer": manufacturer,
            "facility_country": facility_country,
        },
        "policy_signals": policy_signals,
        "sections": sections,
        "labels": {
            "holistic_policy_decision": "approval_granted",
            "risk_score": 0.5,
            "compliant_submission": True,
            "review_program": review_program,
        },
        "review_program": review_program,
        "provenance": {
            "synthetic": False,
            "defect_modes": [],
            "ingestion_mode": "raw_file_intake",
            "source_filename": source_filename or "upload",
            "extraction": extraction_metadata or {},
        },
    }
    from .policy import apply_policy_rules

    recommendation, _, confidence = apply_policy_rules(dossier)
    dossier["labels"]["holistic_policy_decision"] = recommendation
    dossier["labels"]["risk_score"] = round(1.0 - float(confidence), 5)
    dossier["labels"]["compliant_submission"] = recommendation in {"standard_review", "fast_track"}
    return dossier


def _segment_sections(raw_text: str) -> list[dict[str, Any]]:
    normalized = raw_text.replace("\r\n", "\n")
    structured_matches = list(STRUCTURED_SECTION_PATTERN.finditer(normalized))
    if structured_matches:
        sections: list[dict[str, Any]] = []
        for match in structured_matches:
            section_code = str(match.group("section_code")).strip()
            title = str(match.group("title")).strip()
            body = str(match.group("body")).strip()
            alias = HEADING_ALIASES.get(title.lower())
            if alias:
                section_id, module, resolved_title, critical = alias
            else:
                module = section_code.split("_", 1)[0].lstrip("m") if section_code.lower().startswith("m") else "raw"
                section_id = section_code or f"raw_section_{len(sections) + 1}"
                resolved_title = title or f"Imported Section {len(sections) + 1}"
                critical = False
            if body:
                sections.append(_section_payload(section_id, module, resolved_title, critical, body))
        if sections:
            return sections

    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    sections: list[dict[str, Any]] = []
    current_heading: tuple[str, str, str, bool] | None = None
    current_text: list[str] = []
    generic_index = 0

    def flush() -> None:
        nonlocal current_heading, current_text, generic_index
        if not current_text:
            return
        body = "\n\n".join(current_text).strip()
        if current_heading:
            section_id, module, title, critical = current_heading
        else:
            generic_index += 1
            section_id, module, title, critical = (f"raw_section_{generic_index}", "raw", f"Imported Section {generic_index}", False)
        sections.append(_section_payload(section_id, module, title, critical, body))
        current_text = []

    for block in blocks:
        lower = block.lower().strip(":")
        heading = HEADING_ALIASES.get(lower)
        if heading:
            flush()
            current_heading = heading
            continue
        current_text.append(block)

    flush()
    if not sections and normalized.strip():
        sections.append(_section_payload("raw_section_1", "raw", "Imported Section 1", False, normalized.strip()))
    return sections


def _section_payload(section_id: str, module: str, title: str, critical: bool, text: str) -> dict[str, Any]:
    char_count = len(text)
    return {
        "section_id": section_id,
        "module": module,
        "title": title,
        "text": text,
        "critical": critical,
        "constraints": {"min_chars": 50, "max_chars": 12000},
        "labels": {
            "presence": "present",
            "length_status": "length_ok",
            "correctness": "correct",
            "error_tags": [],
        },
        "metrics": {"char_count": char_count},
    }


def _visual_evidence_sections(visual_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for item in visual_evidence:
        page_number = int(item.get("page_number", len(sections) + 1))
        evidence_type = str(item.get("evidence_type", "general_visual_attachment")).replace("_", " ")
        title = f"Visual Evidence Summary - Page {page_number}"
        summary = str(item.get("summary", "")).strip()
        excerpt = str(item.get("ocr_excerpt", "")).strip()
        body = f"Visual evidence type: {evidence_type}. {summary}"
        if excerpt:
            body += f"\n\nOCR excerpt: {excerpt}"
        sections.append(_section_payload(f"visual_page_{page_number}", "visual", title, False, body))
    return sections
