"""
Go-live fix tests — validate the targeted changes introduced in the FINAL GO-LIVE PR.

Covers:
  A) Bodyguard insufficient-data guard (OR condition on warmup)
  B) Paper engine / scheduler bot_id KeyError prevention
  C) System-mode /api/system/mode never returns "unknown"
  D) Database ping uses correct handle
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

import pytest

# Ensure backend is on the path so we can import modules directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# A) Bodyguard: insufficient-data guard (structural + unit)
# ---------------------------------------------------------------------------


def test_bodyguard_warmup_uses_or_condition():
    """Warmup skip condition must use 'or' not 'and' so zero-trade old bots are protected."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "services", "bodyguard_service.py"
    )
    with open(path) as fh:
        source = fh.read()

    # The broken AND condition must not appear
    assert "trades_count < MIN_TRADES_FOR_BODYGUARD and runtime_seconds" not in source, (
        "bodyguard_service.py still uses AND for warmup — must use OR to protect zero-trade bots"
    )
    # The correct OR condition must be present
    assert "trades_count < MIN_TRADES_FOR_BODYGUARD or runtime_seconds" in source, (
        "bodyguard_service.py must use OR in warmup condition"
    )


def test_bodyguard_insufficient_data_status_written():
    """When trades are insufficient, bodyguard must write bodyguard_status='insufficient_data'."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "services", "bodyguard_service.py"
    )
    with open(path) as fh:
        source = fh.read()

    assert "insufficient_data" in source, (
        "bodyguard_service.py must set bodyguard_status='insufficient_data' for zero-trade bots"
    )


def test_bodyguard_unit_skips_lock_zero_trades(monkeypatch):
    """Integration: old bot with 0 trades must not be locked even with 50% drawdown."""
    try:
        import services.bodyguard_service as bodyguard_module
    except (ImportError, ModuleNotFoundError):
        pytest.skip("bodyguard_service dependencies (motor/ccxt) not installed")

    class _FakeBots:
        def __init__(self, bot):
            self.bot = dict(bot)
            self.last_set = {}

        async def find_one(self, query, projection=None):
            return dict(self.bot)

        async def update_one(self, query, update, upsert=False):
            if "$set" in update:
                self.bot.update(update["$set"])
                self.last_set.update(update["$set"])
            if "$unset" in update:
                for k in update["$unset"]:
                    self.bot.pop(k, None)

    bot_id = "old-zero-trade-bot"
    old_created_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    fake_bots = _FakeBots(
        {
            "id": bot_id,
            "user_id": "u1",
            "name": "Old Zero-Trade Bot",
            "status": "active",
            "trading_mode": "paper",
            "risk_mode": "aggressive",
            "trades_count": 0,
            "created_at": old_created_at,
            "current_capital": 500,
            "initial_capital": 1000,
            "equity_peak": 1000,
        }
    )
    monkeypatch.setattr(bodyguard_module.db, "bots_collection", fake_bots)
    monkeypatch.setattr(bodyguard_module.db, "db", None)

    action_taken, _ = asyncio.run(
        bodyguard_module.bodyguard_service.check_bot_drawdown("u1", bot_id)
    )

    assert action_taken is False, "Zero-trade bot must not be locked regardless of runtime"
    assert fake_bots.last_set.get("bodyguard_status") == "insufficient_data"


# ---------------------------------------------------------------------------
# B) Paper engine / scheduler: no KeyError from result['bot_id']
# ---------------------------------------------------------------------------


def test_trading_scheduler_uses_get_for_bot_id():
    """trading_scheduler.py must use result.get('bot_id', bot_id) not result['bot_id']."""
    scheduler_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "trading_scheduler.py"
    )
    with open(scheduler_path) as fh:
        source = fh.read()

    # The broken pattern that caused the KeyError
    assert "result['bot_id']" not in source, (
        "trading_scheduler.py still has result['bot_id'] — must use result.get('bot_id', bot_id)"
    )
    # The safe pattern should be present
    assert "result.get('bot_id', bot_id)" in source, (
        "trading_scheduler.py must use result.get('bot_id', bot_id)"
    )


# ---------------------------------------------------------------------------
# C) System mode: /api/system/mode must not return "unknown"
# ---------------------------------------------------------------------------


def test_system_mode_get_mode_no_unknown():
    """The get_mode route handler must never produce active_mode='unknown'."""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "routes", "system_mode.py"
    )
    with open(route_path) as fh:
        source = fh.read()

    assert 'active_mode = "unknown"' not in source, (
        "routes/system_mode.py still assigns active_mode='unknown' — must default to 'paper'"
    )
    assert 'active_mode = "paper"' in source, (
        "routes/system_mode.py must have a fallback of active_mode='paper'"
    )


# ---------------------------------------------------------------------------
# D) Database ping: must use db.client.admin.command, not db.command
# ---------------------------------------------------------------------------


def test_self_healing_uses_correct_db_ping():
    """self_healing.py must call db.client.admin.command('ping'), not db.command('ping')."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "self_healing.py"
    )
    with open(path) as fh:
        source = fh.read()

    assert "await db.command('ping')" not in source, (
        "self_healing.py still calls db.command('ping') which raises AttributeError"
    )
    assert "db.client.admin.command('ping')" in source, (
        "self_healing.py must call db.client.admin.command('ping')"
    )


def test_system_health_endpoints_uses_correct_db_ping():
    """system_health_endpoints.py must call db.client.admin.command, not db.command."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "routes", "system_health_endpoints.py"
    )
    with open(path) as fh:
        source = fh.read()

    assert "await db.command('ping')" not in source, (
        "system_health_endpoints.py still calls db.command('ping') which raises AttributeError"
    )
    assert "db.client.admin.command('ping')" in source, (
        "system_health_endpoints.py must call db.client.admin.command('ping')"
    )


# ---------------------------------------------------------------------------
# E) Smoke scripts: verify correct endpoint and env var support
# ---------------------------------------------------------------------------


def test_smoke_bodyguard_uses_bots_status_endpoint():
    """smoke_bodyguard_loop.sh must query /api/bots/status not /api/admin/bots."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "scripts", "smoke_bodyguard_loop.sh"
    )
    with open(path) as fh:
        source = fh.read()

    assert "/api/bots/status" in source, (
        "smoke_bodyguard_loop.sh must use /api/bots/status to discover bots"
    )
    assert 'ADMIN_EMAIL' in source, (
        "smoke_bodyguard_loop.sh must support ADMIN_EMAIL env var"
    )
    assert 'ADMIN_PASS' in source, (
        "smoke_bodyguard_loop.sh must support ADMIN_PASS env var"
    )


def test_smoke_paper_trade_uses_bots_status_endpoint():
    """smoke_paper_trade.sh must query /api/bots/status not /api/admin/bots."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "scripts", "smoke_paper_trade.sh"
    )
    with open(path) as fh:
        source = fh.read()

    assert "/api/bots/status" in source, (
        "smoke_paper_trade.sh must use /api/bots/status to discover bots"
    )
    assert 'ADMIN_EMAIL' in source, (
        "smoke_paper_trade.sh must support ADMIN_EMAIL env var"
    )


def test_smoke_health_openapi_uses_api_openapi():
    """smoke_health_openapi.sh must check /api/openapi.json directly."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "scripts", "smoke_health_openapi.sh"
    )
    with open(path) as fh:
        source = fh.read()

    assert "/api/openapi.json" in source, (
        "smoke_health_openapi.sh must check /api/openapi.json directly"
    )
    # Must not use the old redirect shortcut: -L flag with /openapi.json root path
    import re
    assert not re.search(r'check_json[^"]*"\$BASE_URL/openapi\.json".*-L', source), (
        "smoke_health_openapi.sh must not rely on /openapi.json redirect (-L)"
    )
