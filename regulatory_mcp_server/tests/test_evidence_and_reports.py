from __future__ import annotations

from regulatory_mcp_server.tools.evidence_packet import build_evidence_packet
from regulatory_mcp_server.tools.reports import generate_findings_table


def test_build_evidence_packet_collects_tool_outputs():
    result = build_evidence_packet(
        dossier_id="DOS-1",
        review_type="generic",
        section_id="pil-1",
        review_area="patient_information",
        tool_results={
            "search_vector_database": {
                "data": {"results": [{"chunk_id": "c1", "text": "warning text"}]},
                "source_refs": [],
            },
            "compare_generic_patient_information": {
                "data": {"overall_alignment": "partial", "differences": [{"section": "warnings"}]},
                "source_refs": [],
            },
            "compute_inn_similarity": {
                "data": {"rule_result": "pass"},
                "source_refs": [],
            },
        },
    )
    assert result["status"] == "success"
    assert result["data"]["evidence_items"]
    assert "patient_information_gap" in result["data"]["preliminary_flags"]


def test_build_evidence_packet_marks_missing_mandatory_evidence():
    result = build_evidence_packet(
        dossier_id="DOS-2",
        review_type="generic",
        section_id="pil-1",
        review_area="patient_information",
        tool_results={},
    )
    assert result["data"]["ready_for_judgment"] is False
    assert result["warnings"]


def test_generate_findings_table_returns_markdown_and_structured_rows():
    result = generate_findings_table(
        dossier_id="DOS-3",
        findings=[
            {
                "review_area": "naming_inn",
                "finding": "High similarity to the WHO INN",
                "severity": "major",
                "violated_rule": "INN similarity threshold > 70",
                "evidence_ref": "DOS-3:m1_product_information",
                "recommendation": "Rename the product before acceptance.",
                "decision_trace": {"rule_applied": "INN threshold"},
            }
        ],
        group_by="review_area",
    )
    assert result["status"] == "success"
    assert "| Review area | Finding | Severity | Violated rule | Evidence ref | Recommendation |" in result["data"]["markdown_table"]
    assert result["data"]["structured_table"][0]["review_area"] == "naming_inn"


def test_generate_findings_table_handles_empty_findings():
    result = generate_findings_table(
        dossier_id="DOS-4",
        findings=[],
        group_by="review_area",
    )
    assert "No violations identified" in result["data"]["markdown_table"]
