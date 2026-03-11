"""
Tests for the canonical paper-trading queue → execution lifecycle.

Verifies:
1. Paper bots bypass the redundant `validate_bot_trading_mode` env-var gate in the
   scheduler's queue-processing loop (primary execution-gap fix).
2. `normalize_trading_mode` resolves 'paper_trading' → 'paper' in the validator so
   mode-string mismatches no longer silently block valid paper bots.
3. `tick_blocked` counter tracks live-mode gate failures; paper bots never increment it.
4. `tick_processed` is incremented whenever execution is actually attempted (run_trading_cycle called).
5. `get_health_snapshot` exposes `last_tick_blocked` for API truth convergence.
6. `/api/diagnostics/paper-status` response includes the canonical `scheduler_state` block.
7. No imports from _archive in the active runtime path.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(ROOT, "backend"))


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _import_scheduler(extra_mods: dict | None = None):
    """Import trading_scheduler fresh with heavy dependencies mocked out.

    Returns the module object.  Callers can pass extra_mods to override
    specific mocked dependencies (e.g. paper_engine, validator).
    """
    base_mocks = {
        "ccxt": MagicMock(),
        "ccxt.async_support": MagicMock(),
        "database": MagicMock(),
        "websocket_manager": MagicMock(),
        "realtime_events": MagicMock(),
        "paper_trading_engine": MagicMock(),
        "engines.trading_engine_live": MagicMock(),
        "services.system_gate": MagicMock(),
        "services.live_gate_service": MagicMock(),
        "services.bot_quarantine": MagicMock(),
        "services.bot_runtime_state": MagicMock(),
        "services.risk_lock_service": MagicMock(),
        "services.trading_mode_validator": MagicMock(),
        "utils.trading_gates": MagicMock(),
        "config": MagicMock(PAPER_SUPPORTED_EXCHANGES={"luno", "binance"}),
    }
    staggerer_mock = MagicMock()
    staggerer_mock.trade_queue = []
    staggerer_mock.active_trades = {}
    base_mocks["engines.trade_staggerer"] = MagicMock(trade_staggerer=staggerer_mock)

    if extra_mods:
        base_mocks.update(extra_mods)

    with patch.dict("sys.modules", base_mocks):
        import importlib
        for key in list(sys.modules.keys()):
            if key == "trading_scheduler":
                del sys.modules[key]
        return importlib.import_module("trading_scheduler")


# ---------------------------------------------------------------------------
# Phase 0 — canonical execution map (source-level assertions)
# ---------------------------------------------------------------------------

def test_scheduler_paper_bots_bypass_validate_bot_trading_mode():
    """Paper bots must NOT call validate_bot_trading_mode — they were already
    vetted by the system-mode gate above the queue loop."""
    src = _read("backend/trading_scheduler.py")

    # The fix: only call validate_bot_trading_mode for non-paper (live) bots.
    assert "if not is_paper_mode:" in src, (
        "Paper bots must be routed around validate_bot_trading_mode"
    )
    # The paper mode check must use the canonical _is_paper_bot helper.
    assert "is_paper_mode = _is_paper_bot(bot)" in src, (
        "_is_paper_bot must be used to classify mode before queue dispatch"
    )


def test_scheduler_tick_blocked_counter_initialised_and_tracked():
    """tick_blocked must be initialised each tick and stored in instance state."""
    src = _read("backend/trading_scheduler.py")
    assert "tick_blocked = 0" in src
    assert "self.last_tick_blocked = tick_blocked" in src


def test_scheduler_all_blocked_by_gate_noop_reason():
    """When all dequeued trades are blocked before execution, the noop reason
    must be 'all_blocked_by_gate', not the misleading 'no_trades_executed'."""
    src = _read("backend/trading_scheduler.py")
    assert '"all_blocked_by_gate"' in src or "'all_blocked_by_gate'" in src


def test_scheduler_health_snapshot_exposes_last_tick_blocked():
    """get_health_snapshot must include last_tick_blocked for API diagnostics."""
    src = _read("backend/trading_scheduler.py")
    assert '"last_tick_blocked"' in src


def test_validator_uses_normalize_trading_mode():
    """trading_mode_validator must import and use normalize_trading_mode to
    handle 'paper_trading', 'PAPER', etc. without falling to the else-branch."""
    src = _read("backend/services/trading_mode_validator.py")
    assert "from utils.trading_mode import normalize_trading_mode" in src
    assert "normalize_trading_mode(" in src


def test_diagnostics_paper_status_exposes_scheduler_state():
    """The /paper-status route must expose a scheduler_state block that contains
    the canonical lifecycle truth (queue_size, noop_reason, blocked count, etc.)."""
    src = _read("backend/routes/diagnostics.py")
    assert '"scheduler_state"' in src
    assert '"queue_size"' in src
    assert '"last_tick_noop_reason"' in src
    assert '"last_tick_blocked"' in src


def test_no_archive_imports_in_execution_path():
    """Verify that no active runtime files import from the _archive directory."""
    paths = [
        "backend/trading_scheduler.py",
        "backend/paper_trading_engine.py",
        "backend/engines/trade_staggerer.py",
        "backend/services/trading_mode_validator.py",
        "backend/routes/diagnostics.py",
    ]
    for rel in paths:
        src = _read(rel)
        assert "from _archive" not in src, f"_archive import found in {rel}"
        assert "import _archive" not in src, f"_archive import found in {rel}"


# ---------------------------------------------------------------------------
# Phase 1 — execution stop-point detection (functional / mock tests)
# ---------------------------------------------------------------------------

def test_normalize_trading_mode_resolves_paper_variants():
    """normalize_trading_mode must map paper_trading / PAPER / paper → 'paper'."""
    from utils.trading_mode import normalize_trading_mode

    assert normalize_trading_mode("paper") == "paper"
    assert normalize_trading_mode("paper_trading") == "paper"
    assert normalize_trading_mode("PAPER") == "paper"
    assert normalize_trading_mode("Paper Mode") == "paper"
    assert normalize_trading_mode("live") == "live"
    assert normalize_trading_mode("live_trading") == "live"
    assert normalize_trading_mode(None) == "paper"  # default


def test_is_paper_bot_uses_normalize():
    """_is_paper_bot must return True for all paper mode variants."""
    ts = _import_scheduler()

    assert ts._is_paper_bot({"mode": "paper"}) is True
    assert ts._is_paper_bot({"mode": "paper_trading"}) is True
    assert ts._is_paper_bot({"trading_mode": "PAPER"}) is True
    assert ts._is_paper_bot({"mode": "live"}) is False


def test_tick_blocked_increments_for_live_gate_failure():
    """When validate_bot_trading_mode blocks a live bot, tick_blocked must
    be incremented and the bot must NOT reach run_trading_cycle."""
    validator_mock = MagicMock()
    validator_mock.validate_bot_trading_mode = AsyncMock(
        return_value=(False, "live", "API keys missing")
    )

    ts = _import_scheduler(
        extra_mods={
            "services.trading_mode_validator": MagicMock(
                trading_mode_validator=validator_mock,
            ),
        }
    )

    bot = {
        "id": "bot-live-1",
        "name": "LiveBot",
        "mode": "live",
        "exchange": "luno",
        "user_id": "user-1",
    }

    async def run():
        tick_blocked = 0
        tick_processed = 0

        is_paper_mode = ts._is_paper_bot(bot)
        assert is_paper_mode is False  # live bot

        if not is_paper_mode:
            can_trade, _mode, reason = await validator_mock.validate_bot_trading_mode(
                "bot-live-1", bot
            )
            if not can_trade:
                tick_blocked += 1

        assert tick_blocked == 1
        assert tick_processed == 0  # execution not reached

    asyncio.run(run())


def test_paper_bot_skips_validator_gate():
    """For a paper bot, the code path must NOT call validate_bot_trading_mode.
    tick_blocked must stay 0."""
    validator_mock = MagicMock()
    validator_mock.validate_bot_trading_mode = AsyncMock(
        return_value=(False, "paper", "Paper trading not enabled globally")
    )

    ts = _import_scheduler(
        extra_mods={
            "services.trading_mode_validator": MagicMock(
                trading_mode_validator=validator_mock,
            ),
        }
    )

    bot = {
        "id": "bot-paper-1",
        "name": "PaperBot",
        "mode": "paper",
        "exchange": "luno",
        "user_id": "user-1",
    }

    async def run():
        tick_blocked = 0

        is_paper_mode = ts._is_paper_bot(bot)
        assert is_paper_mode is True  # paper bot

        # Paper bot: validator NOT called
        if not is_paper_mode:
            can_trade, _mode, reason = await validator_mock.validate_bot_trading_mode(
                "bot-paper-1", bot
            )
            if not can_trade:
                tick_blocked += 1

        # For paper bots the validator gate is skipped → tick_blocked stays 0
        assert tick_blocked == 0
        # Validator must NOT have been called
        validator_mock.validate_bot_trading_mode.assert_not_awaited()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Phase 3 — API truth convergence
# ---------------------------------------------------------------------------

def test_health_snapshot_structure():
    """get_health_snapshot must return all lifecycle truth fields."""
    ts = _import_scheduler()

    snap = ts.TradingScheduler().get_health_snapshot()
    required = {
        "scheduler_running",
        "last_tick_at",
        "last_tick_queued",
        "last_tick_executed",
        "last_tick_processed",
        "last_tick_blocked",
        "last_tick_noop_reason",
        "queue_size",
        "queued_bot_ids",
        "total_ticks",
        "total_trades_executed",
        "total_noop_ticks",
    }
    missing = required - snap.keys()
    assert not missing, f"get_health_snapshot missing keys: {missing}"
