from __future__ import annotations

import json
import hashlib
import secrets
from html import escape
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from contextvars import ContextVar

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .audit import append_audit_record
from .config import Settings, load_settings
from .conversation import ConversationStore, build_context_monitor, build_model_context
from .data import (
    build_evidence_chunks,
    build_knowledge_wiki_chunks,
    chunking_profiles_catalog,
    load_dossiers,
    load_knowledge_wiki,
    load_uploaded_dossiers,
)
from .governance import build_lineage_tags
from .inference import build_model_client
from .intake import build_dossier_from_raw_text, parse_uploaded_document
from .knowledge_graph import KnowledgeGraph
from .orchestrator import ReasoningEngine, build_section_diagnostics, run_review_orchestration
from .policy import evaluate_amr_stewardship
from .reporting import build_review_report
from .regulatory_mcp_client import RegulatoryMCPClientError, tool_data
from .retrieval import HybridRetriever, Retriever, decompose_query, merge_hits
from .router import (
    CHAT_ONLY_INTENT,
    HISTORICAL_TREND,
    MIXED_INTENT,
    POLICY_GUIDANCE,
    VISUALIZATION_INTENT,
    WIKI_GUIDANCE_INTENT,
    assemble_model_packet,
    build_query_rewrite_plan,
    classify_intent,
    plan_context_scope,
)
from .schemas import (
    AdminUserCreateRequest,
    AdminUserItem,
    AdminUserUpdateRequest,
    AdminUsersResponse,
    AdminDashboardSummaryResponse,
    AdminProgressByReviewerItem,
    AmrStewardshipSummary,
    BenchmarkMetricItem,
    BenchmarkPanelResponse,
    AssistantMessageRequest,
    AssistantMessageResponse,
    Citation,
    ChunkingProfileSummary,
    ContextWindowMonitor,
    ConversationContextUpdateRequest,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessage,
    ConversationSummary,
    ConversationSummarySnapshot,
    DossierListItem,
    DossierListResponse,
    DossierAssignmentRequest,
    DossierAssignmentResponse,
    DossierUploadResponse,
    DossierResponse,
    HealthResponse,
    KnowledgeGraphResponse,
    KnowledgeWikiListResponse,
    KnowledgeWikiPageSummary,
    KnowledgeWikiSearchRequest,
    KnowledgeWikiSearchResponse,
    InteractionMetricsPayload,
    MemorySummary,
    ModelCatalogResponse,
    ModelOption,
    AuthLoginRequest,
    AuthLoginResponse,
    UserProfile,
    ReportRepositoryItem,
    ReportRepositoryResponse,
    ReportRejectionRequest,
    ReviewerPerformanceItem,
    ReviewerPerformanceResponse,
    ReviewerDashboardResponse,
    ReviewRequest,
    ReviewReportRequest,
    ReviewReportResponse,
    ReviewResponse,
    SampleDossierItem,
    SampleDossierListResponse,
    SampleIncomingFileItem,
    SampleIncomingFileListResponse,
    SectionDiagnostic,
    TelemetryPanelMetric,
    TelemetryPanelResponse,
    WorkflowStepState,
    WorkflowStateResponse,
    VerifierSummary,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)


def _derive_application_type(dossier: dict[str, Any]) -> str:
    text_parts = [
        str(dossier.get("dossier_id", "")),
        str(dossier.get("quality_summary", "")),
        str(dossier.get("clinical_details", "")),
    ]
    for section in dossier.get("sections", []):
        text_parts.append(str(section.get("title", "")))
        text_parts.append(str(section.get("text", ""))[:400])
    lowered = " ".join(text_parts).lower()
    if any(term in lowered for term in ("renewal", "renew", "re-registration", "re registration")):
        return "renewal"
    return "new_application"


def _derive_product_group(dossier: dict[str, Any]) -> str:
    amr = evaluate_amr_stewardship(dossier)
    if amr.get("applies"):
        return "antimicrobial"
    atc_code = str(dossier.get("product", {}).get("atc_code", ""))
    if atc_code.startswith("J"):
        return "systemic_anti_infective"
    return "other_product"


def _derive_review_pathway(dossier: dict[str, Any]) -> str:
    decision = str(dossier.get("labels", {}).get("holistic_policy_decision", "standard_review"))
    return decision


def _derive_document_condition(dossier: dict[str, Any]) -> str:
    defects = {str(item) for item in dossier.get("provenance", {}).get("defect_modes", [])}
    if not defects:
        return "well-structured dossier"
    if "ocr_required" in defects or "image_heavy_pdf" in defects:
        return "scanned and image-heavy dossier"
    if "expired_gmp_certificate" in defects or "missing_clinical_package" in defects:
        return "material evidence deficiency"
    return "mixed-quality dossier"


def _sample_expected_outcome(dossier: dict[str, Any]) -> str:
    return str(dossier.get("labels", {}).get("holistic_policy_decision", "standard_review")).replace("_", " ")


def _review_chart_identity_tag(dossier: dict[str, Any] | None) -> str | None:
    if not dossier:
        return None
    manufacturer = str(dossier.get("organization", {}).get("manufacturer", "")).strip()
    drug_name = str(dossier.get("product", {}).get("product_name", "")).strip()
    parts = [part for part in (manufacturer, drug_name) if part]
    if not parts:
        return None
    return " | ".join(parts)


def _enforce_chart_title_identity(
    viz_payload: dict[str, Any] | None,
    *,
    dossier: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(viz_payload, dict):
        return viz_payload
    chart_type = str(viz_payload.get("type", "")).lower()
    if chart_type == "network":
        return viz_payload
    identity = _review_chart_identity_tag(dossier)
    if not identity:
        return viz_payload
    current_title = str(viz_payload.get("title", "")).strip()
    if identity.lower() in current_title.lower():
        return viz_payload
    next_payload = dict(viz_payload)
    if current_title:
        next_payload["title"] = f"{identity} - {current_title}"
    else:
        next_payload["title"] = identity
    return next_payload


def _report_repository_item(report_id: str, snapshot: dict[str, Any]) -> ReportRepositoryItem:
    payload = snapshot.get("report_payload", {})
    workflow = payload.get("workflow_report", {})
    submission = workflow.get("submission_summary", {})
    amr_review = workflow.get("amr_stewardship_review", {})
    overall = workflow.get("overall_judgment", {})
    product_group = str(snapshot.get("product_group") or ("antimicrobial" if amr_review.get("applicable") else "other_product"))
    application_type = str(snapshot.get("application_type") or "new_application")
    return ReportRepositoryItem(
        report_id=report_id,
        dossier_id=str(snapshot.get("dossier_id", "")),
        report_title=str(snapshot.get("report_title", "")),
        generated_at_utc=str(snapshot.get("generated_at_utc", "")),
        product_name=str(snapshot.get("product_name") or submission.get("product_name", "")),
        inn_name=str(snapshot.get("inn_name") or submission.get("active_ingredient", "")),
        product_group=product_group,
        application_type=application_type,
        antimicrobial=bool(snapshot.get("antimicrobial", amr_review.get("applicable", False))),
        aware_category=str(snapshot.get("aware_category") or amr_review.get("aware_category", "not_applicable")),
        final_verdict=str(snapshot.get("final_verdict") or overall.get("final_verdict", "unknown")),
        reviewer_username=snapshot.get("reviewer_username"),
        report_lifecycle_status=str(snapshot.get("report_lifecycle_status", "completed")),
        html_download_url=f"/v1/reports/{report_id}/html",
        pdf_download_url=f"/v1/reports/{report_id}/pdf",
        text_download_url=f"/v1/reports/{report_id}/text",
        word_download_url=f"/v1/reports/{report_id}/word",
        json_download_url=f"/v1/reports/{report_id}/json",
        judge_pack_html_download_url=f"/v1/reports/{report_id}/judge_pack_html",
        judge_pack_pdf_download_url=f"/v1/reports/{report_id}/judge_pack_pdf",
    )


def _build_judge_pack_html(*, report_title: str, dossier_id: str, report_payload: dict[str, Any], decision_log: list[dict[str, Any]], query_letter_html: str) -> str:
    workflow = report_payload.get("workflow_report", {}) if isinstance(report_payload, dict) else {}
    overall = workflow.get("overall_judgment", {}) if isinstance(workflow, dict) else {}
    amr = workflow.get("amr_stewardship_review", {}) if isinstance(workflow, dict) else {}
    findings = workflow.get("findings_register", []) if isinstance(workflow, dict) else []
    critical = [f for f in findings if str(f.get("severity", "")).lower() in {"critical", "major"}][:8]
    critical_rows = "".join(
        f"<li><strong>{escape(str(item.get('severity', 'major')).upper())}</strong>: {escape(str(item.get('issue', 'Issue not stated')))} "
        f"<span style='color:#64748b'>(Rule: {escape(str(item.get('violated_rule', 'n/a')))} | Evidence: {escape(str(item.get('evidence_reference', 'n/a')))} )</span></li>"
        for item in critical
    ) or "<li>No critical findings were listed in this run.</li>"
    issue_cards = "".join(
        "<article style='border:1px solid #e2e8f0;border-radius:10px;padding:10px;background:#fff'>"
        f"<div style='font-weight:700'>{escape(str(item.get('issue', 'Issue')))}</div>"
        f"<div style='font-size:12px;color:#334155;margin-top:4px'>SOP rule: {escape(str(item.get('violated_rule', 'n/a')))}</div>"
        f"<div style='font-size:12px;color:#334155'>Evidence: {escape(str(item.get('location', 'n/a')))} | Ref {escape(str(item.get('evidence_reference', 'n/a')))}</div>"
        f"<div style='font-size:12px;color:#334155'>Decision: {escape(str(item.get('recommendation', 'Query applicant for clarification.')))}</div>"
        "</article>"
        for item in findings[:12]
    ) or "<div>No issue cards available for this review.</div>"
    log_rows = "".join(
        f"<tr><td>{escape(str(item.get('rule_evaluated', '')))}</td><td>{escape(str(item.get('tool_called', '')))}</td><td>{escape(str(item.get('evidence_retrieved', '')))}</td><td>{escape(str(item.get('rule_result', '')))}</td></tr>"
        for item in decision_log
    ) or "<tr><td colspan='4'>No decision log entries</td></tr>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Judge Pack - {escape(dossier_id)}</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:24px}} .card{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:14px;margin-bottom:14px}} table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #e2e8f0;padding:8px;text-align:left;font-size:12px}}th{{background:#eff6ff}} h1{{margin:0 0 8px 0}} ul{{margin:0;padding-left:18px}}</style></head>
<body><div class='card'><h1>National Food and Drug Regulation Agency - Judge Mode Pack</h1><div>{escape(report_title)}</div><div style='font-size:12px;color:#475569'>Dossier: {escape(dossier_id)}</div></div>
<div class='card'><h2>Risk Recap</h2><div>Overall verdict: <strong>{escape(str(overall.get('final_verdict', 'unknown')))}</strong></div><div>AMR class: <strong>{escape(str(amr.get('aware_category', 'not_applicable')))}</strong></div><div>Authorization control: <strong>{escape(str(amr.get('authorization_control', 'standard_authorization')))}</strong></div><ul>{critical_rows}</ul></div>
<div class='card'><h2>Evidence-Grounded Issue Cards</h2><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px'>{issue_cards}</div></div>
<div class='card'><h2>Applicant Query Letter</h2>{query_letter_html}</div>
<div class='card'><h2>Audit Decision Log</h2><table><thead><tr><th>Rule evaluated</th><th>Tool called</th><th>Evidence</th><th>Result</th></tr></thead><tbody>{log_rows}</tbody></table></div>
</body></html>"""
from .telemetry import InteractionMetrics, memory_snapshot

current_user_ctx: ContextVar[dict[str, Any] | None] = ContextVar("current_user_ctx", default=None)
REVIEW_PROGRAMS = {"marketing_authorization", "clinical_trial"}


def _normalize_process_scopes(scopes: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for scope in scopes or []:
        value = str(scope).strip().lower()
        if value in REVIEW_PROGRAMS and value not in normalized:
            normalized.append(value)
    return normalized or ["marketing_authorization"]


def _json_path_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _hash_password(username: str, password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), username.encode("utf-8"), 120000).hex()


def _load_auth_state(settings: Settings) -> dict[str, Any]:
    path = settings.auth_state_path
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    users = payload.get("users", {})
    seed_users = {
        "dachan": {
            "username": "dachan",
            "display_name": "Dachan Manager",
            "role": "superuser",
            "process_scopes": ["marketing_authorization", "clinical_trial"],
            "password_hash": _hash_password("dachan", "123456"),
            "active": True,
            "created_at_utc": datetime.now(UTC).isoformat(),
        },
        "alutakome": {
            "username": "alutakome",
            "display_name": "Alutakome MA",
            "role": "superuser",
            "process_scopes": ["marketing_authorization"],
            "password_hash": _hash_password("alutakome", "dpar@2026#"),
            "active": True,
            "created_at_utc": datetime.now(UTC).isoformat(),
        },
        "namayanja": {
            "username": "namayanja",
            "display_name": "Namayanja Reviewer",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization"],
            "password_hash": _hash_password("namayanja", "Nama@2026#"),
            "active": True,
            "created_at_utc": datetime.now(UTC).isoformat(),
        },
        "kaggwa": {
            "username": "kaggwa",
            "display_name": "Kaggwa Reviewer",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization"],
            "password_hash": _hash_password("kaggwa", "Kaggwa@2026#"),
            "active": True,
            "created_at_utc": datetime.now(UTC).isoformat(),
        },
        "alutakome_ct": {
            "username": "alutakome_ct",
            "display_name": "Alutakome CT",
            "role": "superuser",
            "process_scopes": ["clinical_trial"],
            "password_hash": _hash_password("alutakome_ct", "dpar@2026#"),
            "active": True,
            "created_at_utc": datetime.now(UTC).isoformat(),
        },
    }
    for process_prefix, process_scope in (("ma", "marketing_authorization"), ("ct", "clinical_trial")):
        for index in range(1, 4):
            username = f"{process_prefix}_reviewer_{index}"
            seed_users[username] = {
                "username": username,
                "display_name": f"{'Marketing Authorization' if process_scope == 'marketing_authorization' else 'Clinical Trial'} Reviewer {index}",
                "role": "reviewer",
                "process_scopes": [process_scope],
                "password_hash": _hash_password(username, "dpar@2026#"),
                "active": True,
                "created_at_utc": datetime.now(UTC).isoformat(),
            }
    for username, seed in seed_users.items():
        existing = users.get(username)
        if existing is None:
            users[username] = seed
            continue
        existing["display_name"] = str(existing.get("display_name") or seed["display_name"])
        existing["role"] = str(existing.get("role") or seed["role"])
        existing["process_scopes"] = _normalize_process_scopes(existing.get("process_scopes") or seed["process_scopes"])
        existing["active"] = bool(existing.get("active", True))
        existing["created_at_utc"] = str(existing.get("created_at_utc") or seed["created_at_utc"])
        existing["password_hash"] = str(existing.get("password_hash") or seed["password_hash"])
    auth_state = {"users": users, "sessions": payload.get("sessions", {})}
    _json_path_write(path, auth_state)
    return auth_state


def _load_governance_state(settings: Settings, dossiers: list[dict[str, Any]]) -> dict[str, Any]:
    path = settings.governance_state_path
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    dossier_lifecycle = payload.get("dossier_lifecycle", {})
    for dossier in dossiers:
        dossier_id = str(dossier.get("dossier_id", ""))
        record = dossier_lifecycle.setdefault(
            dossier_id,
            {
                "dossier_id": dossier_id,
                "status": "open",
                "assigned_reviewer": None,
                "final_decision": None,
                "decision_date": None,
                "report_id": None,
                "review_type": "generic",
                "review_program": _infer_review_program(dossier),
                "latest_review_observation": {},
                "history": [],
            },
        )
        record["review_program"] = str(record.get("review_program") or _infer_review_program(dossier))
    governance_state = {
        "conversation_owners": payload.get("conversation_owners", {}),
        "dossier_lifecycle": dossier_lifecycle,
    }
    _json_path_write(path, governance_state)
    return governance_state


def _save_auth_state() -> None:
    _json_path_write(state["settings"].auth_state_path, state["auth_state"])


def _save_governance_state() -> None:
    serializable = {
        "conversation_owners": state["governance_state"]["conversation_owners"],
        "dossier_lifecycle": state["governance_state"]["dossier_lifecycle"],
    }
    _json_path_write(state["settings"].governance_state_path, serializable)


def _current_user(required: bool = True) -> dict[str, Any] | None:
    user = current_user_ctx.get()
    if required and user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _is_superuser(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("role") == "superuser")


def _user_process_scopes(user: dict[str, Any] | None) -> set[str]:
    return set(_normalize_process_scopes((user or {}).get("process_scopes")))


def _infer_review_program(dossier: dict[str, Any]) -> str:
    explicit = str(dossier.get("review_program") or dossier.get("labels", {}).get("review_program") or "").strip().lower()
    if explicit in REVIEW_PROGRAMS:
        return explicit
    text_parts = [
        str(dossier.get("dossier_id", "")),
        str(dossier.get("quality_summary", "")),
        str(dossier.get("clinical_details", "")),
    ]
    for section in dossier.get("sections", []):
        text_parts.append(str(section.get("title", "")))
        text_parts.append(str(section.get("text", ""))[:500])
    lowered = " ".join(text_parts).lower()
    ct_markers = (
        "clinical trial protocol",
        "study protocol",
        "investigator brochure",
        "protocol synopsis",
        "ethics committee approval",
        "informed consent form",
    )
    if any(term in lowered for term in ct_markers):
        return "clinical_trial"
    return "marketing_authorization"


def _require_process_access(user: dict[str, Any], review_program: str) -> None:
    if review_program not in _user_process_scopes(user):
        raise HTTPException(status_code=403, detail=f"You do not have access to the {review_program.replace('_', ' ')} review program.")


def _admin_visible_users(user: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = _user_process_scopes(user)
    visible: list[dict[str, Any]] = []
    for candidate in state["auth_state"]["users"].values():
        candidate_scopes = set(_normalize_process_scopes(candidate.get("process_scopes")))
        if candidate_scopes & scopes:
            visible.append(candidate)
    visible.sort(key=lambda item: (item.get("role") != "superuser", item.get("username", "")))
    return visible


def _user_profile(user: dict[str, Any]) -> UserProfile:
    return UserProfile(
        username=str(user["username"]),
        role=str(user["role"]),
        display_name=str(user.get("display_name", user["username"])),
        process_scopes=_normalize_process_scopes(user.get("process_scopes")),
        active=bool(user.get("active", True)),
    )


def _resolve_session_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    session = state["auth_state"]["sessions"].get(token)
    if not session:
        return None
    username = session.get("username")
    user = state["auth_state"]["users"].get(username)
    if not user:
        return None
    if not bool(user.get("active", True)):
        return None
    return user


def _admin_user_item_payload(user: dict[str, Any]) -> AdminUserItem:
    return AdminUserItem(
        username=str(user["username"]),
        display_name=str(user.get("display_name", user["username"])),
        role=str(user.get("role", "reviewer")),
        process_scopes=_normalize_process_scopes(user.get("process_scopes")),
        active=bool(user.get("active", True)),
        created_at_utc=str(user.get("created_at_utc", "")) or None,
    )


def _require_conversation_access(conversation_id: str, user: dict[str, Any]) -> None:
    owner = state["governance_state"]["conversation_owners"].get(conversation_id)
    if owner and owner != user["username"] and not _is_superuser(user):
        raise HTTPException(status_code=403, detail="This conversation belongs to another reviewer.")
    if owner or _is_superuser(user):
        return
    raise HTTPException(status_code=403, detail="This conversation has no owner and is restricted for privacy.")


def _register_conversation_owner(conversation_id: str, username: str) -> None:
    state["governance_state"]["conversation_owners"][conversation_id] = username
    _save_governance_state()


def _lifecycle_record(dossier_id: str) -> dict[str, Any]:
    dossier = state["dossier_by_id"].get(dossier_id, {})
    return state["governance_state"]["dossier_lifecycle"].setdefault(
        dossier_id,
        {
            "dossier_id": dossier_id,
            "status": "open",
            "assigned_reviewer": None,
            "final_decision": None,
            "decision_date": None,
            "report_id": None,
            "review_type": "generic",
            "review_program": _infer_review_program(dossier) if dossier else "marketing_authorization",
            "latest_review_observation": {},
            "history": [],
        },
    )


def _append_lifecycle_event(dossier_id: str, event: str, *, username: str | None = None, details: dict[str, Any] | None = None) -> None:
    record = _lifecycle_record(dossier_id)
    record.setdefault("history", []).append(
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "event": event,
            "username": username,
            "details": details or {},
        }
    )
    _save_governance_state()


def _record_review_observation(
    *,
    dossier_id: str,
    recommendation: str,
    confidence: float,
    policy_rule_hits: list[str],
    section_diagnostics: list[dict[str, Any]],
    reviewer_username: str,
) -> None:
    record = _lifecycle_record(dossier_id)
    issue_tags: list[str] = []
    for diag in section_diagnostics:
        correctness = str(diag.get("correctness", "")).lower()
        presence = str(diag.get("presence", "")).lower()
        if correctness == "incorrect" or presence == "missing":
            title = str(diag.get("title") or diag.get("section_id") or "unspecified_section").strip()
            if title and title not in issue_tags:
                issue_tags.append(title)
    for hit in policy_rule_hits:
        label = str(hit).strip()
        if label and label not in issue_tags:
            issue_tags.append(label)
    record["latest_review_observation"] = {
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "reviewer_username": reviewer_username,
        "recommendation": recommendation,
        "confidence": round(float(confidence or 0.0), 5),
        "issue_tags": issue_tags[:24],
        "policy_rule_hits": list(policy_rule_hits)[:32],
    }
    _save_governance_state()


def _mark_dossier_in_review(dossier_id: str, user: dict[str, Any], review_type: str) -> None:
    record = _lifecycle_record(dossier_id)
    _require_process_access(user, str(record.get("review_program", "marketing_authorization")))
    if not _is_superuser(user) and record.get("assigned_reviewer") != user["username"]:
        raise HTTPException(status_code=403, detail="This dossier is not assigned to you. Ask the manager to assign it first.")
    if record.get("status") == "done" and record.get("assigned_reviewer") != user["username"] and not _is_superuser(user):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Dossier already reviewed by user {record.get('assigned_reviewer')} with decision "
                f"{record.get('final_decision')} on {record.get('decision_date')}."
            ),
        )
    if record.get("status") in {"in_review", "done"} and record.get("assigned_reviewer") not in {None, user["username"]} and not _is_superuser(user):
        raise HTTPException(status_code=409, detail=f"Dossier is currently assigned to reviewer {record.get('assigned_reviewer')}.")
    if _is_superuser(user) and record.get("assigned_reviewer") is None:
        record["assigned_reviewer"] = user["username"]
    record["status"] = "in_review" if record.get("status") != "done" else record.get("status")
    record["review_type"] = review_type
    record["review_program"] = str(record.get("review_program", "marketing_authorization"))
    _append_lifecycle_event(dossier_id, "review_started", username=user["username"], details={"review_type": review_type})


SOP_WORKFLOW_STEP_LABELS: dict[str, str] = {
    "data_quality_and_vision_extraction_check": "Data quality and vision extraction check",
    "submission_intake_and_familiarization": "Submission intake and familiarization",
    "administrative_completeness_review": "Administrative completeness review",
    "structural_dossier_mapping": "Structural dossier mapping",
    "applicable_rules_identification": "Applicable rules and requirements identification",
    "who_inn_similarity_review": "WHO INN similarity review",
    "section_by_section_technical_review": "Section-by-section technical review",
    "amr_stewardship_review": "AMR stewardship review using AWaRe rules",
    "findings_register": "Identification and recording of findings",
    "severity_classification": "Severity classification",
    "cross_section_consistency_review": "Cross-section consistency review",
    "review_completeness_confirmation": "Review completeness confirmation",
    "overall_judgment": "Overall judgment",
}

SOP_STEP_PROMPT_TEMPLATES: dict[str, str] = {
    "data_quality_and_vision_extraction_check": "Run data quality and vision extraction check for this dossier and summarize scan/OCR risks.",
    "submission_intake_and_familiarization": "Run submission intake and familiarization for this dossier.",
    "administrative_completeness_review": "Run administrative completeness review and identify missing mandatory administrative evidence.",
    "structural_dossier_mapping": "Run structural dossier mapping and confirm required sections/modules are present.",
    "applicable_rules_identification": "Identify applicable SOP rules and requirements for this dossier.",
    "who_inn_similarity_review": "Run WHO INN similarity review and report naming risk status.",
    "section_by_section_technical_review": "Run section-by-section technical review across quality, clinical, and stability evidence.",
    "amr_stewardship_review": "Run AMR stewardship review using AWaRe rules and required controls.",
    "findings_register": "Identify and record findings with evidence references.",
    "severity_classification": "Classify findings by severity and justify each severity level.",
    "cross_section_consistency_review": "Run cross-section consistency review and flag contradictions.",
    "review_completeness_confirmation": "Confirm review completeness against mandatory SOP steps.",
    "overall_judgment": "Provide overall judgment and final regulatory recommendation with evidence-grounded rationale.",
}


def _new_workflow_progress(dossier_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    return {
        "dossier_id": dossier_id,
        "conversation_id": conversation_id,
        "completed_steps": set(),
        "step_sources": {},
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }


def _required_workflow_steps_for_dossier(dossier: dict[str, Any]) -> list[str]:
    amr_applies = bool(evaluate_amr_stewardship(dossier).get("applies"))
    steps = list(SOP_WORKFLOW_STEP_LABELS.keys())
    if not amr_applies:
        steps.remove("amr_stewardship_review")
    return steps


def _pretty_workflow_step(step: str) -> str:
    return SOP_WORKFLOW_STEP_LABELS.get(step, step.replace("_", " ").title())


def _workflow_state_payload(*, dossier: dict[str, Any], conversation_id: str | None) -> WorkflowStateResponse:
    dossier_id = str(dossier.get("dossier_id", ""))
    required_steps = _required_workflow_steps_for_dossier(dossier)
    progress = _get_workflow_progress(dossier_id=dossier_id, conversation_id=conversation_id)
    completed = set(progress.get("completed_steps", set()))
    current_step_id: str | None = None
    steps: list[WorkflowStepState] = []
    for idx, step in enumerate(required_steps, start=1):
        status = "completed" if step in completed else "pending"
        if current_step_id is None and status == "pending":
            current_step_id = step
            status = "current"
        steps.append(
            WorkflowStepState(
                step_id=step,
                step_label=_pretty_workflow_step(step),
                ordinal=idx,
                status=status,
                prompt_template=SOP_STEP_PROMPT_TEMPLATES.get(step, ""),
            )
        )
    return WorkflowStateResponse(
        dossier_id=dossier_id,
        conversation_id=conversation_id,
        review_program=_infer_review_program(dossier),
        current_step_id=current_step_id,
        all_completed=current_step_id is None,
        steps=steps,
    )


def _questions_indicate_full_review(question: str) -> bool:
    lowered = question.lower()
    triggers = (
        "review this dossier",
        "full review",
        "complete review",
        "structured review",
        "review the dossier",
        "review this submission",
        "generate recommendation",
        "give a recommendation",
        "final recommendation",
        "overall judgment",
        "final verdict",
        "final decision",
    )
    return any(trigger in lowered for trigger in triggers)


def _infer_completed_workflow_steps(
    *,
    question: str,
    dossier: dict[str, Any],
    review_payload: dict[str, Any] | None = None,
) -> set[str]:
    lowered = question.lower()
    completed: set[str] = set()
    strict_step = _infer_strict_sop_step(question)
    if strict_step:
        # Strict guided mode: only mark the explicitly requested SOP stage.
        return {strict_step}

    if any(term in lowered for term in ("data quality", "scanned", "ocr", "vision extraction", "image quality", "document quality")):
        completed.add("data_quality_and_vision_extraction_check")
    if any(term in lowered for term in ("submission type", "product", "active ingredient", "applicant", "review pathway", "what type of submission")):
        completed.add("submission_intake_and_familiarization")
    if any(term in lowered for term in ("administrative", "application form", "cover letter", "payment", "signature", "signed", "attachments included")):
        completed.add("administrative_completeness_review")
    if any(term in lowered for term in ("section", "module", "structure", "annex", "readable", "mapping", "where are", "what sections are present")):
        completed.add("structural_dossier_mapping")
    if any(term in lowered for term in ("rule", "rules", "requirements", "checklist", "guidance applies", "what applies", "mandatory sections")):
        completed.add("applicable_rules_identification")
    if any(term in lowered for term in ("inn similarity", "who inn", "product name", "naming", "confusion risk", "similarity index")):
        completed.add("who_inn_similarity_review")
    if any(term in lowered for term in ("stability", "gmp", "clinical", "technical review", "missing evidence", "quality", "adequate", "supporting evidence")):
        completed.add("section_by_section_technical_review")
    if any(term in lowered for term in ("amr", "aware", "glass", "stewardship", "antimicrobial", "access", "watch", "reserve", "restricted authorization", "fast-track")):
        completed.add("amr_stewardship_review")
    if any(term in lowered for term in ("finding", "findings", "issue", "issues", "deficiency", "deficiencies", "contradiction", "violat")):
        completed.add("findings_register")
    if any(term in lowered for term in ("severity", "critical", "major", "minor", "advisory", "block acceptance")):
        completed.add("severity_classification")
    if any(term in lowered for term in ("consistency", "cross-section", "cross section", "inconsistent", "align", "matches across", "shelf-life claims supported")):
        completed.add("cross_section_consistency_review")
    if any(term in lowered for term in ("workflow complete", "workflow completeness", "mandatory workflow", "all workflow steps", "review complete", "review incomplete")):
        completed.add("review_completeness_confirmation")
    if any(term in lowered for term in ("overall judgment", "acceptable", "requires revision", "not acceptable", "escalate", "final verdict")):
        completed.add("overall_judgment")

    if review_payload:
        workflow_summary = review_payload.get("workflow_summary", {}) if isinstance(review_payload, dict) else {}
        if isinstance(workflow_summary, dict):
            dq = workflow_summary.get("data_quality_and_vision_extraction_check", {}) or {}
            if str(dq.get("status", "")).lower() == "completed":
                completed.add("data_quality_and_vision_extraction_check")
            if workflow_summary.get("submission_summary"):
                completed.add("submission_intake_and_familiarization")
            if workflow_summary.get("administrative_review"):
                completed.add("administrative_completeness_review")
            if workflow_summary.get("dossier_structure_review"):
                completed.add("structural_dossier_mapping")
            if workflow_summary.get("applicable_rules_identification"):
                completed.add("applicable_rules_identification")
            inn_review = workflow_summary.get("who_inn_similarity_review", {}) or {}
            if inn_review and str(inn_review.get("threshold_result", "")).lower() not in {"", "not_available"}:
                completed.add("who_inn_similarity_review")
            tech = workflow_summary.get("technical_section_review", {}) or {}
            if tech.get("section_results"):
                completed.add("section_by_section_technical_review")
            amr = workflow_summary.get("amr_stewardship_review", {}) or {}
            if amr and bool(amr.get("applicable")):
                completed.add("amr_stewardship_review")
            if workflow_summary.get("findings_register") is not None:
                completed.add("findings_register")
            if workflow_summary.get("severity_classification"):
                completed.add("severity_classification")
            if workflow_summary.get("cross_section_consistency_review"):
                completed.add("cross_section_consistency_review")
            completeness = workflow_summary.get("review_completeness_confirmation", {}) or {}
            if completeness and str(completeness.get("status", "")).lower() in {"review_complete", "review_incomplete"}:
                completed.add("review_completeness_confirmation")
            if workflow_summary.get("overall_judgment"):
                completed.add("overall_judgment")

    # SOP progression is intentionally driven by explicit reviewer-requested
    # stage interactions to enforce ordered review behavior.
    return completed


def _infer_requested_workflow_step(question: str) -> str | None:
    strict = _infer_strict_sop_step(question)
    if strict:
        return strict
    lowered = question.lower()
    step_keywords: list[tuple[str, tuple[str, ...]]] = [
        ("data_quality_and_vision_extraction_check", ("data quality", "scanned", "ocr", "vision extraction", "image quality", "document quality")),
        ("submission_intake_and_familiarization", ("submission type", "product profile", "applicant", "familiarization", "intake")),
        ("administrative_completeness_review", ("administrative", "application form", "cover letter", "payment", "signature", "attachments")),
        ("structural_dossier_mapping", ("structural mapping", "dossier structure", "module mapping", "section mapping", "what sections are present")),
        ("applicable_rules_identification", ("applicable rules", "requirements apply", "regulatory checklist", "what rules apply")),
        ("who_inn_similarity_review", ("inn", "naming", "who inn", "similarity index", "name similarity")),
        ("section_by_section_technical_review", ("technical review", "quality review", "gmp review", "clinical review", "stability review", "section-by-section")),
        ("amr_stewardship_review", ("amr", "aware", "stewardship", "reserve", "watch", "glass resistance")),
        ("findings_register", ("findings register", "record findings", "list findings", "issues register")),
        ("severity_classification", ("severity classification", "classify severity", "critical major minor", "severity table")),
        ("cross_section_consistency_review", ("cross-section consistency", "consistency check", "cross section consistency", "alignment across sections")),
        ("review_completeness_confirmation", ("review completeness", "workflow complete", "mandatory steps complete", "sop complete")),
        ("overall_judgment", ("overall judgment", "final verdict", "final recommendation", "final decision", "authorize or reject")),
    ]
    for step, keywords in step_keywords:
        if any(keyword in lowered for keyword in keywords):
            return step
    return None


def _infer_strict_sop_step(question: str) -> str | None:
    marker = "sop_step_id::"
    lowered = question.lower()
    idx = lowered.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    tail = lowered[start:].strip()
    if not tail:
        return None
    token = tail.split()[0].strip().strip("]})>,.;:")
    if token in SOP_WORKFLOW_STEP_LABELS:
        return token
    return None


def _get_workflow_progress(dossier_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    progress: dict[str, Any] | None = None
    if conversation_id:
        progress = state["workflow_progress"].get(f"{conversation_id}::{dossier_id}")
    if progress is None:
        progress = state["workflow_progress_by_dossier"].get(dossier_id)
    return progress or _new_workflow_progress(dossier_id=dossier_id, conversation_id=conversation_id)


def _workflow_sequence_gate(
    *,
    dossier: dict[str, Any],
    question: str,
    conversation_id: str | None,
) -> None:
    strict_step = _infer_strict_sop_step(question)
    if _is_sop_information_query(question):
        return
    if _questions_indicate_full_review(question):
        return
    requested_step = _infer_requested_workflow_step(question)
    if requested_step is None:
        return
    dossier_id = str(dossier.get("dossier_id", ""))
    required_steps = _required_workflow_steps_for_dossier(dossier)
    progress = _get_workflow_progress(dossier_id=dossier_id, conversation_id=conversation_id)
    completed_steps = set(progress.get("completed_steps", set()))

    next_required: str | None = None
    for step in required_steps:
        if step not in completed_steps:
            next_required = step
            break
    if next_required is None:
        return

    # First turn exception: always permit the reviewer to ask naturally.
    # Step 1 (data quality + vision extraction) is injected into the response
    # and recorded from workflow output.
    if (
        strict_step is None
        and
        not completed_steps
        and next_required == "data_quality_and_vision_extraction_check"
        and requested_step != next_required
    ):
        return

    if requested_step != next_required:
        requested_index = required_steps.index(requested_step) if requested_step in required_steps else -1
        next_index = required_steps.index(next_required)
        if requested_index > next_index:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "SOP sequence enforcement: this request jumps ahead of required review steps.",
                    "requested_step": requested_step,
                    "requested_step_label": _pretty_workflow_step(requested_step),
                    "next_required_step": next_required,
                    "next_required_step_label": _pretty_workflow_step(next_required),
                    "completed_steps": [step for step in required_steps if step in completed_steps],
                    "missing_steps": [step for step in required_steps if step not in completed_steps],
                },
            )


def _is_sop_information_query(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in (
            "show sop",
            "what is the sop",
            "sop steps",
            "workflow steps",
            "step by step review",
            "what step",
            "what next step",
            "sop status",
            "review sequence",
        )
    )


def _build_sop_status_markdown(*, dossier: dict[str, Any], conversation_id: str | None) -> str:
    dossier_id = str(dossier.get("dossier_id", ""))
    required_steps = _required_workflow_steps_for_dossier(dossier)
    progress = _get_workflow_progress(dossier_id=dossier_id, conversation_id=conversation_id)
    completed = set(progress.get("completed_steps", set()))
    lines = [
        "### SOP Progress (Pre-Market Authorization)",
        "",
        "| Step | Review Stage | Status |",
        "| --- | --- | --- |",
    ]
    for idx, step in enumerate(required_steps, start=1):
        status = "Completed" if step in completed else "Pending"
        lines.append(f"| {idx} | {_pretty_workflow_step(step)} | {status} |")
    lines.append("")
    lines.append("![SOP flow illustration](/sop-flow.svg)")
    return "\n".join(lines)


def _build_external_comparison_markdown(workflow_summary: dict[str, Any] | None) -> str:
    if not workflow_summary:
        return ""
    technical = workflow_summary.get("technical_section_review", {})
    review_specific = technical.get("review_type_specific", {})
    review_type = str(review_specific.get("review_type", "")).lower().strip()
    # External innovator/reference reconciliation table is required only for generic workflows.
    if review_type and review_type != "generic":
        return ""
    matrix = review_specific.get("comparison_matrix", []) or []
    section_provenance = review_specific.get("section_provenance", []) or []
    source_policy = review_specific.get("source_selection_policy", {}) or {}
    verified_urls = review_specific.get("verified_reference_urls", []) or []
    if not matrix:
        return ""
    lines = [
        "### External vs Submitted Evidence (Patient/Safety)",
        "",
        "| Dimension | Submitted Dossier | External Source | Gap |",
        "| --- | --- | --- | --- |",
    ]
    inconsistency_dimensions: list[str] = []
    clinical_keywords = ("indication", "contraindication", "warning", "dose", "dosage", "adverse", "reaction", "interaction")
    pv_keywords = ("pharmacovigilance", "recall", "complaint", "signal", "safety", "risk management", "post-market", "post market")
    clinical_rows: list[dict[str, Any]] = []
    pv_rows: list[dict[str, Any]] = []
    for row in matrix:
        dim = str(row.get("dimension", "Unknown"))
        dim_lower = dim.lower()
        submitted = str(row.get("submitted_evidence", "Not stated")).strip()
        external = str(row.get("external_evidence", "Not stated")).strip()
        gap = "Yes" if row.get("gap") else "No"
        if row.get("gap"):
            inconsistency_dimensions.append(dim)
        submitted = submitted.replace("|", "\\|")
        external = external.replace("|", "\\|")
        lines.append(f"| {dim} | {submitted} | {external} | {gap} |")
        if any(token in dim_lower for token in clinical_keywords):
            clinical_rows.append(row)
        if any(token in dim_lower for token in pv_keywords):
            pv_rows.append(row)
    lines.append("")
    submitted_present_count = sum(1 for row in matrix if row.get("submitted_present"))
    external_present_count = sum(1 for row in matrix if row.get("external_present"))
    lines.append(
        f"Summary: submitted dossier provides **{submitted_present_count}/{len(matrix)}** patient-safety dimensions; external baseline provides **{external_present_count}/{len(matrix)}**."
    )
    if inconsistency_dimensions:
        lines.append(
            f"Inconsistencies detected in: **{', '.join(inconsistency_dimensions)}**. These require applicant clarification or correction."
        )
    else:
        lines.append("No patient-safety inconsistencies were detected between submitted and external evidence for the tracked dimensions.")
    if verified_urls:
        lines.append("")
        lines.append("Verified external references:")
        for url in verified_urls:
            safe_url = str(url).strip()
            lines.append(f"- [{safe_url}]({safe_url})")
    if source_policy:
        lines.append("")
        lines.append("Source selection policy:")
        lines.append(f"- Strategy: {source_policy.get('strategy', 'unknown')}")
        order = source_policy.get("order", [])
        if order:
            lines.append(f"- Priority order: {', '.join(str(item) for item in order)}")
    def _append_focused_table(title: str, focused_rows: list[dict[str, Any]]) -> None:
        if not focused_rows:
            return
        lines.append("")
        lines.append(f"#### {title}")
        lines.append("")
        lines.append("| Dimension | Submitted | External | Reconciliation |")
        lines.append("| --- | --- | --- | --- |")
        for row in focused_rows:
            submitted = str(row.get("submitted_evidence", "Not stated")).strip().replace("|", "\\|")
            external = str(row.get("external_evidence", "Not stated")).strip().replace("|", "\\|")
            recon = "Mismatch - query applicant" if row.get("gap") else "Aligned"
            lines.append(f"| {row.get('dimension', 'Unknown')} | {submitted} | {external} | {recon} |")
    _append_focused_table("Clinical Evidence Reconciliation (Submitted vs External)", clinical_rows)
    _append_focused_table("Pharmacovigilance Evidence Reconciliation (Submitted vs External)", pv_rows)
    if section_provenance:
        lines.append("")
        lines.append("#### External Source Provenance and Confidence")
        lines.append("")
        lines.append("| Section | Source Domain | Source Priority | Confidence |")
        lines.append("| --- | --- | --- | --- |")
        for row in section_provenance:
            lines.append(
                f"| {row.get('section_name', 'unknown')} | {row.get('source_domain', 'unknown')} | {row.get('source_priority', 'n/a')} | {row.get('confidence_score', 'n/a')} |"
            )
    return "\n".join(lines)


def _build_step_detail_markdown(workflow_summary: dict[str, Any] | None) -> str:
    if not workflow_summary:
        return ""
    steps: list[tuple[str, str, str]] = []
    data_quality = workflow_summary.get("data_quality_and_vision_extraction_check", {})
    steps.append(("1", "Data quality and vision extraction check", str(data_quality.get("status", "unknown"))))
    admin = workflow_summary.get("administrative_review", {})
    steps.append(("2", "Administrative completeness review", str(admin.get("status", "unknown"))))
    structure = workflow_summary.get("dossier_structure_review", {})
    steps.append(("3", "Structural dossier mapping", str(structure.get("status", "unknown"))))
    inn = workflow_summary.get("who_inn_similarity_review", {})
    steps.append(("5", "WHO INN similarity review", str(inn.get("threshold_result", "unknown"))))
    tech = workflow_summary.get("technical_section_review", {})
    tech_rows = tech.get("section_results", []) or []
    steps.append(("6", "Section-by-section technical review", f"{len(tech_rows)} sections reviewed"))
    amr = workflow_summary.get("amr_stewardship_review", {})
    steps.append(("7", "AMR stewardship review", str(amr.get("authorization_control", "not_applicable"))))
    consistency = workflow_summary.get("cross_section_consistency_review", {})
    steps.append(("10", "Cross-section consistency review", str(consistency.get("status", "unknown"))))
    completeness = workflow_summary.get("review_completeness_confirmation", {})
    steps.append(("11", "Review completeness confirmation", str(completeness.get("status", "unknown"))))
    overall = workflow_summary.get("overall_judgment", {})
    steps.append(("12", "Overall judgment", str(overall.get("final_verdict", "unknown"))))

    lines = [
        "### SOP Stage Detail",
        "",
        "| Step | Stage | Output Detail |",
        "| --- | --- | --- |",
    ]
    for step_no, label, detail in steps:
        lines.append(f"| {step_no} | {label} | {detail} |")
    return "\n".join(lines)


def _build_scanned_challenge_markdown(workflow_summary: dict[str, Any] | None) -> str:
    if not workflow_summary:
        return ""
    data_quality = workflow_summary.get("data_quality_and_vision_extraction_check", {}) or {}
    challenge = data_quality.get("scanned_document_challenge_mode", {}) or {}
    if not challenge.get("enabled"):
        return ""
    detected = challenge.get("vision_extraction_detected", []) or []
    confidence = challenge.get("extraction_confidence", {}) or {}
    lines = [
        "### Scanned-Document Challenge Mode",
        "",
        "Vision extraction detected:",
    ]
    for item in detected:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "Extraction confidence:",
            f"- GMP expiry date: {confidence.get('gmp_expiry_date', 'n/a')}",
            f"- CoA batch number: {confidence.get('coa_batch_number', 'n/a')}",
            f"- Signature/stamp detected: {'yes' if confidence.get('signature_or_stamp_detected') else 'no'}",
        ]
    )
    risk = str(challenge.get("text_rag_failure_risk", "low"))
    lines.extend(
        [
            "",
            "Text-only RAG challenge:",
            f"- Risk of missing key evidence without vision: {risk}",
            "- Why MCP+vision matters: key regulatory evidence exists in scanned certificates/tables, not plain text.",
        ]
    )
    return "\n".join(lines)


def _build_data_quality_intro_markdown(
    workflow_summary: dict[str, Any] | None,
    dossier: dict[str, Any] | None = None,
) -> str:
    data_quality = (workflow_summary or {}).get("data_quality_and_vision_extraction_check", {}) or {}
    challenge = data_quality.get("scanned_document_challenge_mode", {}) or {}
    extraction = (((dossier or {}).get("provenance", {}) or {}).get("extraction", {}) or {})
    status = str(data_quality.get("status", "completed" if extraction else "unknown"))
    ocr_used = bool(challenge.get("ocr_used", extraction.get("ocr_used", False)))
    page_count = challenge.get("page_count", extraction.get("page_count", "n/a"))
    image_count = challenge.get("image_count", extraction.get("image_count", "n/a"))
    detected = challenge.get("vision_extraction_detected", []) or []
    if not detected and extraction:
        detected = [str(item.get("evidence_type", "scanned evidence")) for item in extraction.get("visual_evidence", [])[:6]]
    lines = [
        "### Data Quality Check (Mandatory Step 1)",
        "",
        f"- Status: {status}",
        f"- OCR/Vision used: {'yes' if ocr_used else 'no'}",
        f"- Pages analyzed: {page_count}",
        f"- Image-heavy pages: {image_count}",
    ]
    if detected:
        lines.append("- Scan signals detected: " + ", ".join(str(item) for item in detected[:6]))
    return "\n".join(lines)


def _build_amr_policy_markdown(workflow_summary: dict[str, Any] | None) -> str:
    if not workflow_summary:
        return ""
    amr = workflow_summary.get("amr_stewardship_review", {}) or {}
    policy = amr.get("policy_decision", {}) or {}
    if not amr:
        return ""
    lines = [
        "### AMR Policy Decision Support",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| Applicable | {amr.get('applicable', False)} |",
        f"| AWaRe Category | {amr.get('aware_category', 'not_applicable')} |",
        f"| Authorization Control | {amr.get('authorization_control', 'standard_authorization')} |",
        f"| Policy Decision | {policy.get('decision', 'standard_authorization')} |",
        f"| Fast Track Candidate | {amr.get('fast_track_status', False)} |",
        f"| Restriction Trigger | {amr.get('watch_or_reserve_caution', False)} |",
    ]
    required_controls = policy.get("required_controls", []) or []
    if required_controls:
        lines.append("")
        lines.append("Required controls:")
        for control in required_controls:
            lines.append(f"- {control}")
    findings = amr.get("findings", []) or []
    if findings:
        lines.append("")
        lines.append("AMR evidence trace:")
        for item in findings[:6]:
            lines.append(f"- {item}")
    stewardship_check = amr.get("amr_stewardship_check", {}) or {}
    if stewardship_check:
        lines.extend(
            [
                "",
                "### AMR Stewardship Check",
                "",
                f"- Active ingredient: {stewardship_check.get('active_ingredient', 'unknown')}",
                f"- AMR class: {stewardship_check.get('amr_class', 'not_applicable')}",
                f"- Product type: {stewardship_check.get('product_type', 'unknown')}",
                f"- Indication: {stewardship_check.get('indication', 'not_stated')}",
                f"- Required warning: {stewardship_check.get('required_warning', 'missing')}",
                f"- Stewardship justification: {stewardship_check.get('stewardship_justification', 'missing')}",
                f"- Decision: {stewardship_check.get('decision', 'pass')}",
            ]
        )
    vet_check = amr.get("veterinary_amr_food_safety_check", {}) or {}
    if vet_check:
        target_species = vet_check.get("target_species", []) or []
        species_rendered = ", ".join(str(item) for item in target_species) if target_species else "not_stated"
        lines.extend(
            [
                "",
                "### Veterinary AMR + Food Safety Check",
                "",
                f"- Target species: {species_rendered}",
                f"- Withdrawal period: {vet_check.get('withdrawal_period', 'missing')}",
                f"- Residue information: {vet_check.get('residue_information', 'missing')}",
                f"- AMR warning: {vet_check.get('amr_warning', 'incomplete')}",
                f"- Decision: {vet_check.get('decision', 'query_applicant')}",
            ]
        )
    return "\n".join(lines)


def _build_uncertainty_and_trace_markdown(
    *,
    confidence: float,
    workflow_summary: dict[str, Any] | None,
) -> str:
    overall = (workflow_summary or {}).get("overall_judgment", {}) or {}
    findings = (workflow_summary or {}).get("findings_register", []) or []
    amr = (workflow_summary or {}).get("amr_stewardship_review", {}) or {}
    critical = [f for f in findings if str(f.get("severity", "")).lower() in {"critical", "major"}]
    lines = [
        "### Safety & Trust: Verdict Trace",
        "",
        f"- Why this verdict: {overall.get('justification', 'Decision followed the structured SOP and evidence-grounded checks.')}",
        f"- Final verdict: {overall.get('final_verdict', 'unknown')}",
        f"- Confidence score: {confidence:.2f}",
    ]
    uncertainty_flags: list[str] = []
    if confidence < 0.7:
        uncertainty_flags.append("overall confidence below 0.70")
    if critical:
        uncertainty_flags.append(f"{len(critical)} critical/major findings require sponsor action")
    source_mode = str(amr.get("source_mode", "unknown"))
    if source_mode != "live_backed":
        uncertainty_flags.append(f"external source mode is {source_mode} (not fully live)")
    if not uncertainty_flags:
        uncertainty_flags.append("no elevated uncertainty flags detected")
    lines.append("- Uncertainty flags: " + "; ".join(uncertainty_flags))
    lines.extend(
        [
            "",
            "| Rule | Tool | Evidence | Decision |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in critical[:5]:
        rule = str(item.get("violated_rule", "SOP check"))
        issue = str(item.get("issue", "Issue found"))
        evidence = str(item.get("evidence_reference", item.get("location", "dossier evidence")))
        tool = "OCR extraction" if any(token in issue.lower() for token in ("scan", "certificate", "gmp", "coa")) else "retrieval + rule evaluation"
        decision = str(item.get("recommendation", "query applicant"))
        lines.append(f"| {rule} | {tool} | {evidence} | {decision} |")
    if not critical:
        lines.append("| SOP checks passed | retrieval + rule evaluation | structured dossier evidence | proceed with current recommendation |")
    return "\n".join(lines)


def _augment_review_rationale(
    *,
    rationale: str,
    dossier: dict[str, Any],
    conversation_id: str | None,
    recommendation: str,
    confidence: float,
    workflow_summary: dict[str, Any] | None,
    question: str,
    force_data_quality_intro: bool = False,
) -> str:
    lowered_question = question.lower()
    is_amr_query = any(term in lowered_question for term in ("amr", "aware", "stewardship", "resistance", "reserve", "watch"))
    requested_step = _infer_requested_workflow_step(question)
    strict_step = _infer_strict_sop_step(question)
    if strict_step:
        ws = workflow_summary or {}
        section_map: dict[str, Any] = {
            "data_quality_and_vision_extraction_check": ws.get("data_quality_and_vision_extraction_check", {}),
            "submission_intake_and_familiarization": ws.get("submission_summary", {}),
            "administrative_completeness_review": ws.get("administrative_review", {}),
            "structural_dossier_mapping": ws.get("dossier_structure_review", {}),
            "applicable_rules_identification": ws.get("applicable_rules_identification", {}),
            "who_inn_similarity_review": ws.get("who_inn_similarity_review", {}),
            "section_by_section_technical_review": ws.get("technical_section_review", {}),
            "amr_stewardship_review": ws.get("amr_stewardship_review", {}),
            "findings_register": ws.get("findings_register", []),
            "severity_classification": ws.get("severity_classification", {}),
            "cross_section_consistency_review": ws.get("cross_section_consistency_review", {}),
            "review_completeness_confirmation": ws.get("review_completeness_confirmation", {}),
            "overall_judgment": ws.get("overall_judgment", {}),
        }
        focus = section_map.get(strict_step, {})
        return (
            f"### SOP Item In Review\n\n- {_pretty_workflow_step(strict_step)}\n\n"
            f"### Step Output\n\n```json\n{json.dumps(focus, ensure_ascii=True, indent=2)}\n```\n\n"
            "Reviewer note: this response is constrained to the selected SOP step."
        )
    parts: list[str] = []
    if requested_step:
        parts.append(f"### SOP Item In Review\n\n- {_pretty_workflow_step(requested_step)}")
        parts.append("")
    if force_data_quality_intro:
        dq_intro = _build_data_quality_intro_markdown(workflow_summary, dossier=dossier)
        if dq_intro:
            parts.append(dq_intro)
            parts.append("")
    parts.append(rationale.strip())
    parts.append("")
    parts.append("### Decision Support Snapshot")
    parts.append("")
    parts.append("| Signal | Value |")
    parts.append("| --- | --- |")
    parts.append(f"| Recommendation | {recommendation} |")
    parts.append(f"| Confidence | {confidence:.2f} |")
    parts.append(f"| Submission Type | pre_market_authorization |")
    parts.append("")
    amr_md = _build_amr_policy_markdown(workflow_summary)
    if is_amr_query and amr_md:
        parts.append(amr_md)
        parts.append("")
    if _is_sop_information_query(question) or any(term in question.lower() for term in ("workflow", "review step", "sop")):
        parts.append(_build_sop_status_markdown(dossier=dossier, conversation_id=conversation_id))
        parts.append("")
    comparison_md = _build_external_comparison_markdown(workflow_summary)
    if comparison_md:
        parts.append(comparison_md)
    step_md = _build_step_detail_markdown(workflow_summary)
    if step_md:
        parts.append("")
        parts.append(step_md)
    scanned_md = _build_scanned_challenge_markdown(workflow_summary)
    if scanned_md:
        parts.append("")
        parts.append(scanned_md)
    if amr_md and not is_amr_query:
        parts.append("")
        parts.append(amr_md)
    trace_md = _build_uncertainty_and_trace_markdown(confidence=confidence, workflow_summary=workflow_summary)
    if trace_md:
        parts.append("")
        parts.append(trace_md)
    amr = (workflow_summary or {}).get("amr_stewardship_review", {}) or {}
    source_mode = str(amr.get("source_mode", "unknown"))
    if source_mode != "live_backed":
        parts.append("")
        parts.append(
            f"### Global Resilience Mode\n\nExternal connectivity is constrained (`{source_mode}`). "
            "Decision support continued on local inference with provenance warnings, and external refresh should be re-run when connectivity improves."
        )
    return "\n".join(part for part in parts if part is not None).strip()


def _record_workflow_progress(
    *,
    dossier_id: str,
    question: str,
    dossier: dict[str, Any],
    review_payload: dict[str, Any] | None = None,
    conversation_id: str | None = None,
) -> None:
    completed_steps = _infer_completed_workflow_steps(question=question, dossier=dossier, review_payload=review_payload)
    if not completed_steps:
        return

    progress_by_key = state["workflow_progress"]
    progress_key = f"{conversation_id or 'global'}::{dossier_id}"
    progress = progress_by_key.get(progress_key) or _new_workflow_progress(dossier_id=dossier_id, conversation_id=conversation_id)
    for step in completed_steps:
        progress["completed_steps"].add(step)
        progress["step_sources"][step] = question
    progress["updated_at_utc"] = datetime.now(UTC).isoformat()
    progress_by_key[progress_key] = progress

    merged = state["workflow_progress_by_dossier"].get(dossier_id) or _new_workflow_progress(dossier_id=dossier_id)
    for step in completed_steps:
        merged["completed_steps"].add(step)
        merged["step_sources"][step] = question
    merged["updated_at_utc"] = progress["updated_at_utc"]
    state["workflow_progress_by_dossier"][dossier_id] = merged


def _workflow_gate_status(dossier: dict[str, Any], conversation_id: str | None = None) -> tuple[bool, list[str]]:
    dossier_id = str(dossier.get("dossier_id", ""))
    progress: dict[str, Any] | None = None
    if conversation_id:
        progress = state["workflow_progress"].get(f"{conversation_id}::{dossier_id}")
    if progress is None:
        progress = state["workflow_progress_by_dossier"].get(dossier_id)
    completed_steps = set(progress.get("completed_steps", set())) if progress else set()
    required_steps = _required_workflow_steps_for_dossier(dossier)
    missing = [step for step in required_steps if step not in completed_steps]
    return not missing, missing


def _snippet(text: str, max_len: int = 220) -> str:
    compact = " ".join(text.split())
    return compact[:max_len] + ("..." if len(compact) > max_len else "")


def _model_option_payload(settings: Settings, model_id: str) -> ModelOption:
    for model in settings.model_catalog:
        if model.id == model_id:
            return ModelOption(
                id=model.id,
                label=model.label,
                runtime_model_id=model.runtime_model_id,
                description=model.description,
            )
    raise HTTPException(status_code=400, detail=f"Model {model_id} is not configured")


def _model_catalog_payload(settings: Settings) -> list[ModelOption]:
    return [
        ModelOption(
            id=model.id,
            label=model.label,
            runtime_model_id=model.runtime_model_id,
            description=model.description,
        )
        for model in settings.model_catalog
    ]


def _search_with_subqueries(
    retriever: Retriever,
    query: str,
    top_k: int,
    dossier_id: str | None = None,
) -> tuple[list[str], list[Any]]:
    sub_queries = decompose_query(query)
    hit_lists = [retriever.search(query=sub_query, top_k=top_k, dossier_id=dossier_id) for sub_query in sub_queries]
    hits = merge_hits(*hit_lists, top_k=top_k)
    return sub_queries, hits


def _ui_page_path(page_name: str) -> Path:
    return state["settings"].ui_pages_path / page_name


def _reports_dir(settings: Settings) -> Path:
    return settings.audit_log_path.parents[1] / "reports"


def _extract_metric_value(metrics: dict[str, Any], key: str) -> float | None:
    raw = metrics.get(key, {})
    if isinstance(raw, dict):
        value = raw.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _benchmark_panel_payload(settings: Settings) -> BenchmarkPanelResponse:
    latest = settings.audit_log_path.parents[1] / "eval" / "latest_report.json"
    if not latest.exists():
        return BenchmarkPanelResponse(metrics=[])
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return BenchmarkPanelResponse(metrics=[])

    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    metrics = payload.get("metrics", {}) if isinstance(payload, dict) else {}
    entity = _extract_metric_value(metrics, "gmp_evidence_extraction_macro_f1")
    if entity is None:
        entity = _extract_metric_value(metrics, "section_presence_accuracy")
    sop = _extract_metric_value(metrics, "holistic_policy_macro_f1")
    scan = _extract_metric_value(metrics, "gmp_evidence_extraction_macro_f1")
    false_query = _extract_metric_value(metrics, "expected_calibration_error")
    citation = _extract_metric_value(metrics, "retrieval_ndcg_at_10")

    panel = [
        BenchmarkMetricItem(
            name="Entity extraction accuracy",
            value=entity,
            display_value=f"{entity * 100:.1f}%" if entity is not None else "n/a",
            source_metric_key="gmp_evidence_extraction_macro_f1",
        ),
        BenchmarkMetricItem(
            name="SOP issue detection",
            value=sop,
            display_value=f"{sop * 100:.1f}%" if sop is not None else "n/a",
            source_metric_key="holistic_policy_macro_f1",
        ),
        BenchmarkMetricItem(
            name="Scanned document extraction",
            value=scan,
            display_value=f"{scan * 100:.1f}%" if scan is not None else "n/a",
            source_metric_key="gmp_evidence_extraction_macro_f1",
        ),
        BenchmarkMetricItem(
            name="False query rate",
            value=false_query,
            display_value=f"{false_query * 100:.1f}%" if false_query is not None else "n/a",
            source_metric_key="expected_calibration_error",
        ),
        BenchmarkMetricItem(
            name="Evidence citation accuracy",
            value=citation,
            display_value=f"{citation * 100:.1f}%" if citation is not None else "n/a",
            source_metric_key="retrieval_ndcg_at_10",
        ),
    ]
    return BenchmarkPanelResponse(
        report_generated_at_utc=summary.get("generated_at_utc"),
        dataset_version=str(summary.get("dataset_version") or "latest_report"),
        records_evaluated=summary.get("records_evaluated"),
        metrics=panel,
    )


def _iter_audit_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _telemetry_panel_payload(settings: Settings) -> TelemetryPanelResponse:
    records = [r for r in _iter_audit_records(settings.audit_log_path) if str(r.get("event", "")) == "review_decision"]
    total = len(records)
    if total == 0:
        return TelemetryPanelResponse(
            generated_at_utc=datetime.now(UTC).isoformat(),
            daily_live_external_check_enabled=settings.external_source_mode == "live_prefer",
            records_evaluated=0,
            metrics=[
                TelemetryPanelMetric(name="Tool-call success rate", value=None, display_value="n/a", description="No review-decision records found."),
                TelemetryPanelMetric(name="External-source hit rate", value=None, display_value="n/a", description="No review-decision records found."),
                TelemetryPanelMetric(name="Citation-groundedness score", value=None, display_value="n/a", description="No review-decision records found."),
            ],
        )

    successful_calls = 0
    external_hits = 0
    grounded_values: list[float] = []
    for row in records:
        abstained = bool(row.get("abstained"))
        citation_count = int(row.get("citation_count", 0) or 0)
        if (not abstained) and citation_count > 0:
            successful_calls += 1
        verifier = row.get("verifier", {})
        grounded = verifier.get("grounded_claim_rate") if isinstance(verifier, dict) else None
        if isinstance(grounded, (int, float)):
            grounded_values.append(float(grounded))
        evidence_packet = row.get("evidence_packet", {})
        external = evidence_packet.get("external_evidence", {}) if isinstance(evidence_packet, dict) else {}
        mode = str(external.get("source_mode", "")).lower()
        source_trace = [str(item).lower() for item in external.get("source_trace", [])] if isinstance(external, dict) else []
        if mode in {"live_backed", "snapshot_backed"} or any("resolved" in entry or "live " in entry for entry in source_trace):
            external_hits += 1

    tool_rate = successful_calls / total
    external_rate = external_hits / total
    grounded_avg = (sum(grounded_values) / len(grounded_values)) if grounded_values else None
    return TelemetryPanelResponse(
        generated_at_utc=datetime.now(UTC).isoformat(),
        daily_live_external_check_enabled=settings.external_source_mode == "live_prefer",
        records_evaluated=total,
        metrics=[
            TelemetryPanelMetric(
                name="Tool-call success rate",
                value=tool_rate,
                display_value=f"{tool_rate * 100:.1f}%",
                description="Share of review orchestration runs that completed without abstention and produced cited evidence.",
            ),
            TelemetryPanelMetric(
                name="External-source hit rate",
                value=external_rate,
                display_value=f"{external_rate * 100:.1f}%",
                description="Share of reviews where external evidence resolved from live/snapshot sources.",
            ),
            TelemetryPanelMetric(
                name="Citation-groundedness score",
                value=grounded_avg,
                display_value=f"{grounded_avg * 100:.1f}%" if grounded_avg is not None else "n/a",
                description="Average grounded-claim rate from verifier checks.",
            ),
        ],
    )


def _should_include_wiki_context(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in (
            "guidance",
            "policy",
            "wiki",
            "framework",
            "standard",
            "aware",
            "glass",
            "stewardship policy",
            "what guidance",
        )
    )


def _filtered_guidance_hits(question: str, hits: list[Any]) -> list[Any]:
    lowered = question.lower()
    wants_amr = any(term in lowered for term in ("aware", "glass", "amr", "stewardship", "antimicrobial"))
    wants_chemistry = any(term in lowered for term in ("chemistry", "similarity", "rxnorm", "chembl", "unichem"))
    wants_sop = any(term in lowered for term in ("sop", "workflow", "standard operating procedure", "review steps", "structured review"))
    wants_tutorial = any(term in lowered for term in ("tutorial", "how to", "how do i", "show me how", "guide me"))
    wants_external_sources = any(
        term in lowered
        for term in (
            "outside source",
            "outside sources",
            "external source",
            "external sources",
            "consulted source",
            "consulted sources",
            "provenance",
            "audit",
            "source trace",
            "source reporting",
            "pubchem",
            "rxnorm",
            "chembl",
            "unichem",
        )
    )
    wants_models = any(term in lowered for term in ("model", "switch", "gemma", "qwen"))

    filtered: list[Any] = []
    for hit in hits:
        title = str(hit.chunk.section_title).lower()
        if "model switching guidance" in title and not wants_models:
            continue
        if wants_amr and not any(term in title for term in ("aware", "glass", "stewardship", "antimicrobial")):
            if not (wants_chemistry and any(term in title for term in ("chemistry", "normalization"))):
                continue
        if wants_chemistry and not any(term in title for term in ("chemistry", "normalization")):
            if not (wants_amr and any(term in title for term in ("aware", "glass", "stewardship"))):
                continue
        if wants_external_sources and not any(
            term in title
            for term in ("external source", "provenance", "audit", "chemistry", "aware", "glass")
        ):
            continue
        if wants_sop and not any(term in title for term in ("sop", "workflow", "review")):
            if not (wants_tutorial and "tutorial" in title):
                continue
        if wants_tutorial and not any(term in title for term in ("tutorial", "how to", "reviewer")):
            if not (wants_sop and any(term in title for term in ("sop", "workflow"))):
                continue
        filtered.append(hit)

    return filtered or hits


def _require_dossier_shape(payload: dict[str, Any]) -> None:
    required_top_level = [
        "dossier_id",
        "country",
        "submission_date",
        "product",
        "organization",
        "policy_signals",
        "sections",
        "labels",
        "provenance",
    ]
    missing = [key for key in required_top_level if key not in payload]
    if missing:
        raise HTTPException(status_code=400, detail=f"Uploaded dossier is missing required keys: {', '.join(missing)}")

    if not isinstance(payload.get("sections"), list) or not payload["sections"]:
        raise HTTPException(status_code=400, detail="Uploaded dossier must contain at least one section")


def _refresh_dossier_state() -> None:
    settings: Settings = state["settings"]
    base_dossiers = load_dossiers(str(settings.data_jsonl_path))
    uploaded_dossiers = load_uploaded_dossiers(settings.uploaded_dossiers_dir)
    dossiers = list(base_dossiers) + uploaded_dossiers
    chunks = build_evidence_chunks(dossiers)
    state["dossiers"] = dossiers
    state["chunks"] = chunks
    state["retriever"] = HybridRetriever(chunks)
    state["dossier_by_id"] = {str(d["dossier_id"]): d for d in dossiers}
    lifecycle = (state.get("governance_state") or {}).get("dossier_lifecycle", {})
    state["knowledge_graph"] = KnowledgeGraph(dossiers, lifecycle)
    governance_state = state.get("governance_state")
    if governance_state is not None:
        for dossier in dossiers:
            _lifecycle_record(str(dossier["dossier_id"]))
        _save_governance_state()


def _build_app_state(settings: Settings) -> dict[str, Any]:
    dossiers = list(load_dossiers(str(settings.data_jsonl_path))) + load_uploaded_dossiers(settings.uploaded_dossiers_dir)
    chunks = build_evidence_chunks(dossiers)
    retriever = HybridRetriever(chunks)
    knowledge_wiki_pages = load_knowledge_wiki(str(settings.knowledge_wiki_path))
    knowledge_wiki_chunks = build_knowledge_wiki_chunks(knowledge_wiki_pages)
    knowledge_wiki_retriever = HybridRetriever(knowledge_wiki_chunks)
    conversation_store = ConversationStore(path=settings.conversations_state_path, settings=settings)
    dossier_by_id = {str(d["dossier_id"]): d for d in dossiers}
    auth_state = _load_auth_state(settings)
    governance_state = _load_governance_state(settings, dossiers)
    knowledge_graph = KnowledgeGraph(dossiers, governance_state.get("dossier_lifecycle", {}))
    return {
        "settings": settings,
        "dossiers": dossiers,
        "chunks": chunks,
        "retriever": retriever,
        "knowledge_wiki_pages": knowledge_wiki_pages,
        "knowledge_wiki_chunks": knowledge_wiki_chunks,
        "knowledge_wiki_retriever": knowledge_wiki_retriever,
        "conversation_store": conversation_store,
        "dossier_by_id": dossier_by_id,
        "knowledge_graph": knowledge_graph,
        "auth_state": auth_state,
        "governance_state": governance_state,
        "workflow_progress": {},
        "workflow_progress_by_dossier": {},
    }


def _build_memory_summary(settings: Settings) -> MemorySummary:
    snap = memory_snapshot()
    within_budget = bool(
        snap["system_available_ram_gb"] >= settings.min_free_ram_gb
        and snap["process_rss_gb"] <= settings.fallback_route_rss_limit_gb
    )
    return MemorySummary(
        process_rss_gb=float(snap["process_rss_gb"]),
        system_total_ram_gb=float(snap["system_total_ram_gb"]),
        system_available_ram_gb=float(snap["system_available_ram_gb"]),
        system_used_ram_percent=float(snap["system_used_ram_percent"]),
        min_free_ram_gb=settings.min_free_ram_gb,
        standard_route_rss_limit_gb=settings.standard_route_rss_limit_gb,
        fallback_route_rss_limit_gb=settings.fallback_route_rss_limit_gb,
        within_budget=within_budget,
    )


def _dossier_list_items(limit: int, user: dict[str, Any]) -> list[DossierListItem]:
    items: list[DossierListItem] = []
    for dossier in state["dossiers"]:
        product = dossier.get("product", {})
        policy_signals = dossier.get("policy_signals", {})
        lifecycle = _lifecycle_record(str(dossier["dossier_id"]))
        review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
        if review_program not in _user_process_scopes(user):
            continue
        if not _is_superuser(user) and lifecycle.get("assigned_reviewer") != user["username"]:
            continue
        progress_state, progress_percent, progress_color = _dossier_progress_view(lifecycle)
        items.append(
            DossierListItem(
                dossier_id=dossier["dossier_id"],
                product_name=str(product.get("product_name", "")),
                inn_name=str(product.get("inn_name", "")),
                country=dossier["country"],
                submission_date=dossier["submission_date"],
                manufacturer_name=str(dossier.get("organization", {}).get("manufacturer_name", "")),
                aware_category=str(policy_signals.get("aware_category", "not_applicable")),
                status=str(lifecycle.get("status", "open")),
                assigned_reviewer=lifecycle.get("assigned_reviewer"),
                review_type=str(lifecycle.get("review_type", "generic")),
                review_program=review_program,
                progress_state=progress_state,
                progress_percent=progress_percent,
                progress_color=progress_color,
            )
        )
        if len(items) >= limit:
            break
    return items


def _knowledge_graph_for_user(user: dict[str, Any]) -> KnowledgeGraph:
    visible = _accessible_dossiers_for_user(user)
    lifecycle = state["governance_state"].get("dossier_lifecycle", {})
    return KnowledgeGraph(visible, lifecycle)


def _accessible_dossiers_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = _user_process_scopes(user)
    results: list[dict[str, Any]] = []
    for dossier in state["dossiers"]:
        if _infer_review_program(dossier) not in scopes:
            continue
        lifecycle = _lifecycle_record(str(dossier.get("dossier_id", "")))
        if not _is_superuser(user) and lifecycle.get("assigned_reviewer") != user["username"]:
            continue
        results.append(dossier)
    return results


def _conversation_title_for_dossier(dossier: dict[str, Any], fallback_dossier_id: str) -> str:
    product_name = str(dossier.get("product", {}).get("product_name", fallback_dossier_id)).strip() or fallback_dossier_id
    manufacturer = str(dossier.get("organization", {}).get("manufacturer_name", "")).strip()
    if manufacturer:
        return f"Review: {manufacturer} - {product_name}"
    return f"Review: {product_name}"


def _citation_payloads(citations: list[dict[str, Any]]) -> list[Citation]:
    return [
        Citation(
            citation_id=str(citation.get("citation_id", "")),
            dossier_id=str(citation.get("dossier_id", "")),
            section_id=str(citation.get("section_id", "")),
            section_title=str(citation.get("section_title", "")),
            score=float(citation.get("score", 0.0)),
            snippet=str(citation.get("snippet", "")),
        )
        for citation in citations
    ]


def _hit_payloads(hits: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "citation_id": hit.chunk.citation_id,
            "dossier_id": hit.chunk.dossier_id,
            "section_id": hit.chunk.section_id,
            "section_title": hit.chunk.section_title,
            "score": round(hit.score, 5),
            "snippet": _snippet(hit.chunk.text),
        }
        for hit in hits
    ]


def _context_monitor_payload(monitor: dict[str, Any]) -> ContextWindowMonitor:
    return ContextWindowMonitor(**monitor)


def _chat_only_rationale(question: str) -> str:
    lowered = question.strip().lower()
    if lowered in {"hi", "hello", "hey", "hi friend", "hello friend", "hey friend", "good morning", "good afternoon"}:
        return "Hi friend. I am ready to assist. You can ask for dossier review, issue discovery, policy guidance, AMR stewardship analysis, or a report-focused summary."
    if any(token in lowered for token in ("hi fried", "helo", "hie", "hay")):
        return "Hello. I am ready to assist with dossier review, issue discovery, policy guidance, AMR stewardship analysis, or report preparation."
    return (
        "I can help with general reviewer questions, dossier review tasks, policy guidance, AMR stewardship analysis, and report preparation. "
        "If you want a dossier-specific answer, select or provide the active dossier first."
    )


def _is_manager_performance_query(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered
        for term in (
            "fastest tot",
            "slowest reviewer",
            "overall tot",
            "turnaround time",
            "where is he struggling",
            "reviewer performance",
            "review velocity",
        )
    )


def _manager_performance_rationale(question: str) -> str:
    summary = _reviewer_performance_summary()
    reviewers = summary["reviewers"]
    if not reviewers:
        return "No completed reviewer cycles are available yet, so turnaround analytics are not ready."
    lines = [
        "### Reviewer Turnaround Analytics",
        "",
        f"- Fastest reviewer: {summary['fastest_reviewer_username'] or 'n/a'}",
        f"- Slowest reviewer: {summary['slowest_reviewer_username'] or 'n/a'}",
        f"- Overall ToT (hours): {summary['overall_average_tot_hours']}",
        "",
        "| Reviewer | Completed | Avg ToT (hrs) | Fastest | Slowest | Struggle Signal |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in reviewers:
        lines.append(
            f"| {row['reviewer_username']} | {row['completed_reviews']} | {row['average_tot_hours']} | {row['fastest_tot_hours']} | {row['slowest_tot_hours']} | {row['struggle_signal']} |"
        )
    return "\n".join(lines)


def _wiki_guidance_rationale(question: str, hits: list[Any]) -> str:
    filtered_hits = _filtered_guidance_hits(question, hits)
    if not filtered_hits:
        return "I did not retrieve relevant reviewer guidance for that question. Try naming the guidance area more directly, such as reviewer workflow, evidence grounding, stewardship policy, or chemistry normalization."
    lowered = question.lower()
    wants_tutorial = any(term in lowered for term in ("tutorial", "how to", "how do i", "show me how", "guide me"))
    wants_sop = any(term in lowered for term in ("sop", "workflow", "standard operating procedure", "review steps"))
    if wants_tutorial or wants_sop:
        lines = ["Here is a practical guide based on the retrieved reviewer guidance:"]
        for index, hit in enumerate(filtered_hits[:3], start=1):
            lines.append(
                f"{index}. {hit.chunk.section_title}: {_snippet(hit.chunk.text, 190)} [{hit.chunk.citation_id}]"
            )
        lines.append("You can ask me to turn this into a shorter checklist, a reviewer training note, or a step-by-step tutorial for a specific review stage.")
        return "\n".join(lines)
    lines = ["I found reviewer guidance that is relevant to your question:"]
    for hit in filtered_hits[:3]:
        lines.append(
            f"- {hit.chunk.section_title}: { _snippet(hit.chunk.text, 180) } [{hit.chunk.citation_id}]"
        )
    lines.append("Use these guidance sections to frame the next dossier-specific review step.")
    return "\n".join(lines)


def _policy_guidance_rationale(question: str, hits: list[Any], dossier: dict[str, Any] | None = None) -> str:
    filtered_hits = _filtered_guidance_hits(question, hits)
    if not filtered_hits:
        return (
            "I did not retrieve relevant reviewer guidance for that question. "
            "Try naming the guidance area more directly, such as WHO AWaRe, GLASS, reviewer workflow, "
            "evidence standards, or chemistry normalization."
        )

    lines = ["I found guidance that is relevant to this review question:"]
    if dossier is not None:
        product = dossier.get("product", {})
        lines.append(
            f"- Active dossier context: **{product.get('product_name', 'Current dossier')}** "
            f"({product.get('inn_name', 'INN not extracted')})."
        )
    for hit in filtered_hits[:3]:
        lines.append(f"- {hit.chunk.section_title}: {_snippet(hit.chunk.text, 180)} [{hit.chunk.citation_id}]")
    lines.append("Use this guidance to frame the next dossier-specific assessment step and keep conclusions tied to cited evidence.")
    return "\n".join(lines)


def _conversation_summary_payload(session: dict[str, Any], settings: Settings) -> ConversationSummary:
    monitor = build_context_monitor(session, settings)
    owner_username = state["governance_state"]["conversation_owners"].get(session["conversation_id"])
    return ConversationSummary(
        conversation_id=session["conversation_id"],
        title=session["title"],
        created_at_utc=session["created_at_utc"],
        updated_at_utc=session["updated_at_utc"],
        linked_from_conversation_id=session.get("linked_from_conversation_id"),
        context_window_tokens=int(session["context_window_tokens"]),
        selected_model_id=str(session["selected_model_id"]),
        dossier_id=session.get("dossier_id"),
        owner_username=owner_username,
        compaction_count=int(session.get("compaction_count", 0)),
        carryover_available=bool(session.get("carryover_summary")),
        context_monitor=_context_monitor_payload(monitor),
    )


def _conversation_detail_payload(session: dict[str, Any], settings: Settings) -> ConversationDetailResponse:
    return ConversationDetailResponse(
        conversation=_conversation_summary_payload(session, settings),
        carryover_summary=str(session.get("carryover_summary", "")),
        rolling_summary=str(session.get("rolling_summary", "")),
        summary_model_id=str(session.get("summary_model_id", settings.low_cost_summary_model_id)),
        last_compaction_reason=session.get("last_compaction_reason"),
        summary_history=[ConversationSummarySnapshot(**item) for item in session.get("summary_history", [])],
        messages=[
            ConversationMessage(
                message_id=str(message["message_id"]),
                role=str(message["role"]),
                content=str(message["content"]),
                created_at_utc=str(message["created_at_utc"]),
                tokens_estimate=int(message["tokens_estimate"]),
                citations=_citation_payloads(message.get("citations", [])),
                archived=bool(message.get("archived", False)),
                metadata=dict(message.get("metadata", {})),
            )
            for message in session.get("messages", [])
        ],
    )


settings = load_settings()
state = _build_app_state(settings)

app = FastAPI(
    title="Dossier Review AI Assistant API",
    version="0.1.0",
    summary="Local-first policy copilot foundation service",
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

PUBLIC_PATHS = {
    "/login",
    "/favicon.svg",
    "/brand-mark.svg",
    "/sop-flow.svg",
    "/v1/auth/login",
    "/v1/auth/me",
    "/v1/auth/logout",
    "/css",
    "/css/",
}

app.mount("/css", StaticFiles(directory=str(settings.ui_pages_path / "css")), name="css")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    token = request.cookies.get("pmada_session")
    user = _resolve_session_user(token)
    ctx_token = current_user_ctx.set(user)
    try:
        if request.method != "OPTIONS" and path not in PUBLIC_PATHS and not path.startswith("/css") and not path.startswith("/css/") and not path.startswith("/docs") and not path.startswith("/openapi"):
            if user is None:
                if path.startswith("/v1/"):
                    return JSONResponse(status_code=401, content={"detail": "Authentication required"})
                return RedirectResponse(url="/login", status_code=303)
        response = await call_next(request)
        return response
    finally:
        current_user_ctx.reset(ctx_token)


@app.get("/login", include_in_schema=False, response_model=None)
def login_page():
    if _current_user(required=False):
        return RedirectResponse(url="/review", status_code=303)
    path = _ui_page_path("login.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Login UI not found")
    return FileResponse(path)


@app.post("/v1/auth/login", response_model=AuthLoginResponse)
def login(request: AuthLoginRequest, response: Response) -> AuthLoginResponse:
    user = state["auth_state"]["users"].get(request.username)
    if user is None or user.get("password_hash") != _hash_password(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not bool(user.get("active", True)):
        raise HTTPException(status_code=403, detail="This account is currently disabled.")
    token = secrets.token_urlsafe(24)
    state["auth_state"]["sessions"][token] = {
        "username": request.username,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    _save_auth_state()
    response.set_cookie("pmada_session", token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 12)
    return AuthLoginResponse(message="Login successful.", user=_user_profile(user))


@app.get("/v1/auth/me", response_model=UserProfile)
def auth_me() -> UserProfile:
    return _user_profile(_current_user())


@app.get("/v1/admin/users", response_model=AdminUsersResponse)
def list_admin_users() -> AdminUsersResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can inspect user access.")
    visible = [_admin_user_item_payload(candidate) for candidate in _admin_visible_users(user)]
    return AdminUsersResponse(total_items=len(visible), items=visible)


@app.post("/v1/admin/dossiers/{dossier_id}/assign", response_model=DossierAssignmentResponse)
def assign_dossier(dossier_id: str, request: DossierAssignmentRequest) -> DossierAssignmentResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can assign dossiers.")
    dossier = state["dossier_by_id"].get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {dossier_id} not found")

    target = state["auth_state"]["users"].get(request.reviewer_username)
    if target is None or not bool(target.get("active", True)):
        raise HTTPException(status_code=404, detail=f"Reviewer {request.reviewer_username} not found or inactive.")
    if str(target.get("role")) not in {"reviewer", "superuser"}:
        raise HTTPException(status_code=400, detail="Target user must be a reviewer or superuser.")

    lifecycle = _lifecycle_record(dossier_id)
    review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
    target_scopes = set(_normalize_process_scopes(target.get("process_scopes")))
    if review_program not in target_scopes:
        raise HTTPException(status_code=400, detail=f"Reviewer {request.reviewer_username} lacks {review_program} scope.")

    lifecycle["assigned_reviewer"] = request.reviewer_username
    lifecycle["status"] = "in_review" if lifecycle.get("status") == "open" else lifecycle.get("status", "open")
    _append_lifecycle_event(
        dossier_id,
        "dossier_assigned_by_manager",
        username=user["username"],
        details={"assigned_reviewer": request.reviewer_username},
    )
    return DossierAssignmentResponse(
        dossier_id=dossier_id,
        assigned_reviewer=request.reviewer_username,
        status=str(lifecycle.get("status", "open")),
    )


@app.get("/v1/admin/reviewer-performance", response_model=ReviewerPerformanceResponse)
def reviewer_performance() -> ReviewerPerformanceResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can view reviewer performance.")
    summary = _reviewer_performance_summary()
    return ReviewerPerformanceResponse(
        overall_average_tot_hours=float(summary["overall_average_tot_hours"]),
        fastest_reviewer_username=summary["fastest_reviewer_username"],
        slowest_reviewer_username=summary["slowest_reviewer_username"],
        reviewers=[ReviewerPerformanceItem(**row) for row in summary["reviewers"]],
    )


@app.get("/v1/admin/dashboard-summary", response_model=AdminDashboardSummaryResponse)
def admin_dashboard_summary() -> AdminDashboardSummaryResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can view admin dashboard summary.")
    summary = _admin_dashboard_summary(user)
    return AdminDashboardSummaryResponse(
        overall_total_dossiers=int(summary["overall_total_dossiers"]),
        overall_not_started=int(summary["overall_not_started"]),
        overall_in_progress=int(summary["overall_in_progress"]),
        overall_done=int(summary["overall_done"]),
        overall_average_tot_hours=float(summary["overall_average_tot_hours"]),
        fastest_reviewer_username=summary["fastest_reviewer_username"],
        slowest_reviewer_username=summary["slowest_reviewer_username"],
        progress_by_reviewer=[AdminProgressByReviewerItem(**row) for row in summary["progress_by_reviewer"]],
        tot_by_reviewer=[ReviewerPerformanceItem(**row) for row in summary["tot_by_reviewer"]],
    )


@app.get("/v1/reviewer/dashboard", response_model=ReviewerDashboardResponse)
def reviewer_dashboard() -> ReviewerDashboardResponse:
    user = _current_user()
    summary = _reviewer_dashboard_summary(user)
    return ReviewerDashboardResponse(**summary)


@app.get("/v1/benchmark/panel", response_model=BenchmarkPanelResponse)
def benchmark_panel() -> BenchmarkPanelResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    _require_process_access(user, "marketing_authorization")
    return _benchmark_panel_payload(settings)


@app.get("/v1/telemetry/panel", response_model=TelemetryPanelResponse)
def telemetry_panel() -> TelemetryPanelResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    _require_process_access(user, "marketing_authorization")
    return _telemetry_panel_payload(settings)


@app.get("/v1/workflow/state", response_model=WorkflowStateResponse)
def workflow_state(dossier_id: str, conversation_id: str | None = None) -> WorkflowStateResponse:
    user = _current_user()
    dossier = state["dossier_by_id"].get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {dossier_id} not found")
    _require_process_access(user, _infer_review_program(dossier))
    _require_dossier_assignment_access(user, _lifecycle_record(dossier_id))
    if conversation_id:
        _require_conversation_access(conversation_id, user)
    return _workflow_state_payload(dossier=dossier, conversation_id=conversation_id)


@app.get("/v1/admin/dossiers/unassigned", response_model=DossierListResponse)
def list_unassigned_dossiers(limit: int = 50) -> DossierListResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can inspect unassigned dossiers.")
    normalized_limit = max(1, min(limit, 200))
    items: list[DossierListItem] = []
    for dossier in state["dossiers"]:
        lifecycle = _lifecycle_record(str(dossier.get("dossier_id", "")))
        if lifecycle.get("assigned_reviewer"):
            continue
        review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
        if review_program not in _user_process_scopes(user):
            continue
        product = dossier.get("product", {})
        policy_signals = dossier.get("policy_signals", {})
        progress_state, progress_percent, progress_color = _dossier_progress_view(lifecycle)
        items.append(
            DossierListItem(
                dossier_id=dossier["dossier_id"],
                product_name=str(product.get("product_name", "")),
                inn_name=str(product.get("inn_name", "")),
                country=dossier["country"],
                submission_date=dossier["submission_date"],
                manufacturer_name=str(dossier.get("organization", {}).get("manufacturer_name", "")),
                aware_category=str(policy_signals.get("aware_category", "not_applicable")),
                status=str(lifecycle.get("status", "open")),
                assigned_reviewer=lifecycle.get("assigned_reviewer"),
                review_type=str(lifecycle.get("review_type", "generic")),
                review_program=review_program,
                progress_state=progress_state,
                progress_percent=progress_percent,
                progress_color=progress_color,
            )
        )
        if len(items) >= normalized_limit:
            break
    return DossierListResponse(total_items=len(items), items=items)


@app.post("/v1/admin/users", response_model=AdminUserItem)
def create_admin_user(request: AdminUserCreateRequest) -> AdminUserItem:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can create users.")
    normalized_scopes = _normalize_process_scopes(request.process_scopes)
    if not set(normalized_scopes).issubset(_user_process_scopes(user)):
        raise HTTPException(status_code=403, detail="You can only create users inside your own review program.")
    if request.username in state["auth_state"]["users"]:
        raise HTTPException(status_code=409, detail="Username already exists.")
    record = {
        "username": request.username,
        "display_name": request.display_name,
        "role": request.role,
        "process_scopes": normalized_scopes,
        "password_hash": _hash_password(request.username, request.password),
        "active": True,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    state["auth_state"]["users"][request.username] = record
    _save_auth_state()
    return _admin_user_item_payload(record)


@app.patch("/v1/admin/users/{username}", response_model=AdminUserItem)
def update_admin_user(username: str, request: AdminUserUpdateRequest) -> AdminUserItem:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can update users.")
    record = state["auth_state"]["users"].get(username)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if not set(_normalize_process_scopes(record.get("process_scopes"))).issubset(_user_process_scopes(user)):
        raise HTTPException(status_code=403, detail="You can only manage users inside your own review program.")
    if request.process_scopes is not None:
        normalized_scopes = _normalize_process_scopes(request.process_scopes)
        if not set(normalized_scopes).issubset(_user_process_scopes(user)):
            raise HTTPException(status_code=403, detail="You can only grant scopes inside your own review program.")
        record["process_scopes"] = normalized_scopes
    if request.display_name is not None:
        record["display_name"] = request.display_name
    if request.role is not None:
        record["role"] = request.role
    if request.active is not None:
        record["active"] = bool(request.active)
    if request.password:
        record["password_hash"] = _hash_password(username, request.password)
    _save_auth_state()
    return _admin_user_item_payload(record)


@app.post("/v1/auth/logout")
def logout(response: Response, request: Request) -> dict[str, Any]:
    token = request.cookies.get("pmada_session")
    if token:
        state["auth_state"]["sessions"].pop(token, None)
        _save_auth_state()
    response.delete_cookie("pmada_session")
    return {"logged_out": True}


@app.get("/", include_in_schema=False)
def ui_shell() -> FileResponse:
    index_path = Path(state["settings"].ui_index_path)
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI shell not found")
    return FileResponse(index_path)


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    path = _ui_page_path("favicon.svg")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/brand-mark.svg", include_in_schema=False)
def brand_mark() -> FileResponse:
    path = _ui_page_path("brand-mark.svg")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand mark not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/sop-flow.svg", include_in_schema=False)
def sop_flow_diagram() -> FileResponse:
    path = _ui_page_path("sop-flow.svg")
    if not path.exists():
        raise HTTPException(status_code=404, detail="SOP flow image not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/review", include_in_schema=False)
def review_page() -> FileResponse:
    path = _ui_page_path("review.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Review UI not found")
    return FileResponse(path)


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only superusers can access the admin panel.")
    path = _ui_page_path("admin.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Admin UI not found")
    return FileResponse(path)


@app.get("/issues", include_in_schema=False)
def issues_page() -> FileResponse:
    path = _ui_page_path("issues.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Issue discovery UI not found")
    return FileResponse(path)


@app.get("/wiki", include_in_schema=False)
def wiki_page() -> FileResponse:
    path = _ui_page_path("wiki.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Wiki UI not found")
    return FileResponse(path)


@app.get("/amr", include_in_schema=False)
def amr_page() -> FileResponse:
    path = _ui_page_path("amr.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="AMR UI not found")
    return FileResponse(path)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    mem = _build_memory_summary(state["settings"])
    return HealthResponse(
        status="ok",
        dossiers_loaded=len(state["dossiers"]),
        sections_indexed=len(state["chunks"]),
        system_total_ram_gb=mem.system_total_ram_gb,
        system_available_ram_gb=mem.system_available_ram_gb,
        process_rss_gb=mem.process_rss_gb,
        model_policy=state["settings"].model_policy,
        retrieval_mode="hybrid_bm25_densevector_rrf_rerank_v2",
        external_source_mode=state["settings"].external_source_mode,
        default_model_id=state["settings"].model_id,
        default_context_window_tokens=state["settings"].default_context_window_tokens,
        available_models=_model_catalog_payload(state["settings"]),
        chunking_profiles=[
            ChunkingProfileSummary(
                source_type=profile.source_type,
                profile_version=profile.profile_version,
                target_tokens=profile.target_tokens,
                overlap_tokens=profile.overlap_tokens,
                title_standalone=profile.title_standalone,
            )
            for profile in chunking_profiles_catalog()
        ],
    )


@app.get("/v1/models", response_model=ModelCatalogResponse)
def list_models() -> ModelCatalogResponse:
    settings: Settings = state["settings"]
    return ModelCatalogResponse(
        default_model_id=settings.model_id,
        available_models=_model_catalog_payload(settings),
    )


@app.get("/v1/conversations", response_model=ConversationListResponse)
def list_conversations() -> ConversationListResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    sessions = state["conversation_store"].list_sessions()
    if not _is_superuser(user):
        filtered_sessions: list[dict[str, Any]] = []
        for session in sessions:
            owner = state["governance_state"]["conversation_owners"].get(session["conversation_id"])
            if owner == user["username"]:
                filtered_sessions.append(session)
        sessions = filtered_sessions
    return ConversationListResponse(
        total_items=len(sessions),
        items=[_conversation_summary_payload(session, settings) for session in sessions],
    )


@app.post("/v1/conversations", response_model=ConversationDetailResponse)
def create_conversation(request: ConversationCreateRequest) -> ConversationDetailResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    selected_model_id = request.model_id or settings.model_id
    _model_option_payload(settings, selected_model_id)
    if request.dossier_id:
        dossier = state["dossier_by_id"].get(request.dossier_id)
        if dossier is None:
            raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")
        lifecycle = _lifecycle_record(request.dossier_id)
        review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
        _require_process_access(user, review_program)
        _require_dossier_assignment_access(user, lifecycle)
    conversation_title = request.title
    if request.dossier_id and not conversation_title:
        dossier = state["dossier_by_id"].get(request.dossier_id)
        if dossier is not None:
            conversation_title = _conversation_title_for_dossier(dossier, request.dossier_id)
    try:
        session, _ = state["conversation_store"].create_session(
            title=conversation_title,
            context_window_tokens=request.context_window_tokens,
            linked_from_conversation_id=request.linked_from_conversation_id,
            selected_model_id=selected_model_id,
            dossier_id=request.dossier_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _register_conversation_owner(session["conversation_id"], user["username"])

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "conversation_created",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "conversation_id": session["conversation_id"],
            "linked_from_conversation_id": request.linked_from_conversation_id,
            "selected_model_id": selected_model_id,
            "context_window_tokens": session["context_window_tokens"],
            "lineage_tags": build_lineage_tags(settings=settings, route="conversation_created", model_id=selected_model_id),
        },
    )
    return _conversation_detail_payload(session, settings)


@app.get("/v1/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str) -> ConversationDetailResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    _require_conversation_access(conversation_id, user)
    session = state["conversation_store"].get_session(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return _conversation_detail_payload(session, settings)


@app.delete("/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, Any]:
    user = _current_user()
    _require_conversation_access(conversation_id, user)
    removed = state["conversation_store"].delete_session(conversation_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    keys_to_remove = [key for key in state["workflow_progress"] if key.startswith(f"{conversation_id}::")]
    for key in keys_to_remove:
        state["workflow_progress"].pop(key, None)
    state["governance_state"]["conversation_owners"].pop(conversation_id, None)
    _save_governance_state()
    return {"conversation_id": conversation_id, "deleted": True}


@app.patch("/v1/conversations/{conversation_id}/context", response_model=ConversationDetailResponse)
def update_conversation_context(
    conversation_id: str,
    request: ConversationContextUpdateRequest,
) -> ConversationDetailResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    _require_conversation_access(conversation_id, user)
    try:
        session, monitor, compacted = state["conversation_store"].update_context_window(
            conversation_id=conversation_id,
            context_window_tokens=request.context_window_tokens,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "conversation_context_updated",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "conversation_id": conversation_id,
            "context_window_tokens": request.context_window_tokens,
            "compacted": compacted,
            "context_monitor": monitor,
            "lineage_tags": build_lineage_tags(settings=settings, route="conversation_context_updated"),
        },
    )
    return _conversation_detail_payload(session, settings)


@app.get("/v1/knowledge-graph", response_model=KnowledgeGraphResponse)
def get_knowledge_graph() -> KnowledgeGraphResponse:
    user = _current_user()
    kg = _knowledge_graph_for_user(user)
    return KnowledgeGraphResponse(
        nodes=[{"id": n.id, "type": n.type, "properties": n.properties} for n in kg.nodes.values()],
        edges=[{"source": e.source, "target": e.target, "type": e.type, "properties": e.properties} for e in kg.edges],
        summary_stats=kg.get_summary_stats()
    )


@app.get("/v1/knowledge-wiki", response_model=KnowledgeWikiListResponse)
def list_knowledge_wiki_pages() -> KnowledgeWikiListResponse:
    pages = state["knowledge_wiki_pages"]
    return KnowledgeWikiListResponse(
        total_pages=len(pages),
        pages=[
            KnowledgeWikiPageSummary(page_id=page.page_id, title=page.title, tags=list(page.tags))
            for page in pages
        ],
    )


@app.get("/v1/dossiers", response_model=DossierListResponse)
def list_dossiers(limit: int = 12) -> DossierListResponse:
    user = _current_user()
    normalized_limit = max(1, min(limit, 50))
    items = _dossier_list_items(normalized_limit, user)
    return DossierListResponse(
        total_items=len(items),
        items=items,
    )


@app.post("/v1/dossiers/upload", response_model=DossierUploadResponse)
def upload_dossier(payload: dict[str, Any] = Body(...)) -> DossierUploadResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    _require_dossier_shape(payload)

    dossier_id = str(payload["dossier_id"])
    if dossier_id in state["dossier_by_id"]:
        raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} already exists")
    review_program = _infer_review_program(payload)
    _require_process_access(user, review_program)
    payload["review_program"] = review_program

    settings.uploaded_dossiers_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.uploaded_dossiers_dir / f"{dossier_id}.json"
    stored_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    _refresh_dossier_state()
    _append_lifecycle_event(dossier_id, "dossier_uploaded", username=user["username"])

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "dossier_uploaded",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dossier_id": dossier_id,
            "stored_path": str(stored_path),
            "lineage_tags": build_lineage_tags(settings=settings, route="dossier_uploaded"),
        },
    )

    return DossierUploadResponse(
        dossier_id=dossier_id,
        message="Dossier uploaded and indexed for review.",
        stored_path=str(stored_path),
        review_program=review_program,
    )


@app.post("/v1/dossiers/intake", response_model=DossierUploadResponse)
async def intake_dossier_file(
    file: UploadFile = File(...),
    dossier_id: str = Form(...),
    country: str = Form(...),
    submission_date: str = Form(...),
    product_name: str = Form(...),
    inn_name: str = Form(...),
    applicant: str = Form(...),
    manufacturer: str = Form(...),
    facility_country: str = Form(...),
    review_program: str = Form("marketing_authorization"),
) -> DossierUploadResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    if dossier_id in state["dossier_by_id"]:
        raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} already exists")
    normalized_program = str(review_program).strip().lower()
    if normalized_program not in REVIEW_PROGRAMS:
        raise HTTPException(status_code=400, detail="review_program must be marketing_authorization or clinical_trial")
    _require_process_access(user, normalized_program)

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded intake file is empty")

    try:
        parsed_document = parse_uploaded_document(file.filename or "upload", payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    model_client = build_model_client(model_id=settings.model_id)
    dossier = build_dossier_from_raw_text(
        dossier_id=dossier_id,
        country=country,
        submission_date=submission_date,
        product_name=product_name,
        inn_name=inn_name,
        applicant=applicant,
        manufacturer=manufacturer,
        facility_country=facility_country,
        raw_text=parsed_document.text,
        source_filename=file.filename or "upload",
        extractor=model_client.extract_policy_signals,
        review_program=normalized_program,
        extraction_metadata={
            "extraction_method": parsed_document.extraction_method,
            "page_count": parsed_document.page_count,
            "image_count": parsed_document.image_count,
            "ocr_used": parsed_document.ocr_used,
            "warnings": list(parsed_document.warnings),
            "visual_evidence": list(parsed_document.visual_evidence),
        },
    )
    _require_dossier_shape(dossier)

    settings.uploaded_dossiers_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.uploaded_dossiers_dir / f"{dossier_id}.json"
    stored_path.write_text(json.dumps(dossier, ensure_ascii=True, indent=2), encoding="utf-8")
    _refresh_dossier_state()
    _append_lifecycle_event(dossier_id, "dossier_intake_uploaded", username=user["username"], details={"source_filename": file.filename})

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "dossier_intake_uploaded",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dossier_id": dossier_id,
            "source_filename": file.filename,
            "stored_path": str(stored_path),
            "extraction_method": parsed_document.extraction_method,
            "ocr_used": parsed_document.ocr_used,
            "page_count": parsed_document.page_count,
            "image_count": parsed_document.image_count,
            "lineage_tags": build_lineage_tags(settings=settings, route="dossier_intake_uploaded"),
        },
    )

    return DossierUploadResponse(
        dossier_id=dossier_id,
        message=f"Dossier intake from {file.filename} was parsed and indexed for review.",
        stored_path=str(stored_path),
        review_program=normalized_program,
    )


@app.get("/v1/sample-dossiers", response_model=SampleDossierListResponse)
def list_sample_dossiers() -> SampleDossierListResponse:
    settings: Settings = state["settings"]
    items: list[SampleDossierItem] = []
    for path in sorted(settings.sample_dossiers_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        product_name = str(payload.get("product", {}).get("product_name", "unknown product"))
        product_group = _derive_product_group(payload)
        application_type = _derive_application_type(payload)
        review_pathway = _derive_review_pathway(payload)
        items.append(
            SampleDossierItem(
                file_name=path.name,
                dossier_id=str(payload.get("dossier_id", path.stem)),
                description=str(
                    payload.get("demo_focus")
                    or f"Showcase dossier for {product_name}"
                ),
                download_url=f"/v1/sample-dossiers/{path.name}",
                product_group=product_group,
                application_type=application_type,
                review_pathway=review_pathway,
                document_condition=_derive_document_condition(payload),
                expected_outcome=_sample_expected_outcome(payload),
            )
        )
    return SampleDossierListResponse(total_items=len(items), items=items)


@app.get("/v1/sample-intake-files", response_model=SampleIncomingFileListResponse)
def list_sample_intake_files() -> SampleIncomingFileListResponse:
    settings: Settings = state["settings"]
    incoming_root = settings.sample_dossiers_dir / "incoming_files"
    catalog_path = incoming_root / "catalog.json"
    catalog: dict[str, Any] = {}
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    items: list[SampleIncomingFileItem] = []
    if incoming_root.exists():
        for path in sorted(incoming_root.glob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in {".pdf", ".txt", ".docx"}:
                continue
            media_type = {
                ".pdf": "application/pdf",
                ".txt": "text/plain",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }.get(suffix, "application/octet-stream")
            description = str(catalog.get(path.name, {}).get("description", path.stem.replace("_", " ").replace("-", " ")))
            item_meta = catalog.get(path.name, {})
            items.append(
                SampleIncomingFileItem(
                    file_name=path.name,
                    description=description,
                    media_type=media_type,
                    download_url=f"/v1/sample-intake-files/{path.name}",
                    product_group=str(item_meta.get("product_group") or ""),
                    application_type=str(item_meta.get("application_type") or ""),
                    review_pathway=str(item_meta.get("review_pathway") or ""),
                    document_condition=str(item_meta.get("document_condition") or ""),
                    expected_outcome=str(item_meta.get("expected_outcome") or ""),
                )
            )
    return SampleIncomingFileListResponse(total_items=len(items), items=items)


@app.get("/v1/sample-dossiers/{file_name}", include_in_schema=False)
def download_sample_dossier(file_name: str) -> FileResponse:
    path = (state["settings"].sample_dossiers_dir / file_name).resolve()
    sample_root = state["settings"].sample_dossiers_dir.resolve()
    if sample_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Sample dossier not found")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/v1/sample-intake-files/{file_name}", include_in_schema=False)
def download_sample_intake_file(file_name: str) -> FileResponse:
    incoming_root = (state["settings"].sample_dossiers_dir / "incoming_files").resolve()
    path = (incoming_root / file_name).resolve()
    if incoming_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Sample intake file not found")
    media_type = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/v1/knowledge-wiki/search", response_model=KnowledgeWikiSearchResponse)
def search_knowledge_wiki(request: KnowledgeWikiSearchRequest) -> KnowledgeWikiSearchResponse:
    settings: Settings = state["settings"]
    top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
    sub_queries, hits = _search_with_subqueries(
        retriever=state["knowledge_wiki_retriever"],
        query=request.query,
        top_k=top_k,
    )

    citations = [
        Citation(
            citation_id=hit.chunk.citation_id,
            dossier_id=hit.chunk.dossier_id,
            section_id=hit.chunk.section_id,
            section_title=hit.chunk.section_title,
            score=round(hit.score, 5),
            snippet=_snippet(hit.chunk.text),
        )
        for hit in hits
    ]

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "knowledge_wiki_search",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "query": request.query,
            "sub_queries": sub_queries,
            "top_k": top_k,
            "result_count": len(citations),
            "lineage_tags": build_lineage_tags(settings=settings, route="knowledge_wiki_search"),
            "memory": _build_memory_summary(settings).model_dump(),
        },
    )

    return KnowledgeWikiSearchResponse(
        query=request.query,
        sub_queries=sub_queries,
        total_hits=len(citations),
        citations=citations,
    )


@app.get("/v1/dossiers/{dossier_id}", response_model=DossierResponse)
def get_dossier(dossier_id: str) -> DossierResponse:
    user = _current_user()
    dossier = state["dossier_by_id"].get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {dossier_id} not found")
    lifecycle = _lifecycle_record(dossier_id)
    review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
    _require_process_access(user, review_program)
    _require_dossier_assignment_access(user, lifecycle)
    progress_state, progress_percent, progress_color = _dossier_progress_view(lifecycle)
    return DossierResponse(
        dossier_id=dossier["dossier_id"],
        country=dossier["country"],
        submission_date=dossier["submission_date"],
        organization=dossier["organization"],
        product=dossier["product"],
        labels=dossier["labels"],
        policy_signals=dossier["policy_signals"],
        section_count=len(dossier.get("sections", [])),
        status=str(lifecycle.get("status", "open")),
        assigned_reviewer=lifecycle.get("assigned_reviewer"),
        final_decision=lifecycle.get("final_decision"),
        review_type=str(lifecycle.get("review_type", "generic")),
        review_program=review_program,
        progress_state=progress_state,
        progress_percent=progress_percent,
        progress_color=progress_color,
    )


@app.post("/v1/retrieval/search", response_model=RetrievalSearchResponse)
def retrieval_search(request: RetrievalSearchRequest) -> RetrievalSearchResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    if request.dossier_id:
        dossier = state["dossier_by_id"].get(request.dossier_id)
        if dossier is None:
            raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")
        lifecycle = _lifecycle_record(request.dossier_id)
        _require_process_access(user, str(lifecycle.get("review_program", _infer_review_program(dossier))))
        _require_dossier_assignment_access(user, lifecycle)
    lineage_tags = build_lineage_tags(settings=settings, route="retrieval")
    top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
    sub_queries = decompose_query(request.query)
    citations: list[Citation] = []
    try:
        index_name = "current_dossier" if request.dossier_id else "all"
        search_response = tool_data(
            "search_vector_database",
            {
                "query": request.query,
                "index": index_name,
                "filters": {"dossier_id": request.dossier_id} if request.dossier_id else {},
                "top_k": top_k,
            },
        )
        rerank_response = tool_data(
            "rerank_search_results",
            {
                "query": request.query,
                "candidate_results": search_response["data"].get("results", []),
                "rerank_criteria": [
                    "regulatory relevance",
                    "section specificity",
                    "current dossier applicability",
                ],
                "top_k": top_k,
            },
        )
        citations = [
            Citation(
                citation_id=str(item.get("metadata", {}).get("citation_id") or item.get("chunk_id", "unknown")),
                dossier_id=str(item.get("metadata", {}).get("dossier_id") or request.dossier_id or "unknown"),
                section_id=str(item.get("metadata", {}).get("section_id") or item.get("chunk_id", "unknown")),
                section_title=str(item.get("metadata", {}).get("section_title") or "Retrieved evidence"),
                score=round(float(item.get("rerank_score", item.get("original_score", 0.0))), 5),
                snippet=_snippet(str(item.get("text", ""))),
            )
            for item in rerank_response["data"].get("reranked_results", [])
        ]
    except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
        sub_queries, hits = _search_with_subqueries(
            retriever=state["retriever"],
            query=request.query,
            top_k=top_k,
            dossier_id=request.dossier_id,
        )

        citations = [
            Citation(
                citation_id=hit.chunk.citation_id,
                dossier_id=hit.chunk.dossier_id,
                section_id=hit.chunk.section_id,
                section_title=hit.chunk.section_title,
                score=round(hit.score, 5),
                snippet=_snippet(hit.chunk.text),
            )
            for hit in hits
        ]

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "retrieval_search",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "query": request.query,
            "sub_queries": sub_queries,
            "dossier_id": request.dossier_id,
            "top_k": top_k,
            "result_count": len(citations),
            "lineage_tags": lineage_tags,
            "memory": _build_memory_summary(settings).model_dump(),
        },
    )

    return RetrievalSearchResponse(
        query=request.query,
        sub_queries=sub_queries,
        total_hits=len(citations),
        citations=citations,
    )


@app.post("/v1/review", response_model=ReviewResponse)
def review_dossier(request: ReviewRequest) -> ReviewResponse:
    metrics = InteractionMetrics()
    dossier = state["dossier_by_id"].get(request.dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")

    settings: Settings = state["settings"]
    user = _current_user()
    _require_process_access(user, _infer_review_program(dossier))
    _mark_dossier_in_review(request.dossier_id, user, request.review_type)
    selected_model_id = request.model_id or settings.model_id
    selected_model = _model_option_payload(settings, selected_model_id)
    conversation_session: dict[str, Any] | None = None
    conversation_context = ""
    conversation_monitor: ContextWindowMonitor | None = None
    
    conversation_id = request.conversation_id
    if conversation_id:
        _require_conversation_access(conversation_id, user)
        conversation_session = state["conversation_store"].get_session(conversation_id)
        if conversation_session is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
        conversation_context = build_model_context(conversation_session, settings)
    else:
        # Implicitly create a new conversation if one doesn't exist
        session, monitor = state["conversation_store"].create_session(
            title=_conversation_title_for_dossier(dossier, request.dossier_id),
            context_window_tokens=request.context_window_tokens,
            selected_model_id=selected_model_id,
            dossier_id=request.dossier_id,
        )
        conversation_id = session["conversation_id"]
        _register_conversation_owner(conversation_id, user["username"])
        conversation_session = session
        conversation_monitor = _context_monitor_payload(monitor)
        conversation_context = build_model_context(session, settings)

    _workflow_sequence_gate(
        dossier=dossier,
        question=request.question,
        conversation_id=conversation_id,
    )

    rewrite_plan = build_query_rewrite_plan(
        question=request.question,
        workspace="review",
        has_active_dossier=True,
        has_conversation=True,
    )
    intent = rewrite_plan.intent
    route_plan = plan_context_scope(intent, workspace="review")

    mem_before = _build_memory_summary(settings)
    if mem_before.system_available_ram_gb < settings.min_free_ram_gb:
        lineage_tags = build_lineage_tags(settings=settings, route="abstain", model_id=selected_model.runtime_model_id)
        
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=conversation_id,
            user_content=request.question,
            assistant_content="Abstained to protect stability under memory pressure on local host.",
            selected_model_id=selected_model.runtime_model_id,
            citations=[],
            dossier_id=request.dossier_id,
            metadata={"route": "abstain", "reason": "memory_pressure_guard"},
        )
        conversation_monitor = _context_monitor_payload(monitor)
        conversation_session = updated_session
        
        metrics.finalize(input_text=request.question, output_text="Abstained")
        append_audit_record(
            path=settings.audit_log_path,
            record={
                "event": "review_decision",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "dossier_id": request.dossier_id,
                "conversation_id": conversation_id,
                "question": request.question,
                "route": "abstain",
                "recommendation": "abstain",
                "abstained": True,
                "abstain_reason": "memory_pressure_guard",
                "policy_rule_hits": ["memory_pressure_guard"],
                "verifier": {
                    "grounded_claim_rate": 0.0,
                    "unsupported_critical_claim_rate": 1.0,
                    "passed": False,
                },
                "citation_count": 0,
                "lineage_tags": lineage_tags,
                "memory": mem_before.model_dump(),
                "selected_model_id": selected_model_id,
                "context_monitor": conversation_monitor.model_dump() if conversation_monitor else None,
                "metrics": {
                    "latency_seconds": metrics.latency_seconds,
                    "input_tokens_estimate": metrics.input_tokens_estimate,
                    "output_tokens_estimate": metrics.output_tokens_estimate,
                },
            },
        )
        sub_queries, _ = _search_with_subqueries(
            retriever=state["retriever"],
            query=request.question,
            top_k=settings.default_top_k,
            dossier_id=request.dossier_id,
        )
        return ReviewResponse(
            dossier_id=request.dossier_id,
            selected_model=selected_model,
            sub_queries=sub_queries,
            conversation_id=conversation_id,
            review_type=request.review_type,
            context_monitor=conversation_monitor,
            recommendation="abstain",
            confidence=0.0,
            route="abstain",
            abstained=True,
            abstain_reason="memory_pressure_guard",
            rationale="Abstained to protect stability under memory pressure on local host.",
            policy_rule_hits=["memory_pressure_guard"],
            section_diagnostics=[],
            citations=[],
            verifier=VerifierSummary(
                grounded_claim_rate=0.0,
                unsupported_critical_claim_rate=1.0,
                passed=False,
            ),
            memory=mem_before,
            lineage_tags=lineage_tags,
            amr_stewardship=AmrStewardshipSummary(
                applies=False,
                normalized_ingredient="not_available",
                normalization_source="not_evaluated",
                active_moiety="not_available",
                parent_compound="not_available",
                pubchem_cid="not_available",
                canonical_smiles="not_available",
                inchikey="not_available",
                chembl_id="not_available",
                unichem_id="not_available",
                aware_category="not_applicable",
                amr_unmet_need="not_applicable",
                targets_mdr_pathogen=False,
                glass_resistance_trend="not_applicable",
                similarity_to_existing_watch="not_applicable",
                existing_watch_comparator="not_applicable",
                chemistry_source="not_evaluated",
                authorization_control="standard_authorization",
                fast_track_candidate=False,
                restricted_authorization=False,
                watch_similarity_restriction=False,
                source_mode="not_evaluated",
                source_trace=["AMR source evaluation was skipped because the request abstained under memory pressure."],
                rationale="AMR stewardship evaluation was skipped because the request abstained under memory pressure.",
            ),
            metrics=InteractionMetricsPayload(
                latency_seconds=metrics.latency_seconds,
                input_tokens_estimate=metrics.input_tokens_estimate,
                output_tokens_estimate=metrics.output_tokens_estimate,
            ),
            intent=intent,
            response_contract=route_plan.response_contract,
            model_packet_version="reason_and_route_v1",
        )

    # Use ReasoningEngine for multi-stage RAG
    engine = ReasoningEngine(model_id=selected_model.runtime_model_id, retriever=state["retriever"])
    reviewer_graph = _knowledge_graph_for_user(user)
    graph_query_result: dict[str, Any] | None = None
    if intent == VISUALIZATION_INTENT or any(term in request.question.lower() for term in ("graph", "network", "connected", "link")):
        try:
            graph_query_result = tool_data(
                "query_knowledge_graph",
                {
                    "question": request.question,
                    "graph_payload": reviewer_graph.to_json(),
                    "summary_stats": reviewer_graph.get_summary_stats(),
                },
            )["data"]
        except (RegulatoryMCPClientError, KeyError, TypeError, ValueError):
            graph_query_result = None
    result = engine.orchestrate(
        dossier=dossier,
        question=request.question,
        workspace="review",
        conversation_context=conversation_context,
        force_fallback=request.force_fallback,
        review_state={
            "summary_stats": reviewer_graph.get_summary_stats(),
            "knowledge_graph": reviewer_graph.to_json(),
            "graph_query_result": graph_query_result,
            "review_type": request.review_type,
        },
    )
    return _finalize_review_dossier_response(
        request=request,
        settings=settings,
        selected_model=selected_model,
        route_plan=route_plan,
        result=result,
        dossier=dossier,
        conversation_id=conversation_id,
        metrics=metrics,
        conversation_context=conversation_context,
    )


def _finalize_review_dossier_response(
    *,
    request: ReviewRequest,
    settings: Settings,
    selected_model: ModelOptionPayload,
    route_plan: RoutePlan,
    result: Any,
    dossier: dict[str, Any],
    conversation_id: str,
    metrics: Any,
    conversation_context: str,
) -> ReviewResponse:
    user = _current_user()
    _record_workflow_progress(
        dossier_id=request.dossier_id,
        question=request.question,
        dossier=dossier,
        review_payload={
            "recommendation": result.recommendation,
            "policy_rule_hits": result.policy_rule_hits,
            "section_diagnostics": result.section_diagnostics,
            "amr_stewardship": result.amr_stewardship,
            "workflow_summary": result.workflow_summary,
        },
        conversation_id=conversation_id,
    )
    is_first_turn_in_conversation = not conversation_context.strip()
    result.rationale = _augment_review_rationale(
        rationale=result.rationale,
        dossier=dossier,
        conversation_id=conversation_id,
        recommendation=result.recommendation,
        confidence=result.confidence,
        workflow_summary=result.workflow_summary,
        question=request.question,
        force_data_quality_intro=is_first_turn_in_conversation,
    )
    metrics.finalize(input_text=request.question + " " + conversation_context, output_text=result.rationale)
    mem_after = _build_memory_summary(settings)
    lineage_tags = build_lineage_tags(settings=settings, route=result.route, model_id=selected_model.runtime_model_id)

    budget_exceeded = (
        (result.route == "standard" and mem_after.process_rss_gb > settings.standard_route_rss_limit_gb)
        or (result.route == "fallback" and mem_after.process_rss_gb > settings.fallback_route_rss_limit_gb)
    )
    if budget_exceeded:
        # Keep grounded regulatory decisions intact; memory pressure is logged as an operational signal.
        if "memory_budget_exceeded" not in result.policy_rule_hits:
            result.policy_rule_hits = result.policy_rule_hits + ["memory_budget_exceeded"]
        result.confidence = min(result.confidence, 0.25)
        if result.abstained:
            result.abstain_reason = result.abstain_reason or "memory_budget_exceeded"
        else:
            result.abstain_reason = None
            memory_note = "Operational note: memory budget threshold was exceeded after response generation."
            if memory_note not in result.rationale:
                result.rationale = f"{result.rationale}\n\n{memory_note}".strip()

    citations = [
        Citation(
            citation_id=hit.chunk.citation_id,
            dossier_id=hit.chunk.dossier_id,
            section_id=hit.chunk.section_id,
            section_title=hit.chunk.section_title,
            score=round(hit.score, 5),
            snippet=_snippet(hit.chunk.text),
        )
        for hit in result.hits
    ]
    append_metadata = {
        "route": result.route,
        "intent": result.intent,
        "response_contract": result.response_contract,
        "recommendation": result.recommendation,
        "abstained": result.abstained,
        "review_type": request.review_type,
        "metrics": {
            "latency_seconds": metrics.latency_seconds,
            "input_tokens_estimate": metrics.input_tokens_estimate,
            "output_tokens_estimate": metrics.output_tokens_estimate,
        },
    }
    try:
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=conversation_id,
            user_content=request.question,
            assistant_content=result.rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[citation.model_dump() for citation in citations],
            dossier_id=request.dossier_id,
            metadata=append_metadata,
        )
    except KeyError:
        # Recover from stale/missing conversation ids during long-running flows by recreating a session.
        session, monitor = state["conversation_store"].create_session(
            title=_conversation_title_for_dossier(dossier, request.dossier_id),
            context_window_tokens=request.context_window_tokens,
            selected_model_id=selected_model.runtime_model_id,
            dossier_id=request.dossier_id,
        )
        conversation_id = str(session["conversation_id"])
        _register_conversation_owner(conversation_id, user["username"])
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=conversation_id,
            user_content=request.question,
            assistant_content=result.rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[citation.model_dump() for citation in citations],
            dossier_id=request.dossier_id,
            metadata=append_metadata,
        )
    conversation_monitor = _context_monitor_payload(monitor)
    _ = updated_session
    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "review_decision",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dossier_id": request.dossier_id,
            "conversation_id": conversation_id,
            "question": request.question,
            "sub_queries": result.sub_queries,
            "route": result.route,
            "intent": result.intent,
            "response_contract": result.response_contract,
            "model_packet_version": result.model_packet_version,
            "context_scope": route_plan.context_scope.__dict__,
            "retrieval_domains": list(route_plan.retrieval_domains),
            "recommendation": result.recommendation,
            "abstained": result.abstained,
            "abstain_reason": result.abstain_reason,
            "policy_rule_hits": result.policy_rule_hits,
            "verifier": result.verifier,
            "evidence_packet": result.evidence_packet,
            "judge_decision": result.judge_decision,
            "judge_verifier": result.judge_verifier,
            "judge_aggregate": result.judge_aggregate,
            "citation_count": len(citations),
            "selected_model_id": selected_model.runtime_model_id,
            "lineage_tags": lineage_tags,
            "memory": mem_after.model_dump(),
            "context_monitor": conversation_monitor.model_dump() if conversation_monitor else None,
            "metrics": {
                "latency_seconds": metrics.latency_seconds,
                "input_tokens_estimate": metrics.input_tokens_estimate,
                "output_tokens_estimate": metrics.output_tokens_estimate,
            },
        },
    )
    return ReviewResponse(
        dossier_id=request.dossier_id,
        selected_model=selected_model,
        sub_queries=result.sub_queries,
        intent=result.intent,
        response_contract=result.response_contract,
        model_packet_version=result.model_packet_version,
        conversation_id=conversation_id,
        review_type=request.review_type,
        context_monitor=conversation_monitor,
        recommendation=result.recommendation,
        confidence=result.confidence,
        route=result.route,
        abstained=result.abstained,
        abstain_reason=result.abstain_reason,
        rationale=result.rationale,
        chain_of_thought=result.chain_of_thought,
        findings_summary_markdown=result.findings_summary_markdown,
        workflow_summary=result.workflow_summary,
        policy_rule_hits=result.policy_rule_hits,
        section_diagnostics=[SectionDiagnostic(**diag) for diag in result.section_diagnostics],
        citations=citations,
        verifier=VerifierSummary(**result.verifier),
        memory=mem_after,
        lineage_tags=lineage_tags,
        amr_stewardship=AmrStewardshipSummary(**result.amr_stewardship),
        metrics=InteractionMetricsPayload(
            latency_seconds=metrics.latency_seconds,
            input_tokens_estimate=metrics.input_tokens_estimate,
            output_tokens_estimate=metrics.output_tokens_estimate,
        ),
        visualization_data=_enforce_chart_title_identity(result.visualization_data, dossier=dossier),
    )


def _dossier_progress_view(lifecycle: dict[str, Any]) -> tuple[str, int, str]:
    status = str(lifecycle.get("status", "open"))
    if status == "done":
        return ("done", 100, "green")
    if status == "in_review":
        return ("in_progress", 60, "amber")
    return ("not_started", 0, "grey")


def _require_dossier_assignment_access(user: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    if _is_superuser(user):
        return
    assigned = lifecycle.get("assigned_reviewer")
    if assigned != user["username"]:
        raise HTTPException(status_code=403, detail="This dossier is not assigned to you.")


def _hours_between(start_iso: str | None, end_iso: str | None) -> float | None:
    if not start_iso or not end_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = (end - start).total_seconds() / 3600.0
    if delta < 0:
        return None
    return round(delta, 4)


def _reviewer_performance_summary() -> dict[str, Any]:
    by_reviewer: dict[str, list[float]] = {}
    for lifecycle in state["governance_state"]["dossier_lifecycle"].values():
        reviewer = lifecycle.get("assigned_reviewer")
        if not reviewer:
            continue
        start_iso = None
        end_iso = None
        for event in lifecycle.get("history", []):
            event_name = str(event.get("event", ""))
            if event_name == "review_started" and event.get("username") == reviewer and start_iso is None:
                start_iso = str(event.get("created_at_utc", ""))
            if event_name == "report_completed":
                end_iso = str(event.get("created_at_utc", ""))
        if lifecycle.get("status") == "done":
            end_iso = end_iso or str(lifecycle.get("decision_date", ""))
        tot_hours = _hours_between(start_iso, end_iso)
        if tot_hours is None:
            continue
        by_reviewer.setdefault(str(reviewer), []).append(tot_hours)

    reviewer_rows: list[dict[str, Any]] = []
    for reviewer, values in by_reviewer.items():
        avg = round(sum(values) / len(values), 4)
        struggle = "none"
        if avg > 72:
            struggle = "high_turnaround_time"
        elif avg > 48:
            struggle = "moderate_turnaround_time"
        reviewer_rows.append(
            {
                "reviewer_username": reviewer,
                "completed_reviews": len(values),
                "average_tot_hours": avg,
                "fastest_tot_hours": min(values),
                "slowest_tot_hours": max(values),
                "struggle_signal": struggle,
            }
        )
    reviewer_rows.sort(key=lambda row: row["average_tot_hours"])
    overall = [row["average_tot_hours"] for row in reviewer_rows]
    return {
        "overall_average_tot_hours": round(sum(overall) / len(overall), 4) if overall else 0.0,
        "fastest_reviewer_username": reviewer_rows[0]["reviewer_username"] if reviewer_rows else None,
        "slowest_reviewer_username": reviewer_rows[-1]["reviewer_username"] if reviewer_rows else None,
        "reviewers": reviewer_rows,
    }


def _reviewer_dashboard_summary(user: dict[str, Any]) -> dict[str, Any]:
    username = str(user["username"])
    lifecycle_map = state["governance_state"].get("dossier_lifecycle", {})
    visible_dossiers = {str(d.get("dossier_id", "")) for d in _accessible_dossiers_for_user(user)}

    assigned_to_me = 0
    in_progress = 0
    finished_reviews = 0
    dossiers_approved = 0
    dossiers_queried = 0
    tot_hours_values: list[float] = []

    for dossier_id, lifecycle in lifecycle_map.items():
        if dossier_id not in visible_dossiers:
            continue
        if lifecycle.get("assigned_reviewer") != username:
            continue
        assigned_to_me += 1
        status = str(lifecycle.get("status", "open"))
        if status == "in_review":
            in_progress += 1
        if status == "done":
            finished_reviews += 1
            final_decision = str(lifecycle.get("final_decision", "")).strip().lower()
            if final_decision in {"acceptable", "acceptable_with_conditions"}:
                dossiers_approved += 1
            elif final_decision:
                dossiers_queried += 1

            start_iso = None
            end_iso = None
            for event in lifecycle.get("history", []):
                event_name = str(event.get("event", ""))
                if event_name == "review_started" and event.get("username") == username and start_iso is None:
                    start_iso = str(event.get("created_at_utc", ""))
                if event_name == "report_completed":
                    end_iso = str(event.get("created_at_utc", ""))
            end_iso = end_iso or str(lifecycle.get("decision_date", ""))
            tot = _hours_between(start_iso, end_iso)
            if tot is not None:
                tot_hours_values.append(tot)

    reports_generated = 0
    reports_root = _reports_dir(state["settings"])
    if reports_root.exists():
        for report_dir in reports_root.iterdir():
            if not report_dir.is_dir():
                continue
            snapshot_path = report_dir / "report.json"
            if not snapshot_path.exists():
                continue
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if str(snapshot.get("reviewer_username", "")) != username:
                continue
            dossier_id = str(snapshot.get("dossier_id", ""))
            if dossier_id and dossier_id in visible_dossiers:
                reports_generated += 1

    average_tot_hours = round(sum(tot_hours_values) / len(tot_hours_values), 4) if tot_hours_values else 0.0
    return {
        "reviewer_username": username,
        "assigned_to_me": assigned_to_me,
        "in_progress": in_progress,
        "finished_reviews": finished_reviews,
        "reports_generated": reports_generated,
        "dossiers_reviewed": finished_reviews,
        "dossiers_approved": dossiers_approved,
        "dossiers_queried": dossiers_queried,
        "average_tot_hours": average_tot_hours,
    }


def _admin_dashboard_summary(user: dict[str, Any]) -> dict[str, Any]:
    scopes = _user_process_scopes(user)
    lifecycle_map = state["governance_state"].get("dossier_lifecycle", {})

    overall_total = 0
    overall_not_started = 0
    overall_in_progress = 0
    overall_done = 0
    by_reviewer: dict[str, dict[str, int]] = {}

    for dossier in state["dossiers"]:
        dossier_id = str(dossier.get("dossier_id", ""))
        lifecycle = lifecycle_map.get(dossier_id) or _lifecycle_record(dossier_id)
        review_program = str(lifecycle.get("review_program", _infer_review_program(dossier)))
        if review_program not in scopes:
            continue
        overall_total += 1
        status = str(lifecycle.get("status", "open"))
        if status == "done":
            overall_done += 1
        elif status == "in_review":
            overall_in_progress += 1
        else:
            overall_not_started += 1

        reviewer = str(lifecycle.get("assigned_reviewer") or "").strip()
        if not reviewer:
            continue
        bucket = by_reviewer.setdefault(
            reviewer,
            {
                "assigned_total": 0,
                "not_started": 0,
                "in_progress": 0,
                "done": 0,
            },
        )
        bucket["assigned_total"] += 1
        if status == "done":
            bucket["done"] += 1
        elif status == "in_review":
            bucket["in_progress"] += 1
        else:
            bucket["not_started"] += 1

    progress_rows = [
        {
            "reviewer_username": reviewer,
            **stats,
        }
        for reviewer, stats in by_reviewer.items()
    ]
    progress_rows.sort(key=lambda row: (row["done"], -row["in_progress"]), reverse=True)

    perf = _reviewer_performance_summary()
    return {
        "overall_total_dossiers": overall_total,
        "overall_not_started": overall_not_started,
        "overall_in_progress": overall_in_progress,
        "overall_done": overall_done,
        "overall_average_tot_hours": float(perf["overall_average_tot_hours"]),
        "fastest_reviewer_username": perf["fastest_reviewer_username"],
        "slowest_reviewer_username": perf["slowest_reviewer_username"],
        "progress_by_reviewer": progress_rows,
        "tot_by_reviewer": perf["reviewers"],
    }
    result.rationale = _augment_review_rationale(
        rationale=result.rationale,
        dossier=dossier,
        conversation_id=conversation_id,
        recommendation=result.recommendation,
        confidence=result.confidence,
        workflow_summary=result.workflow_summary,
        question=request.question,
    )
    metrics.finalize(input_text=request.question + " " + conversation_context, output_text=result.rationale)
    
    mem_after = _build_memory_summary(settings)
    lineage_tags = build_lineage_tags(settings=settings, route=result.route, model_id=selected_model.runtime_model_id)

    budget_exceeded = (
        (result.route == "standard" and mem_after.process_rss_gb > settings.standard_route_rss_limit_gb)
        or (result.route == "fallback" and mem_after.process_rss_gb > settings.fallback_route_rss_limit_gb)
    )
    if budget_exceeded:
        result.recommendation = "abstain"
        result.abstained = True
        result.abstain_reason = "memory_budget_exceeded"
        result.confidence = min(result.confidence, 0.25)
        result.policy_rule_hits = result.policy_rule_hits + ["memory_budget_exceeded"]

    citations = [
        Citation(
            citation_id=hit.chunk.citation_id,
            dossier_id=hit.chunk.dossier_id,
            section_id=hit.chunk.section_id,
            section_title=hit.chunk.section_title,
            score=round(hit.score, 5),
            snippet=_snippet(hit.chunk.text),
        )
        for hit in result.hits
    ]

    updated_session, monitor, _ = state["conversation_store"].append_turn(
        conversation_id=conversation_id,
        user_content=request.question,
        assistant_content=result.rationale,
        selected_model_id=selected_model.runtime_model_id,
        citations=[citation.model_dump() for citation in citations],
        dossier_id=request.dossier_id,
        metadata={
            "route": result.route,
            "intent": result.intent,
            "response_contract": result.response_contract,
            "recommendation": result.recommendation,
            "abstained": result.abstained,
            "review_type": request.review_type,
            "metrics": {
                "latency_seconds": metrics.latency_seconds,
                "input_tokens_estimate": metrics.input_tokens_estimate,
                "output_tokens_estimate": metrics.output_tokens_estimate,
            },
        },
    )
    conversation_monitor = _context_monitor_payload(monitor)
    conversation_session = updated_session

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "review_decision",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dossier_id": request.dossier_id,
            "conversation_id": conversation_id,
            "question": request.question,
            "sub_queries": result.sub_queries,
            "route": result.route,
            "intent": result.intent,
            "response_contract": result.response_contract,
            "model_packet_version": result.model_packet_version,
            "context_scope": route_plan.context_scope.__dict__,
            "retrieval_domains": list(route_plan.retrieval_domains),
            "recommendation": result.recommendation,
            "abstained": result.abstained,
            "abstain_reason": result.abstain_reason,
            "policy_rule_hits": result.policy_rule_hits,
            "verifier": result.verifier,
            "evidence_packet": result.evidence_packet,
            "judge_decision": result.judge_decision,
            "judge_verifier": result.judge_verifier,
            "judge_aggregate": result.judge_aggregate,
            "citation_count": len(citations),
            "selected_model_id": selected_model.runtime_model_id,
            "lineage_tags": lineage_tags,
            "memory": mem_after.model_dump(),
            "context_monitor": conversation_monitor.model_dump() if conversation_monitor else None,
            "metrics": {
                "latency_seconds": metrics.latency_seconds,
                "input_tokens_estimate": metrics.input_tokens_estimate,
                "output_tokens_estimate": metrics.output_tokens_estimate,
            },
        },
    )
    _record_workflow_progress(
        dossier_id=request.dossier_id,
        question=request.question,
        dossier=dossier,
        review_payload={
            "recommendation": result.recommendation,
            "policy_rule_hits": result.policy_rule_hits,
            "section_diagnostics": result.section_diagnostics,
            "amr_stewardship": result.amr_stewardship,
            "workflow_summary": result.workflow_summary,
        },
        conversation_id=conversation_id,
    )
    _record_review_observation(
        dossier_id=request.dossier_id,
        recommendation=result.recommendation,
        confidence=result.confidence,
        policy_rule_hits=list(result.policy_rule_hits or []),
        section_diagnostics=list(result.section_diagnostics or []),
        reviewer_username=str(user.get("username", "unknown")),
    )

    return ReviewResponse(
        dossier_id=request.dossier_id,
        selected_model=selected_model,
        sub_queries=result.sub_queries,
        intent=result.intent,
        response_contract=result.response_contract,
        model_packet_version=result.model_packet_version,
        conversation_id=conversation_id,
        review_type=request.review_type,
        context_monitor=conversation_monitor,
        recommendation=result.recommendation,
        confidence=result.confidence,
        route=result.route,
        abstained=result.abstained,
        abstain_reason=result.abstain_reason,
        rationale=result.rationale,
        chain_of_thought=result.chain_of_thought,
        findings_summary_markdown=result.findings_summary_markdown,
        workflow_summary=result.workflow_summary,
        policy_rule_hits=result.policy_rule_hits,
        section_diagnostics=[SectionDiagnostic(**diag) for diag in result.section_diagnostics],
        citations=citations,
        verifier=VerifierSummary(**result.verifier),
        memory=mem_after,
        lineage_tags=lineage_tags,
        amr_stewardship=AmrStewardshipSummary(**result.amr_stewardship),
        metrics=InteractionMetricsPayload(
            latency_seconds=metrics.latency_seconds,
            input_tokens_estimate=metrics.input_tokens_estimate,
            output_tokens_estimate=metrics.output_tokens_estimate,
        ),
        visualization_data=_enforce_chart_title_identity(result.visualization_data, dossier=dossier),
    )


@app.post("/v1/assistant/message", response_model=AssistantMessageResponse)
def assistant_message(request: AssistantMessageRequest) -> AssistantMessageResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    if _is_superuser(user) and _is_manager_performance_query(request.question):
        selected_model_id = request.model_id or settings.model_id
        selected_model = _model_option_payload(settings, selected_model_id)
        rationale = _manager_performance_rationale(request.question)
        return AssistantMessageResponse(
            workspace=request.workspace,
            dossier_id=request.dossier_id,
            selected_model=selected_model,
            intent="manager_analytics",
            response_contract="manager_analytics_v1",
            model_packet_version="manager_analytics_v1",
            sub_queries=[],
            conversation_id=request.conversation_id,
            context_monitor=None,
            recommendation=None,
            route="manager_analytics",
            abstained=False,
            rationale=rationale,
            findings_summary_markdown=None,
            workflow_summary=None,
            citations=[],
            amr_stewardship=None,
        )
    if request.dossier_id:
        dossier = state["dossier_by_id"].get(request.dossier_id)
        if dossier is None:
            raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")
        _require_process_access(user, _infer_review_program(dossier))
        _require_dossier_assignment_access(user, _lifecycle_record(request.dossier_id))
        _workflow_sequence_gate(
            dossier=dossier,
            question=request.question,
            conversation_id=request.conversation_id,
        )
    selected_model_id = request.model_id or settings.model_id
    selected_model = _model_option_payload(settings, selected_model_id)
    conversation_context = ""
    conversation_monitor: ContextWindowMonitor | None = None
    if request.conversation_id:
        _require_conversation_access(request.conversation_id, user)
        conversation_session = state["conversation_store"].get_session(request.conversation_id)
        if conversation_session is None:
            raise HTTPException(status_code=404, detail=f"Conversation {request.conversation_id} not found")
        conversation_context = build_model_context(conversation_session, settings)
        conversation_monitor = _context_monitor_payload(build_context_monitor(conversation_session, settings))

    rewrite_plan = build_query_rewrite_plan(
        question=request.question,
        workspace=request.workspace,
        has_active_dossier=bool(request.dossier_id),
        has_conversation=bool(request.conversation_id),
    )
    effective_question = rewrite_plan.rewritten_question
    intent = rewrite_plan.intent
    route_plan = plan_context_scope(intent, workspace=request.workspace)


    if intent == CHAT_ONLY_INTENT:
        if not request.conversation_id:
            # Create session for chat only if needed
            session, monitor = state["conversation_store"].create_session(
                title=f"Chat: {request.question[:30]}...",
                context_window_tokens=request.context_window_tokens,
                selected_model_id=selected_model_id,
                dossier_id=request.dossier_id,
            )
            request.conversation_id = session["conversation_id"]
            _register_conversation_owner(request.conversation_id, user["username"])
            conversation_monitor = _context_monitor_payload(monitor)
            conversation_context = build_model_context(session, settings)

        packet = assemble_model_packet(
            question=effective_question,
            workspace=request.workspace,
            route_plan=route_plan,
            dossier_id=request.dossier_id,
            conversation_context=conversation_context,
            review_state={"workspace": request.workspace, "conversation_id": request.conversation_id},
        )
        rationale = _chat_only_rationale(effective_question)
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=request.conversation_id,
            user_content=request.question,
            assistant_content=rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[],
            dossier_id=request.dossier_id,
            metadata={
                "route": "chat_only",
                "intent": intent,
                "response_contract": route_plan.response_contract,
                "workspace": request.workspace,
            },
        )
        conversation_monitor = _context_monitor_payload(monitor)
        return AssistantMessageResponse(
            workspace=request.workspace,
            dossier_id=request.dossier_id,
            selected_model=selected_model,
            intent=intent,
            response_contract=route_plan.response_contract,
            model_packet_version=packet.packet_version,
            sub_queries=[],
            conversation_id=request.conversation_id,
            context_monitor=conversation_monitor,
            recommendation=None,
            route="chat_only",
            abstained=False,
            rationale=rationale,
            findings_summary_markdown=None,
            workflow_summary=None,
            citations=[],
            amr_stewardship=None,
        )

    requested_workflow_step = _infer_requested_workflow_step(request.question) if request.dossier_id else None

    if intent in {WIKI_GUIDANCE_INTENT, POLICY_GUIDANCE, MIXED_INTENT} and not requested_workflow_step:
        if not request.conversation_id:
            session, monitor = state["conversation_store"].create_session(
                title=f"Wiki: {request.question[:30]}...",
                context_window_tokens=request.context_window_tokens,
                selected_model_id=selected_model_id,
                dossier_id=request.dossier_id,
            )
            request.conversation_id = session["conversation_id"]
            _register_conversation_owner(request.conversation_id, user["username"])
            conversation_monitor = _context_monitor_payload(monitor)
            conversation_context = build_model_context(session, settings)

        top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
        sub_queries, wiki_hits = _search_with_subqueries(
            retriever=state["knowledge_wiki_retriever"],
            query=effective_question,
            top_k=max(2, min(4, top_k)),
        )
        dossier = state["dossier_by_id"].get(request.dossier_id) if request.dossier_id else None
        packet = assemble_model_packet(
            question=effective_question,
            workspace=request.workspace,
            route_plan=route_plan,
            dossier_id=request.dossier_id,
            conversation_context=conversation_context,
            wiki_hits=_hit_payloads(wiki_hits),
            review_state={"workspace": request.workspace, "conversation_id": request.conversation_id},
        )
        citations = [
            Citation(
                citation_id=hit.chunk.citation_id,
                dossier_id=hit.chunk.dossier_id,
                section_id=hit.chunk.section_id,
                section_title=hit.chunk.section_title,
                score=round(hit.score, 5),
                snippet=_snippet(hit.chunk.text),
            )
            for hit in wiki_hits
        ]
        rationale = (
            _policy_guidance_rationale(effective_question, wiki_hits, dossier=dossier)
            if intent in {POLICY_GUIDANCE, MIXED_INTENT}
            else _wiki_guidance_rationale(effective_question, wiki_hits)
        )
        if dossier is not None and _is_sop_information_query(request.question):
            rationale = f"{rationale}\n\n{_build_sop_status_markdown(dossier=dossier, conversation_id=request.conversation_id)}".strip()
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=request.conversation_id,
            user_content=request.question,
            assistant_content=rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[citation.model_dump() for citation in citations],
            dossier_id=request.dossier_id,
            metadata={
                "route": "knowledge_wiki",
                "intent": intent,
                "response_contract": route_plan.response_contract,
                "workspace": request.workspace,
            },
        )
        if dossier is not None:
            _record_workflow_progress(
                dossier_id=str(dossier.get("dossier_id", request.dossier_id)),
                question=request.question,
                dossier=dossier,
                review_payload={"policy_rule_hits": [], "section_diagnostics": [], "amr_stewardship": {"applies": False}},
                conversation_id=request.conversation_id,
            )
        conversation_monitor = _context_monitor_payload(monitor)
        return AssistantMessageResponse(
            workspace=request.workspace,
            dossier_id=request.dossier_id,
            selected_model=selected_model,
            intent=intent,
            response_contract=route_plan.response_contract,
            model_packet_version=packet.packet_version,
            sub_queries=sub_queries,
            conversation_id=request.conversation_id,
            context_monitor=conversation_monitor,
            recommendation=None,
            route="knowledge_wiki",
            abstained=False,
            rationale=rationale,
            findings_summary_markdown=None,
            workflow_summary=None,
            citations=citations,
            amr_stewardship=None,
        )

    if not request.dossier_id and intent not in (VISUALIZATION_INTENT, HISTORICAL_TREND):
        raise HTTPException(status_code=400, detail="This request needs an active dossier. Select or upload a dossier before continuing.")

    if not request.dossier_id:
        if not request.conversation_id:
             session, monitor = state["conversation_store"].create_session(
                title=f"Aggregate: {request.question[:30]}...",
                context_window_tokens=request.context_window_tokens,
                selected_model_id=selected_model_id,
            )
             request.conversation_id = session["conversation_id"]
             _register_conversation_owner(request.conversation_id, user["username"])
             conversation_monitor = _context_monitor_payload(monitor)
             conversation_context = build_model_context(session, settings)

        # For aggregate queries without a specific dossier, we use a mock/empty dossier 
        # but provide the full review_state for analysis.
        engine = ReasoningEngine(model_id=selected_model.runtime_model_id, retriever=state["retriever"])
        reviewer_graph = _knowledge_graph_for_user(user)
        graph_query_result: dict[str, Any] | None = None
        if intent == VISUALIZATION_INTENT or any(term in request.question.lower() for term in ("graph", "network", "connected", "link")):
            try:
                graph_query_result = tool_data(
                    "query_knowledge_graph",
                    {
                        "question": request.question,
                        "graph_payload": reviewer_graph.to_json(),
                        "summary_stats": reviewer_graph.get_summary_stats(),
                    },
                )["data"]
            except (RegulatoryMCPClientError, KeyError, TypeError, ValueError):
                graph_query_result = None
        result = engine.orchestrate(
            dossier={"dossier_id": "aggregate", "sections": [], "product": {}, "organization": {}, "policy_signals": {}, "labels": {}, "country": "Global", "submission_date": "2026-04-15"},
            question=request.question,
            workspace=request.workspace,
            conversation_context=conversation_context,
            force_fallback=request.force_fallback,
            review_state={
                "summary_stats": reviewer_graph.get_summary_stats(),
                "knowledge_graph": reviewer_graph.to_json(),
                "graph_query_result": graph_query_result,
                "review_type": request.review_type,
            },
        )
        
        # Append turn to aggregate session
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=request.conversation_id,
            user_content=request.question,
            assistant_content=result.rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[],
            metadata={
                "route": result.route,
                "intent": result.intent or intent,
                "response_contract": result.response_contract or route_plan.response_contract,
                "workspace": request.workspace,
            },
        )
        conversation_monitor = _context_monitor_payload(monitor)

        return AssistantMessageResponse(
            workspace=request.workspace,
            dossier_id=None,
            selected_model=selected_model,
            intent=result.intent or intent,
            response_contract=result.response_contract or route_plan.response_contract,
            model_packet_version=result.model_packet_version or "mcp_aggregate_v1",
            sub_queries=result.sub_queries,
            conversation_id=request.conversation_id,
            context_monitor=conversation_monitor,
            recommendation=None,
            route=result.route,
            abstained=result.abstained,
            rationale=result.rationale,
            chain_of_thought=result.chain_of_thought,
            findings_summary_markdown=result.findings_summary_markdown,
            workflow_summary=result.workflow_summary,
            citations=[],
            amr_stewardship=None,
            visualization_data=result.visualization_data,
        )

    review_response = review_dossier(
        ReviewRequest(
            dossier_id=request.dossier_id,
            workspace=request.workspace,
            question=request.question,
            top_k=request.top_k,
            force_fallback=request.force_fallback,
            model_id=request.model_id,
            conversation_id=request.conversation_id,
            context_window_tokens=request.context_window_tokens,
            review_type=request.review_type,
        )
    )
    return AssistantMessageResponse(
        workspace=request.workspace,
        dossier_id=review_response.dossier_id,
        selected_model=review_response.selected_model,
        intent=review_response.intent or intent,
        response_contract=review_response.response_contract or route_plan.response_contract,
        model_packet_version=review_response.model_packet_version or "mcp_router_packet_v1",
        sub_queries=review_response.sub_queries,
        conversation_id=review_response.conversation_id,
        context_monitor=review_response.context_monitor,
        recommendation=review_response.recommendation,
        route=review_response.route,
        abstained=review_response.abstained,
        rationale=review_response.rationale,
        chain_of_thought=review_response.chain_of_thought,
        findings_summary_markdown=review_response.findings_summary_markdown,
        workflow_summary=review_response.workflow_summary,
        citations=review_response.citations,
        amr_stewardship=review_response.amr_stewardship,
        visualization_data=_enforce_chart_title_identity(
            review_response.visualization_data,
            dossier=state["dossier_by_id"].get(review_response.dossier_id),
        ),
    )


@app.post("/v1/reports/generate", response_model=ReviewReportResponse)
def generate_review_report(request: ReviewReportRequest) -> ReviewReportResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    dossier = state["dossier_by_id"].get(request.dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")
    _require_process_access(user, _infer_review_program(dossier))
    lifecycle = _lifecycle_record(request.dossier_id)
    if lifecycle.get("assigned_reviewer") not in {None, user["username"]} and not _is_superuser(user):
        raise HTTPException(status_code=403, detail="This dossier is assigned to another reviewer.")
    workflow_ready, missing_steps = _workflow_gate_status(dossier, conversation_id=request.conversation_id)
    if not workflow_ready:
        missing_labels = [_pretty_workflow_step(step) for step in missing_steps]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The final report cannot be generated yet because the review SOP is incomplete.",
                "missing_steps": missing_steps,
                "missing_step_labels": missing_labels,
                "conversation_id": request.conversation_id,
            },
        )

    report_title = request.report_title or f"Pre-Market Authorization Review Report - {request.dossier_id}"
    review_payload = dict(request.review_payload)
    review_payload["reviewer_username"] = user["username"]
    report_bundle = build_review_report(dossier=dossier, review_payload=review_payload, report_title=report_title)
    benchmark_panel = _benchmark_panel_payload(settings)
    report_id = f"report-{uuid4().hex[:12]}"
    report_dir = _reports_dir(settings) / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    review_snapshot = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dossier_id": request.dossier_id,
        "report_title": report_title,
        "recipient_email": request.recipient_email,
        "product_name": dossier.get("product", {}).get("product_name", ""),
        "inn_name": dossier.get("product", {}).get("inn_name", ""),
        "product_group": _derive_product_group(dossier),
        "application_type": _derive_application_type(dossier),
        "antimicrobial": bool(evaluate_amr_stewardship(dossier).get("applies")),
        "aware_category": dossier.get("policy_signals", {}).get("aware_category", "not_applicable"),
        "final_verdict": report_bundle["json"].get("workflow_report", {}).get("overall_judgment", {}).get("final_verdict", "unknown"),
        "reviewer_username": user["username"],
        "review_type": request.review_type or _lifecycle_record(request.dossier_id).get("review_type", "generic"),
        "review_program": _infer_review_program(dossier),
        "report_lifecycle_status": "completed",
        "report_payload": report_bundle["json"],
        "benchmark_panel": benchmark_panel.model_dump(),
        "email_subject": report_bundle["email_subject"],
        "email_body": report_bundle["email_body"],
    }
    (report_dir / "report.html").write_text(report_bundle["html"], encoding="utf-8")
    (report_dir / "report.pdf").write_bytes(report_bundle["pdf_bytes"])
    (report_dir / "report.txt").write_text(report_bundle["text"], encoding="utf-8")
    (report_dir / "report.docx").write_bytes(report_bundle["docx_bytes"])
    (report_dir / "query_letter.md").write_text(str(report_bundle.get("query_letter_markdown", "")), encoding="utf-8")
    (report_dir / "query_letter.html").write_text(str(report_bundle.get("query_letter_html", "")), encoding="utf-8")
    (report_dir / "query_letter.txt").write_text(str(report_bundle.get("query_letter_text", "")), encoding="utf-8")
    (report_dir / "decision_log.json").write_text(
        json.dumps(report_bundle.get("decision_log", []), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    judge_pack_html = _build_judge_pack_html(
        report_title=report_title,
        dossier_id=request.dossier_id,
        report_payload=report_bundle.get("json", {}),
        decision_log=list(report_bundle.get("decision_log", [])),
        query_letter_html=str(report_bundle.get("query_letter_html", "")),
    )
    (report_dir / "judge_pack.html").write_text(judge_pack_html, encoding="utf-8")
    (report_dir / "judge_pack.pdf").write_bytes(report_bundle["pdf_bytes"])
    (report_dir / "report.json").write_text(json.dumps(review_snapshot, ensure_ascii=True, indent=2), encoding="utf-8")
    lifecycle["status"] = "done"
    lifecycle["assigned_reviewer"] = user["username"]
    lifecycle["final_decision"] = review_snapshot["final_verdict"]
    lifecycle["decision_date"] = datetime.now(UTC).isoformat()
    lifecycle["report_id"] = report_id
    lifecycle["review_type"] = review_snapshot["review_type"]
    _append_lifecycle_event(
        request.dossier_id,
        "report_completed",
        username=user["username"],
        details={"report_id": report_id, "final_decision": review_snapshot["final_verdict"]},
    )

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "review_report_generated",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "report_id": report_id,
            "dossier_id": request.dossier_id,
            "report_title": report_title,
            "recipient_email": request.recipient_email,
            "lineage_tags": build_lineage_tags(settings=settings, route="review_report_generated"),
        },
    )
    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "review_decision_log_generated",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "report_id": report_id,
            "dossier_id": request.dossier_id,
            "decision_log_entries": len(report_bundle.get("decision_log", [])),
            "sample_entries": list(report_bundle.get("decision_log", []))[:5],
            "lineage_tags": build_lineage_tags(settings=settings, route="review_decision_log_generated"),
        },
    )

    return ReviewReportResponse(
        report_id=report_id,
        dossier_id=request.dossier_id,
        message="Reviewer report generated successfully.",
        report_title=report_title,
        html_download_url=f"/v1/reports/{report_id}/html",
        pdf_download_url=f"/v1/reports/{report_id}/pdf",
        text_download_url=f"/v1/reports/{report_id}/text",
        word_download_url=f"/v1/reports/{report_id}/word",
        json_download_url=f"/v1/reports/{report_id}/json",
        query_letter_download_url=f"/v1/reports/{report_id}/query_letter",
        decision_log_download_url=f"/v1/reports/{report_id}/decision_log",
        judge_pack_html_download_url=f"/v1/reports/{report_id}/judge_pack_html",
        judge_pack_pdf_download_url=f"/v1/reports/{report_id}/judge_pack_pdf",
        email_subject=report_bundle["email_subject"],
        email_body=report_bundle["email_body"],
        report_lifecycle_status="completed",
    )


@app.get("/v1/reports", response_model=ReportRepositoryResponse)
def list_review_reports(
    product_group: str | None = None,
    application_type: str | None = None,
    antimicrobial_only: bool = False,
    final_verdict: str | None = None,
) -> ReportRepositoryResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    allowed_scopes = _user_process_scopes(user)
    root = _reports_dir(settings)
    items: list[ReportRepositoryItem] = []
    if root.exists():
        for report_dir in root.iterdir():
            if not report_dir.is_dir():
                continue
            snapshot_path = report_dir / "report.json"
            if not snapshot_path.exists():
                continue
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            item = _report_repository_item(report_dir.name, snapshot)
            if not _is_superuser(user) and item.reviewer_username not in {None, user["username"]}:
                continue
            report_scope = str(snapshot.get("review_program", "marketing_authorization"))
            if report_scope not in allowed_scopes:
                continue
            if product_group and item.product_group != product_group:
                continue
            if application_type and item.application_type != application_type:
                continue
            if antimicrobial_only and not item.antimicrobial:
                continue
            if final_verdict and item.final_verdict != final_verdict:
                continue
            items.append(item)
    items.sort(key=lambda item: item.generated_at_utc, reverse=True)
    return ReportRepositoryResponse(total_items=len(items), items=items)


@app.get("/v1/reports/{report_id}/{artifact}", include_in_schema=False)
def download_review_report(report_id: str, artifact: str) -> FileResponse:
    settings: Settings = state["settings"]
    user = _current_user()
    report_dir = (_reports_dir(settings) / report_id).resolve()
    root = _reports_dir(settings).resolve()
    if root not in report_dir.parents or not report_dir.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    file_map = {
        "html": ("report.html", "text/html"),
        "pdf": ("report.pdf", "application/pdf"),
        "text": ("report.txt", "text/plain"),
        "word": ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "json": ("report.json", "application/json"),
        "query_letter": ("query_letter.html", "text/html"),
        "decision_log": ("decision_log.json", "application/json"),
        "judge_pack_html": ("judge_pack.html", "text/html"),
        "judge_pack_pdf": ("judge_pack.pdf", "application/pdf"),
    }
    if artifact not in file_map:
        raise HTTPException(status_code=404, detail="Report artifact not found")
    file_name, media_type = file_map[artifact]
    path = report_dir / file_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report artifact not found")
    snapshot_path = report_dir / "report.json"
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        owner = snapshot.get("reviewer_username")
        if owner and owner != user["username"] and not _is_superuser(user):
            raise HTTPException(status_code=403, detail="This report belongs to another reviewer.")
        _require_process_access(user, str(snapshot.get("review_program", "marketing_authorization")))
    if artifact == "text":
        extension = "txt"
    elif artifact == "word":
        extension = "docx"
    elif artifact == "query_letter":
        extension = "html"
    elif artifact == "decision_log":
        extension = "json"
    elif artifact == "judge_pack_html":
        extension = "html"
    elif artifact == "judge_pack_pdf":
        extension = "pdf"
    else:
        extension = artifact
    return FileResponse(path, media_type=media_type, filename=f"{report_id}.{extension}")


@app.post("/v1/reports/{report_id}/reject")
def reject_report(report_id: str, request: ReportRejectionRequest) -> dict[str, Any]:
    settings: Settings = state["settings"]
    user = _current_user()
    if not _is_superuser(user):
        raise HTTPException(status_code=403, detail="Only the superuser can reject a completed report.")
    report_dir = (_reports_dir(settings) / report_id).resolve()
    root = _reports_dir(settings).resolve()
    if root not in report_dir.parents or not report_dir.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    snapshot_path = report_dir / "report.json"
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail="Report snapshot not found")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    _require_process_access(user, str(snapshot.get("review_program", "marketing_authorization")))
    snapshot["report_lifecycle_status"] = "rejected_by_superuser"
    snapshot["rejected_by"] = user["username"]
    snapshot["rejection_reason"] = request.reason
    snapshot["rejected_at_utc"] = datetime.now(UTC).isoformat()
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2), encoding="utf-8")

    dossier_id = str(snapshot.get("dossier_id", ""))
    lifecycle = _lifecycle_record(dossier_id)
    lifecycle["status"] = "reopened"
    lifecycle["final_decision"] = None
    lifecycle["decision_date"] = None
    lifecycle["report_id"] = report_id
    _append_lifecycle_event(
        dossier_id,
        "report_rejected_and_reopened",
        username=user["username"],
        details={"report_id": report_id, "reason": request.reason},
    )
    return {"report_id": report_id, "dossier_id": dossier_id, "status": "reopened"}
