from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_mcp_realistic_simulations import run_simulations


@pytest.mark.asyncio
async def test_realistic_simulations_pass() -> None:
    report = await run_simulations()
    assert report["passed"] is True
    assert report["scenario_count"] >= 5
    assert report["failed_count"] == 0
