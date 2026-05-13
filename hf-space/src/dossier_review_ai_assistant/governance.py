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
    model_id: str | None = None,
) -> dict[str, str]:
    tags = {
        "data_classification": data_classification,
        "data_version": settings.data_version,
        "split_version": settings.split_version,
        "model_policy": settings.model_policy,
        "model_id": model_id or settings.model_id,
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

import json
from pathlib import Path

def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Computes the Jaro-Winkler similarity between two strings."""
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if s1 == s2:
        return 1.0

    len1 = len(s1)
    len2 = len(s2)

    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = (max(len1, len2) // 2) - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)

        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] == s2[j]:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len1) + (matches / len2) + ((matches - transpositions / 2) / matches)
    ) / 3.0

    # Winkler modification
    prefix_limit = 4
    prefix_match = 0
    for i in range(min(len1, len2, prefix_limit)):
        if s1[i] == s2[i]:
            prefix_match += 1
        else:
            break

    return jaro + (prefix_match * 0.1 * (1.0 - jaro))


def verify_inn_infringement(product_name: str, inn_list: list[str], threshold: float = 0.7) -> tuple[bool, float, str | None]:
    """
    Checks if a product name is too similar to any known INN.
    Returns (is_infringement, max_similarity, closest_inn).
    """
    if not product_name:
        return False, 0.0, None

    max_sim = 0.0
    closest_inn = None

    product_normalized = product_name.lower().strip()

    for inn in inn_list:
        sim = jaro_winkler_similarity(product_name, inn)
        inn_normalized = str(inn).lower().strip()

        prefix_len = 0
        for left, right in zip(product_normalized, inn_normalized, strict=False):
            if left != right:
                break
            prefix_len += 1

        # Avoid overcalling class-stem overlaps such as "cef*" or "amox*"
        # when the shared prefix is short and the remainder diverges.
        if sim >= threshold and prefix_len <= 4 and sim < 0.9:
            continue

        if sim > max_sim:
            max_sim = sim
            closest_inn = inn

    return max_sim >= threshold, max_sim, closest_inn


def load_inns_from_snapshot(snapshot_path: Path) -> list[str]:
    """Extracts all normalized ingredients and aliases from the RxNorm snapshot."""
    if not snapshot_path.exists():
        return []
    
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        inns = set()
        for record in data.get("records", []):
            if "normalized_ingredient" in record:
                inns.add(record["normalized_ingredient"])
            for alias in record.get("aliases", []):
                inns.add(alias)
        return sorted(list(inns))
    except Exception:
        return []

