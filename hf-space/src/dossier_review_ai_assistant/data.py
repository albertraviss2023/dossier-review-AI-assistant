from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class EvidenceChunk:
    citation_id: str
    dossier_id: str
    section_id: str
    section_title: str
    module: str
    text: str
    chunk_id: str = ""
    source_type: str = "dossier_section"
    parent_section_id: str = ""
    parent_section_title: str = ""
    chunk_ordinal: int = 1
    chunk_profile_version: str = "legacy_section_v1"
    chunk_token_estimate: int = 0
    start_char: int = 0
    end_char: int = 0
    category: str = "general"


@dataclass(frozen=True)
class ChunkProfile:
    source_type: str
    profile_version: str
    target_tokens: int
    overlap_tokens: int
    title_standalone: bool = False


TOKEN_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9\-]{1,}\b", re.IGNORECASE)
PARAGRAPH_PATTERN = re.compile(r"\n\s*\n+")


DOSSIER_CHUNK_PROFILE = ChunkProfile(
    source_type="dossier_section",
    profile_version="dossier_structured_v1",
    target_tokens=600,
    overlap_tokens=100,
)

KNOWLEDGE_WIKI_CHUNK_PROFILE = ChunkProfile(
    source_type="knowledge_wiki",
    profile_version="wiki_structured_v1",
    target_tokens=320,
    overlap_tokens=50,
    title_standalone=True,
)

ISSUE_CHUNK_PROFILE = ChunkProfile(
    source_type="issue_artifact",
    profile_version="issue_structured_v1",
    target_tokens=220,
    overlap_tokens=40,
    title_standalone=True,
)


def chunking_profiles_catalog() -> tuple[ChunkProfile, ...]:
    return (
        DOSSIER_CHUNK_PROFILE,
        KNOWLEDGE_WIKI_CHUNK_PROFILE,
        ISSUE_CHUNK_PROFILE,
    )


@dataclass(frozen=True)
class KnowledgeWikiPage:
    page_id: str
    title: str
    tags: tuple[str, ...]
    sections: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class TextSpan:
    text: str
    start_char: int
    end_char: int


def chunk_profile_for_source(source_type: str) -> ChunkProfile:
    mapping = {
        "dossier_section": DOSSIER_CHUNK_PROFILE,
        "knowledge_wiki": KNOWLEDGE_WIKI_CHUNK_PROFILE,
        "issue_artifact": ISSUE_CHUNK_PROFILE,
    }
    return mapping.get(source_type, DOSSIER_CHUNK_PROFILE)


def estimate_token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def _paragraph_spans(text: str) -> list[TextSpan]:
    normalized = text.strip()
    if not normalized:
        return []

    spans: list[TextSpan] = []
    cursor = 0
    for part in PARAGRAPH_PATTERN.split(text):
        start = text.find(part, cursor)
        if start < 0:
            continue
        end = start + len(part)
        cursor = end
        stripped = part.strip()
        if not stripped:
            continue
        inner_start = start + part.find(stripped)
        spans.append(TextSpan(text=stripped, start_char=inner_start, end_char=inner_start + len(stripped)))
    return spans


def _tail_token_span(text: str, start_char: int, end_char: int, overlap_tokens: int) -> TextSpan | None:
    if overlap_tokens <= 0 or start_char >= end_char:
        return None

    relative_text = text[start_char:end_char]
    matches = list(TOKEN_PATTERN.finditer(relative_text))
    if not matches:
        return None

    if len(matches) <= overlap_tokens:
        return TextSpan(text=relative_text.strip(), start_char=start_char, end_char=end_char)

    start_idx = len(matches) - overlap_tokens
    overlap_start = start_char + matches[start_idx].start()
    overlap_end = start_char + matches[-1].end()
    return TextSpan(text=text[overlap_start:overlap_end].strip(), start_char=overlap_start, end_char=overlap_end)


def _overlap_tail(text: str, paragraphs: list[TextSpan], overlap_tokens: int) -> list[TextSpan]:
    if overlap_tokens <= 0 or not paragraphs:
        return []
    overlap = _tail_token_span(
        text=text,
        start_char=paragraphs[0].start_char,
        end_char=paragraphs[-1].end_char,
        overlap_tokens=overlap_tokens,
    )
    return [overlap] if overlap and overlap.text else []


def split_text_into_spans(text: str, profile: ChunkProfile) -> list[TextSpan]:
    paragraphs = _paragraph_spans(text)
    if not paragraphs:
        normalized = text.strip()
        if not normalized:
            return []
        start = text.find(normalized)
        return [TextSpan(text=normalized, start_char=max(start, 0), end_char=max(start, 0) + len(normalized))]

    spans: list[TextSpan] = []
    current: list[TextSpan] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        chunk_text = "\n\n".join(span.text for span in current)
        spans.append(
            TextSpan(
                text=chunk_text,
                start_char=current[0].start_char,
                end_char=current[-1].end_char,
            )
        )
        current = _overlap_tail(text, current, profile.overlap_tokens)
        current_tokens = sum(estimate_token_count(span.text) for span in current)

    for paragraph in paragraphs:
        paragraph_tokens = estimate_token_count(paragraph.text)
        if paragraph_tokens >= profile.target_tokens:
            flush()
            tokens = TOKEN_PATTERN.finditer(paragraph.text)
            token_matches = list(tokens)
            start_idx = 0
            ordinal_start_char = paragraph.start_char
            while start_idx < len(token_matches):
                end_idx = min(start_idx + profile.target_tokens, len(token_matches))
                start_char = ordinal_start_char + token_matches[start_idx].start()
                end_char = ordinal_start_char + token_matches[end_idx - 1].end()
                spans.append(TextSpan(text=text[start_char:end_char].strip(), start_char=start_char, end_char=end_char))
                if end_idx == len(token_matches):
                    break
                start_idx = max(start_idx + profile.target_tokens - profile.overlap_tokens, start_idx + 1)
            current = []
            current_tokens = 0
            continue

        if current and current_tokens + paragraph_tokens > profile.target_tokens:
            flush()
            if current and current_tokens + paragraph_tokens > profile.target_tokens:
                current = []
                current_tokens = 0

        current.append(paragraph)
        current_tokens += paragraph_tokens

    flush()
    return spans


@lru_cache(maxsize=4)
def load_dossiers(path: str) -> list[dict[str, Any]]:
    dossiers: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dossiers.append(_normalize_dossier_shape(json.loads(line)))
    return dossiers


def _normalize_dossier_shape(dossier: dict[str, Any]) -> dict[str, Any]:
    """Support both legacy dossier schema and realistic-v2 manifest schema."""
    if "product" in dossier and "organization" in dossier and "country" in dossier:
        return dossier

    normalized = dict(dossier)
    # Map flat manifest fields into legacy nested structures expected by API/UI.
    normalized["country"] = str(
        dossier.get("country")
        or dossier.get("applicant_country")
        or dossier.get("manufacturer_country")
        or "Unknown"
    )
    normalized["submission_date"] = str(dossier.get("submission_date") or "")
    normalized["product"] = {
        "product_name": str(dossier.get("product_name") or ""),
        "inn_name": str(dossier.get("inn") or ""),
        "dosage_form": str(dossier.get("dosage_form") or ""),
        "strength": str(dossier.get("strength") or ""),
        "route_of_administration": str(dossier.get("route_of_administration") or ""),
    }
    normalized["organization"] = {
        "applicant": str(dossier.get("applicant_name") or ""),
        "manufacturer_name": str(dossier.get("manufacturer_name") or ""),
        "facility_country": str(dossier.get("manufacturer_country") or ""),
    }
    normalized["labels"] = dict(dossier.get("labels") or {})
    normalized["policy_signals"] = dict(dossier.get("policy_signals") or {})
    # Normalize sections to include legacy `title` key consumed by retrieval/chunking.
    sections = []
    for section in dossier.get("sections", []):
        row = dict(section)
        if "title" not in row:
            row["title"] = str(row.get("section_name") or row.get("section_id") or "Section")
        sections.append(row)
    normalized["sections"] = sections
    return normalized


def load_uploaded_dossiers(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []

    dossiers: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dossiers.append(payload)
    return dossiers


@lru_cache(maxsize=2)
def load_knowledge_wiki(path: str) -> list[KnowledgeWikiPage]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pages: list[KnowledgeWikiPage] = []
    for row in payload:
        pages.append(
            KnowledgeWikiPage(
                page_id=str(row["page_id"]),
                title=str(row["title"]),
                tags=tuple(str(tag) for tag in row.get("tags", [])),
                sections=tuple(
                    {
                        "heading": str(section["heading"]),
                        "text": str(section["text"]),
                    }
                    for section in row.get("sections", [])
                ),
            )
        )
    return pages


def build_evidence_chunks(dossiers: list[dict[str, Any]]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for dossier in dossiers:
        dossier_id = str(dossier.get("dossier_id", "unknown"))
        sections = dossier.get("sections", [])
        
        # Determine dossier-level category hints
        holistic_decision = str(dossier.get("labels", {}).get("holistic_policy_decision", ""))
        dossier_category = "general"
        if holistic_decision in ("reject_and_return", "deep_review"):
            dossier_category = "regulatory_action"

        for section in sections:
            section_id = str(section.get("section_id", "unknown"))
            section_title = str(section.get("title", "untitled"))
            module = str(section.get("module", "unknown"))
            text = str(section.get("text", ""))
            
            # Determine section category
            category = dossier_category
            if "gmp" in section_id.lower() or "inspection" in section_title.lower():
                category = "regulatory_action"
            elif "clinical" in section_id.lower() or "trial" in section_title.lower():
                category = "clinical_evidence"
            elif "amr" in section_id.lower() or "stewardship" in section_title.lower():
                category = "policy_guidance"

            spans = split_text_into_spans(text, DOSSIER_CHUNK_PROFILE)
            for ordinal, span in enumerate(spans, start=1):
                citation_id = f"{dossier_id}:{section_id}:c{ordinal}"
                chunks.append(
                    EvidenceChunk(
                        citation_id=citation_id,
                        dossier_id=dossier_id,
                        section_id=section_id,
                        section_title=section_title,
                        module=module,
                        text=span.text,
                        chunk_id=citation_id,
                        source_type=DOSSIER_CHUNK_PROFILE.source_type,
                        parent_section_id=section_id,
                        parent_section_title=section_title,
                        chunk_ordinal=ordinal,
                        chunk_profile_version=DOSSIER_CHUNK_PROFILE.profile_version,
                        chunk_token_estimate=estimate_token_count(span.text),
                        start_char=span.start_char,
                        end_char=span.end_char,
                        category=category,
                    )
                )
    return chunks


def build_knowledge_wiki_chunks(pages: list[KnowledgeWikiPage]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for page in pages:
        if KNOWLEDGE_WIKI_CHUNK_PROFILE.title_standalone:
            title_text = page.title.strip()
            chunks.append(
                EvidenceChunk(
                    citation_id=f"knowledge_wiki:{page.page_id}:title",
                    dossier_id="knowledge_wiki",
                    section_id=f"{page.page_id}:title",
                    section_title=f"{page.title} - Title",
                    module="wiki",
                    text=title_text,
                    chunk_id=f"knowledge_wiki:{page.page_id}:title",
                    source_type=KNOWLEDGE_WIKI_CHUNK_PROFILE.source_type,
                    parent_section_id=page.page_id,
                    parent_section_title=page.title,
                    chunk_ordinal=0,
                    chunk_profile_version=KNOWLEDGE_WIKI_CHUNK_PROFILE.profile_version,
                    chunk_token_estimate=estimate_token_count(title_text),
                    start_char=0,
                    end_char=len(title_text),
                )
            )
        for idx, section in enumerate(page.sections, start=1):
            section_id = f"{page.page_id}:{idx}"
            base_text = f"{section['heading']}\n\n{section['text']}".strip()
            spans = split_text_into_spans(base_text, KNOWLEDGE_WIKI_CHUNK_PROFILE)
            for ordinal, span in enumerate(spans, start=1):
                prefix = f"{page.title}. {section['heading']}. ".strip()
                suffix = f" {' '.join(page.tags)}".rstrip() if page.tags else ""
                text = f"{prefix}{span.text}{suffix}".strip()
                chunks.append(
                    EvidenceChunk(
                        citation_id=f"knowledge_wiki:{section_id}:c{ordinal}",
                        dossier_id="knowledge_wiki",
                        section_id=section_id,
                        section_title=f"{page.title} - {section['heading']}",
                        module="wiki",
                        text=text,
                        chunk_id=f"knowledge_wiki:{section_id}:c{ordinal}",
                        source_type=KNOWLEDGE_WIKI_CHUNK_PROFILE.source_type,
                        parent_section_id=section_id,
                        parent_section_title=f"{page.title} - {section['heading']}",
                        chunk_ordinal=ordinal,
                        chunk_profile_version=KNOWLEDGE_WIKI_CHUNK_PROFILE.profile_version,
                        chunk_token_estimate=estimate_token_count(text),
                        start_char=span.start_char,
                        end_char=span.end_char,
                    )
                )
    return chunks


def build_issue_chunks(
    issue_id: str,
    title: str,
    description: str,
    comments: list[dict[str, str]] | None = None,
) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    comments = comments or []

    if ISSUE_CHUNK_PROFILE.title_standalone and title.strip():
        title_text = title.strip()
        chunks.append(
            EvidenceChunk(
                citation_id=f"{issue_id}:title",
                dossier_id=issue_id,
                section_id="title",
                section_title="Issue Title",
                module="issue",
                text=title_text,
                chunk_id=f"{issue_id}:title",
                source_type=ISSUE_CHUNK_PROFILE.source_type,
                parent_section_id="title",
                parent_section_title="Issue Title",
                chunk_ordinal=0,
                chunk_profile_version=ISSUE_CHUNK_PROFILE.profile_version,
                chunk_token_estimate=estimate_token_count(title_text),
                start_char=0,
                end_char=len(title_text),
            )
        )

    for ordinal, span in enumerate(split_text_into_spans(description, ISSUE_CHUNK_PROFILE), start=1):
        chunks.append(
            EvidenceChunk(
                citation_id=f"{issue_id}:description:c{ordinal}",
                dossier_id=issue_id,
                section_id="description",
                section_title="Issue Description",
                module="issue",
                text=span.text,
                chunk_id=f"{issue_id}:description:c{ordinal}",
                source_type=ISSUE_CHUNK_PROFILE.source_type,
                parent_section_id="description",
                parent_section_title="Issue Description",
                chunk_ordinal=ordinal,
                chunk_profile_version=ISSUE_CHUNK_PROFILE.profile_version,
                chunk_token_estimate=estimate_token_count(span.text),
                start_char=span.start_char,
                end_char=span.end_char,
            )
        )

    for idx, comment in enumerate(comments, start=1):
        comment_text = str(comment.get("text", "")).strip()
        author = str(comment.get("author", "unknown"))
        created_at = str(comment.get("created_at", "unknown"))
        if not comment_text:
            continue
        payload = f"{author} {created_at}. {comment_text}".strip()
        chunks.append(
            EvidenceChunk(
                citation_id=f"{issue_id}:comment:{idx}",
                dossier_id=issue_id,
                section_id=f"comment:{idx}",
                section_title=f"Issue Comment {idx}",
                module="issue",
                text=payload,
                chunk_id=f"{issue_id}:comment:{idx}",
                source_type=ISSUE_CHUNK_PROFILE.source_type,
                parent_section_id="comments",
                parent_section_title="Issue Comments",
                chunk_ordinal=idx,
                chunk_profile_version=ISSUE_CHUNK_PROFILE.profile_version,
                chunk_token_estimate=estimate_token_count(payload),
                start_char=0,
                end_char=len(payload),
            )
        )

    return chunks


def build_legacy_section_chunks(dossiers: list[dict[str, Any]]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for dossier in dossiers:
        dossier_id = str(dossier.get("dossier_id", "unknown"))
        sections = dossier.get("sections", [])
        for section in sections:
            section_id = str(section.get("section_id", "unknown"))
            section_title = str(section.get("title", "untitled"))
            module = str(section.get("module", "unknown"))
            text = str(section.get("text", ""))
            citation_id = f"{dossier_id}:{section_id}"
            chunks.append(
                EvidenceChunk(
                    citation_id=citation_id,
                    dossier_id=dossier_id,
                    section_id=section_id,
                    section_title=section_title,
                    module=module,
                    text=text,
                    chunk_id=citation_id,
                    source_type="legacy_section",
                    parent_section_id=section_id,
                    parent_section_title=section_title,
                    chunk_ordinal=1,
                    chunk_profile_version="legacy_section_v1",
                    chunk_token_estimate=estimate_token_count(text),
                    start_char=0,
                    end_char=len(text),
                )
            )
    return chunks
