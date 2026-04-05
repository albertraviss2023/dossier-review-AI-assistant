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
    total_hits: int
    citations: list[Citation]


class DossierResponse(BaseModel):
    dossier_id: str
    country: str
    submission_date: str
    organization: dict[str, Any]
    product: dict[str, Any]
    labels: dict[str, Any]
    policy_signals: dict[str, Any]


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    dossiers_loaded: int
    sections_indexed: int
    system_total_ram_gb: float
    system_available_ram_gb: float
    process_rss_gb: float
    model_policy: str


class ReviewRequest(BaseModel):
    dossier_id: str
    question: str = "Provide policy recommendation with evidence."
    top_k: int | None = Field(default=None, ge=1, le=50)
    force_fallback: bool = False


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


class ReviewResponse(BaseModel):
    dossier_id: str
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
