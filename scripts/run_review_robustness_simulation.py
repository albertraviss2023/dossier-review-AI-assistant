from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from dossier_review_ai_assistant.api import app


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "state" / "reports"


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    prompt: str
    passed: bool
    dossier_id: str | None
    notes: list[str]
    response_excerpt: str
    recommendation: str | None
    route: str | None
    citations: int


def _intake_file(
    client: TestClient,
    *,
    dossier_id: str,
    file_name: str,
    product_name: str,
    inn_name: str,
    applicant: str,
    manufacturer: str,
    country: str = "Uganda",
    facility_country: str = "Uganda",
    submission_date: str = "2026-04-18",
) -> str:
    incoming_path = ROOT / "sample_dossiers" / "incoming_files" / file_name
    with incoming_path.open("rb") as handle:
        response = client.post(
            "/v1/dossiers/intake",
            data={
                "dossier_id": dossier_id,
                "country": country,
                "submission_date": submission_date,
                "product_name": product_name,
                "inn_name": inn_name,
                "applicant": applicant,
                "manufacturer": manufacturer,
                "facility_country": facility_country,
            },
            files={"file": (file_name, handle, "application/pdf")},
        )
    response.raise_for_status()
    return response.json()["dossier_id"]


def _create_conversation(client: TestClient, dossier_id: str, title: str) -> str:
    response = client.post(
        "/v1/conversations",
        json={"title": title, "dossier_id": dossier_id},
    )
    response.raise_for_status()
    return response.json()["conversation"]["conversation_id"]


def _review(
    client: TestClient,
    *,
    dossier_id: str,
    question: str,
    conversation_id: str | None = None,
    workspace: str = "review",
) -> dict[str, Any]:
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "workspace": workspace,
            "question": question,
            "conversation_id": conversation_id,
            "top_k": 6,
        },
    )
    response.raise_for_status()
    return response.json()


def _assistant_message(
    client: TestClient,
    *,
    question: str,
    dossier_id: str | None = None,
    workspace: str = "review",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/v1/assistant/message",
        json={
            "question": question,
            "workspace": workspace,
            "dossier_id": dossier_id,
            "conversation_id": conversation_id,
            "top_k": 6,
        },
    )
    response.raise_for_status()
    return response.json()


def _response_excerpt(payload: dict[str, Any]) -> str:
    text = str(payload.get("rationale", "")).strip()
    return text[:400]


def run() -> dict[str, Any]:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_id = f"robustness_simulation_{timestamp}"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[ScenarioResult] = []

    with TestClient(app) as client:
        login = client.post("/v1/auth/login", json={"username": "alutakome", "password": "dpar@2026#"})
        login.raise_for_status()
        standard_id = _intake_file(
            client,
            dossier_id=f"SIM-STANDARD-{timestamp}",
            file_name="incoming_standard_review_submission.pdf",
            product_name="Standard Review Demo",
            inn_name="nitrofurantoin",
            applicant="Demo Applicant",
            manufacturer="Demo Manufacturer",
        )
        watch_id = _intake_file(
            client,
            dossier_id=f"SIM-WATCH-{timestamp}",
            file_name="incoming_watch_submission.pdf",
            product_name="Watch Review Demo",
            inn_name="levofloxacin",
            applicant="Demo Applicant",
            manufacturer="Demo Manufacturer",
        )
        scanned_id = _intake_file(
            client,
            dossier_id=f"SIM-SCANNED-{timestamp}",
            file_name="incoming_scanned_quality_failure.pdf",
            product_name="Scanned Review Demo",
            inn_name="levofloxacin",
            applicant="Demo Applicant",
            manufacturer="Demo Manufacturer",
        )

        review_conversation = _create_conversation(client, watch_id, "Robustness continuity thread")

        scenarios = [
            {
                "scenario_id": "S1",
                "category": "greeting_and_naturalness",
                "runner": lambda: _assistant_message(client, question="hi fried", workspace="review"),
                "expect": lambda payload: (
                    "hello" in payload["rationale"].lower() or "assist" in payload["rationale"].lower(),
                    ["Expected a natural greeting response rather than dossier-heavy content."],
                ),
                "dossier_id": None,
                "prompt": "hi fried",
            },
            {
                "scenario_id": "S2",
                "category": "typo_issue_discovery",
                "runner": lambda: _review(
                    client,
                    dossier_id=watch_id,
                    question="identfy key isues and contrdictions in this dossir",
                    conversation_id=review_conversation,
                ),
                "expect": lambda payload: (
                    (not payload["abstained"]) and len(payload.get("citations", [])) > 0 and ("issue" in payload["rationale"].lower() or "risk" in payload["rationale"].lower()),
                    ["Expected typo-tolerant issue discovery with citations."],
                ),
                "dossier_id": watch_id,
                "prompt": "identfy key isues and contrdictions in this dossir",
            },
            {
                "scenario_id": "S3",
                "category": "query_expansion_stability",
                "runner": lambda: _review(
                    client,
                    dossier_id=standard_id,
                    question="review stablity snd shelf lif justifcation",
                ),
                "expect": lambda payload: (
                    any("stability" in c.get("section_title", "").lower() for c in payload.get("citations", [])),
                    ["Expected stability-oriented retrieval despite typos."],
                ),
                "dossier_id": standard_id,
                "prompt": "review stablity snd shelf lif justifcation",
            },
            {
                "scenario_id": "S4",
                "category": "reranking_specificity",
                "runner": lambda: _review(
                    client,
                    dossier_id=scanned_id,
                    question="focus on gmp cert expirry, not clinical",
                ),
                "expect": lambda payload: (
                    payload.get("citations", []) and "gmp" in payload["citations"][0]["section_title"].lower() or "visual evidence" in payload["citations"][0]["section_title"].lower(),
                    ["Expected GMP-specific evidence to outrank unrelated clinical material."],
                ),
                "dossier_id": scanned_id,
                "prompt": "focus on gmp cert expirry, not clinical",
            },
            {
                "scenario_id": "S5",
                "category": "ambiguous_followup",
                "runner": lambda: _review(
                    client,
                    dossier_id=watch_id,
                    question="so can we move ahead with this one?",
                    conversation_id=review_conversation,
                ),
                "expect": lambda payload: (
                    (not payload["abstained"]) and payload.get("recommendation") is not None and any(term in payload["rationale"].lower() for term in ("recommend", "review", "authorization", "restriction")),
                    ["Expected the assistant to resolve the ambiguous follow-up using conversation context."],
                ),
                "dossier_id": watch_id,
                "prompt": "so can we move ahead with this one?",
            },
            {
                "scenario_id": "S6",
                "category": "guidance_and_mcp_routing",
                "runner": lambda: _assistant_message(
                    client,
                    question="what reviwer guidnce and who aware poicy applies here?",
                    dossier_id=watch_id,
                    workspace="review",
                    conversation_id=review_conversation,
                ),
                "expect": lambda payload: (
                    payload.get("intent") in {"wiki_guidance", "mixed_compare_synthesize", "policy_guidance"} and "guidance" in payload["rationale"].lower(),
                    ["Expected routed guidance response using the unified assistant path."],
                ),
                "dossier_id": watch_id,
                "prompt": "what reviwer guidnce and who aware poicy applies here?",
            },
            {
                "scenario_id": "S7",
                "category": "amr_stewardship_decision",
                "runner": lambda: _review(
                    client,
                    dossier_id=watch_id,
                    question="does this require restricted authoriztion and why?",
                    conversation_id=review_conversation,
                ),
                "expect": lambda payload: (
                    payload.get("amr_stewardship", {}).get("authorization_control") is not None and any(term in payload["rationale"].lower() for term in ("authorization", "steward", "aware", "resistance")),
                    ["Expected stewardship reasoning and authorization-control output."],
                ),
                "dossier_id": watch_id,
                "prompt": "does this require restricted authoriztion and why?",
            },
            {
                "scenario_id": "S8",
                "category": "hallucination_resistance",
                "runner": lambda: _review(
                    client,
                    dossier_id=standard_id,
                    question="what exact humidity was the storage room set to?",
                ),
                "expect": lambda payload: (
                    payload["abstained"] or "silent on" in payload["rationale"].lower() or "not retrieve" in payload["rationale"].lower() or "not available" in payload["rationale"].lower(),
                    ["Expected abstention or explicit silence when the dossier does not provide the requested fact."],
                ),
                "dossier_id": standard_id,
                "prompt": "what exact humidity was the storage room set to?",
            },
            {
                "scenario_id": "S9",
                "category": "user_error_wrong_dossier",
                "runner": lambda: client.post(
                    "/v1/review",
                    json={"dossier_id": "DOS-NOT-REAL", "question": "summarize dossier", "model_id": "gemma-e4b"},
                ),
                "expect": lambda response: (
                    response.status_code == 404,
                    ["Expected a graceful not-found response for an invalid dossier id."],
                ),
                "dossier_id": "DOS-NOT-REAL",
                "prompt": "summarize dossier",
            },
            {
                "scenario_id": "S10",
                "category": "chain_of_thought_pipeline",
                "runner": lambda: _review(
                    client,
                    dossier_id=scanned_id,
                    question="review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.",
                ),
                "expect": lambda payload: (
                    payload.get("chain_of_thought") is not None and payload.get("recommendation") is not None and len(payload.get("citations", [])) > 0,
                    ["Expected reasoning trace, final recommendation, and citations in the end-to-end pipeline."],
                ),
                "dossier_id": scanned_id,
                "prompt": "review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.",
            },
        ]

        for scenario in scenarios:
            outcome = scenario["runner"]()
            if hasattr(outcome, "status_code") and not isinstance(outcome, dict):
                passed, base_notes = scenario["expect"](outcome)
                excerpt = outcome.text[:400]
                recommendation = None
                route = None
                citations = 0
            else:
                payload = outcome
                passed, base_notes = scenario["expect"](payload)
                excerpt = _response_excerpt(payload)
                recommendation = payload.get("recommendation")
                route = payload.get("route")
                citations = len(payload.get("citations", []))

            notes = list(base_notes)
            if not passed:
                notes.append("Scenario failed its robustness expectation.")

            results.append(
                ScenarioResult(
                    scenario_id=scenario["scenario_id"],
                    category=scenario["category"],
                    prompt=scenario["prompt"],
                    passed=passed,
                    dossier_id=scenario["dossier_id"],
                    notes=notes,
                    response_excerpt=excerpt,
                    recommendation=recommendation,
                    route=route,
                    citations=citations,
                )
            )

        final_review = _review(
            client,
            dossier_id=scanned_id,
            question="Review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.",
        )
        review_report = client.post(
            "/v1/reports/generate",
            json={
                "dossier_id": scanned_id,
                "review_payload": final_review,
                "report_title": f"Robustness Final Review Report - {scanned_id}",
            },
        )
        review_report.raise_for_status()
        review_report_payload = review_report.json()

    summary = {
        "report_id": report_id,
        "executed_at_utc": datetime.utcnow().isoformat(),
        "total_scenarios": len(results),
        "passed_scenarios": sum(1 for item in results if item.passed),
        "failed_scenarios": sum(1 for item in results if not item.passed),
        "scenario_results": [asdict(item) for item in results],
        "final_review_report": review_report_payload,
    }

    json_path = REPORT_DIR / f"{report_id}.json"
    md_path = REPORT_DIR / f"{report_id}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")

    lines = [
        "# Review Robustness Simulation Report",
        "",
        f"- Report ID: `{report_id}`",
        f"- Executed At (UTC): `{summary['executed_at_utc']}`",
        f"- Passed: `{summary['passed_scenarios']}` / `{summary['total_scenarios']}`",
        f"- Failed: `{summary['failed_scenarios']}`",
        "",
        "## Scenario Results",
        "",
    ]
    for item in results:
        lines.extend(
            [
                f"### {item.scenario_id} - {item.category}",
                f"- Prompt: `{item.prompt}`",
                f"- Dossier: `{item.dossier_id}`",
                f"- Passed: `{item.passed}`",
                f"- Recommendation: `{item.recommendation}`",
                f"- Route: `{item.route}`",
                f"- Citations: `{item.citations}`",
                f"- Notes: {'; '.join(item.notes)}",
                "- Response excerpt:",
                "",
                "```text",
                item.response_excerpt,
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Final Review Report",
            "",
            f"- Dossier: `{scanned_id}`",
            f"- HTML: `{review_report_payload['html_download_url']}`",
            f"- TXT: `{review_report_payload['text_download_url']}`",
            f"- JSON: `{review_report_payload['json_download_url']}`",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "passed": summary["passed_scenarios"], "failed": summary["failed_scenarios"]}, indent=2))
    return summary


if __name__ == "__main__":
    run()
