from __future__ import annotations

from argparse import Namespace

from evaluation.run_evaluation import evaluate


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
    assert "release_gate_status" in report["summary"]
