from __future__ import annotations

import asyncio
from pathlib import Path

from regulatory_mcp_server.app import mcp, settings


def test_server_registers_health_tool():
    async def run() -> list[str]:
        tools = await mcp.list_tools()
        return [tool.name for tool in tools]

    tool_names = asyncio.run(run())
    assert "health_status" in tool_names


def test_health_tool_returns_structured_json():
    async def run():
        res = await mcp.call_tool("health_status", {})
        if isinstance(res, tuple):
            res = res[0]  # Get list[Content] from (list[Content], raw_result)
        return res

    result = asyncio.run(run())
    text_payload = result[0].text
    assert '"status": "success"' in text_payload
    assert '"server_name": "Regulatory MCP Server"' in text_payload
    assert settings.streamable_http_path in text_payload

