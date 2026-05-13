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
    ui_pages_path: Path
    knowledge_wiki_path: Path
    conversations_state_path: Path
    uploaded_dossiers_dir: Path
    sample_dossiers_dir: Path
    source_snapshots_dir: Path
    auth_state_path: Path
    governance_state_path: Path
    external_source_mode: str
    external_source_timeout_seconds: float
    rxnorm_live_url: str
    who_aware_live_url: str
    who_glass_live_url: str
    chemistry_similarity_live_url: str
    default_top_k: int
    max_retrieval_k: int
    data_version: str
    split_version: str
    model_policy: str
    model_provider: str
    demo_mode: bool
    local_model_enabled: bool
    gemini_enabled: bool
    model_id: str
    low_cost_summary_model_id: str
    gemini_api_key_env: str
    gemini_model_name: str
    gemini_api_base_url: str
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
    cors_origins: tuple[str, ...]
    model_catalog: tuple[ModelProfile, ...]


def _default_model_catalog() -> tuple[ModelProfile, ...]:
    return (
        ModelProfile(
            id="gemma-4-4b-it",
            label="Gemma 4 4B-IT (Default)",
            runtime_model_id="gemma-4-4b-it",
            description="High-precision instruction-tuned model for regulatory auditing (8GB VRAM).",
        ),
        ModelProfile(
            id="gemma-4-31b-it-q4",
            label="Gemma 4 31B-IT Q4 (Least Cost)",
            runtime_model_id="gemma-4-31b-it-q4",
            description="Quantized 31B model for complex comparative reasoning with optimal cost efficiency.",
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
        str(root / "synthetic_dossier_dataset_realistic_v2" / "manifests" / "dossier_manifests.jsonl"),
    )
    audit_log = os.getenv(
        "DOSSIER_AUDIT_LOG",
        str(root / "state" / "audit" / "recommendations.jsonl"),
    )
    ui_index = os.getenv(
        "DOSSIER_UI_INDEX",
        str(root / "ui" / "review.html"),
    )
    ui_pages_path = os.getenv(
        "DOSSIER_UI_PAGES_PATH",
        str(root / "ui"),
    )
    knowledge_wiki = os.getenv(
        "DOSSIER_KNOWLEDGE_WIKI",
        str(root / "state" / "knowledge_wiki.json"),
    )
    conversations_state = os.getenv(
        "DOSSIER_CONVERSATIONS_STATE",
        str(root / "state" / "conversations.json"),
    )
    uploaded_dossiers_dir = os.getenv(
        "DOSSIER_UPLOADED_DOSSIERS_DIR",
        str(root / "state" / "uploads"),
    )
    sample_dossiers_dir = os.getenv(
        "DOSSIER_SAMPLE_DOSSIERS_DIR",
        str(root / "sample_dossiers"),
    )
    source_snapshots_dir = os.getenv(
        "DOSSIER_SOURCE_SNAPSHOTS_DIR",
        str(root / "state" / "source_snapshots"),
    )
    auth_state_path = os.getenv(
        "DOSSIER_AUTH_STATE_PATH",
        str(root / "state" / "auth_state.json"),
    )
    governance_state_path = os.getenv(
        "DOSSIER_GOVERNANCE_STATE_PATH",
        str(root / "state" / "governance_state.json"),
    )
    external_source_mode = os.getenv("DOSSIER_EXTERNAL_SOURCE_MODE", "live_prefer")
    external_source_timeout_seconds = float(os.getenv("DOSSIER_EXTERNAL_SOURCE_TIMEOUT_SECONDS", "4.0"))
    rxnorm_live_url = os.getenv("DOSSIER_RXNORM_LIVE_URL", "")
    who_aware_live_url = os.getenv("DOSSIER_WHO_AWARE_LIVE_URL", "")
    who_glass_live_url = os.getenv("DOSSIER_WHO_GLASS_LIVE_URL", "")
    chemistry_similarity_live_url = os.getenv("DOSSIER_CHEMISTRY_SIMILARITY_LIVE_URL", "")
    default_top_k = int(os.getenv("DOSSIER_DEFAULT_TOP_K", "5"))
    max_retrieval_k = int(os.getenv("DOSSIER_MAX_RETRIEVAL_K", "20"))
    data_version = os.getenv("DOSSIER_DATA_VERSION", "realistic_v2_2026-05-11")
    split_version = os.getenv("DOSSIER_SPLIT_VERSION", "realistic_v2_2026-05-11")
    model_catalog = _load_model_catalog()
    default_model_id = model_catalog[0].id if model_catalog else "gemma-e4b"
    model_policy = os.getenv("DOSSIER_MODEL_POLICY", "local_multi_model")
    model_provider = os.getenv("DOSSIER_MODEL_PROVIDER", "local").strip().lower()
    demo_mode = os.getenv("DOSSIER_DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
    local_model_enabled = os.getenv("DOSSIER_LOCAL_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    gemini_enabled = os.getenv("DOSSIER_GEMINI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    model_id = os.getenv("DOSSIER_MODEL_ID", default_model_id)
    low_cost_summary_model_id = os.getenv("DOSSIER_LOW_COST_SUMMARY_MODEL_ID", "gemma-e2b")
    gemini_api_key_env = os.getenv("DOSSIER_GEMINI_API_KEY_ENV", "GEMINI_API_KEY")
    gemini_model_name = os.getenv("DOSSIER_GEMINI_MODEL", "gemini-2.5-pro")
    gemini_api_base_url = os.getenv("DOSSIER_GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
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
    cors_raw = os.getenv("DOSSIER_CORS_ORIGINS", "")
    cors_origins = tuple(item.strip() for item in cors_raw.split(",") if item.strip())

    return Settings(
        data_jsonl_path=Path(data_jsonl),
        audit_log_path=Path(audit_log),
        ui_index_path=Path(ui_index),
        ui_pages_path=Path(ui_pages_path),
        knowledge_wiki_path=Path(knowledge_wiki),
        conversations_state_path=Path(conversations_state),
        uploaded_dossiers_dir=Path(uploaded_dossiers_dir),
        sample_dossiers_dir=Path(sample_dossiers_dir),
        source_snapshots_dir=Path(source_snapshots_dir),
        auth_state_path=Path(auth_state_path),
        governance_state_path=Path(governance_state_path),
        external_source_mode=external_source_mode,
        external_source_timeout_seconds=external_source_timeout_seconds,
        rxnorm_live_url=rxnorm_live_url,
        who_aware_live_url=who_aware_live_url,
        who_glass_live_url=who_glass_live_url,
        chemistry_similarity_live_url=chemistry_similarity_live_url,
        default_top_k=default_top_k,
        max_retrieval_k=max_retrieval_k,
        data_version=data_version,
        split_version=split_version,
        model_policy=model_policy,
        model_provider=model_provider,
        demo_mode=demo_mode,
        local_model_enabled=local_model_enabled,
        gemini_enabled=gemini_enabled,
        model_id=model_id,
        low_cost_summary_model_id=low_cost_summary_model_id,
        gemini_api_key_env=gemini_api_key_env,
        gemini_model_name=gemini_model_name,
        gemini_api_base_url=gemini_api_base_url,
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
        cors_origins=cors_origins,
        model_catalog=model_catalog,
    )
