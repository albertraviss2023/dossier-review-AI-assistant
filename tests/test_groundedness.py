from __future__ import annotations

from dossier_review_ai_assistant.gates import verify_claim_groundedness
from dossier_review_ai_assistant.inference import extract_cited_claims


def test_extract_cited_claims_parses_numbered_lines():
    text = """
    1. GMP certificate is valid. [DOS-1:m1_gmp:c1]
    2. Primary endpoint was met. [DOS-1:m2_clinical:c1]
    """

    claims = extract_cited_claims(text)

    assert len(claims) == 2
    assert claims[0]["citation_id"] == "DOS-1:m1_gmp:c1"
    assert claims[1]["citation_id"] == "DOS-1:m2_clinical:c1"


def test_extract_cited_claims_parses_inline_citations_across_sentence_fragments():
    text = (
        "Grounded rationale: GMP certificate is valid [DOS-1:m1_gmp:c1]. "
        "Primary endpoint was met [DOS-1:m2_clinical:c1]."
    )

    claims = extract_cited_claims(text)

    assert len(claims) == 2
    assert claims[0]["text"].startswith("Grounded rationale")


def test_verify_claim_groundedness_fails_when_any_claim_has_invalid_citation():
    claims = [
        {"text": "Supported claim", "citation_id": "DOS-1:m1_gmp:c1"},
        {"text": "Unsupported claim", "citation_id": "missing-citation"},
    ]

    result = verify_claim_groundedness(claims, {"DOS-1:m1_gmp:c1"})

    assert result["grounded_claim_rate"] == 0.5
    assert result["unsupported_critical_claim_rate"] == 0.5
    assert result["passed"] is False


def test_verify_claim_groundedness_passes_when_all_claims_are_supported():
    claims = [
        {"text": "Supported claim one", "citation_id": "DOS-1:m1_gmp:c1"},
        {"text": "Supported claim two", "citation_id": "DOS-1:m2_clinical:c1"},
    ]

    result = verify_claim_groundedness(claims, {"DOS-1:m1_gmp:c1", "DOS-1:m2_clinical:c1"})

    assert result["grounded_claim_rate"] == 1.0
    assert result["unsupported_critical_claim_rate"] == 0.0
    assert result["passed"] is True
