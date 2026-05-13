from __future__ import annotations

from dossier_review_ai_assistant.orchestrator import (
    aggregate_judge_decision,
    build_evidence_packet,
    build_judge_decision,
    verify_judge_decision,
)


def test_build_evidence_packet_keeps_query_rewrite_and_source_boundaries():
    dossier = {
        "dossier_id": "DOS-100",
        "product": {"product_name": "ReviewCase", "inn_name": "amoxicillin"},
        "sections": [
            {"title": "Manufacturer and GMP Evidence"},
            {"title": "Clinical Overview and Benefit-Risk Summary"},
        ],
    }
    evidence = [
        {
            "citation_id": "DOS-100:m1:c1",
            "dossier_id": "DOS-100",
            "section_id": "m1",
            "section_title": "Manufacturer and GMP Evidence",
            "score": 0.91,
            "snippet": "GMP certificate remains valid.",
            "text": "GMP certificate remains valid.",
        }
    ]
    model_packet = {
        "analysis": {
            "original_question": "Review stability and GMP status",
            "resolved_question": "Review stability and GMP status",
            "constraints": ["Manufacturer"],
            "expansion_terms": ["good manufacturing practice", "certificate validity"],
            "sub_queries": ["Review stability and GMP status", "Review stability and GMP status certificate validity"],
            "metadata_filter": {"category": "regulatory_action"},
            "rewrite_notes": ["Added regulatory terminology variants for recall."],
            "discarded_count": 2,
        },
        "review_state": {"active_dossier_id": "DOS-100"},
    }
    amr = {
        "applies": False,
        "source_mode": "snapshot_only",
        "source_trace": [],
        "aware_category": "not_applicable",
        "authorization_control": "standard_authorization",
    }

    packet = build_evidence_packet(
        dossier=dossier,
        question="Review stability and GMP status",
        intent="dossier_review",
        evidence=evidence,
        amr_stewardship=amr,
        model_packet=model_packet,
    )

    assert packet.packet_version == "evidence_packet_v1"
    assert "gmp_certificate_and_inspection_rule" in packet.applicable_rules
    assert packet.query_rewrite["constraints"] == ["Manufacturer"]
    assert packet.query_rewrite["metadata_filter"] == {"category": "regulatory_action"}
    assert packet.dossier_evidence[0]["citation_id"] == "DOS-100:m1:c1"
    assert packet.review_state["active_dossier_id"] == "DOS-100"
    assert any("Judge input packet contains 1 dossier evidence chunks." == note for note in packet.packet_notes)


def test_judge_and_verifier_produce_rule_bound_findings():
    dossier = {
        "dossier_id": "DOS-200",
        "product": {"product_name": "RiskCase", "inn_name": "cefiderocol"},
        "policy_signals": {
            "gmp_inspection_status": "non_compliant",
            "gmp_certificate_validity": "expired",
            "clinical_data_available": True,
            "pivotal_trial_outcome": "endpoint_met",
        },
        "sections": [
            {"title": "Manufacturer and GMP Evidence"},
            {"title": "Clinical Overview and Benefit-Risk Summary"},
        ],
    }
    packet = build_evidence_packet(
        dossier=dossier,
        question="Review the GMP and clinical posture for this dossier",
        intent="dossier_review",
        evidence=[
            {
                "citation_id": "DOS-200:m1:c1",
                "dossier_id": "DOS-200",
                "section_id": "m1",
                "section_title": "Manufacturer and GMP Evidence",
                "score": 0.95,
                "snippet": "GMP certificate expired after non-compliant inspection findings.",
                "text": "GMP certificate expired after non-compliant inspection findings.",
            }
        ],
        amr_stewardship={
            "applies": False,
            "source_mode": "snapshot_only",
            "source_trace": [],
            "aware_category": "not_applicable",
            "authorization_control": "standard_authorization",
        },
        model_packet={"analysis": {}},
    )
    judge = build_judge_decision(
        dossier=dossier,
        evidence_packet=packet,
        section_diagnostics=[],
        amr_stewardship={"applies": False},
    )
    verifier = verify_judge_decision(judge_decision=judge, evidence_packet=packet)
    aggregate = aggregate_judge_decision(judge_decision=judge)

    assert judge.schema_version == "judge_v1"
    assert any(finding.requirement_id == "gmp_quality" and finding.issue_present for finding in judge.findings)
    assert verifier.passed is True
    assert aggregate["final_status"] == "approval_denied"
