from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import Finding, FindingsTable, GenerateFindingsTableRequest

from .common import build_tool_envelope, tool_audit


LOGGER = logging.getLogger("regulatory_mcp_server.tools.reports")


@mcp.tool(name="generate_findings_table", description="Generate grouped structured findings rows and a markdown table for report-ready rendering.")
@tool_audit(tool_name="generate_findings_table", logger=LOGGER)
def generate_findings_table(
    dossier_id: str,
    findings: list[dict[str, Any]],
    group_by: str = "review_area",
) -> dict[str, Any]:
    payload = {
        "dossier_id": dossier_id,
        "findings": findings,
        "group_by": group_by,
    }
    request = GenerateFindingsTableRequest.model_validate(payload)
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in request.findings:
        grouped[finding.review_area].append(finding)

    markdown_sections: list[str] = []
    if not request.findings:
        markdown_sections.extend(
            [
                "| Review area | Finding | Severity | Violated rule | Evidence ref | Recommendation |",
                "| --- | --- | --- | --- | --- | --- |",
                "| none | No violations identified | none | n/a | n/a | Continue standard review monitoring |",
            ]
        )
    else:
        for review_area, rows in grouped.items():
            markdown_sections.append(f"### {review_area.replace('_', ' ').title()}")
            markdown_sections.append("")
            markdown_sections.append("| Review area | Finding | Severity | Violated rule | Evidence ref | Recommendation |")
            markdown_sections.append("| --- | --- | --- | --- | --- | --- |")
            for row in rows:
                markdown_sections.append(
                    f"| {row.review_area} | {row.finding} | {row.severity} | {row.violated_rule} | {row.evidence_ref} | {row.recommendation} |"
                )
            markdown_sections.append("")

    table = FindingsTable(
        markdown_table="\n".join(markdown_sections).strip(),
        structured_table=request.findings,
    )
    return build_tool_envelope(
        tool_name="generate_findings_table",
        payload=payload,
        data=table.model_dump(mode="json"),
        warnings=[],
        source_refs=[],
    )
