from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class RegulatoryMCPClientError(RuntimeError):
    pass


class RegulatoryMCPClient:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def ensure_started(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._start_loop, daemon=True)
            self._thread.start()
            while self._loop is None or not self._loop.is_running():
                import time
                time.sleep(0.01)

    async def _connect(self):
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "regulatory_mcp_server.server"],
            env={**os.environ, "PYTHONPATH": os.getcwd()},
        )
        stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(*stdio_transport))
        await self._session.initialize()

    async def _call_tool_internal(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._session:
            await self._connect()
        
        assert self._session is not None
        result = await self._session.call_tool(tool_name, payload)
        if not result.content:
            raise RegulatoryMCPClientError(f"MCP tool {tool_name} returned no content.")
        
        message = result.content[0]
        text = getattr(message, "text", None)
        if not text:
            raise RegulatoryMCPClientError(f"MCP tool {tool_name} returned no text payload.")
        return json.loads(text)

    def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_started()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(self._call_tool_internal(tool_name, payload), self._loop)
        return future.result()

    def close(self):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._exit_stack.aclose(), self._loop).result()
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
        self._session = None
        self._loop = None
        self._thread = None


_global_client = RegulatoryMCPClient()


def call_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _global_client.call_tool(tool_name, payload)


def tool_data(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = call_tool(tool_name, payload)
    if response.get("status") != "success":
        raise RegulatoryMCPClientError(
            f"MCP tool {tool_name} failed with status={response.get('status')} warnings={response.get('warnings', [])}"
        )
    return response
