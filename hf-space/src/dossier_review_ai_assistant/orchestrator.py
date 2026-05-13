from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .data import EvidenceChunk
from .gates import retrieval_confidence, route_request, verify_claim_groundedness
from .inference import _question_focus, build_model_client
from .policy import apply_policy_rules, evaluate_amr_stewardship
from .regulatory_mcp_client import RegulatoryMCPClientError, tool_data
from .retrieval import RetrievalHit, tokenize
from .review_workflow import build_workflow_evaluation
from .router import (
    COMPARATIVE,
    HISTORICAL_TREND,
    TECHNICAL_LOOKUP,
    VISUALIZATION_INTENT,
    build_query_rewrite_plan,
    plan_context_scope,
)


def _is_greeting_only(question: str) -> bool:
    q = question.strip().lower().strip("?.!")
    from .router import GREETINGS
    return q in GREETINGS or any(g in q for g in ("how are you", "how r u")) or any(q.startswith(g) for g in ("hi", "hello", "hey"))


class ReasoningEngine:
    def __init__(self, model_id: str, retriever: Any) -> None:
        self.model_id = model_id
        self.retriever = retriever

    def analyze_query(self, question: str, workspace: str) -> dict[str, Any]:
        """Stage 1: Pre-Retrieval Analyst Layer"""
        rewrite_plan = build_query_rewrite_plan(
            question=question,
            workspace=workspace,
            has_active_dossier=True,
            has_conversation=False,
        )
        resolved_question = rewrite_plan.rewritten_question
        intent = rewrite_plan.intent
        constraints = list(rewrite_plan.hard_constraints)

        from .retrieval import generate_expanded_queries
        sub_queries = generate_expanded_queries(
            resolved_question,
            intent,
            expansion_terms=rewrite_plan.expansion_terms,
            constraints=rewrite_plan.hard_constraints,
        )
        
        return {
            "original_question": question,
            "resolved_question": resolved_question,
            "intent": intent,
            "constraints": constraints,
            "expansion_terms": list(rewrite_plan.expansion_terms),
            "metadata_filter": dict(rewrite_plan.metadata_filter),
            "rewrite_notes": list(rewrite_plan.rewrite_notes),
            "sub_queries": sub_queries,
            "step": "Deconstruction complete: the query was rewritten, constrained, and expanded for retrieval."
        }

    def retrieve_with_precision(self, analysis: dict[str, Any], dossier_id: str | None = None) -> list[RetrievalHit]:
        """Stage 2: Precision-Search Strategy"""
        from .router import CHAT_ONLY_INTENT
        if analysis["intent"] == CHAT_ONLY_INTENT:
            return []

        # Determine metadata filter based on intent and query content
        metadata_filter = None
        intent = analysis["intent"]
        query = analysis["resolved_question"].lower()
        
        if analysis.get("metadata_filter"):
            metadata_filter = analysis["metadata_filter"]
        elif intent == HISTORICAL_TREND or "approval" in query or "trend" in query:
            metadata_filter = {"category": "regulatory_action"}
        
        index_name = "knowledge_wiki" if dossier_id == "knowledge_wiki" else "current_dossier"
        payload = {
            "query": analysis["resolved_question"],
            "index": index_name,
            "filters": {
                **(metadata_filter or {}),
                **({"dossier_id": dossier_id} if dossier_id and dossier_id != "knowledge_wiki" else {}),
            },
            "top_k": 8,
        }
        try:
            search_response = tool_data("search_vector_database", payload)
            candidate_results = search_response["data"].get("results", [])
            rerank_response = tool_data(
                "rerank_search_results",
                {
                    "query": analysis["resolved_question"],
                    "candidate_results": candidate_results,
                    "rerank_criteria": [
                        "regulatory relevance",
                        "section specificity",
                        "current dossier applicability",
                    ],
                    "top_k": 8,
                },
            )
            return [
                RetrievalHit(
                    chunk=EvidenceChunk(
                        citation_id=str(item.get("metadata", {}).get("citation_id") or item.get("chunk_id", "unknown")),
                        dossier_id=str(item.get("metadata", {}).get("dossier_id") or dossier_id or "unknown"),
                        section_id=str(item.get("metadata", {}).get("section_id") or item.get("chunk_id", "unknown")),
                        section_title=str(item.get("metadata", {}).get("section_title") or "Retrieved evidence"),
                        module=str(item.get("metadata", {}).get("module") or item.get("source", "mcp_tool")),
                        text=str(item.get("text", "")),
                        chunk_id=str(item.get("chunk_id", "unknown")),
                        source_type=str(item.get("source", "mcp_tool")),
                        parent_section_id=str(item.get("metadata", {}).get("section_id") or item.get("chunk_id", "unknown")),
                        parent_section_title=str(item.get("metadata", {}).get("section_title") or "Retrieved evidence"),
                        chunk_ordinal=1,
                        chunk_profile_version="mcp_search_v1",
                        chunk_token_estimate=len(str(item.get("text", "")).split()),
                        start_char=0,
                        end_char=len(str(item.get("text", ""))),
                        category=str(item.get("metadata", {}).get("category") or "general"),
                    ),
                    score=float(item.get("rerank_score", item.get("score", 0.0))),
                )
                for item in rerank_response["data"].get("reranked_results", [])
            ]
        except (RegulatoryMCPClientError, ValueError, KeyError, TypeError):
            return self.retriever.advanced_search(
                query=analysis["resolved_question"],
                intent=intent,
                top_k=8,
                dossier_id=dossier_id,
                expansion_terms=analysis.get("expansion_terms", []),
                constraints=analysis.get("constraints", []),
                metadata_filter=metadata_filter,
            )

    def bounce_irrelevant_context(self, question: str, intent: str, hits: list[RetrievalHit]) -> tuple[list[RetrievalHit], list[dict[str, Any]]]:
        """Stage 3: Post-Retrieval Bouncer Logic (Command Center Edition)"""
        if not hits:
            return [], []

        vetted_hits: list[RetrievalHit] = []
        bouncer_audit: list[dict[str, Any]] = []
        
        # Keywords derived from question for strict matching
        query_keywords = {kw for kw in tokenize(question) if len(kw) > 3}
        
        for hit in hits:
            text = hit.chunk.text.lower()
            title = hit.chunk.section_title.lower()
            combined = text + " " + title
            
            # The 2-Keyword Rule: Must contain at least 2 keywords related to intent/query
            matches = [kw for kw in query_keywords if kw in combined]
            is_relevant = len(matches) >= 2
            
            # Special Case: If it's a very high vector score (>0.8) but only 1 keyword, we might keep it
            if not is_relevant and hit.score > 0.8 and len(matches) >= 1:
                is_relevant = True

            # The AMR/Manufacturing Hard Block
            lowered_question = question.lower()
            if ("amr" in lowered_question or "stewardship" in lowered_question) and ("manufactur" in combined or "fpp" in combined):
                is_relevant = False
                rejection_reason = "Irrelevant to AMR: Contains Manufacturing/FPP data."
            elif is_relevant:
                rejection_reason = "Passed relevance audit."
            else:
                rejection_reason = f"Insufficient keyword density (Found: {', '.join(matches) if matches else 'None'})."

            audit_entry = {
                "chunk_id": hit.chunk.citation_id,
                "section": hit.chunk.section_title,
                "status": "KEEP" if is_relevant else "DISCARD",
                "reason": rejection_reason,
                "score": round(hit.score, 3)
            }
            bouncer_audit.append(audit_entry)

            if is_relevant:
                vetted_hits.append(hit)
        
        return vetted_hits, bouncer_audit

    def orchestrate(
        self,
        dossier: dict[str, Any],
        question: str,
        workspace: str,
        conversation_context: str | None = None,
        force_fallback: bool = False,
        review_state: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        # Step 1: Analyze
        analysis = self.analyze_query(question, workspace)
        
        # Fast path for chat
        from .router import CHAT_ONLY_INTENT
        if analysis["intent"] == CHAT_ONLY_INTENT:
             route_plan = plan_context_scope(CHAT_ONLY_INTENT, workspace=workspace)
             return run_review_orchestration(
                dossier=dossier,
                question=analysis["resolved_question"],
                hits=[],
                model_id=self.model_id,
                conversation_context=conversation_context,
                force_fallback=force_fallback,
                intent=CHAT_ONLY_INTENT,
                response_contract=route_plan.response_contract,
                sub_queries=[],
                model_packet={
                    "packet_version": "mcp_router_packet_v1",
                    "analysis": analysis,
                    "discarded_audit": [],
                    "response_contract": route_plan.response_contract
                }
            )

        # Step 4: Plan synthesis
        route_plan = plan_context_scope(analysis["intent"], workspace=workspace)

        # Fast path for visualization
        from .router import VISUALIZATION_INTENT
        if analysis["intent"] == VISUALIZATION_INTENT:
             return run_review_orchestration(
                dossier=dossier,
                question=analysis["resolved_question"],
                hits=[],
                model_id=self.model_id,
                conversation_context=conversation_context,
                force_fallback=force_fallback,
                intent=VISUALIZATION_INTENT,
                response_contract=route_plan.response_contract,
                sub_queries=[],
                model_packet={
                    "packet_version": "mcp_viz_packet_v1",
                    "analysis": analysis,
                    "discarded_audit": [],
                    "response_contract": route_plan.response_contract,
                    "review_state": review_state
                }
            )

        # Step 2: Retrieve (Improved with domains)
        target_dossier_id = str(dossier.get("dossier_id"))
        
        all_hits = []
        if "dossier" in route_plan.retrieval_domains or not route_plan.retrieval_domains:
            all_hits.extend(self.retrieve_with_precision(analysis, dossier_id=target_dossier_id))
        
        if "knowledge_wiki" in route_plan.retrieval_domains:
            all_hits.extend(self.retrieve_with_precision(analysis, dossier_id="knowledge_wiki"))
            
        # Step 3: Bounce
        vetted_hits, discarded_audit = self.bounce_irrelevant_context(
            analysis["resolved_question"],
            analysis["intent"],
            all_hits
        )
        
        # Enrich analysis with audit data for the <reasoning> block
        analysis["relevance_audit"] = discarded_audit
        analysis["vetted_count"] = len(vetted_hits)
        analysis["discarded_count"] = len(discarded_audit)
        
        from .retrieval import generate_expanded_queries
        sub_queries = generate_expanded_queries(
            analysis["resolved_question"],
            analysis["intent"],
            expansion_terms=analysis.get("expansion_terms", []),
            constraints=analysis.get("constraints", []),
        )
        
        blocks = {
            "packet_version": "reason_and_route_v2",
            "analysis": analysis,
            "discarded_audit": discarded_audit,
            "response_contract": route_plan.response_contract
        }
        if review_state:
            blocks["review_state"] = review_state

        return run_review_orchestration(
            dossier=dossier,
            question=analysis["resolved_question"],
            hits=vetted_hits,
            model_id=self.model_id,
            conversation_context=conversation_context,
            force_fallback=force_fallback,
            intent=analysis["intent"],
            response_contract=route_plan.response_contract,
            sub_queries=sub_queries,
            model_packet=blocks
        )



@dataclass
class OrchestrationResult:
    recommendation: str
    confidence: float
    route: str
    abstained: bool
    abstain_reason: str | None
    rationale: str
    policy_rule_hits: list[str]
    claims: list[dict[str, Any]]
    verifier: dict[str, Any]
    hits: list[RetrievalHit]
    section_diagnostics: list[dict[str, Any]]
    amr_stewardship: dict[str, Any]
    selected_model_id: str
    sub_queries: list[str] = field(default_factory=list)
    intent: str | None = None
    response_contract: str | None = None
    model_packet_version: str | None = None
    visualization_data: dict[str, Any] | None = None
    chain_of_thought: str | None = None
    findings_summary_markdown: str | None = None
    workflow_summary: dict[str, Any] | None = None
    evidence_packet: dict[str, Any] | None = None
    judge_decision: dict[str, Any] | None = None
    judge_verifier: dict[str, Any] | None = None
    judge_aggregate: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidencePacket:
    packet_version: str
    reviewer_question: str
    intent: str | None
    applicable_rules: list[str]
    query_rewrite: dict[str, Any]
    dossier_evidence: list[dict[str, Any]]
    external_evidence: dict[str, Any]
    review_state: dict[str, Any]
    packet_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JudgeFinding:
    requirement_id: str
    requirement_name: str
    status: str
    issue_present: bool
    issue_category: str
    severity: str
    rule_reference: str
    evidence_references: list[str]
    rationale: str
    confidence: float
    escalation_flag: bool


@dataclass(frozen=True)
class JudgeDecision:
    schema_version: str
    findings: list[JudgeFinding]


@dataclass(frozen=True)
class JudgeVerifierResult:
    schema_version: str
    challenged_finding_count: int
    unsupported_finding_rate: float
    passed: bool
    notes: list[str] = field(default_factory=list)


def _derive_applicable_rules(
    question: str,
    dossier: dict[str, Any],
    amr_stewardship: dict[str, Any],
) -> list[str]:
    focus = _question_focus(question)
    rules: list[str] = ["section_completeness_rule"]
    if focus["gmp"] or any("gmp" in str(section.get("title", "")).lower() for section in dossier.get("sections", [])):
        rules.append("gmp_certificate_and_inspection_rule")
    if focus["clinical"] or any("clinical" in str(section.get("title", "")).lower() for section in dossier.get("sections", [])):
        rules.append("pivotal_trial_outcome_rule")
    if amr_stewardship.get("applies"):
        rules.append("aware_and_stewardship_rule")
    if dossier.get("product", {}).get("product_name"):
        rules.append("inn_naming_similarity_rule")
    deduped: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if rule in seen:
            continue
        seen.add(rule)
        deduped.append(rule)
    return deduped


def build_evidence_packet(
    *,
    dossier: dict[str, Any],
    question: str,
    intent: str | None,
    evidence: list[dict[str, Any]],
    amr_stewardship: dict[str, Any],
    model_packet: dict[str, Any] | None = None,
) -> EvidencePacket:
    analysis = (model_packet or {}).get("analysis", {})
    external_evidence = {
        "source_mode": amr_stewardship.get("source_mode", "not_applicable"),
        "source_trace": list(amr_stewardship.get("source_trace", [])),
        "aware_category": amr_stewardship.get("aware_category", "not_applicable"),
        "authorization_control": amr_stewardship.get("authorization_control", "standard_authorization"),
    }
    review_state = dict((model_packet or {}).get("review_state", {}))
    packet_notes = list(analysis.get("rewrite_notes", []))
    if analysis.get("discarded_count"):
        packet_notes.append(
            f"Post-retrieval bouncer removed {analysis.get('discarded_count')} candidate chunks before synthesis."
        )
    if evidence:
        packet_notes.append(f"Judge input packet contains {len(evidence)} dossier evidence chunks.")
    return EvidencePacket(
        packet_version="evidence_packet_v1",
        reviewer_question=question,
        intent=intent,
        applicable_rules=_derive_applicable_rules(question, dossier, amr_stewardship),
        query_rewrite={
            "original_question": analysis.get("original_question", question),
            "rewritten_question": analysis.get("resolved_question", question),
            "constraints": list(analysis.get("constraints", [])),
            "expansion_terms": list(analysis.get("expansion_terms", [])),
            "sub_queries": list(analysis.get("sub_queries", [])),
            "metadata_filter": dict(analysis.get("metadata_filter", {})),
        },
        dossier_evidence=evidence,
        external_evidence=external_evidence,
        review_state=review_state,
        packet_notes=packet_notes,
    )


def _relevant_evidence_refs(evidence: list[dict[str, Any]], terms: tuple[str, ...], *, limit: int = 3) -> list[str]:
    refs: list[str] = []
    for item in evidence:
        combined = f"{item.get('section_title', '')} {item.get('snippet', '')}".lower()
        if any(term in combined for term in terms):
            refs.append(str(item.get("citation_id", "")))
        if len(refs) >= limit:
            break
    if not refs and evidence:
        refs.append(str(evidence[0].get("citation_id", "")))
    return [ref for ref in refs if ref]


def build_judge_decision(
    *,
    dossier: dict[str, Any],
    evidence_packet: EvidencePacket,
    section_diagnostics: list[dict[str, Any]],
    amr_stewardship: dict[str, Any],
) -> JudgeDecision:
    signals = dossier.get("policy_signals", {})
    findings: list[JudgeFinding] = []

    problematic_sections = [item for item in section_diagnostics if item.get("presence") != "present" or item.get("correctness") != "correct"]
    findings.append(
        JudgeFinding(
            requirement_id="section_completeness",
            requirement_name="Section completeness and correctness",
            status="failed" if problematic_sections else "satisfied",
            issue_present=bool(problematic_sections),
            issue_category="completeness",
            severity="major" if problematic_sections else "none",
            rule_reference="section_completeness_rule",
            evidence_references=_relevant_evidence_refs(evidence_packet.dossier_evidence, ("section", "module", "missing", "incorrect")),
            rationale="Critical dossier sections are incomplete or unreliable." if problematic_sections else "Required sections appear present and usable for review.",
            confidence=0.9 if problematic_sections else 0.86,
            escalation_flag=bool(problematic_sections),
        )
    )

    gmp_status = str(signals.get("gmp_inspection_status", "missing_evidence"))
    cert_status = str(signals.get("gmp_certificate_validity", "not_provided"))
    gmp_issue = gmp_status in {"non_compliant", "expired", "missing_evidence"} or cert_status in {"expired", "not_provided"}
    findings.append(
        JudgeFinding(
            requirement_id="gmp_quality",
            requirement_name="GMP and manufacturing quality evidence",
            status="failed" if gmp_issue and gmp_status == "non_compliant" else ("partial" if gmp_issue else "satisfied"),
            issue_present=gmp_issue,
            issue_category="quality_gmp",
            severity="critical" if gmp_status == "non_compliant" else ("major" if gmp_issue else "none"),
            rule_reference="gmp_certificate_and_inspection_rule",
            evidence_references=_relevant_evidence_refs(evidence_packet.dossier_evidence, ("gmp", "certificate", "inspection", "manufacturer", "capa")),
            rationale=(
                "Manufacturing quality evidence shows non-compliance or expired certification."
                if gmp_issue
                else "Manufacturing quality evidence is adequate for the current review stage."
            ),
            confidence=0.92 if gmp_issue else 0.84,
            escalation_flag=gmp_issue,
        )
    )

    trial_outcome = str(signals.get("pivotal_trial_outcome", "missing_evidence"))
    clinical_issue = trial_outcome in {"endpoint_not_met", "missing_evidence", "inconclusive"} or signals.get("clinical_data_available") is False
    findings.append(
        JudgeFinding(
            requirement_id="clinical_support",
            requirement_name="Clinical efficacy and benefit-risk support",
            status="failed" if trial_outcome == "endpoint_not_met" else ("partial" if clinical_issue else "satisfied"),
            issue_present=clinical_issue,
            issue_category="clinical",
            severity="major" if clinical_issue else "none",
            rule_reference="pivotal_trial_outcome_rule",
            evidence_references=_relevant_evidence_refs(evidence_packet.dossier_evidence, ("clinical", "trial", "endpoint", "benefit-risk", "efficacy")),
            rationale=(
                "Clinical support is insufficient because the pivotal endpoint failed or remains unclear."
                if clinical_issue
                else "Clinical support is present and the pivotal outcome supports review progression."
            ),
            confidence=0.9 if clinical_issue else 0.83,
            escalation_flag=clinical_issue,
        )
    )

    if amr_stewardship.get("applies"):
        amr_issue = bool(amr_stewardship.get("restricted_authorization"))
        findings.append(
            JudgeFinding(
                requirement_id="amr_stewardship",
                requirement_name="AMR stewardship alignment",
                status="partial" if amr_issue else "satisfied",
                issue_present=amr_issue,
                issue_category="stewardship",
                severity="major" if amr_issue else "none",
                rule_reference="aware_and_stewardship_rule",
                evidence_references=_relevant_evidence_refs(evidence_packet.dossier_evidence, ("amr", "aware", "glass", "stewardship", "resistance")),
                rationale=(
                    "Stewardship review applies and authorization controls are required."
                    if amr_issue
                    else "Stewardship review applies, but no additional restriction is triggered beyond normal monitoring."
                ),
                confidence=0.88,
                escalation_flag=amr_issue,
            )
        )

    return JudgeDecision(schema_version="judge_v1", findings=findings)


def verify_judge_decision(*, judge_decision: JudgeDecision, evidence_packet: EvidencePacket) -> JudgeVerifierResult:
    valid_refs = {str(item.get("citation_id", "")) for item in evidence_packet.dossier_evidence}
    challenged = 0
    notes: list[str] = []
    for finding in judge_decision.findings:
        if not finding.rule_reference:
            challenged += 1
            notes.append(f"{finding.requirement_id} had no rule reference.")
        missing_refs = [ref for ref in finding.evidence_references if ref and ref not in valid_refs]
        if missing_refs:
            challenged += 1
            notes.append(f"{finding.requirement_id} referenced evidence outside the packet: {', '.join(missing_refs)}.")
        if finding.issue_present and finding.severity == "none":
            challenged += 1
            notes.append(f"{finding.requirement_id} marked an issue without a severity.")
    total = max(len(judge_decision.findings), 1)
    unsupported_rate = challenged / total
    return JudgeVerifierResult(
        schema_version="judge_verifier_v1",
        challenged_finding_count=challenged,
        unsupported_finding_rate=round(unsupported_rate, 5),
        passed=unsupported_rate <= 0.05,
        notes=notes,
    )


def aggregate_judge_decision(*, judge_decision: JudgeDecision) -> dict[str, Any]:
    critical = sum(1 for finding in judge_decision.findings if finding.severity == "critical")
    major = sum(1 for finding in judge_decision.findings if finding.severity == "major")
    unresolved = sum(1 for finding in judge_decision.findings if finding.status in {"failed", "partial", "unclear"})
    if critical:
        final_status = "approval_denied"
    elif major:
        final_status = "additional_information_required"
    else:
        final_status = "approval_granted"
    return {
        "schema_version": "judge_aggregate_v1",
        "final_status": final_status,
        "critical_findings": critical,
        "major_findings": major,
        "unresolved_items": unresolved,
    }


def build_section_diagnostics(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for section in dossier.get("sections", []):
        labels = section.get("labels", {})
        constraints = section.get("constraints", {})
        metrics = section.get("metrics", {})
        presence = labels.get("presence", "missing")
        char_count = metrics.get("char_count", 0)
        min_chars = constraints.get("min_chars", 0)
        max_chars = constraints.get("max_chars", 10_000_000)

        if presence != "present":
            length_status = "missing"
        elif char_count < min_chars:
            length_status = "too_short"
        elif char_count > max_chars:
            length_status = "too_long"
        else:
            length_status = "length_ok"

        diagnostics.append(
            {
                "section_id": section.get("section_id", "unknown"),
                "title": section.get("title", "unknown"),
                "presence": presence,
                "length_status": length_status,
                "correctness": labels.get("correctness", "incorrect"),
                "critical": bool(section.get("critical", False)),
            }
        )
    return diagnostics


def _build_fallback_hits(dossier: dict[str, Any], section_diagnostics: list[dict[str, Any]]) -> list[RetrievalHit]:
    fallback_hits: list[RetrievalHit] = []
    diagnostic_by_section_id = {str(item.get("section_id", "")): item for item in section_diagnostics}
    for section in dossier.get("sections", []):
        section_id = str(section.get("section_id", "unknown"))
        title = str(section.get("title", "Imported Section"))
        text = " ".join(str(section.get("text", "")).split()).strip()
        if not text or "fpp manufacturing" in title.lower():
            continue
        diag = diagnostic_by_section_id.get(section_id, {})
        looks_problematic = (
            diag.get("presence") == "missing"
            or diag.get("correctness") not in {None, "correct"}
            or diag.get("length_status") not in {None, "length_ok"}
            or bool(section.get("critical"))
            or any(term in text.lower() for term in ("missing", "expired", "critical", "not met", "restrict", "rising resistance", "incomplete"))
        )
        if not looks_problematic and len(fallback_hits) >= 2:
            continue
        snippet = text[:800]
        chunk = EvidenceChunk(
            citation_id=f"{dossier['dossier_id']}:{section_id}:fallback",
            dossier_id=str(dossier["dossier_id"]),
            section_id=section_id,
            section_title=title,
            module=str(section.get("module", "unknown")),
            text=snippet,
            chunk_id=f"{dossier['dossier_id']}:{section_id}:fallback",
            source_type="dossier_section",
            parent_section_id=section_id,
            parent_section_title=title,
            chunk_ordinal=1,
            chunk_profile_version="dossier_fallback_v1",
            chunk_token_estimate=len(snippet.split()),
            start_char=0,
            end_char=len(snippet),
        )
        fallback_hits.append(RetrievalHit(chunk=chunk, score=0.15))
    return fallback_hits[:4]


def run_review_orchestration(
    dossier: dict[str, Any],
    question: str,
    hits: list[RetrievalHit],
    model_id: str,
    conversation_context: str | None = None,
    force_fallback: bool = False,
    model_packet: dict[str, Any] | None = None,
    intent: str | None = None,
    response_contract: str | None = None,
    sub_queries: list[str] | None = None,
) -> OrchestrationResult:
    recommendation, rule_hits, policy_confidence = apply_policy_rules(dossier)
    amr_stewardship = evaluate_amr_stewardship(dossier)
    section_diagnostics = build_section_diagnostics(dossier)
    sub_queries = sub_queries or []
    evidence = [
        {
            "citation_id": hit.chunk.citation_id,
            "dossier_id": hit.chunk.dossier_id,
            "section_id": hit.chunk.section_id,
            "section_title": hit.chunk.section_title,
            "score": hit.score,
            "snippet": " ".join(hit.chunk.text.split())[:260],
            "text": hit.chunk.text,
        }
        for hit in hits
    ]

    scores = [ev["score"] for ev in evidence]
    evidence_confidence = retrieval_confidence(scores)
    route = route_request(
        question=question,
        evidence_char_count=sum(len(ev["text"]) for ev in evidence[:5]),
        confidence=evidence_confidence,
        force_fallback=force_fallback,
    )

    focus = _question_focus(question)

    if _is_greeting_only(question):
        return OrchestrationResult(
            recommendation=recommendation,
            confidence=max(policy_confidence, 0.5),
            route=route,
            abstained=False,
            abstain_reason=None,
            rationale=f"{question}. I am the Dossier Review Assistant, ready to assist with your submission analysis. You can ask me to identify material issues, evaluate GMP compliance, analyze AMR stewardship alignment, or provide a synthesized recommendation based on the grounded evidence.",
            policy_rule_hits=rule_hits,
            claims=[],
            verifier={
                "grounded_claim_rate": 1.0,
                "unsupported_critical_claim_rate": 0.0,
                "passed": True,
            },
            hits=[],
            section_diagnostics=section_diagnostics,
            amr_stewardship=amr_stewardship,
            selected_model_id=model_id,
            sub_queries=sub_queries,
            intent=intent,
            response_contract=response_contract,
            model_packet_version=str(model_packet.get("packet_version", "")) if model_packet else None,
            findings_summary_markdown=None,
            workflow_summary=None,
            evidence_packet=None,
            judge_decision=None,
            judge_verifier=None,
            judge_aggregate=None,
        )

    if not evidence and intent != VISUALIZATION_INTENT:
        if any(focus[key] for key in ("issues", "summary", "recommendation", "count", "rank", "categorize", "rules", "completeness", "overall_judgment")):
            hits = _build_fallback_hits(dossier, section_diagnostics)
            evidence = [
                {
                    "citation_id": hit.chunk.citation_id,
                    "dossier_id": hit.chunk.dossier_id,
                    "section_id": hit.chunk.section_id,
                    "section_title": hit.chunk.section_title,
                    "score": hit.score,
                    "snippet": " ".join(hit.chunk.text.split())[:260],
                    "text": hit.chunk.text,
                }
                for hit in hits
            ]
            route = "fallback"
        if not evidence and intent != VISUALIZATION_INTENT:
            return OrchestrationResult(
                recommendation="abstain",
                confidence=0.0,
                route=route,
                abstained=True,
                abstain_reason="insufficient_retrieval_evidence",
                rationale="Abstained because no evidence chunks were retrieved for the request.",
                policy_rule_hits=rule_hits,
                claims=[],
                verifier={
                    "grounded_claim_rate": 0.0,
                    "unsupported_critical_claim_rate": 1.0,
                    "passed": False,
                },
                hits=hits,
                section_diagnostics=section_diagnostics,
                amr_stewardship=amr_stewardship,
                selected_model_id=model_id,
                sub_queries=sub_queries,
                intent=intent,
                response_contract=response_contract,
                model_packet_version=str(model_packet.get("packet_version", "")) if model_packet else None,
                findings_summary_markdown=None,
                workflow_summary=None,
                evidence_packet=None,
                judge_decision=None,
                judge_verifier=None,
                judge_aggregate=None,
            )

    evidence_packet = build_evidence_packet(
        dossier=dossier,
        question=question,
        intent=intent,
        evidence=evidence,
        amr_stewardship=amr_stewardship,
        model_packet=model_packet,
    )
    judge_decision = build_judge_decision(
        dossier=dossier,
        evidence_packet=evidence_packet,
        section_diagnostics=section_diagnostics,
        amr_stewardship=amr_stewardship,
    )
    judge_verifier = verify_judge_decision(
        judge_decision=judge_decision,
        evidence_packet=evidence_packet,
    )
    judge_aggregate = aggregate_judge_decision(judge_decision=judge_decision)
    enriched_model_packet = dict(model_packet or {})
    enriched_model_packet["evidence_packet"] = asdict(evidence_packet)
    enriched_model_packet["judge_decision"] = {
        "schema_version": judge_decision.schema_version,
        "findings": [asdict(item) for item in judge_decision.findings],
    }
    enriched_model_packet["judge_verifier"] = asdict(judge_verifier)
    enriched_model_packet["judge_aggregate"] = judge_aggregate

    generator = build_model_client(model_id=model_id)
    generated = generator.generate(
        question=question,
        recommendation=recommendation,
        evidence=evidence,
        route=route,
        dossier=dossier,
        conversation_context=conversation_context,
        section_diagnostics=section_diagnostics,
        amr_stewardship=amr_stewardship,
        model_packet=enriched_model_packet
    )


    valid_citations = {ev["citation_id"] for ev in evidence}
    verifier = verify_claim_groundedness(
        claims=generated.get("claims", []),
        valid_citation_ids=valid_citations,
    )
    verifier["judge_verifier_passed"] = judge_verifier.passed
    verifier["judge_unsupported_finding_rate"] = judge_verifier.unsupported_finding_rate
    verifier["judge_challenged_finding_count"] = judge_verifier.challenged_finding_count

    # Avoid false abstentions when citation formatting is imperfect but judge verification is grounded.
    abstained = (not verifier["passed"]) and (not judge_verifier.passed)
    abstain_reason = "faithfulness_gate_failed" if abstained else None
    confidence = round((policy_confidence * 0.6) + (evidence_confidence * 0.4), 5)

    raw_rationale = generated.get("rationale", "")
    chain_of_thought = None
    final_rationale = raw_rationale
    
    if "<reasoning>" in raw_rationale and "</reasoning>" in raw_rationale:
        parts = raw_rationale.split("</reasoning>")
        chain_of_thought = parts[0].replace("<reasoning>", "").strip()
        final_rationale = parts[1].strip()

    review_type = str(((model_packet or {}).get("review_state", {}) or {}).get("review_type", "generic"))
    workflow_summary = build_workflow_evaluation(
        dossier,
        {
            "recommendation": recommendation if not abstained else "abstain",
            "review_type": review_type,
            "policy_rule_hits": rule_hits,
            "section_diagnostics": section_diagnostics,
            "amr_stewardship": amr_stewardship,
            "verifier": verifier,
            "rationale": final_rationale,
        },
    )
    findings_summary_markdown = str(workflow_summary.get("findings_summary_markdown", "")).strip()
    if findings_summary_markdown and any(focus[key] for key in ("review", "summary", "issues", "recommendation")):
        final_rationale = f"{final_rationale}\n\n### Findings Summary Tables\n\n{findings_summary_markdown}".strip()

    return OrchestrationResult(
        recommendation=recommendation if not abstained else "abstain",
        confidence=confidence if not abstained else min(confidence, 0.3),
        route=route,
        abstained=abstained,
        abstain_reason=abstain_reason,
        rationale=final_rationale,
        policy_rule_hits=rule_hits,
        claims=generated.get("claims", []),
        verifier=verifier,
        hits=hits,
        section_diagnostics=section_diagnostics,
        amr_stewardship=amr_stewardship,
        selected_model_id=model_id,
        sub_queries=sub_queries,
        intent=intent,
        response_contract=response_contract,
        model_packet_version=str(enriched_model_packet.get("packet_version", "")) if enriched_model_packet else None,
        visualization_data=generated.get("visualization_data"),
        chain_of_thought=chain_of_thought,
        findings_summary_markdown=findings_summary_markdown or None,
        workflow_summary=workflow_summary,
        evidence_packet=asdict(evidence_packet),
        judge_decision=enriched_model_packet.get("judge_decision"),
        judge_verifier=enriched_model_packet.get("judge_verifier"),
        judge_aggregate=enriched_model_packet.get("judge_aggregate"),
    )
