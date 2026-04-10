from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProfile:
    id: str
    label: str
    runtime_model_id: str
    description: str


@dataclass(frozen=True)
class Settings:
    data_jsonl_path: Path
    audit_log_path: Path
    ui_index_path: Path
    knowledge_wiki_path: Path
    conversations_state_path: Path
    default_top_k: int
    max_retrieval_k: int
    data_version: str
    split_version: str
    model_policy: str
    model_id: str
    low_cost_summary_model_id: str
    prompt_version: str
    retention_days: int
    min_free_ram_gb: float
    standard_route_rss_limit_gb: float
    fallback_route_rss_limit_gb: float
    default_context_window_tokens: int
    min_context_window_tokens: int
    max_context_window_tokens: int
    context_compaction_threshold: float
    context_keep_last_messages: int
    vllm_base_url: str
    vllm_api_key_env: str
    hf_token_env_var: str
    model_catalog: tuple[ModelProfile, ...]


def _default_model_catalog() -> tuple[ModelProfile, ...]:
    return (
        ModelProfile(
            id="gemma-e4b",
            label="Gemma E4B",
            runtime_model_id="gemma-e4b",
            description="Primary balanced local model for dossier review.",
        ),
        ModelProfile(
            id="gemma-e2b",
            label="Gemma E2B",
            runtime_model_id="gemma-e2b",
            description="Smaller fast local model for lighter retrieval-backed tasks.",
        ),
        ModelProfile(
            id="qwen-3.5",
            label="Qwen 3.5",
            runtime_model_id="qwen-3.5",
            description="Alternative reasoning profile for comparative synthesis.",
        ),
    )


def _load_model_catalog() -> tuple[ModelProfile, ...]:
    raw = os.getenv("DOSSIER_MODEL_CATALOG")
    if not raw:
        return _default_model_catalog()

    parsed = json.loads(raw)
    profiles: list[ModelProfile] = []
    for item in parsed:
        profiles.append(
            ModelProfile(
                id=str(item["id"]),
                label=str(item["label"]),
                runtime_model_id=str(item.get("runtime_model_id", item["id"])),
                description=str(item.get("description", "")),
            )
        )
    return tuple(profiles) if profiles else _default_model_catalog()


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
    knowledge_wiki = os.getenv(
        "DOSSIER_KNOWLEDGE_WIKI",
        str(root / "state" / "knowledge_wiki.json"),
    )
    conversations_state = os.getenv(
        "DOSSIER_CONVERSATIONS_STATE",
        str(root / "state" / "conversations.json"),
    )
    default_top_k = int(os.getenv("DOSSIER_DEFAULT_TOP_K", "5"))
    max_retrieval_k = int(os.getenv("DOSSIER_MAX_RETRIEVAL_K", "20"))
    data_version = os.getenv("DOSSIER_DATA_VERSION", "balanced_v1_2026-04-05")
    split_version = os.getenv("DOSSIER_SPLIT_VERSION", "balanced_v1_2026-04-05")
    model_catalog = _load_model_catalog()
    default_model_id = model_catalog[0].id if model_catalog else "gemma-e4b"
    model_policy = os.getenv("DOSSIER_MODEL_POLICY", "local_multi_model")
    model_id = os.getenv("DOSSIER_MODEL_ID", default_model_id)
    low_cost_summary_model_id = os.getenv("DOSSIER_LOW_COST_SUMMARY_MODEL_ID", "gemma-e2b")
    prompt_version = os.getenv("DOSSIER_PROMPT_VERSION", "review_v1")
    retention_days = int(os.getenv("DOSSIER_RETENTION_DAYS", "30"))
    min_free_ram_gb = float(os.getenv("DOSSIER_MIN_FREE_RAM_GB", "0.5"))
    standard_route_rss_limit_gb = float(os.getenv("DOSSIER_STANDARD_ROUTE_RSS_LIMIT_GB", "20.0"))
    fallback_route_rss_limit_gb = float(os.getenv("DOSSIER_FALLBACK_ROUTE_RSS_LIMIT_GB", "26.0"))
    default_context_window_tokens = int(os.getenv("DOSSIER_DEFAULT_CONTEXT_WINDOW_TOKENS", "4096"))
    min_context_window_tokens = int(os.getenv("DOSSIER_MIN_CONTEXT_WINDOW_TOKENS", "1024"))
    max_context_window_tokens = int(os.getenv("DOSSIER_MAX_CONTEXT_WINDOW_TOKENS", "32768"))
    context_compaction_threshold = float(os.getenv("DOSSIER_CONTEXT_COMPACTION_THRESHOLD", "0.98"))
    context_keep_last_messages = int(os.getenv("DOSSIER_CONTEXT_KEEP_LAST_MESSAGES", "4"))
    vllm_base_url = os.getenv("DOSSIER_VLLM_BASE_URL", "http://127.0.0.1:8001/v1/chat/completions")
    vllm_api_key_env = os.getenv("DOSSIER_VLLM_API_KEY_ENV", "VLLM_API_KEY")
    hf_token_env_var = os.getenv("DOSSIER_HF_TOKEN_ENV_VAR", "HF_TOKEN")

    return Settings(
        data_jsonl_path=Path(data_jsonl),
        audit_log_path=Path(audit_log),
        ui_index_path=Path(ui_index),
        knowledge_wiki_path=Path(knowledge_wiki),
        conversations_state_path=Path(conversations_state),
        default_top_k=default_top_k,
        max_retrieval_k=max_retrieval_k,
        data_version=data_version,
        split_version=split_version,
        model_policy=model_policy,
        model_id=model_id,
        low_cost_summary_model_id=low_cost_summary_model_id,
        prompt_version=prompt_version,
        retention_days=retention_days,
        min_free_ram_gb=min_free_ram_gb,
        standard_route_rss_limit_gb=standard_route_rss_limit_gb,
        fallback_route_rss_limit_gb=fallback_route_rss_limit_gb,
        default_context_window_tokens=default_context_window_tokens,
        min_context_window_tokens=min_context_window_tokens,
        max_context_window_tokens=max_context_window_tokens,
        context_compaction_threshold=context_compaction_threshold,
        context_keep_last_messages=context_keep_last_messages,
        vllm_base_url=vllm_base_url,
        vllm_api_key_env=vllm_api_key_env,
        hf_token_env_var=hf_token_env_var,
        model_catalog=model_catalog,
    )
