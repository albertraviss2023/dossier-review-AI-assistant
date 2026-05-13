from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regulatory_mcp_server.app import mcp


async def run_sequence() -> dict:
    summary: list[dict] = []

    async def call(name: str, args: dict) -> dict:
        result = await mcp.call_tool(name, args)
        if isinstance(result, tuple):
            result = result[0]
        payload = json.loads(result[0].text)
        summary.append({"tool": name, "status": payload.get("status"), "warnings": payload.get("warnings", [])})
        return payload

    tools = await mcp.list_tools()
    tool_names = [tool.name for tool in tools]
    summary.append({"tool": "list_tools", "status": "success", "count": len(tool_names)})

    health = await call("health_status", {})
    search = await call(
        "search_vector_database",
        {"query": "WHO AWaRe Watch escalation", "index": "knowledge_wiki", "filters": {}, "top_k": 3},
    )
    reranked = await call(
        "rerank_search_results",
        {
            "query": "WHO AWaRe Watch escalation",
            "candidate_results": search["data"]["results"],
            "rerank_criteria": ["regulatory relevance", "section specificity"],
            "top_k": 2,
        },
    )
    examples = await call(
        "get_section_examples",
        {
            "section_type": "patient_information_leaflet",
            "example_type": "both",
            "product_type": "generic",
            "top_k": 4,
        },
    )
    compared_section = await call(
        "compare_current_section_to_examples",
        {
            "current_section": {
                "section_id": "pil-1",
                "section_type": "patient_information_leaflet",
                "title": "Patient Information Leaflet",
                "text": "The leaflet gives the indication only and a vague dose statement.",
            },
            "correct_examples": [],
            "incorrect_examples": [],
            "comparison_dimensions": ["completeness", "safety wording", "contraindications", "dosage clarity"],
        },
    )
    inn_candidates = await call(
        "fetch_who_inn_candidates",
        {"active_ingredient": "paracetamol", "proposed_name": "Paracare"},
    )
    inn_similarity = await call(
        "compute_inn_similarity",
        {"proposed_name": "amoxicillin", "inn_candidates": ["amoxicillin"], "threshold": 70},
    )
    aware_reference = await call(
        "fetch_aware_reserve_reference",
        {"active_ingredient": "levofloxacin", "source_mode": "cached"},
    )
    antimicrobial_similarity = await call(
        "compute_antimicrobial_similarity",
        {
            "active_ingredient": "levofloxacin",
            "aware_reference": {
                "active_ingredient": "levofloxacin",
                "is_antimicrobial": True,
                "aware_category": "Watch",
                "reserve_related": False,
                "nearest_reserve_agent": "ciprofloxacin",
            },
            "comparison_mode": "class_or_structure",
        },
    )
    innovator_pil = await call(
        "fetch_innovator_patient_information",
        {"active_ingredient": "amoxicillin", "reference_urls": ["https://www.medicines.org.uk/emc/product/541/pil"]},
    )
    generic_pil = await call(
        "compare_generic_patient_information",
        {
            "current_pil_sections": [
                {"section_name": "indications", "text": "This leaflet explains what the medicine is for and how much to take.", "source_url": None}
            ],
            "innovator_pil_sections": innovator_pil["data"]["sections"],
            "comparison_dimensions": ["warnings", "storage"],
        },
    )
    evidence_packet = await call(
        "build_evidence_packet",
        {
            "dossier_id": "DOS-MCP-001",
            "review_type": "generic",
            "section_id": "pil-1",
            "review_area": "patient_information",
            "tool_results": {
                "search_vector_database": search,
                "rerank_search_results": reranked,
                "get_section_examples": examples,
                "compare_current_section_to_examples": compared_section,
                "fetch_who_inn_candidates": inn_candidates,
                "compute_inn_similarity": inn_similarity,
                "fetch_aware_reserve_reference": aware_reference,
                "compute_antimicrobial_similarity": antimicrobial_similarity,
                "fetch_innovator_patient_information": innovator_pil,
                "compare_generic_patient_information": generic_pil,
            },
        },
    )
    findings = await call(
        "generate_findings_table",
        {
            "dossier_id": "DOS-MCP-001",
            "findings": [
                {
                    "review_area": "patient_information",
                    "finding": "Generic PIL does not align with innovator warnings.",
                    "severity": "major",
                    "violated_rule": "Generic patient information should align closely with innovator/reference material",
                    "evidence_ref": "DOS-MCP-001:pil-1",
                    "recommendation": "Align warnings and storage wording with the innovator reference.",
                    "decision_trace": {"tool": "compare_generic_patient_information"},
                }
            ],
            "group_by": "review_area",
        },
    )

    passed = all(item.get("status") == "success" for item in summary if item["tool"] != "list_tools")
    return {
        "passed": passed,
        "tool_names": tool_names,
        "summary": summary,
        "final_outputs": {
            "health": health,
            "evidence_packet": evidence_packet,
            "findings_table": findings,
        },
    }


def main() -> None:
    report = asyncio.run(run_sequence())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
