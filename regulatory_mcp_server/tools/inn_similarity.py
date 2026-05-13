from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import (
    ComputeInnSimilarityRequest,
    FetchWhoInnCandidatesRequest,
    SimilarityResult,
)

from .common import build_tool_envelope, tool_audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WHO_INN_CACHE = PROJECT_ROOT / "regulatory_mcp_server" / "data" / "cached_sources" / "who_inn_candidates.json"
LOGGER = logging.getLogger("regulatory_mcp_server.tools.inn_similarity")


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch.isalnum())


@lru_cache(maxsize=2)
def _load_candidates() -> list[dict[str, Any]]:
    payload = json.loads(WHO_INN_CACHE.read_text(encoding="utf-8"))
    return list(payload.get("records", []))


@mcp.tool(name="fetch_who_inn_candidates", description="Fetch candidate WHO INNs for an active ingredient or proposed product name from the local cache.")
@tool_audit(tool_name="fetch_who_inn_candidates", logger=LOGGER)
def fetch_who_inn_candidates(
    active_ingredient: str,
    proposed_name: str,
) -> dict[str, Any]:
    payload = {
        "active_ingredient": active_ingredient,
        "proposed_name": proposed_name,
    }
    request = FetchWhoInnCandidatesRequest.model_validate(payload)
    active = _normalize(request.active_ingredient)
    proposed = _normalize(request.proposed_name)
    candidates: list[dict[str, Any]] = []
    for record in _load_candidates():
        inn = str(record.get("inn", ""))
        aliases = [_normalize(str(item)) for item in record.get("aliases", [])]
        match_basis = None
        if active and active in aliases:
            match_basis = "active_ingredient"
        elif proposed and any(alias.startswith(proposed[:4]) or proposed.startswith(alias[:4]) for alias in aliases if alias):
            match_basis = "name_similarity"
        if match_basis:
            candidates.append(
                {
                    "inn": inn,
                    "source_url": record.get("source_url"),
                    "match_basis": match_basis,
                }
            )
    warnings = []
    if not candidates:
        warnings.append("No WHO INN candidate was matched from the local cache.")
    return build_tool_envelope(
        tool_name="fetch_who_inn_candidates",
        payload=payload,
        data={"candidates": candidates},
        warnings=warnings,
        source_refs=[
            {
                "source": "who_inn_cache",
                "source_type": "cache",
                "metadata": {"path": str(WHO_INN_CACHE)},
            }
        ],
    )


def _levenshtein_ratio(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    rows = len(left) + 1
    cols = len(right) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
    distance = matrix[-1][-1]
    return 1.0 - (distance / max(len(left), len(right), 1))


@mcp.tool(name="compute_inn_similarity", description="Compute orthographic and stem-based similarity between a proposed name and WHO INN candidates.")
@tool_audit(tool_name="compute_inn_similarity", logger=LOGGER)
def compute_inn_similarity(
    proposed_name: str,
    inn_candidates: list[str],
    threshold: float = 70.0,
) -> dict[str, Any]:
    payload = {
        "proposed_name": proposed_name,
        "inn_candidates": inn_candidates,
        "threshold": threshold,
    }
    request = ComputeInnSimilarityRequest.model_validate(payload)
    proposed = _normalize(request.proposed_name)
    best_inn = ""
    best_score = 0.0
    best_types: list[str] = []

    for candidate in request.inn_candidates:
        normalized_candidate = _normalize(candidate)
        score = _levenshtein_ratio(proposed, normalized_candidate) * 100.0
        similarity_types = ["orthographic"]
        if normalized_candidate[:4] and normalized_candidate[:4] in proposed:
            similarity_types.append("stem_based")
        if score > best_score:
            best_score = score
            best_inn = candidate
            best_types = similarity_types

    rule_result = "flagged" if best_score > request.threshold else "pass"
    decision_effect = "cannot_accept_until_resolved" if rule_result == "flagged" else "can_continue"
    warnings = ["phonetic similarity not available in the current local fixture implementation"] if best_inn else []
    similarity = SimilarityResult(
        proposed_name=request.proposed_name,
        best_match_inn=best_inn or "unknown",
        similarity_index=round(best_score, 4),
        similarity_type=best_types or ["orthographic"],
        rule_result=rule_result,
        decision_effect=decision_effect,
    )
    return build_tool_envelope(
        tool_name="compute_inn_similarity",
        payload=payload,
        data=similarity.model_dump(mode="json"),
        warnings=warnings,
        source_refs=[],
    )

