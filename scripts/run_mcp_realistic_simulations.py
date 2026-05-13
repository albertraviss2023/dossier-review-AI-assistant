from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dossier_review_ai_assistant.api import app  # noqa: E402
from regulatory_mcp_server.app import mcp  # noqa: E402


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    summary: str
    details: dict[str, Any]


async def _call(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = await mcp.call_tool(tool_name, payload)
    if isinstance(result, tuple):
        result = result[0]
    return json.loads(result[0].text)


async def run_simulations() -> dict[str, Any]:
    scenarios: list[ScenarioResult] = []

    generic_ref = await _call(
        "fetch_innovator_patient_information",
        {
            "active_ingredient": "paracetamol",
            "reference_urls": [
                "https://www.medicines.org.uk/emc/product/5164/xpil/print",
                "https://www.medicines.org.uk/emc/files/pil.5164.pdf",
            ],
        },
    )
    generic_compare = await _call(
        "compare_generic_patient_information",
        {
            "current_pil_sections": [
                {
                    "section_name": "warnings",
                    "text": "This leaflet describes pain relief and dosage, but it omits clear overdose and child-safety warning language.",
                    "source_url": None,
                }
            ],
            "innovator_pil_sections": generic_ref["data"]["sections"],
            "comparison_dimensions": ["warnings", "storage", "dosage"],
        },
    )
    inn_similarity = await _call(
        "compute_inn_similarity",
        {
            "proposed_name": "Paracare",
            "inn_candidates": ["paracetamol"],
            "threshold": 70,
        },
    )
    generic_findings = await _call(
        "generate_findings_table",
        {
            "dossier_id": "SIM-GENERIC-001",
            "findings": [
                {
                    "review_area": "patient_information",
                    "finding": "Generic patient information misses innovator-aligned warning content.",
                    "severity": "major",
                    "violated_rule": "Generic patient information should align closely with innovator/reference material",
                    "evidence_ref": "SIM-GENERIC-001:pil",
                    "recommendation": "Restore the missing warning and storage language from the verified reference.",
                    "decision_trace": {"tool": "compare_generic_patient_information"},
                }
            ],
            "group_by": "review_area",
        },
    )
    scenarios.append(
        ScenarioResult(
            name="generic_paracetamol_reference_review",
            passed=(
                generic_ref["status"] == "success"
                and generic_compare["status"] == "success"
                and generic_compare["data"]["overall_alignment"] in {"partial", "not_aligned"}
                and inn_similarity["data"]["decision_effect"] == "can_continue"
                and "| Review area | Finding | Severity |" in generic_findings["data"]["markdown_table"]
            ),
            summary="Generic patient-information comparison and INN review completed.",
            details={
                "innovator_reference": generic_ref["data"]["reference_product"],
                "overall_alignment": generic_compare["data"]["overall_alignment"],
                "inn_decision_effect": inn_similarity["data"]["decision_effect"],
            },
        )
    )

    aware_ref = await _call(
        "fetch_aware_reserve_reference",
        {"active_ingredient": "levofloxacin", "source_mode": "cached"},
    )
    amr_similarity = await _call(
        "compute_antimicrobial_similarity",
        {
            "active_ingredient": "levofloxacin",
            "aware_reference": aware_ref["data"],
            "comparison_mode": "class_or_structure",
        },
    )
    scenarios.append(
        ScenarioResult(
            name="antimicrobial_watch_caution",
            passed=(
                aware_ref["status"] == "success"
                and amr_similarity["status"] == "success"
                and amr_similarity["data"]["aware_category"] == "Watch"
                and amr_similarity["data"]["stewardship_flag"] in {"review_required", "reserve_caution", "required_control"}
            ),
            summary="AWaRe classification and stewardship flag computed.",
            details={
                "aware_category": amr_similarity["data"]["aware_category"],
                "stewardship_flag": amr_similarity["data"]["stewardship_flag"],
            },
        )
    )

    examples = await _call(
        "get_section_examples",
        {
            "section_type": "patient_information_leaflet",
            "example_type": "both",
            "product_type": "generic",
            "top_k": 4,
        },
    )
    section_compare = await _call(
        "compare_current_section_to_examples",
        {
            "current_section": {
                "section_id": "pil-deficient-1",
                "section_type": "patient_information_leaflet",
                "title": "Patient Information Leaflet",
                "text": "The leaflet only says what the medicine is for and gives a vague dose.",
            },
            "correct_examples": [item for item in examples["data"]["examples"] if item["label"] == "correct"],
            "incorrect_examples": [item for item in examples["data"]["examples"] if item["label"] == "incorrect"],
            "comparison_dimensions": ["completeness", "safety wording", "contraindications", "dosage clarity"],
        },
    )
    scenarios.append(
        ScenarioResult(
            name="incorrect_section_example_comparison",
            passed=(
                section_compare["status"] == "success"
                and section_compare["data"]["classification"] in {"partially_compliant", "non_compliant"}
                and len(section_compare["data"]["evidence"]) >= 1
            ),
            summary="Incorrect section comparison produced deterministic findings.",
            details={"classification": section_compare["data"]["classification"]},
        )
    )

    client = TestClient(app)
    login = client.post("/v1/auth/login", json={"username": "alutakome", "password": "dpar@2026#"})
    if login.status_code != 200:
        raise RuntimeError(f"Simulation login failed: {login.text}")
    chart_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "Plot the approval distribution for antimicrobial dossiers as a chart.",
        },
    )
    table_response = client.post(
        "/v1/review",
        json={
            "dossier_id": client.get("/v1/dossiers").json()["items"][0]["dossier_id"],
            "question": "Review this dossier, identify the key issues, and include findings summary tables.",
            "review_type": "generic",
        },
    )
    chart_payload = chart_response.json()
    table_payload = table_response.json()
    scenarios.append(
        ScenarioResult(
            name="chat_chart_and_markdown_table_routing",
            passed=(
                chart_response.status_code == 200
                and chart_payload.get("visualization_data") is not None
                and table_response.status_code == 200
                and "| Severity | Violated rule | Evidence reference | Recommendation |" in (table_payload.get("findings_summary_markdown") or "")
            ),
            summary="Chart request and findings tables rendered through the app.",
            details={
                "chart_type": (chart_payload.get("visualization_data") or {}).get("type"),
                "review_recommendation": table_payload.get("recommendation"),
            },
        )
    )

    external_trace = await _call(
        "fetch_innovator_patient_information",
        {
            "active_ingredient": "paracetamol",
            "reference_urls": ["https://www.medicines.org.uk/emc/product/5164/xpil/print"],
        },
    )
    scenarios.append(
        ScenarioResult(
            name="external_source_supported_answer_trace",
            passed=(
                external_trace["status"] == "success"
                and len(external_trace.get("source_refs", [])) >= 1
                and external_trace.get("audit", {}).get("tool_name") == "fetch_innovator_patient_information"
            ),
            summary="External-source-backed cache trace was preserved in the MCP envelope.",
            details={
                "source_type": external_trace["source_refs"][0]["source_type"],
                "audit_tool": external_trace["audit"]["tool_name"],
            },
        )
    )

    passed = sum(1 for scenario in scenarios if scenario.passed)
    failed = len(scenarios) - passed
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "passed": failed == 0,
        "scenario_count": len(scenarios),
        "passed_count": passed,
        "failed_count": failed,
        "scenarios": [asdict(item) for item in scenarios],
    }


def main() -> None:
    report = asyncio.run(run_simulations())
    reports_dir = REPO_ROOT / "state" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"mcp_realistic_simulations_{timestamp}.json"
    md_path = reports_dir / f"mcp_realistic_simulations_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# MCP Realistic Simulation Report",
        "",
        f"- Generated: {report['generated_at_utc']}",
        f"- Passed: {report['passed_count']}/{report['scenario_count']}",
        f"- Failed: {report['failed_count']}",
        "",
    ]
    for scenario in report["scenarios"]:
        lines.append(f"## {scenario['name']}")
        lines.append("")
        lines.append(f"- Passed: {scenario['passed']}")
        lines.append(f"- Summary: {scenario['summary']}")
        for key, value in scenario["details"].items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "passed": report["passed"]}, indent=2))


if __name__ == "__main__":
    main()
