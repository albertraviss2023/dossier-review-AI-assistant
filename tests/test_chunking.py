from __future__ import annotations

from dossier_review_ai_assistant.data import (
    DOSSIER_CHUNK_PROFILE,
    ISSUE_CHUNK_PROFILE,
    KNOWLEDGE_WIKI_CHUNK_PROFILE,
    KnowledgeWikiPage,
    build_evidence_chunks,
    build_issue_chunks,
    build_knowledge_wiki_chunks,
    estimate_token_count,
    chunk_profile_for_source,
    split_text_into_spans,
)


def test_chunk_profile_lookup_returns_source_specific_profiles():
    assert chunk_profile_for_source("dossier_section") == DOSSIER_CHUNK_PROFILE
    assert chunk_profile_for_source("knowledge_wiki") == KNOWLEDGE_WIKI_CHUNK_PROFILE
    assert chunk_profile_for_source("issue_artifact") == ISSUE_CHUNK_PROFILE


def test_issue_chunk_builder_indexes_title_description_and_comments_separately():
    chunks = build_issue_chunks(
        issue_id="ISSUE-42",
        title="Payment failure on renewal",
        description="Renewal flow fails after card confirmation.\n\nError appears only for annual plans.",
        comments=[
            {"author": "alice", "created_at": "2026-04-11T10:00:00Z", "text": "Can reproduce on staging."},
            {"author": "bob", "created_at": "2026-04-11T11:15:00Z", "text": "Looks related to webhook retries."},
        ],
    )

    assert chunks[0].citation_id == "ISSUE-42:title"
    assert chunks[0].source_type == "issue_artifact"
    assert any(chunk.section_id == "description" for chunk in chunks)
    assert any(chunk.section_id == "comment:1" for chunk in chunks)
    assert any(chunk.section_id == "comment:2" for chunk in chunks)


def test_wiki_chunk_builder_keeps_title_as_standalone_unit():
    page = KnowledgeWikiPage(
        page_id="retrieval-playbook",
        title="Retrieval Playbook",
        tags=("rag", "chunking"),
        sections=(
            {
                "heading": "Chunking",
                "text": "Use token-bounded chunks and preserve headings for retrieval precision.",
            },
        ),
    )

    chunks = build_knowledge_wiki_chunks([page])

    assert chunks[0].citation_id == "knowledge_wiki:retrieval-playbook:title"
    assert chunks[0].chunk_ordinal == 0
    assert chunks[0].source_type == "knowledge_wiki"


def test_split_text_into_spans_respects_token_budget_and_overlap():
    paragraphs = [
        "alpha beta gamma delta epsilon zeta eta theta",
        "iota kappa lambda mu nu xi omicron pi",
        "rho sigma tau upsilon phi chi psi omega",
    ]
    text = "\n\n".join(paragraphs)
    profile = DOSSIER_CHUNK_PROFILE.__class__(
        source_type=DOSSIER_CHUNK_PROFILE.source_type,
        profile_version="test_profile_v1",
        target_tokens=14,
        overlap_tokens=4,
    )

    spans = split_text_into_spans(text, profile)

    assert len(spans) >= 2
    assert all(estimate_token_count(span.text) <= 14 for span in spans)
    assert "epsilon" in spans[0].text.lower()
    assert "epsilon" in spans[1].text.lower()


def test_split_text_into_spans_splits_large_single_paragraph_when_needed():
    text = " ".join(f"token{i}" for i in range(60))
    profile = DOSSIER_CHUNK_PROFILE.__class__(
        source_type=DOSSIER_CHUNK_PROFILE.source_type,
        profile_version="test_profile_v1",
        target_tokens=20,
        overlap_tokens=5,
    )

    spans = split_text_into_spans(text, profile)

    assert len(spans) >= 3
    assert all(estimate_token_count(span.text) <= 20 for span in spans)


def test_dossier_chunks_preserve_provenance_metadata_and_reconstructable_spans():
    dossier = {
        "dossier_id": "D-PROV",
        "sections": [
            {
                "section_id": "m1",
                "title": "Administrative",
                "module": "M1",
                "text": "First evidence sentence.\n\nSecond evidence sentence with more detail.",
            }
        ],
    }

    chunks = build_evidence_chunks([dossier])

    assert chunks
    first = chunks[0]
    assert first.chunk_id == first.citation_id
    assert first.parent_section_id == "m1"
    assert first.parent_section_title == "Administrative"
    assert first.chunk_profile_version == DOSSIER_CHUNK_PROFILE.profile_version
    assert first.chunk_token_estimate == estimate_token_count(first.text)
    assert first.end_char > first.start_char >= 0
    source_text = dossier["sections"][0]["text"]
    reconstructed = source_text[first.start_char:first.end_char].strip()
    assert reconstructed
    assert reconstructed in first.text or first.text in reconstructed
