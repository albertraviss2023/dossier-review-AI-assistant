from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .audit import append_audit_record
from .config import Settings, load_settings
from .data import build_evidence_chunks, load_dossiers
from .governance import build_lineage_tags
from .orchestrator import run_review_orchestration
from .retrieval import LexicalRetriever
from .schemas import (
    Citation,
    DossierResponse,
    HealthResponse,
    MemorySummary,
    ReviewRequest,
    ReviewResponse,
    SectionDiagnostic,
    VerifierSummary,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from .telemetry import memory_snapshot


def _snippet(text: str, max_len: int = 220) -> str:
    compact = " ".join(text.split())
    return compact[:max_len] + ("..." if len(compact) > max_len else "")


def _build_app_state(settings: Settings) -> dict[str, Any]:
    dossiers = load_dossiers(str(settings.data_jsonl_path))
    chunks = build_evidence_chunks(dossiers)
    retriever = LexicalRetriever(chunks)
    dossier_by_id = {str(d["dossier_id"]): d for d in dossiers}
    return {
        "settings": settings,
        "dossiers": dossiers,
        "chunks": chunks,
        "retriever": retriever,
        "dossier_by_id": dossier_by_id,
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


settings = load_settings()
state = _build_app_state(settings)

app = FastAPI(
    title="Dossier Review AI Assistant API",
    version="0.1.0",
    summary="Local-first policy copilot foundation service",
)


@app.get("/", include_in_schema=False)
def ui_shell() -> FileResponse:
    index_path = Path(state["settings"].ui_index_path)
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI shell not found")
    return FileResponse(index_path)


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
    )


@app.get("/v1/dossiers/{dossier_id}", response_model=DossierResponse)
def get_dossier(dossier_id: str) -> DossierResponse:
    dossier = state["dossier_by_id"].get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {dossier_id} not found")
    return DossierResponse(
        dossier_id=dossier["dossier_id"],
        country=dossier["country"],
        submission_date=dossier["submission_date"],
        organization=dossier["organization"],
        product=dossier["product"],
        labels=dossier["labels"],
        policy_signals=dossier["policy_signals"],
    )


@app.post("/v1/retrieval/search", response_model=RetrievalSearchResponse)
def retrieval_search(request: RetrievalSearchRequest) -> RetrievalSearchResponse:
    settings: Settings = state["settings"]
    lineage_tags = build_lineage_tags(settings=settings, route="retrieval")
    top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
    hits = state["retriever"].search(
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
            "dossier_id": request.dossier_id,
            "top_k": top_k,
            "result_count": len(citations),
            "lineage_tags": lineage_tags,
            "memory": _build_memory_summary(settings).model_dump(),
        },
    )

    return RetrievalSearchResponse(
        query=request.query,
        total_hits=len(citations),
        citations=citations,
    )


@app.post("/v1/review", response_model=ReviewResponse)
def review_dossier(request: ReviewRequest) -> ReviewResponse:
    dossier = state["dossier_by_id"].get(request.dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")

    settings: Settings = state["settings"]
    mem_before = _build_memory_summary(settings)
    if mem_before.system_available_ram_gb < settings.min_free_ram_gb:
        lineage_tags = build_lineage_tags(settings=settings, route="abstain")
        append_audit_record(
            path=settings.audit_log_path,
            record={
                "event": "review_decision",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "dossier_id": request.dossier_id,
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
            },
        )
        return ReviewResponse(
            dossier_id=request.dossier_id,
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
        )

    top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
    hits = state["retriever"].search(
        query=request.question,
        top_k=top_k,
        dossier_id=request.dossier_id,
    )
    result = run_review_orchestration(
        dossier=dossier,
        question=request.question,
        hits=hits,
        force_fallback=request.force_fallback,
    )
    mem_after = _build_memory_summary(settings)
    lineage_tags = build_lineage_tags(settings=settings, route=result.route)

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

    append_audit_record(
        path=settings.audit_log_path,
        record={
            "event": "review_decision",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dossier_id": request.dossier_id,
            "question": request.question,
            "route": result.route,
            "recommendation": result.recommendation,
            "abstained": result.abstained,
            "abstain_reason": result.abstain_reason,
            "policy_rule_hits": result.policy_rule_hits,
            "verifier": result.verifier,
            "citation_count": len(citations),
            "lineage_tags": lineage_tags,
            "memory": mem_after.model_dump(),
        },
    )

    return ReviewResponse(
        dossier_id=request.dossier_id,
        recommendation=result.recommendation,
        confidence=result.confidence,
        route=result.route,
        abstained=result.abstained,
        abstain_reason=result.abstain_reason,
        rationale=result.rationale,
        policy_rule_hits=result.policy_rule_hits,
        section_diagnostics=[SectionDiagnostic(**diag) for diag in result.section_diagnostics],
        citations=citations,
        verifier=VerifierSummary(**result.verifier),
        memory=mem_after,
        lineage_tags=lineage_tags,
    )
