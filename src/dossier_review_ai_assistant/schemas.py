from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    dossier_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class Citation(BaseModel):
    citation_id: str
    dossier_id: str
    section_id: str
    section_title: str
    score: float
    snippet: str


class RetrievalSearchResponse(BaseModel):
    query: str
    sub_queries: list[str]
    total_hits: int
    citations: list[Citation]


class ModelOption(BaseModel):
    id: str
    label: str
    runtime_model_id: str
    description: str


class ModelCatalogResponse(BaseModel):
    default_model_id: str
    available_models: list[ModelOption]


class DossierResponse(BaseModel):
    dossier_id: str
    country: str
    submission_date: str
    organization: dict[str, Any]
    product: dict[str, Any]
    labels: dict[str, Any]
    policy_signals: dict[str, Any]


class DossierListItem(BaseModel):
    dossier_id: str
    product_name: str
    inn_name: str
    country: str
    submission_date: str
    aware_category: str


class DossierListResponse(BaseModel):
    total_items: int
    items: list[DossierListItem]


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    dossiers_loaded: int
    sections_indexed: int
    system_total_ram_gb: float
    system_available_ram_gb: float
    process_rss_gb: float
    model_policy: str
    default_model_id: str
    default_context_window_tokens: int
    available_models: list[ModelOption]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dossier_id: str
    question: str = "Provide policy recommendation with evidence."
    top_k: int | None = Field(default=None, ge=1, le=50)
    force_fallback: bool = False
    model_id: str | None = None
    conversation_id: str | None = None


class KnowledgeWikiPageSummary(BaseModel):
    page_id: str
    title: str
    tags: list[str]


class KnowledgeWikiListResponse(BaseModel):
    total_pages: int
    pages: list[KnowledgeWikiPageSummary]


class KnowledgeWikiSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    top_k: int | None = Field(default=None, ge=1, le=50)


class KnowledgeWikiSearchResponse(BaseModel):
    query: str
    sub_queries: list[str]
    total_hits: int
    citations: list[Citation]


class SectionDiagnostic(BaseModel):
    section_id: str
    title: str
    presence: str
    length_status: str
    correctness: str
    critical: bool


class VerifierSummary(BaseModel):
    grounded_claim_rate: float
    unsupported_critical_claim_rate: float
    passed: bool


class MemorySummary(BaseModel):
    process_rss_gb: float
    system_total_ram_gb: float
    system_available_ram_gb: float
    system_used_ram_percent: float
    min_free_ram_gb: float
    standard_route_rss_limit_gb: float
    fallback_route_rss_limit_gb: float
    within_budget: bool


class ContextWindowMonitor(BaseModel):
    context_window_tokens: int
    used_tokens: int
    remaining_tokens: int
    usage_ratio: float
    threshold_tokens: int
    compaction_threshold_ratio: float
    rolling_summary_tokens: int
    carryover_tokens: int
    active_message_tokens: int
    archived_messages_count: int
    compaction_count: int
    auto_compaction_required: bool
    last_compacted_at: str | None = None
    conversation_engine: str


class ConversationMessage(BaseModel):
    message_id: str
    role: str
    content: str
    created_at_utc: str
    tokens_estimate: int
    citations: list[Citation] = Field(default_factory=list)
    archived: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummarySnapshot(BaseModel):
    created_at_utc: str
    summary_model_id: str
    summary_text: str
    source_message_count: int
    reason: str
    tokens_estimate: int


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at_utc: str
    updated_at_utc: str
    linked_from_conversation_id: str | None = None
    context_window_tokens: int
    selected_model_id: str
    dossier_id: str | None = None
    compaction_count: int
    carryover_available: bool
    context_monitor: ContextWindowMonitor


class ConversationDetailResponse(BaseModel):
    conversation: ConversationSummary
    carryover_summary: str
    rolling_summary: str
    summary_model_id: str
    last_compaction_reason: str | None = None
    summary_history: list[ConversationSummarySnapshot]
    messages: list[ConversationMessage]


class ConversationListResponse(BaseModel):
    total_items: int
    items: list[ConversationSummary]


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=32768)
    linked_from_conversation_id: str | None = None
    model_id: str | None = None
    dossier_id: str | None = None


class ConversationContextUpdateRequest(BaseModel):
    context_window_tokens: int = Field(ge=1024, le=32768)


class AmrStewardshipSummary(BaseModel):
    applies: bool
    aware_category: str
    amr_unmet_need: str
    targets_mdr_pathogen: bool
    glass_resistance_trend: str
    similarity_to_existing_watch: str
    existing_watch_comparator: str
    authorization_control: str
    fast_track_candidate: bool
    restricted_authorization: bool
    watch_similarity_restriction: bool
    rationale: str


class ReviewResponse(BaseModel):
    dossier_id: str
    selected_model: ModelOption
    sub_queries: list[str]
    conversation_id: str | None = None
    context_monitor: ContextWindowMonitor | None = None
    recommendation: str
    confidence: float
    route: str
    abstained: bool
    abstain_reason: str | None = None
    rationale: str
    policy_rule_hits: list[str]
    section_diagnostics: list[SectionDiagnostic]
    citations: list[Citation]
    verifier: VerifierSummary
    memory: MemorySummary
    lineage_tags: dict[str, str]
    amr_stewardship: AmrStewardshipSummary
