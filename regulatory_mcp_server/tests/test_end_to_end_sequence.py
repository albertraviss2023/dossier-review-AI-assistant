from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_mcp_end_to_end import run_sequence


@pytest.mark.asyncio
async def test_mcp_end_to_end_sequence_passes() -> None:
    report = await run_sequence()

    assert report["passed"] is True
    assert "health_status" in report["tool_names"]
    assert "search_vector_database" in report["tool_names"]
    assert "generate_findings_table" in report["tool_names"]
    assert report["final_outputs"]["health"]["status"] == "success"
    assert report["final_outputs"]["evidence_packet"]["data"]["ready_for_judgment"] is True
    assert "markdown_table" in report["final_outputs"]["findings_table"]["data"]
