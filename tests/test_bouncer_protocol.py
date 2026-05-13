from __future__ import annotations
import pytest
from dossier_review_ai_assistant.orchestrator import ReasoningEngine
from dossier_review_ai_assistant.retrieval import RetrievalHit
from dossier_review_ai_assistant.data import EvidenceChunk

class MockRetriever:
    def advanced_search(self, query, intent, top_k, dossier_id):
        return []

@pytest.fixture
def reasoning_engine():
    return ReasoningEngine(model_id="test-model", retriever=MockRetriever())

def test_bouncer_discards_manufacturing_for_amr_query(reasoning_engine):
    question = "What are the AMR stewardship implications?"
    intent = "TECHNICAL_AMR"
    
    # Create a hit that is about manufacturing
    chunk = EvidenceChunk(
        citation_id="doc1:sec1:c1",
        dossier_id="doc1",
        section_id="sec1",
        section_title="FPP Manufacturing Process",
        module="m3",
        text="The manufacturing process for the finished pharmaceutical product involves several steps...",
        chunk_id="doc1:sec1:c1"
    )
    hit = RetrievalHit(chunk=chunk, score=0.9)
    
    vetted, audit = reasoning_engine.bounce_irrelevant_context(question, intent, [hit])
    
    assert len(vetted) == 0
    assert len(audit) == 1
    assert audit[0]["status"] == "DISCARD"
    assert "Manufacturing/FPP data" in audit[0]["reason"]

def test_bouncer_keeps_relevant_amr_content(reasoning_engine):
    question = "What are the AMR stewardship implications?"
    intent = "TECHNICAL_AMR"
    
    # Create a hit that is about AMR
    chunk = EvidenceChunk(
        citation_id="doc1:sec2:c1",
        dossier_id="doc1",
        section_id="sec2",
        section_title="AMR Stewardship Narrative",
        module="m1",
        text="The product is aligned with the WHO AWaRe Watch category. Stewardship measures include...",
        chunk_id="doc1:sec2:c1"
    )
    hit = RetrievalHit(chunk=chunk, score=0.9)
    
    vetted, audit = reasoning_engine.bounce_irrelevant_context(question, intent, [hit])
    
    assert len(vetted) == 1
    assert audit[0]["status"] == "KEEP"
    assert "Passed relevance audit" in audit[0]["reason"]

def test_fallback_skips_fpp_manufacturing(reasoning_engine):
    from dossier_review_ai_assistant.orchestrator import _build_fallback_hits
    
    dossier = {
        "dossier_id": "test_doc",
        "sections": [
            {
                "section_id": "sec_fpp",
                "title": "FPP Manufacturing",
                "text": "Manufacturing details here..."
            },
            {
                "section_id": "sec_valid",
                "title": "Clinical Overview",
                "text": "Clinical details here with some missing data terms."
            }
        ]
    }
    # Diagnostics to trigger fallback
    diagnostics = [
        {"section_id": "sec_fpp", "presence": "present", "correctness": "correct", "length_status": "length_ok"},
        {"section_id": "sec_valid", "presence": "present", "correctness": "incorrect", "length_status": "length_ok"}
    ]
    
    hits = _build_fallback_hits(dossier, diagnostics)
    
    # Should only have Clinical Overview, not FPP Manufacturing
    titles = [hit.chunk.section_title for hit in hits]
    assert "FPP Manufacturing" not in titles
    assert "Clinical Overview" in titles
