from __future__ import annotations

import logging
from uuid import uuid4
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import BuildEvidencePacketRequest, EvidencePacket

from .common import build_tool_envelope, tool_audit


LOGGER = logging.getLogger("regulatory_mcp_server.tools.evidence_packet")


@mcp.tool(name="build_evidence_packet", description="Combine MCP tool outputs into a structured evidence packet ready for the judgment layer.")
@tool_audit(tool_name="build_evidence_packet", logger=LOGGER)
def build_evidence_packet(
    dossier_id: str,
    review_type: str,
    section_id: str,
    review_area: str,
    tool_results: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "dossier_id": dossier_id,
        "review_type": review_type,
        "section_id": section_id,
        "review_area": review_area,
        "tool_results": tool_results,
    }
    request = BuildEvidencePacketRequest.model_validate(payload)
    tool_results_data = request.tool_results
    rules_applied: list[str] = []
    evidence_items: list[dict[str, Any]] = []
    examples_used: list[dict[str, Any]] = []
    external_sources_used: list[dict[str, Any]] = []
    preliminary_flags: list[str] = []

    search_results = tool_results_data.get("search_vector_database", {}).get("data", {}).get("results", [])
    reranked_results = tool_results_data.get("rerank_search_results", {}).get("data", {}).get("reranked_results", [])
    example_comparison = tool_results_data.get("compare_current_section_to_examples", {}).get("data", {})
    inn_similarity = tool_results_data.get("compute_inn_similarity", {}).get("data", {})
    aware_result = tool_results_data.get("compute_antimicrobial_similarity", {}).get("data", {})
    patient_alignment = tool_results_data.get("compare_generic_patient_information", {}).get("data", {})

    evidence_items.extend(search_results[:5])
    evidence_items.extend(reranked_results[:5])
    examples_used.extend(tool_results_data.get("get_section_examples", {}).get("data", {}).get("examples", []))

    if inn_similarity:
        rules_applied.append("WHO INN similarity review is mandatory and always reported")
        if inn_similarity.get("rule_result") == "flagged":
            preliminary_flags.append("naming_flag")

    if aware_result:
        rules_applied.append("AMR stewardship review must use controlled AWaRe logic")
        if aware_result.get("stewardship_flag") in {"reserve_caution", "required_control"}:
            preliminary_flags.append("stewardship_flag")

    if patient_alignment:
        rules_applied.append("Generic patient information should align closely with innovator/reference material")
        if patient_alignment.get("overall_alignment") in {"partial", "not_aligned"}:
            preliminary_flags.append("patient_information_gap")

    for tool_name, result in tool_results_data.items():
        for ref in result.get("source_refs", []):
            external_sources_used.append({"tool_name": tool_name, **ref})

    if example_comparison.get("classification") in {"partially_compliant", "non_compliant"}:
        preliminary_flags.append("section_example_mismatch")

    ready_for_judgment = bool(evidence_items) and not (
        request.review_area == "patient_information" and request.review_type == "generic" and not patient_alignment
    )
    warnings = []
    if not ready_for_judgment:
        warnings.append("Mandatory evidence for this review area is incomplete; the packet is not yet ready for judgment.")

    packet = EvidencePacket(
        evidence_packet_id=f"ep-{uuid4().hex[:12]}",
        dossier_id=request.dossier_id,
        review_area=request.review_area,
        rules_applied=rules_applied,
        evidence_items=evidence_items,
        examples_used=examples_used,
        external_sources_used=external_sources_used,
        preliminary_flags=sorted(set(preliminary_flags)),
        ready_for_judgment=ready_for_judgment,
    )

    return build_tool_envelope(
        tool_name="build_evidence_packet",
        payload=payload,
        data=packet.model_dump(mode="json"),
        warnings=warnings,
        source_refs=[],
    )

