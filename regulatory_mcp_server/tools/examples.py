from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import (
    CompareCurrentSectionRequest,
    GetSectionExamplesRequest,
    SectionExample,
)

from .common import build_tool_envelope, tool_audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "regulatory_mcp_server" / "data" / "test_examples"
LOGGER = logging.getLogger("regulatory_mcp_server.tools.examples")

DIMENSION_TERMS: dict[str, tuple[str, ...]] = {
    "completeness": ("indication", "dosage", "contraindication", "warning", "side effect", "storage"),
    "safety wording": ("warning", "precaution", "side effect"),
    "contraindications": ("contraindication", "must not", "do not take"),
    "dosage clarity": ("dose", "dosage", "take", "instructions"),
    "storage": ("storage", "store"),
    "indications": ("indication", "used for", "treatment"),
    "side_effects": ("side effect", "adverse"),
}


@lru_cache(maxsize=8)
def _load_examples(section_type: str) -> list[SectionExample]:
    path = EXAMPLES_DIR / f"{section_type}_examples.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [SectionExample.model_validate(row) for row in rows]


@mcp.tool(name="get_section_examples", description="Return correct and incorrect regulatory section examples from local fixtures.")
@tool_audit(tool_name="get_section_examples", logger=LOGGER)
def get_section_examples(
    section_type: str,
    example_type: str,
    product_type: str = "any",
    top_k: int = 5,
) -> dict[str, Any]:
    payload = {
        "section_type": section_type,
        "example_type": example_type,
        "product_type": product_type,
        "top_k": top_k,
    }
    request = GetSectionExamplesRequest.model_validate(payload)
    examples = _load_examples(request.section_type)
    filtered = [
        item
        for item in examples
        if (request.example_type == "both" or item.label == request.example_type)
        and (request.product_type == "any" or item.product_type in (request.product_type, "any"))
    ]
    filtered = filtered[: request.top_k]

    return build_tool_envelope(
        tool_name="get_section_examples",
        payload=payload,
        data={"examples": [item.model_dump(mode="json") for item in filtered]},
        warnings=["No section examples matched the current filter set."] if not filtered else [],
        source_refs=[
            {
                "source": "section_examples_fixture",
                "source_type": "fixture",
                "metadata": {"path": str(EXAMPLES_DIR / f'{request.section_type}_examples.json')},
            }
        ],
    )


def _dimension_present(text: str, dimension: str) -> bool:
    lowered = text.lower()
    terms = DIMENSION_TERMS.get(dimension.lower(), (dimension.lower(),))
    return any(term in lowered for term in terms)


@mcp.tool(name="compare_current_section_to_examples", description="Compare a current dossier section against correct and incorrect examples across regulatory dimensions.")
@tool_audit(tool_name="compare_current_section_to_examples", logger=LOGGER)
def compare_current_section_to_examples(
    current_section: dict[str, Any],
    comparison_dimensions: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "current_section": current_section,
        "comparison_dimensions": comparison_dimensions,
    }
    request = CompareCurrentSectionRequest.model_validate(payload)
    current_text = request.current_section.text
    dimensions = request.comparison_dimensions or ["completeness", "safety wording", "contraindications", "dosage clarity"]

    evidence: list[dict[str, Any]] = []
    matched_good_patterns: list[str] = []
    matched_bad_patterns: list[str] = []

    for dimension in dimensions:
        present = _dimension_present(current_text, dimension)
        if present:
            matched_good_patterns.append(dimension)
        else:
            matched_bad_patterns.append(dimension)
            severity = "critical" if dimension in {"contraindications", "safety wording"} else "major"
            evidence.append(
                {
                    "dimension": dimension,
                    "finding": f"The current section does not adequately cover {dimension}.",
                    "severity": severity,
                    "evidence_excerpt": current_text[:240],
                }
            )

    missing_count = len(matched_bad_patterns)
    if missing_count == 0:
        classification = "compliant"
    elif missing_count <= 2:
        classification = "partially_compliant"
    else:
        classification = "non_compliant"

    return build_tool_envelope(
        tool_name="compare_current_section_to_examples",
        payload=payload,
        data={
            "classification": classification,
            "matched_good_patterns": matched_good_patterns,
            "matched_bad_patterns": matched_bad_patterns,
            "evidence": evidence,
        },
        warnings=[],
        source_refs=[],
    )
