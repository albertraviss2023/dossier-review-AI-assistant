from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import SearchResult, VectorSearchRequest

from dossier_review_ai_assistant.data import (
    build_evidence_chunks,
    build_knowledge_wiki_chunks,
    load_knowledge_wiki,
    load_uploaded_dossiers,
)
from dossier_review_ai_assistant.config import load_settings
from dossier_review_ai_assistant.retrieval import HybridRetriever, tokenize

from .common import build_tool_envelope, tool_audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DOSSIERS_DIR = PROJECT_ROOT / "sample_dossiers"
KNOWLEDGE_WIKI_PATH = PROJECT_ROOT / "state" / "knowledge_wiki.json"
LOGGER = logging.getLogger("regulatory_mcp_server.tools.vector_search")


def _load_fixture_dossiers() -> list[dict[str, Any]]:
    dossiers: list[dict[str, Any]] = []
    for path in sorted(SAMPLE_DOSSIERS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("sections"):
            dossiers.append(payload)
    uploaded_dir = load_settings().uploaded_dossiers_dir
    for payload in load_uploaded_dossiers(uploaded_dir):
        if isinstance(payload, dict) and payload.get("sections"):
            dossiers.append(payload)
    return dossiers


def _build_index(index_name: str) -> HybridRetriever:
    index_name = index_name.lower()
    chunks = []
    if index_name in {"all", "dossiers", "current_dossier", "examples", "prior_findings"}:
        chunks.extend(build_evidence_chunks(_load_fixture_dossiers()))
    if index_name in {"all", "regulatory_guidance", "guidance", "knowledge_wiki"}:
        wiki_pages = load_knowledge_wiki(str(KNOWLEDGE_WIKI_PATH))
        chunks.extend(build_knowledge_wiki_chunks(wiki_pages))
    return HybridRetriever(chunks)


def _allowed_index(index_name: str) -> bool:
    return index_name.lower() in {
        "all",
        "dossiers",
        "current_dossier",
        "examples",
        "prior_findings",
        "regulatory_guidance",
        "guidance",
        "knowledge_wiki",
    }


@mcp.tool(name="search_vector_database", description="Search local regulatory guidance and dossier fixture indexes for relevant evidence chunks.")
@tool_audit(tool_name="search_vector_database", logger=LOGGER)
def search_vector_database(
    query: str,
    index: str,
    dossier_id: str | None = None,
    filters: dict[str, Any] | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Search local regulatory guidance and dossier indexes.

    Args:
        query: The natural language search query.
        index: The index to search (e.g., 'knowledge_wiki', 'dossiers', 'all').
        dossier_id: Optional ID to restrict search to a specific dossier.
        filters: Optional additional metadata filters (e.g., {'module': 'm1'}).
        top_k: Number of results to return.
    """
    payload = {
        "query": query,
        "index": index,
        "filters": {**(filters or {}), "dossier_id": dossier_id} if dossier_id else (filters or {}),
        "top_k": top_k,
    }
    request = VectorSearchRequest.model_validate(payload)
    index_name = request.index.lower()

    if not _allowed_index(index_name):
        raise ValueError(
            "Unsupported index. Allowed values are all, dossiers, current_dossier, examples, prior_findings, regulatory_guidance, guidance, knowledge_wiki."
        )

    retriever = _build_index(index_name)
    hits = retriever.search(
        query=request.query,
        top_k=request.top_k,
        dossier_id=request.filters.get("dossier_id"),
        metadata_filter=request.filters or None,
    )
    query_tokens = {token for token in tokenize(request.query) if len(token) > 3}
    filtered_hits = []
    for hit in hits:
        chunk_tokens = {token for token in tokenize(hit.chunk.section_title + " " + hit.chunk.text) if len(token) > 3}
        token_overlap = len(query_tokens & chunk_tokens)
        if token_overlap > 0 or float(hit.score) >= 0.25:
            filtered_hits.append(hit)

    results = [
        SearchResult(
            chunk_id=hit.chunk.chunk_id or hit.chunk.citation_id,
            source=hit.chunk.source_type,
            text=hit.chunk.text,
            score=round(float(hit.score), 6),
            metadata={
                "citation_id": hit.chunk.citation_id,
                "dossier_id": hit.chunk.dossier_id,
                "section_id": hit.chunk.section_id,
                "section_title": hit.chunk.section_title,
                "module": hit.chunk.module,
                "category": hit.chunk.category,
            },
        ).model_dump(mode="json")
        for hit in filtered_hits
    ]

    warnings: list[str] = []
    if not results:
        warnings.append("No results matched the query and filters in the selected local index.")

    source_refs = []
    if index_name in {"all", "regulatory_guidance", "guidance", "knowledge_wiki"}:
        source_refs.append(
            {
                "source": "knowledge_wiki_fixture",
                "source_type": "fixture",
                "metadata": {"path": str(KNOWLEDGE_WIKI_PATH)},
            }
        )
    if index_name in {"all", "dossiers", "current_dossier", "examples", "prior_findings"}:
        source_refs.append(
            {
                "source": "sample_dossiers_fixture",
                "source_type": "fixture",
                "metadata": {"path": str(SAMPLE_DOSSIERS_DIR)},
            }
        )

    return build_tool_envelope(
        tool_name="search_vector_database",
        payload=payload,
        data={"results": results},
        warnings=warnings,
        source_refs=source_refs,
    )
