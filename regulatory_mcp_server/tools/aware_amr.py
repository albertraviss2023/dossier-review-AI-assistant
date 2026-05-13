from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import (
    AWaReResult,
    ComputeAntimicrobialSimilarityRequest,
    FetchAwareReserveReferenceRequest,
)

from .common import build_tool_envelope, tool_audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AWARE_CACHE = PROJECT_ROOT / "regulatory_mcp_server" / "data" / "cached_sources" / "aware_reference.json"
LOGGER = logging.getLogger("regulatory_mcp_server.tools.aware_amr")


def _normalize(value: str) -> str:
    return " ".join(str(value).lower().split())


@lru_cache(maxsize=2)
def _load_reference() -> dict[str, Any]:
    return json.loads(AWARE_CACHE.read_text(encoding="utf-8"))


@mcp.tool(name="fetch_aware_reserve_reference", description="Resolve local cached AWaRe / Reserve stewardship reference data for an active ingredient.")
@tool_audit(tool_name="fetch_aware_reserve_reference", logger=LOGGER)
def fetch_aware_reserve_reference(active_ingredient: str, source_mode: str = "cached") -> dict[str, Any]:
    """
    Fetch AWaRe (Access, Watch, Reserve) antimicrobial stewardship data.
    
    Args:
        active_ingredient: The name of the antimicrobial (e.g., 'amoxicillin', 'colistin', 'levofloxacin').
        source_mode: The retrieval mode ('cached' is recommended for local testing).
        
    Example:
        active_ingredient: "colistin"
    """
    payload = {"active_ingredient": active_ingredient, "source_mode": source_mode}
    request = FetchAwareReserveReferenceRequest.model_validate(payload)
    ref = _load_reference()
    record = next(
        (row for row in ref.get("records", []) if _normalize(row.get("active_ingredient", "")) == _normalize(request.active_ingredient)),
        None,
    )
    if record is None:
        data = AWaReResult(
            active_ingredient=request.active_ingredient,
            is_antimicrobial=False,
            aware_category="Unknown",
            reserve_related=False,
            source=ref.get("source", "cached_fixture"),
            source_date=ref.get("source_date", "unknown"),
        ).model_dump(mode="json")
        warnings = ["Active ingredient was not found in the local AWaRe fixture."]
    else:
        data = AWaReResult(
            active_ingredient=record["active_ingredient"],
            is_antimicrobial=bool(record["is_antimicrobial"]),
            aware_category=record["aware_category"],
            reserve_related=bool(record["reserve_related"]),
            source=ref.get("source", "cached_fixture"),
            source_date=ref.get("source_date", "unknown"),
        ).model_dump(mode="json")
        warnings = []
    return build_tool_envelope(
        tool_name="fetch_aware_reserve_reference",
        payload=payload,
        data=data,
        warnings=warnings,
        source_refs=[
            {
                "source": "aware_reference_cache",
                "source_type": "cache",
                "metadata": {"path": str(AWARE_CACHE)},
            }
        ],
    )


@mcp.tool(name="compute_antimicrobial_similarity", description="Compute AWaRe stewardship similarity and reserve caution from cached antimicrobial reference data.")
@tool_audit(tool_name="compute_antimicrobial_similarity", logger=LOGGER)
def compute_antimicrobial_similarity(
    active_ingredient: str,
    aware_reference: dict[str, Any],
    chemical_structure: str | None = None,
    comparison_mode: str = "class_or_structure",
) -> dict[str, Any]:
    payload = {
        "active_ingredient": active_ingredient,
        "aware_reference": aware_reference,
        "chemical_structure": chemical_structure,
        "comparison_mode": comparison_mode,
    }
    request = ComputeAntimicrobialSimilarityRequest.model_validate(payload)
    aware = request.aware_reference
    is_antimicrobial = bool(aware.get("is_antimicrobial"))
    aware_category = str(aware.get("aware_category", "Unknown"))
    reserve_related = bool(aware.get("reserve_related"))
    nearest_reserve_agent = aware.get("nearest_reserve_agent")

    if not is_antimicrobial:
        data = {
            "is_antimicrobial": False,
            "aware_category": aware_category if aware_category in {"Access", "Watch", "Reserve", "Not listed", "Unknown"} else "Not listed",
            "reserve_similarity": {
                "score": 0.0,
                "nearest_reserve_agent": None,
                "basis": "not_available",
            },
            "stewardship_flag": "not_applicable",
            "recommendation": "No AWaRe stewardship review is required because the product is not antimicrobial.",
        }
        return build_tool_envelope(
            tool_name="compute_antimicrobial_similarity",
            payload=payload,
            data=data,
            warnings=[],
            source_refs=[],
        )

    if aware_category == "Reserve":
        score = 1.0
        stewardship_flag = "required_control"
        recommendation = "Reserve-category or reserve-related products require the highest stewardship caution and controlled handling."
    elif aware_category == "Watch":
        score = 0.72
        stewardship_flag = "reserve_caution" if reserve_related else "review_required"
        recommendation = "Watch-category antimicrobial products require stewardship review and may need additional restrictions depending on comparator and resistance context."
    elif aware_category == "Access":
        score = 0.25
        stewardship_flag = "review_required"
        recommendation = "Access-category antimicrobial products still require AWaRe review, but usually remain under routine stewardship monitoring."
    else:
        score = 0.0
        stewardship_flag = "review_required"
        recommendation = "The antimicrobial is not clearly mapped in the current AWaRe reference and should be reviewed manually."

    data = {
        "is_antimicrobial": True,
        "aware_category": aware_category,
        "reserve_similarity": {
            "score": round(score, 4),
            "nearest_reserve_agent": nearest_reserve_agent,
            "basis": "class-level" if nearest_reserve_agent or aware_category in {"Watch", "Reserve"} else "not_available",
        },
        "stewardship_flag": stewardship_flag,
        "recommendation": recommendation,
    }
    return build_tool_envelope(
        tool_name="compute_antimicrobial_similarity",
        payload=payload,
        data=data,
        warnings=["Structure-level comparison is not enabled in the current local fixture implementation."],
        source_refs=[],
    )
