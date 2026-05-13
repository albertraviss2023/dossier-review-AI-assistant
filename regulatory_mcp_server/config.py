from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RegulatoryMCPSettings(BaseSettings):
    server_name: str = "Regulatory MCP Server"
    host: str = "127.0.0.1"
    port: int = 8010
    streamable_http_path: str = "/mcp"
    log_level: str = "INFO"
    # External source retrieval is a core control for patient-safety checks and is enabled by default.
    # Cache remains fallback-only resilience, not the primary evidence path.
    external_access_enabled: bool = True
    allowed_external_domains: list[str] = Field(
        default_factory=lambda: [
            "www.medicines.org.uk",
            "medicines.org.uk",
            "products.mhra.gov.uk",
            "www.gov.uk",
            "dailymed.nlm.nih.gov",
            "www.accessdata.fda.gov",
            "www.ema.europa.eu",
            "www.who.int",
            "who.int",
        ]
    )
    cache_dir: Path = Field(default_factory=lambda: Path("regulatory_mcp_server/data/cached_sources"))
    audit_log_path: Path = Field(default_factory=lambda: Path("state/audit/regulatory_mcp_tool_calls.jsonl"))

    model_config = SettingsConfigDict(
        env_prefix="REGULATORY_MCP_",
        env_file=".env",
        extra="ignore",
    )
