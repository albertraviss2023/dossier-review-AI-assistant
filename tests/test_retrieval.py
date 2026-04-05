from __future__ import annotations

from dossier_review_ai_assistant.data import EvidenceChunk
from dossier_review_ai_assistant.retrieval import LexicalRetriever


def test_lexical_retriever_scores_relevant_chunk_higher():
    chunks = [
        EvidenceChunk(
            citation_id="D1:S1",
            dossier_id="D1",
            section_id="S1",
            section_title="GMP status",
            module="M1",
            text="The GMP certificate is valid and the latest inspection is compliant.",
        ),
        EvidenceChunk(
            citation_id="D2:S1",
            dossier_id="D2",
            section_id="S1",
            section_title="Clinical outcomes",
            module="M5",
            text="Primary endpoint was not met in the pivotal trial.",
        ),
    ]
    retriever = LexicalRetriever(chunks)
    hits = retriever.search("gmp certificate inspection status", top_k=2)
    assert hits
    assert hits[0].chunk.citation_id == "D1:S1"


def test_lexical_retriever_applies_dossier_filter():
    chunks = [
        EvidenceChunk(
            citation_id="D1:S1",
            dossier_id="D1",
            section_id="S1",
            section_title="A",
            module="M1",
            text="certificate valid",
        ),
        EvidenceChunk(
            citation_id="D2:S1",
            dossier_id="D2",
            section_id="S1",
            section_title="B",
            module="M1",
            text="certificate valid",
        ),
    ]
    retriever = LexicalRetriever(chunks)
    hits = retriever.search("certificate", top_k=10, dossier_id="D1")
    assert len(hits) == 1
    assert hits[0].chunk.dossier_id == "D1"
