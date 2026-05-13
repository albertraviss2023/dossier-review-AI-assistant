from __future__ import annotations

import logging
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import RerankedResult, RerankSearchRequest

from dossier_review_ai_assistant.retrieval import tokenize

from .common import build_tool_envelope, tool_audit


LOGGER = logging.getLogger("regulatory_mcp_server.tools.reranker")

REGULATORY_KEYWORDS = {
    "rule",
    "guidance",
    "required",
    "contraindications",
    "warnings",
    "gmp",
    "evidence",
    "clinical",
    "patient",
    "information",
    "stewardship",
    "aware",
    "reserve",
    "watch",
}


def _overlap_score(query_tokens: set[str], text: str) -> float:
    candidate_tokens = {token for token in tokenize(text) if len(token) > 3}
    if not query_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)


@mcp.tool(name="rerank_search_results", description="Rerank candidate evidence chunks by regulatory relevance and dossier applicability.")
@tool_audit(tool_name="rerank_search_results", logger=LOGGER)
def rerank_search_results(
    query: str,
    candidate_results: list[dict[str, Any]],
    rerank_criteria: list[str] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    payload = {
        "query": query,
        "candidate_results": candidate_results,
        "rerank_criteria": rerank_criteria or [],
        "top_k": top_k,
    }
    request = RerankSearchRequest.model_validate(payload)
    query_tokens = {token for token in tokenize(request.query) if len(token) > 3}
    criteria = {item.lower() for item in request.rerank_criteria}

    ranked: list[dict[str, Any]] = []
    for candidate in request.candidate_results:
        text = candidate.text
        metadata = candidate.metadata or {}
        title = str(metadata.get("section_title", ""))
        source = str(candidate.source)
        original_score = float(candidate.score)

        regulatory_overlap = _overlap_score(query_tokens | REGULATORY_KEYWORDS, text + " " + title)
        query_overlap = _overlap_score(query_tokens, text + " " + title)
        section_specificity = 0.12 if metadata.get("section_id") else 0.0
        dossier_applicability = 0.1 if source == "dossier_section" else 0.04
        guidance_bonus = 0.08 if source == "knowledge_wiki" and "regulatory relevance" in criteria else 0.0
        current_dossier_bonus = 0.08 if "current dossier applicability" in criteria and source == "dossier_section" else 0.0
        specificity_bonus = 0.07 if "section specificity" in criteria and title else 0.0

        rerank_score = (
            (original_score * 0.45)
            + (query_overlap * 0.25)
            + (regulatory_overlap * 0.12)
            + section_specificity
            + dossier_applicability
            + guidance_bonus
            + current_dossier_bonus
            + specificity_bonus
        )

        reason_parts = []
        if query_overlap:
            reason_parts.append("direct query overlap")
        if regulatory_overlap:
            reason_parts.append("regulatory keyword alignment")
        if source == "dossier_section":
            reason_parts.append("current dossier applicability")
        if title:
            reason_parts.append("section-specific metadata")
        reason = ", ".join(reason_parts) or "score preserved from original retrieval ordering"

        ranked.append(
            RerankedResult(
                chunk_id=candidate.chunk_id,
                text=text,
                original_score=round(original_score, 6),
                rerank_score=round(rerank_score, 6),
                reason=reason,
                metadata=metadata,
            ).model_dump(mode="json")
        )

    ranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    reranked_results = ranked[: request.top_k]
    warnings: list[str] = []
    if not reranked_results:
        warnings.append("No candidate results were supplied for reranking.")

    return build_tool_envelope(
        tool_name="rerank_search_results",
        payload=payload,
        data={"reranked_results": reranked_results},
        warnings=warnings,
        source_refs=[],
    )
