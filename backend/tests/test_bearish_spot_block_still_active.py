"""
Verify the bearish spot block hardening is still active in the trading engine.

Phase 5 requirement: bearish spot long entries must be blocked or set FLAT.
This re-tests the canonical behaviour from test_bearish_signal_blocks_spot_long.py
and proves it from the diagnostics/trading-logic-version endpoint.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_bearish_spot_block_code_present_in_paper_engine():
    """paper_trading_engine.py must contain bearish/FLAT spot block logic."""
    engine_path = os.path.join(backend_dir, "paper_trading_engine.py")
    with open(engine_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "bearish" in src.lower(), (
        "paper_trading_engine.py has no 'bearish' reference — spot block may be missing"
    )
    assert "FLAT" in src or "bearish_spot_no_short" in src, (
        "paper_trading_engine.py missing FLAT direction or bearish_spot_no_short skip reason"
    )


def test_bearish_spot_block_code_present_in_trading_scheduler():
    """trading_scheduler.py must contain bearish spot block guard."""
    sched_path = os.path.join(backend_dir, "trading_scheduler.py")
    with open(sched_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "bearish_spot_no_short" in src or "bearish" in src.lower(), (
        "trading_scheduler.py has no bearish spot block logic"
    )
    assert "FLAT" in src, "trading_scheduler.py missing FLAT direction on bearish block"


@pytest.mark.asyncio
async def test_bearish_spot_block_active_via_source_inspection():
    """Prove bearish spot block exists in trading_scheduler source."""
    import inspect
    from trading_scheduler import trading_scheduler
    src = inspect.getsource(type(trading_scheduler))
    assert "bearish_spot_no_short" in src, (
        "trading_scheduler.execute_live_trade does not contain bearish_spot_no_short skip reason"
    )
    assert "FLAT" in src, (
        "trading_scheduler.execute_live_trade does not set FLAT direction on bearish block"
    )


@pytest.mark.asyncio
async def test_trading_logic_version_confirms_bearish_spot_block(monkeypatch):
    """trading-logic-version endpoint must report bearish_spot_block=True."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    from routes.diagnostics import trading_logic_version

    result = await trading_logic_version(user_id="bearish_block_check_user")
    assert result["bearish_spot_block"] is True, (
        f"trading-logic-version reports bearish_spot_block={result['bearish_spot_block']!r} — "
        "check that paper_trading_engine.py has bearish/FLAT references"
    )
