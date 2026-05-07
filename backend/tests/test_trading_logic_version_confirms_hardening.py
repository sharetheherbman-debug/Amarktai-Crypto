"""
Verify trading-logic-version endpoint exists and confirms hardening is applied.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_trading_logic_version_route_declared():
    """Route must be declared in routes/diagnostics.py."""
    diag_path = os.path.join(backend_dir, "routes", "diagnostics.py")
    with open(diag_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert '@router.get("/trading-logic-version")' in src, (
        "GET /api/diagnostics/trading-logic-version not declared in diagnostics.py"
    )


def test_trading_logic_version_route_mounted_in_openapi():
    """Route must appear in app OpenAPI paths."""
    from server import app

    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/trading-logic-version" in paths, (
        "GET /api/diagnostics/trading-logic-version not found in OpenAPI — route not mounted"
    )


@pytest.mark.asyncio
async def test_trading_logic_version_returns_required_fields(monkeypatch):
    """Response must include all hardening proof fields."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    monkeypatch.setenv("MACRO_SIGNAL_WEIGHT", "0.0")

    from routes.diagnostics import trading_logic_version

    result = await trading_logic_version(user_id="logic_version_user")

    required_fields = {
        "commit_sha",
        "edge_init_fixed",
        "signal_status_gate",
        "bearish_spot_block",
        "expectancy_gate",
        "fake_signal_live_weight_zero",
        "stagnation_exit_minutes",
        "paper_fill_recording_enabled",
        "learning_loop_enabled",
        "live_enabled",
    }
    missing = required_fields - set(result.keys())
    assert not missing, f"Missing proof fields in trading-logic-version response: {missing}"


@pytest.mark.asyncio
async def test_trading_logic_version_live_enabled_is_false(monkeypatch):
    """live_enabled must be False when ENABLE_LIVE_TRADING is not set."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

    from routes.diagnostics import trading_logic_version

    result = await trading_logic_version(user_id="live_disabled_user")
    assert result["live_enabled"] is False, (
        f"live_enabled should be False but got {result['live_enabled']}"
    )


@pytest.mark.asyncio
async def test_trading_logic_version_stagnation_exit_not_too_short(monkeypatch):
    """stagnation_exit_minutes must be >= 30 to avoid premature exits."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

    from routes.diagnostics import trading_logic_version

    result = await trading_logic_version(user_id="stagnation_check_user")
    assert result["stagnation_exit_minutes"] >= 30, (
        f"stagnation_exit_minutes={result['stagnation_exit_minutes']} is too short (minimum 30)"
    )


@pytest.mark.asyncio
async def test_trading_logic_version_expectancy_gate_present(monkeypatch):
    """expectancy_gate must be True confirming MIN_EXPECTANCY_ZAR is configured."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

    from routes.diagnostics import trading_logic_version

    result = await trading_logic_version(user_id="expectancy_gate_user")
    assert result["expectancy_gate"] is True, (
        "expectancy_gate should be True but MIN_EXPECTANCY_ZAR not accessible from config"
    )
