from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from regulatory_mcp_server.app import mcp, settings

from .common import build_tool_envelope, tool_audit


LOGGER = logging.getLogger("regulatory_mcp_server.tools.health")


@mcp.tool(name="health_status", description="Return server health, transport, and configuration status.")
@tool_audit(tool_name="health_status", logger=LOGGER)
def health_status() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    cache_dir = Path(settings.cache_dir)
    audit_log = Path(settings.audit_log_path)
    return build_tool_envelope(
        tool_name="health_status",
        payload=payload,
        data={
            "server_name": settings.server_name,
            "status": "ok",
            "host": settings.host,
            "port": settings.port,
            "streamable_http_path": settings.streamable_http_path,
            "external_access_enabled": settings.external_access_enabled,
            "allowed_external_domains": settings.allowed_external_domains,
            "cache_dir": str(cache_dir),
            "audit_log_path": str(audit_log),
        },
        warnings=[],
        source_refs=[],
    )

