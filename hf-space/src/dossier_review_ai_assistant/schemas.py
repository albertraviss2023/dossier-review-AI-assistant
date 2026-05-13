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
    section_count: int = 0
    status: str = "open"
    assigned_reviewer: str | None = None
    final_decision: str | None = None
    review_type: str = "generic"
    review_program: str = "marketing_authorization"
    progress_state: str = "not_started"
    progress_percent: int = 0
    progress_color: str = "grey"


class DossierListItem(BaseModel):
    dossier_id: str
    product_name: str
    inn_name: str
    country: str
    submission_date: str
    manufacturer_name: str = ""
    aware_category: str
    status: str = "open"
    assigned_reviewer: str | None = None
    review_type: str = "generic"
    review_program: str = "marketing_authorization"
    progress_state: str = "not_started"
    progress_percent: int = 0
    progress_color: str = "grey"


class DossierListResponse(BaseModel):
    total_items: int
    items: list[DossierListItem]


class DossierUploadResponse(BaseModel):
    dossier_id: str
    message: str
    stored_path: str
    review_program: str = "marketing_authorization"


class SampleDossierItem(BaseModel):
    file_name: str
    dossier_id: str
    description: str
    download_url: str
    product_group: str | None = None
    application_type: str | None = None
    review_pathway: str | None = None
    document_condition: str | None = None
    expected_outcome: str | None = None


class SampleDossierListResponse(BaseModel):
    total_items: int
    items: list[SampleDossierItem]


class SampleIncomingFileItem(BaseModel):
    file_name: str
    description: str
    media_type: str
    download_url: str
    product_group: str | None = None
    application_type: str | None = None
    review_pathway: str | None = None
    document_condition: str | None = None
    expected_outcome: str | None = None


class SampleIncomingFileListResponse(BaseModel):
    total_items: int
    items: list[SampleIncomingFileItem]


class ChunkingProfileSummary(BaseModel):
    source_type: str
    profile_version: str
    target_tokens: int
    overlap_tokens: int
    title_standalone: bool


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    dossiers_loaded: int
    sections_indexed: int
    system_total_ram_gb: float
    system_available_ram_gb: float
    process_rss_gb: float
    model_policy: str
    retrieval_mode: str
    external_source_mode: str
    default_model_id: str
    default_context_window_tokens: int
    available_models: list[ModelOption]
    chunking_profiles: list[ChunkingProfileSummary]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dossier_id: str
    workspace: str = "review"
    question: str = "Provide policy recommendation with evidence."
    review_type: str = "generic"
    top_k: int | None = Field(default=None, ge=1, le=50)
    force_fallback: bool = False
    model_id: str | None = None
    conversation_id: str | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=32768)


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
    owner_username: str | None = None
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
    normalized_ingredient: str
    normalization_source: str
    active_moiety: str
    parent_compound: str
    pubchem_cid: str
    canonical_smiles: str
    inchikey: str
    chembl_id: str
    unichem_id: str
    aware_category: str
    amr_unmet_need: str
    targets_mdr_pathogen: bool
    glass_resistance_trend: str
    similarity_to_existing_watch: str
    existing_watch_comparator: str
    chemistry_source: str
    authorization_control: str
    fast_track_candidate: bool
    restricted_authorization: bool
    watch_similarity_restriction: bool
    source_mode: str
    source_trace: list[str]
    rationale: str


class InteractionMetricsPayload(BaseModel):
    latency_seconds: float
    input_tokens_estimate: int
    output_tokens_estimate: int


class VisualizationData(BaseModel):
    type: str  # 'bar', 'pie', 'line'
    title: str
    labels: list[str]
    datasets: list[dict[str, Any]]


class AssistantMessageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str
    workspace: str = "review"
    dossier_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    force_fallback: bool = False
    model_id: str | None = None
    conversation_id: str | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=32768)
    review_type: str = "generic"


class AssistantMessageResponse(BaseModel):
    workspace: str
    dossier_id: str | None = None
    selected_model: ModelOption
    intent: str
    response_contract: str
    model_packet_version: str
    sub_queries: list[str]
    conversation_id: str | None = None
    context_monitor: ContextWindowMonitor | None = None
    recommendation: str | None = None
    route: str | None = None
    abstained: bool = False
    rationale: str
    chain_of_thought: str | None = None
    findings_summary_markdown: str | None = None
    workflow_summary: dict[str, Any] | None = None
    citations: list[Citation] = Field(default_factory=list)
    amr_stewardship: AmrStewardshipSummary | None = None
    visualization_data: VisualizationData | None = None


class ReviewResponse(BaseModel):
    dossier_id: str
    selected_model: ModelOption
    sub_queries: list[str]
    intent: str | None = None
    response_contract: str | None = None
    model_packet_version: str | None = None
    conversation_id: str | None = None
    review_type: str = "generic"
    context_monitor: ContextWindowMonitor | None = None
    recommendation: str
    confidence: float
    route: str
    abstained: bool
    abstain_reason: str | None = None
    rationale: str
    chain_of_thought: str | None = None
    findings_summary_markdown: str | None = None
    workflow_summary: dict[str, Any] | None = None
    policy_rule_hits: list[str]
    section_diagnostics: list[SectionDiagnostic]
    citations: list[Citation]
    verifier: VerifierSummary
    memory: MemorySummary
    lineage_tags: dict[str, str]
    amr_stewardship: AmrStewardshipSummary
    metrics: InteractionMetricsPayload | None = None
    visualization_data: VisualizationData | None = None


class KnowledgeGraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    summary_stats: dict[str, Any]


class ReviewReportRequest(BaseModel):
    dossier_id: str
    review_payload: dict[str, Any]
    conversation_id: str | None = None
    review_type: str | None = None
    report_title: str | None = None
    recipient_email: str | None = None


class ReviewReportResponse(BaseModel):
    report_id: str
    dossier_id: str
    message: str
    report_title: str
    html_download_url: str
    pdf_download_url: str
    text_download_url: str
    word_download_url: str
    json_download_url: str
    query_letter_download_url: str | None = None
    decision_log_download_url: str | None = None
    judge_pack_html_download_url: str | None = None
    judge_pack_pdf_download_url: str | None = None
    email_subject: str
    email_body: str
    report_lifecycle_status: str = "completed"


class ReportRepositoryItem(BaseModel):
    report_id: str
    dossier_id: str
    report_title: str
    generated_at_utc: str
    product_name: str
    inn_name: str
    product_group: str
    application_type: str
    antimicrobial: bool
    aware_category: str
    final_verdict: str
    reviewer_username: str | None = None
    report_lifecycle_status: str = "completed"
    html_download_url: str
    pdf_download_url: str
    text_download_url: str
    word_download_url: str
    json_download_url: str
    judge_pack_html_download_url: str | None = None
    judge_pack_pdf_download_url: str | None = None


class UserProfile(BaseModel):
    username: str
    role: str
    display_name: str
    process_scopes: list[str] = Field(default_factory=list)
    active: bool = True


class AdminUserItem(BaseModel):
    username: str
    display_name: str
    role: str
    process_scopes: list[str] = Field(default_factory=list)
    active: bool = True
    created_at_utc: str | None = None


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=3)
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=2)
    role: str = Field(pattern="^(reviewer|superuser)$")
    process_scopes: list[str] = Field(default_factory=list, min_length=1)


class AdminUserUpdateRequest(BaseModel):
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str | None = Field(default=None, pattern="^(reviewer|superuser)$")
    process_scopes: list[str] | None = None
    active: bool | None = None


class AdminUsersResponse(BaseModel):
    total_items: int
    items: list[AdminUserItem]


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthLoginResponse(BaseModel):
    message: str
    user: UserProfile


class ReportRejectionRequest(BaseModel):
    reason: str = Field(min_length=3)


class ReportRepositoryResponse(BaseModel):
    total_items: int
    items: list[ReportRepositoryItem]


class ReviewerPerformanceItem(BaseModel):
    reviewer_username: str
    completed_reviews: int
    average_tot_hours: float
    fastest_tot_hours: float | None = None
    slowest_tot_hours: float | None = None
    struggle_signal: str = "none"


class ReviewerPerformanceResponse(BaseModel):
    overall_average_tot_hours: float
    fastest_reviewer_username: str | None = None
    slowest_reviewer_username: str | None = None
    reviewers: list[ReviewerPerformanceItem]


class DossierAssignmentRequest(BaseModel):
    reviewer_username: str


class DossierAssignmentResponse(BaseModel):
    dossier_id: str
    assigned_reviewer: str
    status: str


class ReviewerDashboardResponse(BaseModel):
    reviewer_username: str
    assigned_to_me: int
    in_progress: int
    finished_reviews: int
    reports_generated: int
    dossiers_reviewed: int
    dossiers_approved: int
    dossiers_queried: int
    average_tot_hours: float


class AdminProgressByReviewerItem(BaseModel):
    reviewer_username: str
    assigned_total: int
    not_started: int
    in_progress: int
    done: int


class AdminDashboardSummaryResponse(BaseModel):
    overall_total_dossiers: int
    overall_not_started: int
    overall_in_progress: int
    overall_done: int
    overall_average_tot_hours: float
    fastest_reviewer_username: str | None = None
    slowest_reviewer_username: str | None = None
    progress_by_reviewer: list[AdminProgressByReviewerItem]
    tot_by_reviewer: list[ReviewerPerformanceItem]


class BenchmarkMetricItem(BaseModel):
    name: str
    value: float | None = None
    display_value: str
    source_metric_key: str | None = None


class BenchmarkPanelResponse(BaseModel):
    report_generated_at_utc: str | None = None
    dataset_version: str | None = None
    records_evaluated: int | None = None
    metrics: list[BenchmarkMetricItem] = Field(default_factory=list)


class TelemetryPanelMetric(BaseModel):
    name: str
    value: float | None = None
    display_value: str
    description: str | None = None


class TelemetryPanelResponse(BaseModel):
    generated_at_utc: str | None = None
    daily_live_external_check_enabled: bool = False
    records_evaluated: int = 0
    metrics: list[TelemetryPanelMetric] = Field(default_factory=list)


class WorkflowStepState(BaseModel):
    step_id: str
    step_label: str
    ordinal: int
    status: str
    prompt_template: str


class WorkflowStateResponse(BaseModel):
    dossier_id: str
    conversation_id: str | None = None
    review_program: str
    current_step_id: str | None = None
    all_completed: bool = False
    steps: list[WorkflowStepState] = Field(default_factory=list)
