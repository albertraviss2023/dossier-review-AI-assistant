from __future__ import annotations

from typing import Any


def retrieval_confidence(scores: list[float]) -> float:
    if not scores:
        return 0.0
    top = max(scores)
    if len(scores) == 1:
        return min(1.0, top / 10.0)
    avg = sum(scores) / len(scores)
    spread = (top - avg) / max(top, 1e-6)
    return max(0.0, min(1.0, (top / 10.0) * (0.6 + 0.4 * spread)))


def route_request(
    question: str,
    evidence_char_count: int,
    confidence: float,
    force_fallback: bool = False,
) -> str:
    if force_fallback:
        return "fallback"
    if confidence < 0.35:
        return "fallback"
    complexity_score = len(question) + evidence_char_count
    if complexity_score > 10000:
        return "fallback"
    return "standard"


def verify_claim_groundedness(claims: list[dict[str, Any]], valid_citation_ids: set[str]) -> dict[str, Any]:
    if not claims:
        return {
            "grounded_claim_rate": 0.0,
            "unsupported_critical_claim_rate": 1.0,
            "passed": False,
        }

    grounded = 0
    unsupported = 0
    for claim in claims:
        citation_id = str(claim.get("citation_id", ""))
        if citation_id and citation_id in valid_citation_ids:
            grounded += 1
        else:
            unsupported += 1

    total = len(claims)
    grounded_rate = grounded / total
    unsupported_rate = unsupported / total
    return {
        "grounded_claim_rate": round(grounded_rate, 5),
        "unsupported_critical_claim_rate": round(unsupported_rate, 5),
        "passed": grounded_rate >= 0.95 and unsupported_rate <= 0.03,
    }

