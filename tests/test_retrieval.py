from __future__ import annotations

from dossier_review_ai_assistant.data import (
    EvidenceChunk,
    build_evidence_chunks,
    build_legacy_section_chunks,
)
from dossier_review_ai_assistant.retrieval import HybridRetriever, LexicalRetriever, generate_expanded_queries
from dossier_review_ai_assistant.retrieval import DenseVectorRetriever


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


def test_structure_aware_chunking_beats_legacy_section_chunk_for_late_section_query():
    filler = " ".join(f"filler{i}" for i in range(800))
    focused = "gmp certificate expired after failed inspection and missing capa evidence"
    dossier = {
        "dossier_id": "D-LONG",
        "sections": [
            {
                "section_id": "S1",
                "title": "Long blended section",
                "module": "M1",
                "text": f"{filler}\n\n{focused}",
            }
        ],
    }

    legacy_hits = LexicalRetriever(build_legacy_section_chunks([dossier])).search(
        "expired inspection capa evidence",
        top_k=1,
    )
    structured_hits = LexicalRetriever(build_evidence_chunks([dossier])).search(
        "expired inspection capa evidence",
        top_k=1,
    )

    assert legacy_hits
    assert structured_hits
    assert structured_hits[0].score > legacy_hits[0].score
    assert "expired" in structured_hits[0].chunk.text.lower()
    assert structured_hits[0].chunk.chunk_profile_version != "legacy_section_v1"


def test_hybrid_retriever_uses_title_and_semantic_expansion():
    chunks = [
        EvidenceChunk(
            citation_id="D1:S1:c1",
            dossier_id="D1",
            section_id="S1",
            section_title="GMP inspection follow-up",
            module="M1",
            text="Corrective action plan has been filed and site certification remains under review.",
            chunk_id="D1:S1:c1",
            source_type="dossier_section",
            parent_section_id="S1",
            parent_section_title="GMP inspection follow-up",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=16,
            start_char=0,
            end_char=90,
        ),
        EvidenceChunk(
            citation_id="D2:S1:c1",
            dossier_id="D2",
            section_id="S1",
            section_title="Clinical benefit summary",
            module="M5",
            text="The pivotal endpoint was met and safety profile was acceptable.",
            chunk_id="D2:S1:c1",
            source_type="dossier_section",
            parent_section_id="S1",
            parent_section_title="Clinical benefit summary",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=11,
            start_char=0,
            end_char=67,
        ),
    ]

    hits = HybridRetriever(chunks).search("gmp capa inspection certificate", top_k=2)

    assert hits
    assert hits[0].chunk.citation_id == "D1:S1:c1"


def test_hybrid_retriever_applies_reranking_to_prefer_precise_short_chunk():
    chunks = [
        EvidenceChunk(
            citation_id="D1:long:c1",
            dossier_id="D1",
            section_id="long",
            section_title="General dossier narrative",
            module="M2",
            text="certificate " * 40 + "inspection " * 20,
            chunk_id="D1:long:c1",
            source_type="dossier_section",
            parent_section_id="long",
            parent_section_title="General dossier narrative",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=60,
            start_char=0,
            end_char=480,
        ),
        EvidenceChunk(
            citation_id="D1:short:c1",
            dossier_id="D1",
            section_id="short",
            section_title="GMP certificate inspection",
            module="M1",
            text="GMP certificate failed inspection and missing CAPA evidence.",
            chunk_id="D1:short:c1",
            source_type="dossier_section",
            parent_section_id="short",
            parent_section_title="GMP certificate inspection",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=8,
            start_char=0,
            end_char=58,
        ),
    ]

    hits = HybridRetriever(chunks).search("gmp certificate inspection capa", top_k=2)

    assert hits[0].chunk.citation_id == "D1:short:c1"


def test_dense_vector_retriever_indexes_local_dense_vectors():
    chunks = [
        EvidenceChunk(
            citation_id="D1:title:c1",
            dossier_id="D1",
            section_id="title",
            section_title="Restricted authorization control",
            module="M1",
            text="Reserve antibiotic requires stewardship restriction and restricted authorization.",
            chunk_id="D1:title:c1",
            source_type="dossier_section",
            parent_section_id="title",
            parent_section_title="Restricted authorization control",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=9,
            start_char=0,
            end_char=79,
        ),
        EvidenceChunk(
            citation_id="D2:title:c1",
            dossier_id="D2",
            section_id="title",
            section_title="Routine approval path",
            module="M1",
            text="Standard authorization remains acceptable for non-critical routine cases.",
            chunk_id="D2:title:c1",
            source_type="dossier_section",
            parent_section_id="title",
            parent_section_title="Routine approval path",
            chunk_ordinal=1,
            chunk_profile_version="dossier_structured_v1",
            chunk_token_estimate=9,
            start_char=0,
            end_char=73,
        ),
    ]

    retriever = DenseVectorRetriever(chunks)
    hits = retriever.search("restricted authorization stewardship", top_k=2)

    assert hits
    assert len(retriever.index.vectors) == 2
    assert hits[0].chunk.citation_id == "D1:title:c1"


def test_generate_expanded_queries_uses_expansion_terms_and_constraints():
    queries = generate_expanded_queries(
        "review stability data",
        "dossier_review",
        expansion_terms=("shelf life", "storage conditions", "accelerated studies"),
        constraints=("Module 3", "Product"),
        max_queries=5,
    )

    assert queries[0] == "review stability data"
    assert any("shelf life" in query for query in queries)
    assert any("Module 3" in query for query in queries)
