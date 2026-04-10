from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceChunk:
    citation_id: str
    dossier_id: str
    section_id: str
    section_title: str
    module: str
    text: str


@dataclass(frozen=True)
class KnowledgeWikiPage:
    page_id: str
    title: str
    tags: tuple[str, ...]
    sections: tuple[dict[str, str], ...]


@lru_cache(maxsize=4)
def load_dossiers(path: str) -> list[dict[str, Any]]:
    dossiers: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dossiers.append(json.loads(line))
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
                )
            )
    return chunks


def build_knowledge_wiki_chunks(pages: list[KnowledgeWikiPage]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for page in pages:
        for idx, section in enumerate(page.sections, start=1):
            section_id = f"{page.page_id}:{idx}"
            tag_text = " ".join(page.tags)
            text = f"{page.title}. {section['heading']}. {section['text']} {tag_text}".strip()
            chunks.append(
                EvidenceChunk(
                    citation_id=f"knowledge_wiki:{section_id}",
                    dossier_id="knowledge_wiki",
                    section_id=section_id,
                    section_title=f"{page.title} - {section['heading']}",
                    module="wiki",
                    text=text,
                )
            )
    return chunks
