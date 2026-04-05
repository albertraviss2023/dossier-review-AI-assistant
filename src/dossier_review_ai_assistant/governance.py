from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Settings

REQUIRED_LINEAGE_KEYS = {
    "data_classification",
    "data_version",
    "split_version",
    "model_policy",
    "model_id",
    "prompt_version",
}


def build_lineage_tags(
    settings: Settings,
    route: str | None = None,
    data_classification: str = "synthetic",
) -> dict[str, str]:
    tags = {
        "data_classification": data_classification,
        "data_version": settings.data_version,
        "split_version": settings.split_version,
        "model_policy": settings.model_policy,
        "model_id": settings.model_id,
        "prompt_version": settings.prompt_version,
    }
    if route:
        tags["route_profile"] = route
    return tags


def lineage_is_complete(tags: dict[str, Any]) -> bool:
    if not tags:
        return False
    for key in REQUIRED_LINEAGE_KEYS:
        value = tags.get(key)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def lineage_coverage(tags_list: list[dict[str, Any]]) -> float:
    if not tags_list:
        return 0.0
    complete = sum(1 for tags in tags_list if lineage_is_complete(tags))
    return complete / len(tags_list)


def retention_stats(
    records: list[dict[str, Any]],
    retention_days: int,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    retained = 0
    expired = 0
    malformed = 0

    for record in records:
        ts_raw = record.get("created_at_utc")
        if not ts_raw:
            malformed += 1
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            ts = ts.astimezone(UTC)
        except ValueError:
            malformed += 1
            continue

        if ts < cutoff:
            expired += 1
        else:
            retained += 1

    total_valid = retained + expired
    compliance_rate = (retained / total_valid) if total_valid else 1.0
    return {
        "retention_days": retention_days,
        "total_records": len(records),
        "retained_records": retained,
        "expired_records": expired,
        "malformed_records": malformed,
        "compliance_rate": round(compliance_rate, 6),
    }

