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


@lru_cache(maxsize=4)
def load_dossiers(path: str) -> list[dict[str, Any]]:
    dossiers: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dossiers.append(json.loads(line))
    return dossiers


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

