from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .audit import append_audit_record
from .config import Settings, load_settings
from .conversation import ConversationStore, build_context_monitor, build_model_context
from .data import build_evidence_chunks, build_knowledge_wiki_chunks, load_dossiers, load_knowledge_wiki
from .governance import build_lineage_tags
from .orchestrator import run_review_orchestration
from .retrieval import LexicalRetriever, decompose_query, merge_hits
from .schemas import (
    AmrStewardshipSummary,
    Citation,
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
    DossierResponse,
    HealthResponse,
    KnowledgeWikiListResponse,
    KnowledgeWikiPageSummary,
    KnowledgeWikiSearchRequest,
    KnowledgeWikiSearchResponse,
    MemorySummary,
    ModelCatalogResponse,
    ModelOption,
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
    retriever: LexicalRetriever,
    query: str,
    top_k: int,
    dossier_id: str | None = None,
) -> tuple[list[str], list[Any]]:
    sub_queries = decompose_query(query)
    hit_lists = [retriever.search(query=sub_query, top_k=top_k, dossier_id=dossier_id) for sub_query in sub_queries]
    hits = merge_hits(*hit_lists, top_k=top_k)
    return sub_queries, hits


def _build_app_state(settings: Settings) -> dict[str, Any]:
    dossiers = load_dossiers(str(settings.data_jsonl_path))
    chunks = build_evidence_chunks(dossiers)
    retriever = LexicalRetriever(chunks)
    knowledge_wiki_pages = load_knowledge_wiki(str(settings.knowledge_wiki_path))
    knowledge_wiki_chunks = build_knowledge_wiki_chunks(knowledge_wiki_pages)
    knowledge_wiki_retriever = LexicalRetriever(knowledge_wiki_chunks)
    conversation_store = ConversationStore(path=settings.conversations_state_path, settings=settings)
    dossier_by_id = {str(d["dossier_id"]): d for d in dossiers}
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


def _dossier_list_items(limit: int) -> list[DossierListItem]:
    items: list[DossierListItem] = []
    for dossier in state["dossiers"][:limit]:
        product = dossier.get("product", {})
        policy_signals = dossier.get("policy_signals", {})
        items.append(
            DossierListItem(
                dossier_id=dossier["dossier_id"],
                product_name=str(product.get("product_name", "")),
                inn_name=str(product.get("inn_name", "")),
                country=dossier["country"],
                submission_date=dossier["submission_date"],
                aware_category=str(policy_signals.get("aware_category", "not_applicable")),
            )
        )
    return items


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


def _context_monitor_payload(monitor: dict[str, Any]) -> ContextWindowMonitor:
    return ContextWindowMonitor(**monitor)


def _conversation_summary_payload(session: dict[str, Any], settings: Settings) -> ConversationSummary:
    monitor = build_context_monitor(session, settings)
    return ConversationSummary(
        conversation_id=session["conversation_id"],
        title=session["title"],
        created_at_utc=session["created_at_utc"],
        updated_at_utc=session["updated_at_utc"],
        linked_from_conversation_id=session.get("linked_from_conversation_id"),
        context_window_tokens=int(session["context_window_tokens"]),
        selected_model_id=str(session["selected_model_id"]),
        dossier_id=session.get("dossier_id"),
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
        default_model_id=state["settings"].model_id,
        default_context_window_tokens=state["settings"].default_context_window_tokens,
        available_models=_model_catalog_payload(state["settings"]),
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
    sessions = state["conversation_store"].list_sessions()
    return ConversationListResponse(
        total_items=len(sessions),
        items=[_conversation_summary_payload(session, settings) for session in sessions],
    )


@app.post("/v1/conversations", response_model=ConversationDetailResponse)
def create_conversation(request: ConversationCreateRequest) -> ConversationDetailResponse:
    settings: Settings = state["settings"]
    selected_model_id = request.model_id or settings.model_id
    _model_option_payload(settings, selected_model_id)
    try:
        session, _ = state["conversation_store"].create_session(
            title=request.title,
            context_window_tokens=request.context_window_tokens,
            linked_from_conversation_id=request.linked_from_conversation_id,
            selected_model_id=selected_model_id,
            dossier_id=request.dossier_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    session = state["conversation_store"].get_session(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return _conversation_detail_payload(session, settings)


@app.patch("/v1/conversations/{conversation_id}/context", response_model=ConversationDetailResponse)
def update_conversation_context(
    conversation_id: str,
    request: ConversationContextUpdateRequest,
) -> ConversationDetailResponse:
    settings: Settings = state["settings"]
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
    normalized_limit = max(1, min(limit, 50))
    items = _dossier_list_items(normalized_limit)
    return DossierListResponse(
        total_items=len(items),
        items=items,
    )


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
    dossier = state["dossier_by_id"].get(request.dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {request.dossier_id} not found")

    settings: Settings = state["settings"]
    selected_model_id = request.model_id or settings.model_id
    selected_model = _model_option_payload(settings, selected_model_id)
    conversation_session: dict[str, Any] | None = None
    conversation_context = ""
    conversation_monitor: ContextWindowMonitor | None = None
    if request.conversation_id:
        conversation_session = state["conversation_store"].get_session(request.conversation_id)
        if conversation_session is None:
            raise HTTPException(status_code=404, detail=f"Conversation {request.conversation_id} not found")
        conversation_context = build_model_context(conversation_session, settings)

    mem_before = _build_memory_summary(settings)
    if mem_before.system_available_ram_gb < settings.min_free_ram_gb:
        lineage_tags = build_lineage_tags(settings=settings, route="abstain", model_id=selected_model.runtime_model_id)
        if request.conversation_id:
            updated_session, monitor, _ = state["conversation_store"].append_turn(
                conversation_id=request.conversation_id,
                user_content=request.question,
                assistant_content="Abstained to protect stability under memory pressure on local host.",
                selected_model_id=selected_model.runtime_model_id,
                citations=[],
                dossier_id=request.dossier_id,
                metadata={"route": "abstain", "reason": "memory_pressure_guard"},
            )
            conversation_monitor = _context_monitor_payload(monitor)
            conversation_session = updated_session
        append_audit_record(
            path=settings.audit_log_path,
            record={
                "event": "review_decision",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "dossier_id": request.dossier_id,
                "conversation_id": request.conversation_id,
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
            },
        )
        return ReviewResponse(
            dossier_id=request.dossier_id,
            selected_model=selected_model,
            sub_queries=[],
            conversation_id=request.conversation_id,
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
                aware_category="not_applicable",
                amr_unmet_need="not_applicable",
                targets_mdr_pathogen=False,
                glass_resistance_trend="not_applicable",
                similarity_to_existing_watch="not_applicable",
                existing_watch_comparator="not_applicable",
                authorization_control="standard_authorization",
                fast_track_candidate=False,
                restricted_authorization=False,
                watch_similarity_restriction=False,
                rationale="AMR stewardship evaluation was skipped because the request abstained under memory pressure.",
            ),
        )

    top_k = min(request.top_k or settings.default_top_k, settings.max_retrieval_k)
    sub_queries, dossier_hits = _search_with_subqueries(
        retriever=state["retriever"],
        query=request.question,
        top_k=top_k,
        dossier_id=request.dossier_id,
    )
    _, wiki_hits = _search_with_subqueries(
        retriever=state["knowledge_wiki_retriever"],
        query=request.question,
        top_k=max(2, min(4, top_k)),
    )
    hits = merge_hits(dossier_hits, wiki_hits, top_k=top_k + 2)
    result = run_review_orchestration(
        dossier=dossier,
        question=request.question,
        hits=hits,
        model_id=selected_model.runtime_model_id,
        conversation_context=conversation_context,
        force_fallback=request.force_fallback,
    )
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

    if request.conversation_id:
        updated_session, monitor, _ = state["conversation_store"].append_turn(
            conversation_id=request.conversation_id,
            user_content=request.question,
            assistant_content=result.rationale,
            selected_model_id=selected_model.runtime_model_id,
            citations=[citation.model_dump() for citation in citations],
            dossier_id=request.dossier_id,
            metadata={
                "route": result.route,
                "recommendation": result.recommendation,
                "abstained": result.abstained,
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
            "conversation_id": request.conversation_id,
            "question": request.question,
            "sub_queries": sub_queries,
            "route": result.route,
            "recommendation": result.recommendation,
            "abstained": result.abstained,
            "abstain_reason": result.abstain_reason,
            "policy_rule_hits": result.policy_rule_hits,
            "verifier": result.verifier,
            "citation_count": len(citations),
            "selected_model_id": selected_model.runtime_model_id,
            "lineage_tags": lineage_tags,
            "memory": mem_after.model_dump(),
            "context_monitor": conversation_monitor.model_dump() if conversation_monitor else None,
        },
    )

    return ReviewResponse(
        dossier_id=request.dossier_id,
        selected_model=selected_model,
        sub_queries=sub_queries,
        conversation_id=request.conversation_id,
        context_monitor=conversation_monitor,
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
        amr_stewardship=AmrStewardshipSummary(**result.amr_stewardship),
    )
