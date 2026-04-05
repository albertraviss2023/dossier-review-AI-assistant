from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dossier_review_ai_assistant.config import load_settings
from dossier_review_ai_assistant.governance import (
    build_lineage_tags,
    lineage_coverage,
    lineage_is_complete,
    retention_stats,
)


def test_lineage_tags_complete():
    settings = load_settings()
    tags = build_lineage_tags(settings=settings, route="standard")
    assert lineage_is_complete(tags)
    assert tags["model_policy"] == "gemma4_only"


def test_lineage_coverage_ratio():
    settings = load_settings()
    complete = build_lineage_tags(settings=settings, route="standard")
    incomplete = {"model_policy": "gemma4_only"}
    ratio = lineage_coverage([complete, incomplete])
    assert 0.0 < ratio < 1.0


def test_retention_stats_marks_expired_records():
    now = datetime.now(UTC)
    records = [
        {"created_at_utc": (now - timedelta(days=1)).isoformat()},
        {"created_at_utc": (now - timedelta(days=45)).isoformat()},
    ]
    summary = retention_stats(records, retention_days=30, now_utc=now)
    assert summary["expired_records"] == 1
    assert summary["retained_records"] == 1

