from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class ToolAuditRecord(BaseModel):
    tool_name: str
    timestamp: datetime
    request_id: str
    input_hash: str


class SourceReference(BaseModel):
    source: str
    source_url: HttpUrl | None = None
    source_type: str | None = None
    citation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolEnvelope(BaseModel):
    status: Literal["success", "error"]
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)
    audit: ToolAuditRecord


class DossierSection(BaseModel):
    section_id: str
    section_type: str
    title: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    index: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=50)


class RerankSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    candidate_results: list[SearchResult] = Field(default_factory=list)
    rerank_criteria: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=50)


class GetSectionExamplesRequest(BaseModel):
    section_type: str
    example_type: Literal["correct", "incorrect", "both"]
    product_type: Literal["generic", "innovation", "any"] = "any"
    top_k: int = Field(default=5, ge=1, le=20)


class CompareCurrentSectionRequest(BaseModel):
    current_section: DossierSection
    correct_examples: list[SectionExample] = Field(default_factory=list)
    incorrect_examples: list[SectionExample] = Field(default_factory=list)
    comparison_dimensions: list[str] = Field(default_factory=list)


class FetchWhoInnCandidatesRequest(BaseModel):
    active_ingredient: str
    proposed_name: str


class ComputeInnSimilarityRequest(BaseModel):
    proposed_name: str
    inn_candidates: list[str] = Field(default_factory=list)
    threshold: float = Field(default=70.0, ge=0.0, le=100.0)


class FetchAwareReserveReferenceRequest(BaseModel):
    active_ingredient: str
    source_mode: Literal["cached", "external_or_cached"] = "cached"


class ComputeAntimicrobialSimilarityRequest(BaseModel):
    active_ingredient: str
    chemical_structure: str | None = None
    aware_reference: dict[str, Any]
    comparison_mode: Literal["class_or_structure"] = "class_or_structure"


class FetchInnovatorPatientInformationRequest(BaseModel):
    active_ingredient: str
    reference_urls: list[str] = Field(default_factory=list)


class CompareGenericPatientInformationRequest(BaseModel):
    current_pil_sections: list[PatientInfoSection] = Field(default_factory=list)
    innovator_pil_sections: list[PatientInfoSection] = Field(default_factory=list)
    comparison_dimensions: list[str] = Field(default_factory=list)


class BuildEvidencePacketRequest(BaseModel):
    dossier_id: str
    review_type: Literal["generic", "innovation"]
    section_id: str
    review_area: str
    tool_results: dict[str, Any] = Field(default_factory=dict)


class GenerateFindingsTableRequest(BaseModel):
    dossier_id: str
    findings: list[Finding] = Field(default_factory=list)
    group_by: Literal["review_area"] = "review_area"


class SearchResult(BaseModel):
    chunk_id: str
    source: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankedResult(BaseModel):
    chunk_id: str
    text: str
    original_score: float
    rerank_score: float
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SectionExample(BaseModel):
    example_id: str
    label: Literal["correct", "incorrect"]
    section_type: str
    product_type: Literal["generic", "innovation", "any"] = "any"
    section_text: str
    why_labeled: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimilarityResult(BaseModel):
    proposed_name: str
    best_match_inn: str
    similarity_index: float
    similarity_type: list[str]
    rule_result: Literal["pass", "flagged"]
    decision_effect: Literal["can_continue", "cannot_accept_until_resolved"]


class AWaReResult(BaseModel):
    active_ingredient: str
    is_antimicrobial: bool
    aware_category: Literal["Access", "Watch", "Reserve", "Not listed", "Unknown"]
    reserve_related: bool
    source: str
    source_date: str


class PatientInfoSection(BaseModel):
    section_name: str
    text: str
    source_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidencePacket(BaseModel):
    evidence_packet_id: str
    dossier_id: str
    review_area: str
    rules_applied: list[str] = Field(default_factory=list)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    examples_used: list[dict[str, Any]] = Field(default_factory=list)
    external_sources_used: list[dict[str, Any]] = Field(default_factory=list)
    preliminary_flags: list[str] = Field(default_factory=list)
    ready_for_judgment: bool


class Finding(BaseModel):
    review_area: str
    finding: str
    severity: Literal["critical", "major", "minor", "advisory"]
    violated_rule: str
    evidence_ref: str
    recommendation: str
    decision_trace: dict[str, Any] = Field(default_factory=dict)


class FindingsTable(BaseModel):
    markdown_table: str
    structured_table: list[Finding] = Field(default_factory=list)
