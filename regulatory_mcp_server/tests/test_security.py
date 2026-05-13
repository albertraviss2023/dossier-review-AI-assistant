from __future__ import annotations

import json
from pathlib import Path

import pytest

from regulatory_mcp_server.app import mcp, settings


@pytest.mark.asyncio
async def test_blocked_domain_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_access_enabled", False)
    monkeypatch.setattr(settings, "allowed_external_domains", ["www.medicines.org.uk"])
    result = await mcp.call_tool(
        "fetch_innovator_patient_information",
        {
            "active_ingredient": "amoxicillin",
            "reference_urls": ["https://evil.example.com/pil"],
        },
    )
    if isinstance(result, tuple):
        result = result[0]
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "Blocked reference URL domain(s)" in payload["data"]["error"]


@pytest.mark.asyncio
async def test_invalid_url_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_access_enabled", False)
    result = await mcp.call_tool(
        "fetch_innovator_patient_information",
        {
            "active_ingredient": "amoxicillin",
            "reference_urls": ["javascript:alert(1)"],
        },
    )
    if isinstance(result, tuple):
        result = result[0]
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "Invalid reference URL(s)" in payload["data"]["error"]


@pytest.mark.asyncio
async def test_external_disabled_mode_uses_cache(monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_access_enabled", False)
    monkeypatch.setattr(settings, "allowed_external_domains", ["www.medicines.org.uk"])
    result = await mcp.call_tool(
        "fetch_innovator_patient_information",
        {
            "active_ingredient": "amoxicillin",
            "reference_urls": ["https://www.medicines.org.uk/emc/product/541/pil"],
        },
    )
    if isinstance(result, tuple):
        result = result[0]
    payload = json.loads(result[0].text)
    assert payload["status"] == "success"
    assert payload["data"]["sections"]


@pytest.mark.asyncio
async def test_audit_log_records_tool_name_and_request_metadata(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(settings, "audit_log_path", str(audit_path))
    result = await mcp.call_tool("health_status", {})
    if isinstance(result, tuple):
        result = result[0]
    payload = json.loads(result[0].text)
    assert payload["status"] == "success"
    assert audit_path.exists()
    log_lines = audit_path.read_text().splitlines()
    assert len(log_lines) >= 1
    last_record = json.loads(log_lines[-1])
    assert last_record["tool_name"] == "health_status"
    assert "request_id" in last_record
