"""
Tests: Risk Lock Service — Centralized Daily Loss Lock Management

Validates:
1. activate_daily_loss_lock writes all required fields
2. clear_daily_loss_lock removes all lock fields
3. is_locked_today respects the day_key (stale locks are NOT active)
4. is_locked_today returns True for same-day lock
5. trading_scheduler BotPauseReason has DAILY_LOSS_LOCK constant
6. evaluate_and_lock_if_breached activates lock when threshold exceeded
7. evaluate_and_lock_if_breached returns False when PnL is positive
8. evaluate_and_lock_if_breached returns False when capital is zero
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.risk_lock_service import (
    RiskLockService,
    FIELD_ACTIVE,
    FIELD_DAY_KEY,
    FIELD_LOCKED_AT,
    FIELD_LOCKED_REASON,
    FIELD_LOSS_PCT,
    FIELD_RESET_AT,
    FIELD_RESET_BY,
)


def run(coro):
    return asyncio.run(coro)


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _yesterday():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _make_db(
    user_doc=None,
    bot_docs=None,
    trade_docs=None,
    update_result_count=1,
):
    """Build a minimal mock db suitable for risk_lock_service calls."""
    db = MagicMock()

    ur = MagicMock()
    ur.modified_count = update_result_count
    db.users_collection.update_one = AsyncMock(return_value=ur)
    db.users_collection.find_one = AsyncMock(return_value=user_doc)

    bot_cursor = MagicMock()
    bot_cursor.to_list = AsyncMock(return_value=bot_docs or [])
    db.bots_collection.find = MagicMock(return_value=bot_cursor)

    trade_cursor = MagicMock()
    trade_cursor.to_list = AsyncMock(return_value=trade_docs or [])
    db.trades_collection.find = MagicMock(return_value=trade_cursor)

    return db


class TestActivateDailyLossLock:
    """activate_daily_loss_lock writes all required fields."""

    def test_writes_all_fields(self):
        db = _make_db()
        svc = RiskLockService()
        result = run(svc.activate_daily_loss_lock("user1", "Test reason", 12.5, db=db))

        assert result is True
        db.users_collection.update_one.assert_called_once()
        call_args = db.users_collection.update_one.call_args
        filter_doc, update_doc = call_args[0]
        assert filter_doc == {"id": "user1"}
        set_doc = update_doc["$set"]
        assert set_doc[FIELD_ACTIVE] is True
        assert set_doc[FIELD_DAY_KEY] == _today()
        assert set_doc[FIELD_LOCKED_REASON] == "Test reason"
        assert set_doc[FIELD_LOSS_PCT] == 12.5
        assert FIELD_LOCKED_AT in set_doc

    def test_returns_false_on_db_error(self):
        db = MagicMock()
        db.users_collection.update_one = AsyncMock(side_effect=Exception("DB error"))
        svc = RiskLockService()
        result = run(svc.activate_daily_loss_lock("user1", "reason", db=db))
        assert result is False


class TestClearDailyLossLock:
    """clear_daily_loss_lock resets the user lock state."""

    def test_writes_inactive_and_unsets_fields(self):
        db = _make_db()
        svc = RiskLockService()
        result = run(svc.clear_daily_loss_lock("user1", cleared_by="admin:user1", db=db))

        assert result is True
        call_args = db.users_collection.update_one.call_args
        _, update_doc = call_args[0]
        assert update_doc["$set"][FIELD_ACTIVE] is False
        assert update_doc["$set"][FIELD_RESET_BY] == "admin:user1"
        assert FIELD_RESET_AT in update_doc["$set"]
        # All lock fields should be unset
        assert FIELD_LOCKED_AT in update_doc["$unset"]
        assert FIELD_LOCKED_REASON in update_doc["$unset"]
        assert FIELD_LOSS_PCT in update_doc["$unset"]
        assert FIELD_DAY_KEY in update_doc["$unset"]

    def test_returns_false_on_db_error(self):
        db = MagicMock()
        db.users_collection.update_one = AsyncMock(side_effect=Exception("DB error"))
        svc = RiskLockService()
        result = run(svc.clear_daily_loss_lock("user1", db=db))
        assert result is False


class TestIsLockedToday:
    """is_locked_today returns correct (is_locked, reason) pair."""

    def test_same_day_lock_returns_true(self):
        user_doc = {
            FIELD_ACTIVE: True,
            FIELD_DAY_KEY: _today(),
            FIELD_LOCKED_REASON: "Daily loss 25%",
        }
        db = _make_db(user_doc=user_doc)
        svc = RiskLockService()
        locked, reason = run(svc.is_locked_today("user1", db=db))
        assert locked is True
        assert "25%" in (reason or "")

    def test_stale_day_lock_returns_false(self):
        user_doc = {
            FIELD_ACTIVE: True,
            FIELD_DAY_KEY: _yesterday(),
            FIELD_LOCKED_REASON: "Old lock",
        }
        db = _make_db(user_doc=user_doc)
        svc = RiskLockService()
        locked, reason = run(svc.is_locked_today("user1", db=db))
        assert locked is False

    def test_no_lock_returns_false(self):
        user_doc = {FIELD_ACTIVE: False}
        db = _make_db(user_doc=user_doc)
        svc = RiskLockService()
        locked, reason = run(svc.is_locked_today("user1", db=db))
        assert locked is False

    def test_missing_user_returns_false(self):
        db = _make_db(user_doc=None)
        svc = RiskLockService()
        locked, reason = run(svc.is_locked_today("unknown_user", db=db))
        assert locked is False


class TestEvaluateAndLockIfBreached:
    """evaluate_and_lock_if_breached computes PnL and activates lock when appropriate."""

    def _make_db_for_evaluate(self, bots, trades, risk_profile="balanced"):
        db = MagicMock()
        ur = MagicMock()
        ur.modified_count = 1
        db.users_collection.update_one = AsyncMock(return_value=ur)
        db.users_collection.find_one = AsyncMock(
            return_value={"risk_profile": risk_profile}
        )
        bot_cursor = MagicMock()
        bot_cursor.to_list = AsyncMock(return_value=bots)
        db.bots_collection.find = MagicMock(return_value=bot_cursor)
        trade_cursor = MagicMock()
        trade_cursor.to_list = AsyncMock(return_value=trades)
        db.trades_collection.find = MagicMock(return_value=trade_cursor)
        return db

    def test_breach_activates_lock(self):
        # Capital = 1000, loss = 250 → 25% > balanced 20% threshold
        bots = [{"current_capital": 1000}]
        trades = [{"net_pnl": -250, "status": "closed"}]
        db = self._make_db_for_evaluate(bots, trades, "balanced")
        svc = RiskLockService()
        breached, pct, reason = run(svc.evaluate_and_lock_if_breached("user1", db=db))
        assert breached is True
        assert pct > 20.0
        assert "threshold" in reason.lower() or "%" in reason
        db.users_collection.update_one.assert_called_once()  # lock was written

    def test_no_breach_does_not_lock(self):
        # Capital = 1000, loss = 50 → 5% < balanced 20% threshold
        bots = [{"current_capital": 1000}]
        trades = [{"net_pnl": -50, "status": "closed"}]
        db = self._make_db_for_evaluate(bots, trades, "balanced")
        svc = RiskLockService()
        breached, pct, reason = run(svc.evaluate_and_lock_if_breached("user1", db=db))
        assert breached is False
        db.users_collection.update_one.assert_not_called()

    def test_positive_pnl_does_not_lock(self):
        bots = [{"current_capital": 1000}]
        trades = [{"net_pnl": 100, "status": "closed"}]
        db = self._make_db_for_evaluate(bots, trades)
        svc = RiskLockService()
        breached, pct, reason = run(svc.evaluate_and_lock_if_breached("user1", db=db))
        assert breached is False

    def test_zero_capital_does_not_lock(self):
        bots = [{"current_capital": 0}]
        trades = [{"net_pnl": -100}]
        db = self._make_db_for_evaluate(bots, trades)
        svc = RiskLockService()
        breached, pct, reason = run(svc.evaluate_and_lock_if_breached("user1", db=db))
        assert breached is False

    def test_no_trades_does_not_lock(self):
        bots = [{"current_capital": 1000}]
        trades = []
        db = self._make_db_for_evaluate(bots, trades)
        svc = RiskLockService()
        breached, pct, reason = run(svc.evaluate_and_lock_if_breached("user1", db=db))
        assert breached is False


class TestBotPauseReasonHasDailyLossLock:
    """trading_scheduler.BotPauseReason must declare DAILY_LOSS_LOCK."""

    def test_daily_loss_lock_reason_exists(self):
        # trading_scheduler imports paper_trading_engine which needs ccxt.
        # Parse the source file directly so the test works in environments
        # that don't have the full runtime installed.
        import os
        scheduler_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'trading_scheduler.py'
        )
        with open(scheduler_path) as f:
            source = f.read()
        assert "DAILY_LOSS_LOCK" in source, (
            "BotPauseReason in trading_scheduler.py must define DAILY_LOSS_LOCK"
        )
        assert '"DAILY_LOSS_LOCK"' in source, (
            "DAILY_LOSS_LOCK value must be the string 'DAILY_LOSS_LOCK'"
        )
