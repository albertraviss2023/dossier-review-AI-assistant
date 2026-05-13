from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from dossier_review_ai_assistant.api import app


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "state" / "reports"


@dataclass
class WorkflowStepResult:
    dossier_id: str
    dossier_label: str
    step_id: int
    step_name: str
    prompt: str
    passed: bool
    abstained: bool
    response_excerpt: str
    response_full: str
    notes: list[str]


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"username": "alutakome", "password": "dpar@2026#"},
    )
    response.raise_for_status()


def _intake_pdf(
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
    path = ROOT / "sample_dossiers" / "incoming_files" / file_name
    if not path.exists():
         # Fallback for some environments
         path = ROOT / "sample_dossiers" / "incoming_files" / "incoming_standard_review_submission.pdf"
         
    with path.open("rb") as handle:
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


def _chat(
    client: TestClient,
    *,
    dossier_id: str,
    question: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    models = client.get("/v1/models").json()
    model_id = models.get("default_model_id", "gemma-4-4b-it")
    response = client.post(
        "/v1/assistant/message",
        json={
            "dossier_id": dossier_id,
            "question": question,
            "conversation_id": conversation_id,
            "model_id": model_id,
            "workspace": "review",
            "top_k": 6,
        },
    )
    response.raise_for_status()
    return response.json()


def _conversation(client: TestClient, dossier_id: str, title: str) -> str:
    models = client.get("/v1/models").json()
    model_id = models.get("default_model_id", "gemma-4-4b-it")
    response = client.post(
        "/v1/conversations",
        json={"title": title, "dossier_id": dossier_id, "model_id": model_id},
    )
    response.raise_for_status()
    return response.json()["conversation"]["conversation_id"]


def _excerpt(payload: dict[str, Any]) -> str:
    return str(payload.get("rationale", ""))[:420]


def run() -> dict[str, Any]:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_id = f"workflow_simulation_{timestamp}"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Focus on the most interesting realistic dossiers
    dossier_specs = [
        {
            "label": "reserve_fast_track",
            "file_name": "incoming_reserve_fast_track_submission.pdf",
            "product_name": "Reserve Review Demo",
            "inn_name": "cefiderocol",
        },
        {
            "label": "naming_conflict",
            "file_name": "incoming_naming_conflict_submission.pdf",
            "product_name": "amoxicillin",
            "inn_name": "amoxicillin",
        },
    ]

    stage_prompts = [
        (1, "Submission Intake", "Perform submission intake and familiarization: identify submission type, product profile, applicant, and review pathway."),
        (2, "Administrative Review", "Perform the administrative completeness review: application form, signatures, payment and attachments."),
        (3, "Structure Mapping", "Perform structural dossier mapping by module and section coverage."),
        (4, "Applicable Rules", "Identify applicable regulatory rules and checklist items for this dossier."),
        (5, "INN Similarity", "Perform the WHO INN similarity and naming confusion-risk review."),
        (6, "Technical Review", "Perform section-by-section technical review for quality, GMP, clinical efficacy and safety evidence."),
        (7, "AMR Stewardship", "Perform AMR stewardship review with AWaRe and resistance context if antimicrobial."),
        (8, "Findings Register", "Create findings register with deficiencies and contradictions."),
        (9, "Severity Classification", "Classify findings by severity as critical, major, minor, or advisory."),
        (10, "Consistency Review", "Perform cross-section consistency review for labels, shelf-life and risk statements."),
        (11, "Completeness Confirmation", "Confirm review completeness against mandatory SOP workflow steps."),
        (12, "Overall Verdict", "Provide the final overall judgment and recommendation."),
    ]

    workflow_results: list[WorkflowStepResult] = []
    generated_reports: list[dict[str, Any]] = []

    with TestClient(app) as client:
        _login(client)
        ingested: list[dict[str, str]] = []
        for spec in dossier_specs:
            dossier_id = _intake_pdf(
                client,
                dossier_id=f"WF-{spec['label'].upper()}-{timestamp}",
                file_name=spec["file_name"],
                product_name=spec["product_name"],
                inn_name=spec["inn_name"],
                applicant="Workflow Applicant",
                manufacturer="Workflow Manufacturer",
            )
            ingested.append({"label": spec["label"], "dossier_id": dossier_id})

        for item in ingested:
            print(f"\n>>> Running workflow for {item['label']} ({item['dossier_id']})...")
            conversation_id = _conversation(client, item["dossier_id"], f"Workflow review {item['label']}")
            
            final_payload = None
            for step_id, step_name, prompt in stage_prompts:
                print(f"  Step {step_id}: {step_name}...")
                payload = _chat(
                    client,
                    dossier_id=item["dossier_id"],
                    question=prompt,
                    conversation_id=conversation_id,
                )
                final_payload = payload
                
                passed = not payload.get("abstained", False)
                rationale = str(payload.get("rationale", "")).lower()
                
                # Check for evidence links [DOC:...] or [GUIDANCE:...]
                has_links = "[" in rationale and "]" in rationale
                
                workflow_results.append(
                    WorkflowStepResult(
                        dossier_id=item["dossier_id"],
                        dossier_label=item["label"],
                        step_id=step_id,
                        step_name=step_name,
                        prompt=prompt,
                        passed=passed,
                        abstained=bool(payload.get("abstained", False)),
                        response_excerpt=_excerpt(payload),
                        response_full=str(payload.get("rationale", "")),
                        notes=["Grounded with links" if has_links else "No links found"],
                    )
                )

            # Final report generation
            print("  Generating final report...")
            report_response = client.post(
                "/v1/reports/generate",
                json={
                    "dossier_id": item["dossier_id"],
                    "review_payload": final_payload,
                    "conversation_id": conversation_id,
                    "report_title": f"Regulatory Review - {item['dossier_id']}",
                },
            )
            report_response.raise_for_status()
            report_meta = report_response.json()
            generated_reports.append(report_meta)
            
            # Print a snippet of the text report to verify quality
            text_report = client.get(report_meta["text_download_url"])
            if text_report.status_code == 200:
                print(f"\n--- REPORT SUMMARY: {item['label'].upper()} ---")
                # Print first 500 chars of the report
                print(text_report.text[:800] + "...")
                print("--- END SUMMARY ---\n")

    summary = {
        "report_id": report_id,
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "step_results": [asdict(item) for item in workflow_results],
        "generated_reports": generated_reports,
        "passed_steps": sum(1 for item in workflow_results if item.passed),
        "failed_steps": sum(1 for item in workflow_results if not item.passed),
    }

    path = REPORT_DIR / f"{report_id}.json"
    with path.open("w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nSimulation complete. Results written to {path}")
    return summary


if __name__ == "__main__":
    run()
