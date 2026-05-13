from __future__ import annotations

from argparse import Namespace

import json
from pathlib import Path

from evaluation.run_evaluation import evaluate, select_balanced_eval_dossiers


def test_evaluation_harness_runs_and_returns_metrics():
    args = Namespace(
        acceptance="docs/acceptance-criteria.yaml",
        raw_jsonl="synthetic_data/data/raw/balanced_v1_2026-04-05/dossiers.jsonl",
        test_jsonl="synthetic_data/data/splits/balanced_v1_2026-04-05/test.jsonl",
        output="state/eval/test_report.json",
        max_records=25,
    )
    report = evaluate(args)
    assert "summary" in report
    assert "metrics" in report
    assert "holistic_policy_macro_f1" in report["metrics"]
    assert "zenbook_standard_route_peak_rss_gb" in report["metrics"]
    assert "lineage_tag_coverage" in report["metrics"]
    assert "retention_policy_compliance_rate" in report["metrics"]
    assert "chunking_budget_overrun_rate" in report["metrics"]
    assert "chunking_retrieval_lift_vs_section_baseline" in report["metrics"]
    assert "aware_category_macro_f1" in report["metrics"]
    assert "source_backed_resolution_rate" in report["metrics"]
    assert "chemistry_identifier_coverage_rate" in report["metrics"]
    assert "watch_restriction_recall" in report["metrics"]
    assert "conversational_followup_success_rate" in report["metrics"]
    assert "linked_context_carryover_rate" in report["metrics"]
    assert "external_source_trace_integrity_rate" in report["metrics"]
    assert "external_source_context_awareness_rate" in report["metrics"]
    assert "intent_routing_accuracy" in report["metrics"]
    assert "context_scope_precision" in report["metrics"]
    assert "source_leakage_rate" in report["metrics"]
    assert "model_packet_contract_rate" in report["metrics"]
    assert "release_gate_status" in report["summary"]
    assert "failed_metrics" in report["summary"]
    assert "amr_scope" in report["summary"]
    assert "synthetic_data_coverage" in report["summary"]
    assert report["summary"]["evaluation_profile"]["retriever"] == "hybrid_bm25_densevector_rrf_rerank_v2"
    assert report["summary"]["evaluation_profile"]["conversation_eval_mode"] == "conversation_store_linked_context_v1"


def test_balanced_eval_selector_keeps_key_regulatory_scenarios():
    path = Path(r"d:\projects\ai dossier assistant\synthetic_data\data\splits\balanced_v1_2026-04-05\test.jsonl")
    dossiers = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = select_balanced_eval_dossiers(dossiers, 25)

    reject_count = sum(1 for dossier in selected if dossier.get("labels", {}).get("holistic_policy_decision") == "reject_and_return")
    watch_positive_count = sum(
        1
        for dossier in selected
        if (
            str(dossier.get("policy_signals", {}).get("aware_category", "not_applicable")) == "watch"
            and str(dossier.get("policy_signals", {}).get("similarity_to_existing_watch", "not_applicable")) == "high"
            and str(dossier.get("policy_signals", {}).get("glass_resistance_trend", "not_applicable")) == "rising"
        )
    )

    assert len(selected) == 25
    assert reject_count >= 1
    assert watch_positive_count >= 1
