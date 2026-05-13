from __future__ import annotations

from dossier_review_ai_assistant.router import (
    AMR_INTENT,
    CHAT_ONLY_INTENT,
    ISSUE_DISCOVERY_INTENT,
    MIXED_INTENT,
    POLICY_GUIDANCE,
    REVIEW_INTENT,
    WIKI_GUIDANCE_INTENT,
    assemble_model_packet,
    build_query_rewrite_plan,
    classify_intent,
    plan_context_scope,
)


def test_classify_intent_covers_primary_reviewer_modes():
    assert classify_intent(question="Hi friend", workspace="review", has_active_dossier=True, has_conversation=False) == CHAT_ONLY_INTENT
    assert classify_intent(question="Find issues and contradictions in this dossier", workspace="review", has_active_dossier=True, has_conversation=False) == ISSUE_DISCOVERY_INTENT
    assert classify_intent(question="What guidance should I consult before confirming the recommendation?", workspace="review", has_active_dossier=True, has_conversation=False) == POLICY_GUIDANCE
    assert classify_intent(question="Explain the AWaRe and GLASS implications for this dossier", workspace="review", has_active_dossier=True, has_conversation=False) == AMR_INTENT
    assert classify_intent(question="Compare this dossier with WHO guidance and external stewardship evidence", workspace="review", has_active_dossier=True, has_conversation=False) == MIXED_INTENT
    assert classify_intent(question="Review this dossier and recommend the next action", workspace="review", has_active_dossier=True, has_conversation=False) == REVIEW_INTENT


def test_plan_context_scope_separates_domains_for_each_intent():
    wiki_plan = plan_context_scope(WIKI_GUIDANCE_INTENT, workspace="wiki")
    review_plan = plan_context_scope(REVIEW_INTENT, workspace="review")
    mixed_plan = plan_context_scope(MIXED_INTENT, workspace="review")

    assert wiki_plan.context_scope.include_wiki is True
    assert wiki_plan.context_scope.include_dossier is False

    assert review_plan.context_scope.include_dossier is True
    assert review_plan.context_scope.include_wiki is False
    assert review_plan.context_scope.include_external is False

    assert mixed_plan.context_scope.include_dossier is True
    assert mixed_plan.context_scope.include_wiki is True
    assert mixed_plan.context_scope.include_external is True


def test_assemble_model_packet_labels_source_boundaries():
    route_plan = plan_context_scope(MIXED_INTENT, workspace="review")
    packet = assemble_model_packet(
        question="Compare dossier findings with WHO guidance and chemistry sources",
        workspace="review",
        route_plan=route_plan,
        dossier_id="DOS-001",
        conversation_context="Prior turn focused on GMP and clinical evidence.",
        dossier_hits=[{"citation_id": "DOS-001:sec1:c1"}],
        wiki_hits=[{"citation_id": "knowledge_wiki:who-aware-and-glass:title"}],
        external_context={"source_trace": ["WHO AWaRe snapshot resolved"]},
        review_state={"active_dossier_id": "DOS-001"},
    )

    assert packet.packet_version == "mcp_router_packet_v1"
    assert packet.intent == MIXED_INTENT
    assert packet.blocks["conversation"]["summary"]
    assert packet.blocks["dossier"]["hits"][0]["citation_id"] == "DOS-001:sec1:c1"
    assert packet.blocks["wiki"]["hits"][0]["citation_id"].startswith("knowledge_wiki:")
    assert packet.blocks["external"]["source_trace"] == ["WHO AWaRe snapshot resolved"]
    assert packet.source_boundaries["dossier"] == "dossier_submission_evidence"


def test_build_query_rewrite_plan_adds_regulatory_synonyms_for_stability_review():
    plan = build_query_rewrite_plan(
        question="Review stability data for this dossier",
        workspace="review",
        has_active_dossier=True,
        has_conversation=False,
    )

    assert plan.intent == REVIEW_INTENT
    assert plan.rewritten_question == "Review stability data for this dossier"
    assert "shelf life" in plan.expansion_terms
    assert "accelerated studies" in plan.expansion_terms
    assert any("retrieval" in note.lower() or "terminology" in note.lower() for note in plan.rewrite_notes)


def test_build_query_rewrite_plan_normalizes_common_regulatory_typos():
    plan = build_query_rewrite_plan(
        question="review stablity snd shelf lif justifcation",
        workspace="review",
        has_active_dossier=True,
        has_conversation=False,
    )

    assert plan.rewritten_question == "review stability and shelf life justification"
    assert "shelf life" in plan.expansion_terms


def test_build_query_rewrite_plan_applies_regulatory_action_filter_for_trend_queries():
    plan = build_query_rewrite_plan(
        question="Explain the approval history over time for these dossiers",
        workspace="review",
        has_active_dossier=False,
        has_conversation=False,
    )

    assert plan.intent == "historical_trend"
    assert plan.metadata_filter == {"category": "regulatory_action"}
