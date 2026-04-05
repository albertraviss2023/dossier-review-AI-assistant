from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_jsonl_path: Path
    audit_log_path: Path
    ui_index_path: Path
    default_top_k: int
    max_retrieval_k: int
    data_version: str
    split_version: str
    model_policy: str
    model_id: str
    prompt_version: str
    retention_days: int
    min_free_ram_gb: float
    standard_route_rss_limit_gb: float
    fallback_route_rss_limit_gb: float


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    data_jsonl = os.getenv(
        "DOSSIER_DATA_JSONL",
        str(root / "synthetic_data" / "data" / "raw" / "balanced_v1_2026-04-05" / "dossiers.jsonl"),
    )
    audit_log = os.getenv(
        "DOSSIER_AUDIT_LOG",
        str(root / "state" / "audit" / "recommendations.jsonl"),
    )
    ui_index = os.getenv(
        "DOSSIER_UI_INDEX",
        str(root / "ui" / "index.html"),
    )
    default_top_k = int(os.getenv("DOSSIER_DEFAULT_TOP_K", "5"))
    max_retrieval_k = int(os.getenv("DOSSIER_MAX_RETRIEVAL_K", "20"))
    data_version = os.getenv("DOSSIER_DATA_VERSION", "balanced_v1_2026-04-05")
    split_version = os.getenv("DOSSIER_SPLIT_VERSION", "balanced_v1_2026-04-05")
    model_policy = os.getenv("DOSSIER_MODEL_POLICY", "gemma4_only")
    model_id = os.getenv("DOSSIER_MODEL_ID", "ai/gemma4:4B-Q4_K_XL")
    prompt_version = os.getenv("DOSSIER_PROMPT_VERSION", "review_v1")
    retention_days = int(os.getenv("DOSSIER_RETENTION_DAYS", "30"))
    min_free_ram_gb = float(os.getenv("DOSSIER_MIN_FREE_RAM_GB", "0.5"))
    standard_route_rss_limit_gb = float(os.getenv("DOSSIER_STANDARD_ROUTE_RSS_LIMIT_GB", "20.0"))
    fallback_route_rss_limit_gb = float(os.getenv("DOSSIER_FALLBACK_ROUTE_RSS_LIMIT_GB", "26.0"))

    return Settings(
        data_jsonl_path=Path(data_jsonl),
        audit_log_path=Path(audit_log),
        ui_index_path=Path(ui_index),
        default_top_k=default_top_k,
        max_retrieval_k=max_retrieval_k,
        data_version=data_version,
        split_version=split_version,
        model_policy=model_policy,
        model_id=model_id,
        prompt_version=prompt_version,
        retention_days=retention_days,
        min_free_ram_gb=min_free_ram_gb,
        standard_route_rss_limit_gb=standard_route_rss_limit_gb,
        fallback_route_rss_limit_gb=fallback_route_rss_limit_gb,
    )
