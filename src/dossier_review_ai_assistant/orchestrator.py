from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gates import retrieval_confidence, route_request, verify_claim_groundedness
from .inference import Gemma4Client
from .policy import apply_policy_rules
from .retrieval import RetrievalHit


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


def run_review_orchestration(
    dossier: dict[str, Any],
    question: str,
    hits: list[RetrievalHit],
    force_fallback: bool = False,
) -> OrchestrationResult:
    recommendation, rule_hits, policy_confidence = apply_policy_rules(dossier)
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

    if not evidence:
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
            section_diagnostics=build_section_diagnostics(dossier),
        )

    generator = Gemma4Client()
    generated = generator.generate(
        question=question,
        recommendation=recommendation,
        evidence=evidence,
        route=route,
    )

    valid_citations = {ev["citation_id"] for ev in evidence}
    verifier = verify_claim_groundedness(
        claims=generated.get("claims", []),
        valid_citation_ids=valid_citations,
    )

    abstained = not verifier["passed"]
    abstain_reason = "faithfulness_gate_failed" if abstained else None
    confidence = round((policy_confidence * 0.6) + (evidence_confidence * 0.4), 5)

    return OrchestrationResult(
        recommendation=recommendation if not abstained else "abstain",
        confidence=confidence if not abstained else min(confidence, 0.3),
        route=route,
        abstained=abstained,
        abstain_reason=abstain_reason,
        rationale=generated.get("rationale", ""),
        policy_rule_hits=rule_hits,
        claims=generated.get("claims", []),
        verifier=verifier,
        hits=hits,
        section_diagnostics=build_section_diagnostics(dossier),
    )

