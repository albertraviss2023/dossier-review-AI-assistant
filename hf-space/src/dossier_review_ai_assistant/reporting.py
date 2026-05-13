from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
import json
from html import escape
import re
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .policy import evaluate_amr_stewardship, evaluate_naming_policy
from .review_workflow import REVIEW_AREA_LABELS, REVIEW_AREA_ORDER, build_workflow_evaluation


def _titleize(value: str) -> str:
    return str(value or "unknown").replace("_", " ").title()


def _find_section(dossier: dict[str, Any], *keywords: str) -> dict[str, Any] | None:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for section in dossier.get("sections", []):
        title = str(section.get("title", "")).lower()
        text = str(section.get("text", "")).lower()
        if all(any(keyword in field for field in (title, text)) for keyword in lowered_keywords):
            return section
    return None


def _severity_from_recommendation(recommendation: str) -> str:
    mapping = {
        "approval_denied": "critical",
        "additional_information_required": "major",
        "approval_granted": "minor",
        "abstain": "major",
    }
    return mapping.get(str(recommendation), "major")


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "major": 0, "minor": 0, "advisory": 0}
    for item in findings:
        severity = str(item.get("severity", "advisory")).lower()
        if severity not in counts:
            severity = "advisory"
        counts[severity] += 1
    return counts


def _yes_no(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def _bullet_items(items: list[str], fallback: str) -> list[str]:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return cleaned or [fallback]


def _xml_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _clean_report_narrative(text: Any) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\[[^\]]+:[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _render_findings_summary_html(summary_tables: dict[str, list[dict[str, Any]]]) -> str:
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
        if rows:
            body = "".join(
                "<tr>"
                f"<td>{escape(str(row.get('severity', 'advisory')).title())}</td>"
                f"<td>{escape(str(row.get('violated_rule', '')))}</td>"
                f"<td>{escape(str(ref_map.get(str(row.get('evidence_reference', '')).strip(), 'n/a')))}</td>"
                f"<td>{escape(str(row.get('recommendation', '')))}</td>"
                "</tr>"
                for row in rows
            )
        else:
            body = (
                "<tr>"
                "<td>None</td>"
                "<td>No recorded violations in this area.</td>"
                "<td>n/a</td>"
                "<td>Continue standard review monitoring.</td>"
                "</tr>"
            )
        sections.append(
            f"""
            <div class="summary-table-card">
              <h3>{escape(REVIEW_AREA_LABELS[area])}</h3>
              <table>
                <thead>
                  <tr><th>Severity</th><th>Violated Rule</th><th>Evidence Reference</th><th>Recommendation</th></tr>
                </thead>
                <tbody>{body}</tbody>
              </table>
            </div>
            """.strip()
        )
    return "".join(sections)


def _render_findings_summary_text(summary_tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    ref_map: dict[str, int] = {}
    next_ref = 1
    for area in REVIEW_AREA_ORDER:
        for row in summary_tables.get(area, []):
            ref = str(row.get("evidence_reference", "")).strip()
            if ref and ref not in ref_map:
                ref_map[ref] = next_ref
                next_ref += 1

    lines: list[str] = []
    for area in REVIEW_AREA_ORDER:
        rows = summary_tables.get(area, [])
        lines.append(REVIEW_AREA_LABELS[area])
        if rows:
            for row in rows:
                lines.append(
                    "- "
                    f"Severity: {row.get('severity', 'advisory')} | "
                    f"Violated rule: {row.get('violated_rule', '')} | "
                    f"Evidence reference: {ref_map.get(str(row.get('evidence_reference', '')).strip(), 'n/a')} | "
                    f"Recommendation: {row.get('recommendation', '')}"
                )
        else:
            lines.append("- Severity: none | Violated rule: No recorded violations in this area | Evidence reference: n/a | Recommendation: Continue standard review monitoring")
        lines.append("")
    return lines


def build_applicant_query_letter(
    *,
    dossier: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, str]:
    product_name = str(dossier.get("product", {}).get("product_name", "the submitted product"))
    findings = list(workflow.get("findings_register", []) or [])
    actionable = [item for item in findings if str(item.get("severity", "")).lower() in {"critical", "major", "minor"}]
    if not actionable:
        body_md = (
            "Dear Applicant,\n\n"
            f"Following screening of your submission for {product_name}, no applicant queries were raised at this stage.\n\n"
            "Regards,\nRegulatory Reviewer"
        )
    else:
        lines = [
            "Dear Applicant,",
            "",
            f"Following screening of your submission for {product_name}, the following queries are raised:",
            "",
        ]
        for idx, finding in enumerate(actionable, start=1):
            step = str(finding.get("workflow_step", "Review Item")).strip()
            issue = str(finding.get("issue", "Evidence gap identified.")).strip()
            rec = str(finding.get("recommendation", "Please provide corrected and complete evidence.")).strip()
            rule = str(finding.get("violated_rule", "SOP requirement")).strip()
            location = str(finding.get("location", "dossier section")).strip()
            lines.extend(
                [
                    f"{idx}. {step}",
                    f"{issue}",
                    f"Rule reference: {rule}.",
                    f"Evidence location: {location}.",
                    f"Requested action: {rec}",
                    "",
                ]
            )
        lines.extend(["Regards,", "Regulatory Reviewer"])
        body_md = "\n".join(lines).strip()

    html_lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Applicant Query Letter</title>",
        "<style>",
        "body{font-family:'Segoe UI',Arial,sans-serif;background:#f5f8fc;color:#1f2937;margin:0;padding:24px;}",
        ".letter{max-width:900px;margin:0 auto;background:#fff;border:1px solid #d7e3f1;border-radius:14px;overflow:hidden;box-shadow:0 10px 30px rgba(15,23,42,.08);}",
        ".head{padding:22px 28px;background:linear-gradient(135deg,#0f4c81,#2563eb);color:#fff;}",
        ".head h1{margin:0;font-size:20px;letter-spacing:.02em;}",
        ".head p{margin:6px 0 0;opacity:.9;font-size:13px;}",
        ".meta{padding:14px 28px;background:#eef5ff;border-bottom:1px solid #d7e3f1;color:#334155;font-size:13px;}",
        ".content{padding:24px 28px;line-height:1.65;font-size:14px;}",
        ".q{margin:14px 0 0;padding:12px 14px;border:1px solid #dbe7f3;border-radius:10px;background:#f8fbff;}",
        ".q strong{color:#0f3d66;}",
        ".footer{padding:16px 28px;border-top:1px solid #e5edf6;background:#fafcff;color:#475569;font-size:12px;}",
        "</style></head><body>",
        "<div class='letter'>",
        "<div class='head'><h1>National Food and Drug Regulation Agency</h1><p>Regulatory Review and Market Authorization Directorate</p></div>",
        f"<div class='meta'>Document: Applicant Query Letter &nbsp;|&nbsp; Generated: {escape(datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC'))}</div>",
        "<div class='content'>",
    ]
    for raw in body_md.splitlines():
        stripped = raw.strip()
        if not stripped:
            html_lines.append("<br/>")
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            html_lines.append(f"<div class='q'><strong>{escape(stripped)}</strong></div>")
        else:
            html_lines.append(f"<p>{escape(raw)}</p>")
    html_lines.extend(
        [
            "</div>",
            "<div class='footer'>This communication is issued by the National Food and Drug Regulation Agency for regulatory follow-up on submitted dossier evidence.</div>",
            "</div></body></html>",
        ]
    )
    body_html = "".join(html_lines)
    return {"markdown": body_md, "html": body_html, "text": body_md}


def build_decision_log(
    *,
    dossier: dict[str, Any],
    workflow: dict[str, Any],
    reviewer_username: str | None = None,
) -> list[dict[str, Any]]:
    findings = list(workflow.get("findings_register", []) or [])
    now = datetime.now(UTC).isoformat()
    decision_log: list[dict[str, Any]] = []
    for idx, finding in enumerate(findings, start=1):
        evidence_ref = str(finding.get("evidence_reference", "")).strip() or str(finding.get("location", "unknown"))
        lower_loc = str(finding.get("location", "")).lower()
        tool = "OCR extraction" if any(token in lower_loc for token in ("gmp", "certificate", "scan", "stability", "coa")) else "retrieval + rule evaluation"
        rule_id = f"SOP-{idx:04d}"
        violated = str(finding.get("violated_rule", "")).strip()
        if "gmp" in violated.lower():
            rule_id = "M1-GMP-001"
        elif "inn similarity" in violated.lower() or "naming" in violated.lower():
            rule_id = "M1-INN-001"
        elif "withdrawal" in violated.lower():
            rule_id = "VET-WITHDRAWAL-001"
        result = "query" if str(finding.get("severity", "")).lower() in {"critical", "major", "minor"} else "pass"
        decision_log.append(
            {
                "log_id": f"{dossier.get('dossier_id', 'DOS')}-LOG-{idx:03d}",
                "rule_evaluated": rule_id,
                "rule_text": violated,
                "tool_called": tool,
                "evidence_retrieved": evidence_ref,
                "extracted_value": str(finding.get("issue", "")),
                "rule_result": result,
                "reviewer_action": "pending" if result == "query" else "accepted",
                "reviewer_username": reviewer_username or "unknown",
                "timestamp_utc": now,
            }
        )
    return decision_log


def _docx_paragraph(text: str, *, heading: str | None = None) -> str:
    style_xml = ""
    if heading == "title":
        style_xml = "<w:pPr><w:pStyle w:val=\"Title\"/></w:pPr>"
    elif heading == "h1":
        style_xml = "<w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr>"
    elif heading == "h2":
        style_xml = "<w:pPr><w:pStyle w:val=\"Heading2\"/></w:pPr>"
    elif heading == "h3":
        style_xml = "<w:pPr><w:pStyle w:val=\"Heading3\"/></w:pPr>"
    safe = _xml_escape(text)
    return f"<w:p>{style_xml}<w:r><w:t xml:space=\"preserve\">{safe}</w:t></w:r></w:p>"


def _build_docx_bytes(paragraphs: list[tuple[str, str | None]]) -> bytes:
    document_body = "".join(_docx_paragraph(text, heading=heading) for text, heading in paragraphs)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
 xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:w10="urn:schemas-microsoft-com:office:word"
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
 xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
 xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
 xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
 xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
 mc:Ignorable="w14 wp14">
  <w:body>
    {document_body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
</w:styles>"""

    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Pre-Market Authorization Review Report</dc:title>
  <dc:creator>Dossier Review AI Assistant</dc:creator>
</cp:coreProperties>"""

    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Dossier Review AI Assistant</Application>
</Properties>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/_rels/document.xml.rels", document_rels)
        docx.writestr("word/styles.xml", styles)
        docx.writestr("docProps/core.xml", core)
        docx.writestr("docProps/app.xml", app)
    return buffer.getvalue()


def _build_simple_pdf_bytes(lines: list[str]) -> bytes:
    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 780
    content_lines = ["BT", "/F1 10 Tf"]
    for line in lines:
        safe = esc(str(line))[:180]
        content_lines.append(f"1 0 0 1 50 {y} Tm ({safe}) Tj")
        y -= 14
        if y < 60:
            break
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    xref = [0]
    for obj in objects:
        xref.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(xref)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for pos in xref[1:]:
        pdf.extend(f"{pos:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(xref)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


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


def _workflow_evaluation(dossier: dict[str, Any], review_payload: dict[str, Any]) -> dict[str, Any]:
    product = dossier.get("product", {})
    organization = dossier.get("organization", {})
    review_type = str(review_payload.get("review_type", "generic"))
    section_diagnostics = review_payload.get("section_diagnostics", [])
    policy_hits = list(review_payload.get("policy_rule_hits", []))
    naming = evaluate_naming_policy(dossier)
    amr = evaluate_amr_stewardship(dossier)

    admin_section = _find_section(dossier, "application") or _find_section(dossier, "administrative")
    structure_missing = [
        item for item in section_diagnostics
        if item.get("presence") != "present" or item.get("correctness") != "correct" or item.get("length_status") != "length_ok"
    ]
    technical_findings = [
        item for item in section_diagnostics
        if item.get("presence") != "present" or item.get("correctness") != "correct" or item.get("length_status") != "length_ok"
    ]

    findings_register: list[dict[str, Any]] = []

    def add_finding(
        *,
        workflow_step: str,
        issue: str,
        violated_rule: str,
        severity: str,
        location: str,
        recommendation: str,
    ) -> None:
        findings_register.append(
            {
                "workflow_step": workflow_step,
                "issue": issue,
                "violated_rule": violated_rule,
                "severity": severity,
                "location": location,
                "recommendation": recommendation,
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
        )
    else:
        admin_text = str(admin_section.get("text", "")).lower()
        if "signed" not in admin_text and "signature" not in admin_text:
            admin_violations.append("No signature evidence was detected in the administrative material.")
            add_finding(
                workflow_step="Administrative completeness review",
                issue="No signature evidence was detected in the administrative material.",
                violated_rule="Missing signed application form = violation",
                severity="major",
                location=str(admin_section.get("title", "Administrative section")),
                recommendation="Confirm the signed application form is present and legible.",
            )
        if "payment" not in admin_text and "fee" not in admin_text:
            admin_violations.append("No proof of payment was detected in the administrative material.")
            add_finding(
                workflow_step="Administrative completeness review",
                issue="No proof of payment was detected in the administrative material.",
                violated_rule="Missing proof of payment where required = violation",
                severity="minor",
                location=str(admin_section.get("title", "Administrative section")),
                recommendation="Confirm the payment receipt or fee evidence is included where required.",
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
        "rule_consequence": "Product name cannot be accepted because INN similarity exceeds 70%."
        if naming.get("is_infringement")
        else "No blocking INN naming issue was identified.",
    }
    if naming.get("is_infringement"):
        add_finding(
            workflow_step="WHO INN similarity review",
            issue=f"Product name exceeds the INN similarity threshold against {naming_step['who_inn']}.",
            violated_rule="INN similarity > 70% = naming violation",
            severity="critical",
            location="Product Information and Naming",
            recommendation="Rename the product before the dossier can be accepted.",
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
                )
    if any("gmp" in hit for hit in policy_hits):
        add_finding(
            workflow_step="Section-by-section technical review",
            issue="Manufacturing quality evidence indicates GMP non-compliance, expiry, or missing support.",
            violated_rule="Required evidence missing = violation",
            severity="critical" if "gmp_non_compliant" in policy_hits else "major",
            location="Manufacturer and GMP Evidence",
            recommendation="Resolve GMP deficiencies and provide current manufacturing evidence.",
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
    }
    if amr.get("restricted_authorization"):
        add_finding(
            workflow_step="AMR stewardship review using AWaRe rules",
            issue="AWaRe-controlled antimicrobial requires restricted authorization or stewardship caution.",
            violated_rule="Watch / Reserve stewardship-sensitive products should trigger stewardship caution",
            severity="major",
            location="AMR Stewardship Narrative",
            recommendation="Document the stewardship restriction and reviewer control measures.",
        )

    consistency_findings: list[str] = []
    product_name = str(product.get("product_name", "")).strip()
    inn_name = str(product.get("inn_name", "")).strip()
    if product_name and inn_name and product_name.lower() == inn_name.lower():
        consistency_findings.append("Proposed product name is identical to the INN and may create naming confusion.")
        add_finding(
            workflow_step="Cross-section consistency review",
            issue="Proposed product name is identical to the INN and may create naming confusion.",
            violated_rule="Product identity inconsistency or confusion risk = violation",
            severity="major",
            location="Product Information and Naming",
            recommendation="Use a distinct product name and verify consistent naming across all dossier sections.",
        )
    if _find_section(dossier, "stability") is None:
        consistency_findings.append("No stability section was mapped, so shelf-life claims cannot be cross-checked.")
        add_finding(
            workflow_step="Cross-section consistency review",
            issue="Shelf-life claims could not be cross-checked against a mapped stability section.",
            violated_rule="Claim not supported by evidence = violation",
            severity="major",
            location="Stability and Shelf-Life Justification",
            recommendation="Provide or correctly map the stability section before finalizing the review.",
        )

    severity_summary = _severity_counts(findings_register)
    mandatory_steps = {
        "submission_intake_and_familiarization": True,
        "administrative_completeness_review": admin_section is not None,
        "structural_dossier_mapping": bool(section_diagnostics),
        "applicable_rules_identification": True,
        "who_inn_similarity_review": True,
        "section_by_section_technical_review": bool(section_diagnostics),
        "amr_stewardship_review": True if amr.get("applies") else True,
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

    verdict = _verdict_label(review_payload, workflow_complete, naming, amr)
    recommendation = str(review_payload.get("recommendation", "unknown"))

    return {
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
        },
        "amr_stewardship_review": amr_step,
        "findings_register": findings_register,
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
            "justification": (
                "The final verdict reflects the full structured review, including naming safety, technical adequacy, stewardship policy, and recorded rule violations."
            ),
            "blocking_issues": [
                item["issue"] for item in findings_register if item["severity"] in {"critical", "major"}
            ],
            "escalation_needed": verdict == "escalate_for_higher_review",
        },
    }


def build_review_report(
    *,
    dossier: dict[str, Any],
    review_payload: dict[str, Any],
    report_title: str,
) -> dict[str, Any]:
    workflow = build_workflow_evaluation(dossier, review_payload)
    query_letter = build_applicant_query_letter(dossier=dossier, workflow=workflow)
    decision_log = build_decision_log(
        dossier=dossier,
        workflow=workflow,
        reviewer_username=str(review_payload.get("reviewer_username") or "unknown"),
    )
    citations = review_payload.get("citations", [])
    section_diagnostics = review_payload.get("section_diagnostics", [])
    amr = review_payload.get("amr_stewardship", {})
    verifier = review_payload.get("verifier", {})

    rec_label = _titleize(str(review_payload.get("recommendation", "unknown")))
    auth_label = _titleize(str(amr.get("authorization_control", "standard_authorization")))
    verdict_label = _titleize(str(workflow["overall_judgment"]["final_verdict"]))
    findings_register = workflow["findings_register"]
    submission_summary = workflow["submission_summary"]
    admin_review = workflow["administrative_review"]
    structure_review = workflow["dossier_structure_review"]
    naming_review = workflow["who_inn_similarity_review"]
    technical_review = workflow["technical_section_review"]["section_results"]
    amr_review = workflow["amr_stewardship_review"]
    consistency_review = workflow["cross_section_consistency_review"]
    completeness_review = workflow["review_completeness_confirmation"]
    overall_judgment = workflow["overall_judgment"]
    severity_summary = workflow["severity_classification"]
    review_type_specific = workflow["technical_section_review"]["review_type_specific"]
    findings_summary_tables = workflow["findings_summary_tables"]
    findings_summary_markdown = workflow["findings_summary_markdown"]
    decision_log_rows = "".join(
        f"<tr><td>{escape(str(item.get('rule_evaluated', '')))}</td><td>{escape(str(item.get('tool_called', '')))}</td><td>{escape(str(item.get('evidence_retrieved', '')))}</td><td>{escape(str(item.get('extracted_value', '')))}</td><td>{escape(str(item.get('rule_result', '')))}</td><td>{escape(str(item.get('reviewer_action', '')))}</td></tr>"
        for item in decision_log
    ) or "<tr><td colspan='6'>No decision log records were generated.</td></tr>"
    cleaned_rationale = _clean_report_narrative(review_payload.get("rationale", ""))
    findings_summary_html = _render_findings_summary_html(findings_summary_tables)
    findings_summary_text = _render_findings_summary_text(findings_summary_tables)

    admin_items = _bullet_items(
        admin_review["violations"],
        "No administrative violations were detected from the available dossier evidence.",
    )
    structure_items = _bullet_items(
        structure_review["violations"],
        "No structural dossier violations were detected.",
    )
    consistency_items = _bullet_items(
        consistency_review["findings"],
        "No cross-section consistency findings were detected.",
    )
    blocking_items = _bullet_items(
        overall_judgment["blocking_issues"],
        "No blocking issues were identified by the structured workflow.",
    )
    completeness_notes = _bullet_items(
        completeness_review["notes"],
        "No unresolved workflow gaps remain after the structured review.",
    )
    findings_rows = "".join(
        f"<tr><td>{escape(str(item.get('workflow_step', '')))}</td><td>{escape(str(item.get('issue', '')))}</td><td>{escape(str(item.get('violated_rule', '')))}</td><td>{escape(str(item.get('severity', '')))}</td><td>{escape(str(item.get('location', '')))}</td><td>{escape(str(item.get('recommendation', '')))}</td></tr>"
        for item in findings_register
    ) or "<tr><td colspan='6'>No workflow violations were recorded.</td></tr>"
    technical_rows = "".join(
        f"<tr><td>{escape(str(item.get('section', 'unknown')))}</td><td>{escape(str(item.get('status', 'unknown')).replace('_', ' '))}</td><td>{escape(str(item.get('presence', 'unknown')))}</td><td>{escape(str(item.get('length_status', 'unknown')))}</td><td>{escape(str(item.get('correctness', 'unknown')))}</td><td>{escape(_yes_no(item.get('critical', False)))}</td></tr>"
        for item in technical_review
    )
    citation_rows = "".join(
        f"<tr><td>{escape(str(item.get('citation_id', 'unknown')))}</td><td>{escape(str(item.get('section_title', 'unknown')))}</td><td>{escape(str(item.get('snippet', '')))}</td></tr>"
        for item in citations
    ) or "<tr><td colspan='3'>No citations were attached to this report.</td></tr>"
    rule_list_html = "".join(f"<li>{escape(str(rule))}</li>" for rule in workflow["applicable_rules_identification"]["rules"])
    amr_findings_html = "".join(
        f"<li>{escape(str(item))}</li>" for item in amr_review.get("findings", [])
    ) or "<li>No AMR source-backed findings were recorded for this dossier.</li>"
    completion_steps_html = "".join(
        f"<tr><td>{escape(str(step).replace('_', ' ').title())}</td><td>{escape(_yes_no(status))}</td></tr>"
        for step, status in completeness_review["mandatory_steps"].items()
    )

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{escape(report_title)}</title>
    <style>
      body {{ font-family: 'Segoe UI', sans-serif; margin: 0; color: #1f2933; line-height: 1.5; background:#f5f8fc; }}
      .page {{ max-width: 1120px; margin: 24px auto; background:#fff; border:1px solid #d7e3f1; border-radius:16px; overflow:hidden; box-shadow:0 12px 32px rgba(15,23,42,.08); }}
      h1, h2, h3 {{ font-family: Georgia, serif; color: #111827; }}
      .brand {{ padding:18px 24px; background: linear-gradient(135deg,#0f4c81,#2563eb); color:#fff; }}
      .brand h1 {{ margin:0; font-size:24px; color:#fff; }}
      .brand p {{ margin:6px 0 0; opacity:.9; font-size:13px; }}
      .content-wrap {{ padding: 22px 28px 30px; }}
      .hero {{ border: 1px solid #d7dfe5; border-radius: 18px; padding: 20px; background: linear-gradient(180deg,#fbfdff 0%,#f3f8ff 100%); }}
      .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }}
      .card {{ border: 1px solid #d7dfe5; border-radius: 16px; padding: 14px; background: #fff; }}
      .pill {{ display: inline-block; padding: 6px 10px; border-radius: 999px; background: #eef2f5; margin-right: 6px; margin-bottom: 6px; font-size: 0.85em; font-weight: 600; }}
      .muted {{ color: #5f6f7a; }}
      ul {{ padding-left: 20px; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
      th, td {{ border-bottom: 1px solid #e6ecef; text-align: left; padding: 12px 8px; vertical-align: top; }}
      th {{ background: #f8fafc; color: #475569; font-weight: 600; text-transform: uppercase; font-size: 0.75em; letter-spacing: 0.05em; }}
      .section {{ margin-top: 28px; }}
      .subhead {{ margin-top: 16px; font-size: 0.95em; font-weight: 700; color: #334155; }}
      .summary-table-card {{ margin-top: 18px; }}
      .summary-table-card h3 {{ margin-bottom: 10px; font-size: 1rem; color: #1e3a8a; }}
      .summary-table-card table {{ margin-top: 0; }}
    </style>
  </head>
  <body>
    <div class="page">
    <div class="brand">
      <h1>National Food and Drug Regulation Agency</h1>
      <p>Pre-Market Authorization Review Report</p>
    </div>
    <div class="content-wrap">
    <div class="hero">
      <h1>{escape(report_title)}</h1>
      <p class="muted">Dossier {escape(str(dossier.get("dossier_id", "unknown")))} | Product {escape(str(dossier.get("product", {}).get("product_name", "unknown")))} | Applicant {escape(str(dossier.get("organization", {}).get("applicant", "unknown")))}</p>
      <div class="grid">
        <div class="card"><strong>System Recommendation</strong><div>{escape(rec_label)}</div></div>
        <div class="card"><strong>Final Verdict</strong><div>{escape(verdict_label)}</div></div>
        <div class="card"><strong>Confidence</strong><div>{escape(str(review_payload.get("confidence", "unknown")))}</div></div>
        <div class="card"><strong>Authorization</strong><div>{escape(auth_label)}</div></div>
      </div>
    </div>
    <div class="section">
      <h2>Submission Summary</h2>
      <table><tbody>
        {''.join(f"<tr><th>{escape(str(key).replace('_', ' ').title())}</th><td>{escape(str(value))}</td></tr>" for key, value in submission_summary.items())}
      </tbody></table>
    </div>
    <div class="section">
      <h2>Administrative Review Outcome</h2>
      <p><strong>Status:</strong> {escape(str(admin_review['status']).replace('_', ' ').title())}</p>
      <p class="subhead">Administrative findings</p>
      <ul>{''.join(f"<li>{escape(item)}</li>" for item in admin_items)}</ul>
    </div>
    <div class="section">
      <h2>Dossier Structure Review Outcome</h2>
      <p><strong>Status:</strong> {escape(str(structure_review['status']).replace('_', ' ').title())}</p>
      <p class="subhead">Mapping and readability findings</p>
      <ul>{''.join(f"<li>{escape(item)}</li>" for item in structure_items)}</ul>
    </div>
    <div class="section">
      <h2>Applicable Rules And Requirements</h2>
      <ul>{rule_list_html}</ul>
    </div>
    <div class="section">
      <h2>WHO INN Similarity Review</h2>
      <table><tbody>
        {''.join(f"<tr><th>{escape(str(key).replace('_', ' ').title())}</th><td>{escape(str(value))}</td></tr>" for key, value in naming_review.items())}
      </tbody></table>
    </div>
    <div class="section">
      <h2>Section-By-Section Technical Review</h2>
      <p class="subhead">Requirement-by-requirement section status</p>
      <table>
        <thead><tr><th>Section</th><th>Status</th><th>Presence</th><th>Length</th><th>Correctness</th><th>Critical</th></tr></thead>
        <tbody>{technical_rows}</tbody>
      </table>
    </div>
    <div class="section">
      <h2>{escape(str(review_type_specific['review_type']).title())} Review-Specific Assessment</h2>
      <table><tbody>
        <tr><th>Status</th><td>{escape(str(review_type_specific['status']).replace('_', ' ').title())}</td></tr>
        <tr><th>Baseline available</th><td>{escape(_yes_no(review_type_specific['baseline_available']))}</td></tr>
        <tr><th>Baseline verified</th><td>{escape(_yes_no(review_type_specific.get('baseline_verified', False)))}</td></tr>
        <tr><th>Baseline reference</th><td>{escape(str(review_type_specific.get('baseline_reference_name') or 'Not supplied'))}</td></tr>
        <tr><th>Verified external URLs</th><td>{escape(', '.join(review_type_specific.get('verified_reference_urls', [])) or 'None')}</td></tr>
      </tbody></table>
      <p class="subhead">Review-type notes</p>
      <ul>{''.join(f"<li>{escape(str(item))}</li>" for item in review_type_specific.get("notes", []))}</ul>
    </div>
    <div class="section">
      <h2>AMR Stewardship Review</h2>
      <p><strong>Applicable:</strong> {escape(_yes_no(amr_review['applicable']))}</p>
      <div>
        <span class="pill">AWaRe {escape(str(amr.get('aware_category', 'not_applicable')))}</span>
        <span class="pill">Authorization {escape(str(amr.get('authorization_control', 'standard_authorization')).replace('_', ' '))}</span>
        <span class="pill">Fast Track {escape(_yes_no(amr.get('fast_track_candidate', False)))}</span>
        <span class="pill">Restriction {escape(_yes_no(amr.get('restricted_authorization', False)))}</span>
      </div>
      <p class="subhead">Stewardship interpretation</p>
      <p>{escape(str(amr_review['stewardship_rule_application']))}</p>
      <p class="subhead">Source-backed stewardship findings</p>
      <ul>{amr_findings_html}</ul>
    </div>
    <div class="section">
      <h2>Workflow Illustration</h2>
      <p style="font-family: monospace;">Intake -> Admin -> Structure -> Rules -> INN -> Technical -> AMR -> Findings -> Severity -> Consistency -> Completeness -> Verdict</p>
    </div>
    <div class="section">
      <h2>Findings Register</h2>
      <table>
        <thead><tr><th>Workflow Step</th><th>Issue</th><th>Violated Rule</th><th>Severity</th><th>Location</th><th>Recommendation</th></tr></thead>
        <tbody>{findings_rows}</tbody>
      </table>
    </div>
    <div class="section">
      <h2>Severity Classification</h2>
      <div>
        <span class="pill">Critical {escape(str(severity_summary['critical']))}</span>
        <span class="pill">Major {escape(str(severity_summary['major']))}</span>
        <span class="pill">Minor {escape(str(severity_summary['minor']))}</span>
        <span class="pill">Advisory {escape(str(severity_summary['advisory']))}</span>
      </div>
    </div>
    <div class="section">
      <h2>Findings Summary Tables</h2>
      {findings_summary_html}
    </div>
    <div class="section">
      <h2>Cross-Section Consistency Review</h2>
      <p><strong>Status:</strong> {escape(str(consistency_review['status']).replace('_', ' ').title())}</p>
      <ul>{''.join(f"<li>{escape(item)}</li>" for item in consistency_items)}</ul>
    </div>
    <div class="section">
      <h2>Review Completeness Confirmation</h2>
      <p><strong>Status:</strong> {escape(str(completeness_review['status']).replace('_', ' ').title())}</p>
      <p class="subhead">Mandatory workflow steps</p>
      <table>
        <thead><tr><th>Workflow step</th><th>Completed</th></tr></thead>
        <tbody>{completion_steps_html}</tbody>
      </table>
      <p class="subhead">Completeness notes</p>
      <ul>{''.join(f"<li>{escape(item)}</li>" for item in completeness_notes)}</ul>
    </div>
    <div class="section">
      <h2>Overall Judgment</h2>
      <p><strong>Final verdict:</strong> {escape(verdict_label)}</p>
      <p><strong>System recommendation:</strong> {escape(rec_label)}</p>
      <p><strong>Authorization control:</strong> {escape(auth_label)}</p>
      <p>{escape(str(overall_judgment['justification']))}</p>
      <p class="subhead">Blocking issues</p>
      <ul>{''.join(f"<li>{escape(item)}</li>" for item in blocking_items)}</ul>
      <p><strong>Escalation needed:</strong> {escape(_yes_no(overall_judgment['escalation_needed']))}</p>
    </div>
    <div class="section">
      <h2>Reviewer Narrative Summary</h2>
      <p>{escape(cleaned_rationale or "The final narrative summary was not available in the current response payload.")}</p>
    </div>
    <div class="section">
      <h2>Evidence Citations</h2>
      <table>
        <thead><tr><th>Citation</th><th>Section</th><th>Snippet</th></tr></thead>
        <tbody>{citation_rows}</tbody>
      </table>
    </div>
    <div class="section">
      <h2>Decision Log</h2>
      <table>
        <thead><tr><th>Rule</th><th>Tool</th><th>Evidence</th><th>Extracted Value</th><th>Result</th><th>Reviewer Action</th></tr></thead>
        <tbody>{decision_log_rows}</tbody>
      </table>
    </div>
    <div class="section">
      <h2>Verification Summary</h2>
      <div>
        <span class="pill">Grounded claim rate {escape(str(verifier.get('grounded_claim_rate', 'unknown')))}</span>
        <span class="pill">Verifier passed {escape(str(verifier.get('passed', False)))}</span>
      </div>
    </div>
    </div>
    </div>
  </body>
</html>"""

    text_lines = [
        "NATIONAL DRUG AGENCY",
        "Pre-Market Authorization Review Report",
        "",
        report_title,
        "",
        "Submission Summary",
    ]
    text_lines.extend(f"- {str(key).replace('_', ' ').title()}: {value}" for key, value in submission_summary.items())
    text_lines.extend(
        [
            "",
            "Administrative Review Outcome",
            f"- Status: {admin_review['status']}",
        ]
    )
    text_lines.extend(f"- {item}" for item in admin_items)
    text_lines.extend(
        [
            "",
            "Dossier Structure Review Outcome",
            f"- Status: {structure_review['status']}",
        ]
    )
    text_lines.extend(f"- {item}" for item in structure_items)
    text_lines.extend(
        [
            "",
            "Applicable Rules And Requirements",
        ]
    )
    text_lines.extend(f"- {rule}" for rule in workflow["applicable_rules_identification"]["rules"])
    text_lines.extend(
        [
            "",
            "WHO INN Similarity Review",
        ]
    )
    text_lines.extend(f"- {str(key).replace('_', ' ').title()}: {value}" for key, value in naming_review.items())
    text_lines.extend(
        [
            "",
            "Section-By-Section Technical Review",
        ]
    )
    text_lines.extend(
        f"- {item['section']}: status={item['status']}, presence={item['presence']}, length={item['length_status']}, correctness={item['correctness']}, critical={item['critical']}"
        for item in technical_review
    )
    text_lines.extend(
        [
            "",
            f"{str(review_type_specific['review_type']).title()} Review-Specific Assessment",
            f"- Status: {review_type_specific['status']}",
            f"- Baseline available: {_yes_no(review_type_specific['baseline_available'])}",
        ]
    )
    if review_type_specific.get("baseline_reference_name"):
        text_lines.append(f"- Baseline reference: {review_type_specific['baseline_reference_name']}")
    text_lines.extend(f"- Note: {item}" for item in review_type_specific.get("notes", []))
    text_lines.extend(
        [
            "",
            "AMR Stewardship Review",
            f"- Applicable: {amr_review['applicable']}",
            f"- AWaRe Category: {amr_review['aware_category']}",
            f"- Fast Track Status: {amr_review['fast_track_status']}",
            f"- Authorization Control: {amr_review['authorization_control']}",
            f"- Stewardship Rule Application: {amr_review['stewardship_rule_application']}",
        ]
    )
    text_lines.extend(f"- AMR finding: {item}" for item in amr_review.get("findings", []) or ["No AMR source-backed findings were recorded for this dossier."])
    text_lines.extend(
        [
            "",
            "Findings Register",
        ]
    )
    text_lines.extend(
        f"- [{item['severity'].upper()}] {item['workflow_step']}: {item['issue']} | Rule: {item['violated_rule']} | Location: {item['location']} | Recommendation: {item['recommendation']}"
        for item in findings_register
    )
    text_lines.extend(
        [
            "",
            "Severity Classification",
        ]
    )
    text_lines.extend(f"- {str(key).title()}: {value}" for key, value in severity_summary.items())
    text_lines.extend(
        [
            "",
            "Findings Summary Tables",
        ]
    )
    text_lines.extend(findings_summary_text)
    text_lines.extend(
        [
            "",
            "Cross-Section Consistency Review",
            f"- Status: {consistency_review['status']}",
        ]
    )
    text_lines.extend(f"- {item}" for item in consistency_items)
    text_lines.extend(
        [
            "",
            "Review Completeness Confirmation",
            f"- Status: {completeness_review['status']}",
            "- Mandatory workflow steps:",
        ]
    )
    text_lines.extend(
        f"  - {str(step).replace('_', ' ').title()}: {_yes_no(status)}"
        for step, status in completeness_review["mandatory_steps"].items()
    )
    text_lines.extend(
        [
            "- Completeness notes:",
        ]
    )
    text_lines.extend(f"  - {item}" for item in completeness_notes)
    text_lines.extend(
        [
            "",
            "Overall Judgment",
            f"- Final verdict: {overall_judgment['final_verdict']}",
            f"- System recommendation: {review_payload.get('recommendation', 'unknown')}",
            f"- Authorization control: {amr.get('authorization_control', 'standard_authorization')}",
            f"- Justification: {overall_judgment['justification']}",
            f"- Escalation needed: {_yes_no(overall_judgment['escalation_needed'])}",
            "- Blocking issues:",
        ]
    )
    text_lines.extend(f"  - {item}" for item in blocking_items)
    text_lines.extend(
        [
            "",
            "Reviewer Narrative Summary",
            cleaned_rationale or "The final narrative summary was not available in the current response payload.",
            "",
            "Evidence Citations",
        ]
    )
    text_lines.extend(
        f"- {item.get('citation_id', 'unknown')} | {item.get('section_title', 'unknown')} | {item.get('snippet', '')}"
        for item in citations
    )
    text_lines.extend(
        [
            "",
            "Verification Summary",
            f"- Grounded claim rate: {verifier.get('grounded_claim_rate', 'unknown')}",
            f"- Verifier passed: {verifier.get('passed', False)}",
        ]
    )
    text_lines.extend(["", "Decision Log"])
    for item in decision_log:
        text_lines.append(
            f"- Rule: {item.get('rule_evaluated')} | Tool: {item.get('tool_called')} | Evidence: {item.get('evidence_retrieved')} | Result: {item.get('rule_result')} | Action: {item.get('reviewer_action')}"
        )

    email_subject = f"{report_title} - {review_payload.get('recommendation', 'decision')}"
    email_body = "\n".join(text_lines[:35])
    docx_paragraphs: list[tuple[str, str | None]] = [
        ("National Food and Drug Regulation Agency", "title"),
        ("Pre-Market Authorization Review Report", "h2"),
        (report_title, "title"),
        ("Submission Summary", "h1"),
    ]
    docx_paragraphs.extend((f"{str(key).replace('_', ' ').title()}: {value}", None) for key, value in submission_summary.items())
    docx_paragraphs.extend([
        ("Administrative Review Outcome", "h1"),
        (f"Status: {admin_review['status']}", None),
    ])
    docx_paragraphs.extend((f"- {item}", None) for item in admin_items)
    docx_paragraphs.extend([
        ("Dossier Structure Review Outcome", "h1"),
        (f"Status: {structure_review['status']}", None),
    ])
    docx_paragraphs.extend((f"- {item}", None) for item in structure_items)
    docx_paragraphs.extend([("Applicable Rules And Requirements", "h1")])
    docx_paragraphs.extend((f"- {rule}", None) for rule in workflow["applicable_rules_identification"]["rules"])
    docx_paragraphs.extend([("WHO INN Similarity Review", "h1")])
    docx_paragraphs.extend((f"{str(key).replace('_', ' ').title()}: {value}", None) for key, value in naming_review.items())
    docx_paragraphs.extend([("Section-By-Section Technical Review", "h1")])
    docx_paragraphs.extend(
        (f"- {item['section']}: status={item['status']}, presence={item['presence']}, length={item['length_status']}, correctness={item['correctness']}, critical={item['critical']}", None)
        for item in technical_review
    )
    docx_paragraphs.extend([
        (f"{str(review_type_specific['review_type']).title()} Review-Specific Assessment", "h2"),
        (f"Status: {review_type_specific['status']}", None),
        (f"Baseline available: {_yes_no(review_type_specific['baseline_available'])}", None),
        (f"Baseline verified: {_yes_no(review_type_specific.get('baseline_verified', False))}", None),
    ])
    if review_type_specific.get("baseline_reference_name"):
        docx_paragraphs.append((f"Baseline reference: {review_type_specific['baseline_reference_name']}", None))
    if review_type_specific.get("verified_reference_urls"):
        docx_paragraphs.append((f"Verified external URLs: {', '.join(review_type_specific['verified_reference_urls'])}", None))
    docx_paragraphs.extend((f"- Note: {item}", None) for item in review_type_specific.get("notes", []))
    docx_paragraphs.extend([
        ("AMR Stewardship Review", "h1"),
        (f"Applicable: {amr_review['applicable']}", None),
        (f"AWaRe Category: {amr_review['aware_category']}", None),
        (f"Fast Track Status: {amr_review['fast_track_status']}", None),
        (f"Authorization Control: {amr_review['authorization_control']}", None),
        (f"Stewardship Rule Application: {amr_review['stewardship_rule_application']}", None),
    ])
    docx_paragraphs.extend((f"- AMR finding: {item}", None) for item in amr_review.get("findings", []) or ["No AMR source-backed findings were recorded for this dossier."])
    docx_paragraphs.extend([("Findings Register", "h1")])
    docx_paragraphs.extend(
        (f"- [{item['severity'].upper()}] {item['workflow_step']}: {item['issue']} | Rule: {item['violated_rule']} | Location: {item['location']} | Recommendation: {item['recommendation']}", None)
        for item in findings_register
    )
    docx_paragraphs.extend([("Severity Classification", "h1")])
    docx_paragraphs.extend((f"- {str(key).title()}: {value}", None) for key, value in severity_summary.items())
    docx_paragraphs.extend([("Findings Summary Tables", "h1")])
    docx_paragraphs.extend((line, None) for line in findings_summary_text if line)
    docx_paragraphs.extend([
        ("Cross-Section Consistency Review", "h1"),
        (f"Status: {consistency_review['status']}", None),
    ])
    docx_paragraphs.extend((f"- {item}", None) for item in consistency_items)
    docx_paragraphs.extend([
        ("Review Completeness Confirmation", "h1"),
        (f"Status: {completeness_review['status']}", None),
        ("Mandatory workflow steps:", "h2"),
    ])
    docx_paragraphs.extend((f"- {str(step).replace('_', ' ').title()}: {_yes_no(status)}", None) for step, status in completeness_review["mandatory_steps"].items())
    docx_paragraphs.extend([("Completeness notes:", "h2")])
    docx_paragraphs.extend((f"- {item}", None) for item in completeness_notes)
    docx_paragraphs.extend([
        ("Overall Judgment", "h1"),
        (f"Final verdict: {overall_judgment['final_verdict']}", None),
        (f"System recommendation: {review_payload.get('recommendation', 'unknown')}", None),
        (f"Authorization control: {amr.get('authorization_control', 'standard_authorization')}", None),
        (f"Justification: {overall_judgment['justification']}", None),
        (f"Escalation needed: {_yes_no(overall_judgment['escalation_needed'])}", None),
        ("Blocking issues:", "h2"),
    ])
    docx_paragraphs.extend((f"- {item}", None) for item in blocking_items)
    docx_paragraphs.extend([
        ("Reviewer Narrative Summary", "h1"),
        (cleaned_rationale or "The final narrative summary was not available in the current response payload.", None),
        ("Evidence Citations", "h1"),
    ])
    docx_paragraphs.extend(
        (f"- {item.get('citation_id', 'unknown')} | {item.get('section_title', 'unknown')} | {item.get('snippet', '')}", None)
        for item in citations
    )
    docx_paragraphs.extend([("Decision Log", "h1")])
    docx_paragraphs.extend(
        (
            f"- Rule: {item.get('rule_evaluated')} | Tool: {item.get('tool_called')} | Evidence: {item.get('evidence_retrieved')} | Result: {item.get('rule_result')} | Action: {item.get('reviewer_action')}",
            None,
        )
        for item in decision_log
    )
    docx_paragraphs.extend([
        ("Verification Summary", "h1"),
        (f"Grounded claim rate: {verifier.get('grounded_claim_rate', 'unknown')}", None),
        (f"Verifier passed: {verifier.get('passed', False)}", None),
    ])
    report_json = {
        "report_title": report_title,
        "workflow_report": workflow,
        "findings_summary_markdown": findings_summary_markdown,
        "query_letter": query_letter,
        "decision_log": decision_log,
        "review_payload": review_payload,
        "email_subject": email_subject,
        "email_body": email_body,
    }
    return {
        "html": html,
        "text": "\n".join(text_lines),
        "pdf_bytes": _build_simple_pdf_bytes(text_lines),
        "docx_bytes": _build_docx_bytes(docx_paragraphs),
        "json": report_json,
        "email_subject": email_subject,
        "email_body": email_body,
        "query_letter_markdown": query_letter["markdown"],
        "query_letter_html": query_letter["html"],
        "query_letter_text": query_letter["text"],
        "decision_log": decision_log,
    }
