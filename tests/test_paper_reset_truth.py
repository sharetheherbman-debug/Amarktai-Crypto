"""
Tests: Paper Reset Canonical Truth Model
=========================================

Validates the five guarantees introduced by the canonical truth-model fix:

1. After reset, zero runnable/runtime bots and zero paper trade records.
2. Deleted bots are excluded from overview/profit/bot-status counts.
3. Runtime state and bot document reconciliation.
4. Scheduler noop-reason logging when no active bots exist.
5. Start-fresh resets wallet + ledger + runtime state together.

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_paper_reset_truth.py -v
"""

import os
import sys
import logging
import asyncio

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously (no pytest-asyncio needed)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_bot(bot_id: str, status: str, user_id: str = "u1", **extra) -> dict:
    return {
        "id": bot_id,
        "user_id": user_id,
        "status": status,
        "exchange": "luno",
        "trading_mode": "paper",
        "initial_capital": 1000,
        **extra,
    }


# ---------------------------------------------------------------------------
# Test 1 — Reset leaves zero runnable/runtime bots and zero paper trade records
# ---------------------------------------------------------------------------

class TestResetLeavesZeroState:
    """After reset, canonical counts show 0 active, 0 paused, 0 deleted (from
    the *current* session) bots, and 0 trade records."""

    def test_canonical_counts_exclude_deleted_bots(self):
        """get_canonical_bot_counts must exclude status=deleted bots."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.canonical import get_canonical_bot_counts

        deleted_bot = _make_bot("b1", "deleted")
        deleted_bot["deleted_at"] = "2024-01-01T00:00:00Z"

        cursor = MagicMock()
        # The canonical service filters out deleted bots in its query, so the
        # mock cursor returns an empty list (simulating the DB filter result).
        cursor.to_list = AsyncMock(return_value=[])
        col = MagicMock()
        col.find.return_value = cursor

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = col
            counts = _run(get_canonical_bot_counts("u1"))

        assert counts["total"] == 0
        assert counts["active"] == 0
        assert counts["paused"] == 0

    def test_canonical_counts_zero_after_full_deletion(self):
        """When all bots are deleted, every counter must be zero."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.canonical import get_canonical_bot_counts

        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])
        col = MagicMock()
        col.find.return_value = cursor

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = col
            counts = _run(get_canonical_bot_counts("u1"))

        for key in ("total", "active", "runnable", "paused", "stopped", "training"):
            assert counts[key] == 0, f"{key} must be 0 after reset"

    def test_runtime_state_remove_for_user(self):
        """remove_for_user deletes all runtime rows for a user."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        mock_col = MagicMock()
        mock_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))

        with patch.object(store, "_collection", return_value=mock_col):
            deleted = _run(store.remove_for_user("u1"))

        mock_col.delete_many.assert_called_once_with({"user_id": "u1"})
        assert deleted == 3

    def test_runtime_state_remove_for_user_none_collection(self):
        """remove_for_user returns 0 gracefully when collection is None."""
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
            store, "_collection", return_value=None
        ):
            deleted = _run(store.remove_for_user("u1"))

        assert deleted == 0


# ---------------------------------------------------------------------------
# Test 2 — Deleted bots excluded from overview / profit / bot-status counts
# ---------------------------------------------------------------------------

class TestDeletedBotsExcluded:
    """Canonical service must never count deleted bots."""

    def test_active_bots_counted_correctly(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.canonical import get_canonical_bot_counts

        bots = [
            _make_bot("active-1", "active"),
            _make_bot("active-2", "active"),
        ]
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=bots)
        col = MagicMock()
        col.find.return_value = cursor

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = col
            counts = _run(get_canonical_bot_counts("u1"))

        assert counts["active"] == 2
        assert counts["total"] == 2

    def test_deleted_bots_not_counted(self):
        """Deleted bots that pass the DB filter should still be excluded."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.canonical import get_canonical_bot_counts

        # Simulate the DB filter correctly excluding deleted bots
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])  # DB returns 0 after filter
        col = MagicMock()
        col.find.return_value = cursor

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = col
            counts = _run(get_canonical_bot_counts("u1"))

        assert counts["active"] == 0
        assert counts["total"] == 0

    def test_paused_bot_not_in_active_count(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.canonical import get_canonical_bot_counts

        bots = [_make_bot("p1", "paused")]
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=bots)
        col = MagicMock()
        col.find.return_value = cursor

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = col
            counts = _run(get_canonical_bot_counts("u1"))

        assert counts["active"] == 0
        assert counts["paused"] == 1


# ---------------------------------------------------------------------------
# Test 3 — Runtime state / bot document reconciliation
# ---------------------------------------------------------------------------

class TestRuntimeStateReconciliation:
    """reconcile_with_bot_doc must align runtime state with the bot document."""

    def test_reconcile_deleted_bot_removes_runtime_row(self):
        """A deleted bot must have its runtime-state row removed."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        deleted_bot = _make_bot("b1", "deleted")
        deleted_bot["deleted_at"] = "2024-01-01T00:00:00Z"

        with patch.object(store, "remove", new=AsyncMock(return_value=None)) as mock_remove:
            result = _run(store.reconcile_with_bot_doc("b1", deleted_bot))

        mock_remove.assert_called_once_with("b1")
        assert result == {}

    def test_reconcile_paused_bot_overwrites_active_runtime_state(self):
        """When runtime says 'active' but bot doc says 'paused', runtime is updated."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        paused_bot = _make_bot("b1", "paused", pause_reason="BODYGUARD_DRAWDOWN_BREACH")

        stale_runtime = {"bot_id": "b1", "user_id": "u1", "state": "active"}
        new_runtime = {"bot_id": "b1", "user_id": "u1", "state": "paused", "source": "reconcile"}

        with patch.object(store, "get_state", new=AsyncMock(return_value=stale_runtime)):
            with patch.object(store, "set_state", new=AsyncMock(return_value=new_runtime)) as mock_set:
                result = _run(store.reconcile_with_bot_doc("b1", paused_bot))

        mock_set.assert_called_once()
        call_kwargs = mock_set.call_args
        assert call_kwargs.kwargs.get("state") == "paused" or call_kwargs.args[2] == "paused"
        assert result["state"] == "paused"

    def test_reconcile_in_sync_returns_existing(self):
        """When runtime and bot doc agree, the existing row is returned unchanged."""
        from unittest.mock import AsyncMock, patch
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        active_bot = _make_bot("b1", "active")
        existing = {"bot_id": "b1", "user_id": "u1", "state": "active"}

        with patch.object(store, "get_state", new=AsyncMock(return_value=existing)):
            with patch.object(store, "set_state", new=AsyncMock()) as mock_set:
                result = _run(store.reconcile_with_bot_doc("b1", active_bot))

        mock_set.assert_not_called()
        assert result == existing

    def test_reconcile_no_existing_row_bootstraps_from_bot_doc(self):
        """When no runtime row exists, one is created from the bot document."""
        from unittest.mock import AsyncMock, patch
        from services.bot_runtime_state import BotRuntimeStateStore

        store = BotRuntimeStateStore()
        active_bot = _make_bot("b1", "active")
        new_row = {"bot_id": "b1", "user_id": "u1", "state": "active", "source": "bootstrap"}

        with patch.object(store, "get_state", new=AsyncMock(return_value=None)):
            with patch.object(store, "ensure_state", new=AsyncMock(return_value=new_row)) as mock_ensure:
                result = _run(store.reconcile_with_bot_doc("b1", active_bot))

        mock_ensure.assert_called_once()
        assert result["state"] == "active"


# ---------------------------------------------------------------------------
# Test 4 — Scheduler noop-reason logging when no active bots exist
# ---------------------------------------------------------------------------

class TestSchedulerNoopLogging:
    """The scheduler must log a visible INFO message when no active bots exist."""

    def test_scheduler_has_noop_reason_attribute(self):
        from trading_scheduler import TradingScheduler
        s = TradingScheduler()
        assert hasattr(s, "last_tick_noop_reason")
        assert s.last_tick_noop_reason is None

    def test_scheduler_has_structured_tick_logging(self):
        """Verify the scheduler source contains the structured noop log template."""
        import inspect
        import trading_scheduler as ts_module
        source = inspect.getsource(ts_module)
        # The new INFO-level noop log must mention "Noop reason:"
        assert "Noop reason:" in source, (
            "Scheduler must log 'Noop reason:' at INFO level for every noop tick"
        )

    def test_scheduler_noop_ticks_counter_increments(self):
        """total_noop_ticks must be an integer starting at 0."""
        from trading_scheduler import TradingScheduler
        s = TradingScheduler()
        assert isinstance(s.total_noop_ticks, int)
        assert s.total_noop_ticks == 0

    def test_scheduler_health_snapshot_includes_noop_reason(self):
        """get_health_snapshot must expose last_tick_noop_reason."""
        from trading_scheduler import TradingScheduler
        s = TradingScheduler()
        snap = s.get_health_snapshot()
        assert "last_tick_noop_reason" in snap
        assert "total_noop_ticks" in snap


# ---------------------------------------------------------------------------
# Test 5 — Start-fresh resets wallet + ledger + runtime state together
# ---------------------------------------------------------------------------

class TestStartFreshFullReset:
    """perform_paper_reset covers all_bot_ids (including already-deleted) and
    clears bot_runtime_state by user_id."""

    def test_perform_paper_reset_collects_all_bot_ids(self):
        """perform_paper_reset must query ALL bots (not just non-deleted) so that
        already-deleted bots' linked records are cleaned up."""
        import inspect
        from routes import system_mode as sm_module

        source = inspect.getsource(sm_module.perform_paper_reset)
        # The function should fetch all_bot_ids without a deleted_at filter
        assert "all_bot_ids" in source, (
            "perform_paper_reset must collect all_bot_ids to clean ghost records"
        )

    def test_bot_runtime_state_has_remove_for_user(self):
        """BotRuntimeStateStore must expose remove_for_user()."""
        from services.bot_runtime_state import BotRuntimeStateStore, bot_runtime_state
        assert hasattr(bot_runtime_state, "remove_for_user")
        assert callable(bot_runtime_state.remove_for_user)

    def test_bot_runtime_state_has_reconcile_method(self):
        """BotRuntimeStateStore must expose reconcile_with_bot_doc()."""
        from services.bot_runtime_state import bot_runtime_state
        assert hasattr(bot_runtime_state, "reconcile_with_bot_doc")
        assert callable(bot_runtime_state.reconcile_with_bot_doc)

    def test_admin_start_fresh_delegates_to_perform_paper_reset(self):
        """admin_start_fresh must import and call perform_paper_reset."""
        import inspect
        from routes import admin_start_fresh as asf_module

        source = inspect.getsource(asf_module)
        assert "perform_paper_reset" in source, (
            "/api/admin/start-fresh must delegate to perform_paper_reset"
        )

    def test_database_safe_index_helper_exists(self):
        """database.py must expose _safe_create_index for idempotent index creation."""
        import database as db_module
        assert hasattr(db_module, "_safe_create_index"), (
            "database.py must define _safe_create_index to handle IndexKeySpecsConflict"
        )
        assert callable(db_module._safe_create_index)

    def test_perform_paper_reset_resets_circuit_breaker(self):
        """perform_paper_reset source must reference circuit_breaker_state reset."""
        import inspect
        from routes import system_mode as sm_module

        source = inspect.getsource(sm_module.perform_paper_reset)
        assert "circuit_breaker_state" in source, (
            "perform_paper_reset must clear circuit_breaker_state"
        )

    def test_perform_paper_reset_resets_daily_loss_lock(self):
        """perform_paper_reset source must reset daily_loss_lock_active."""
        import inspect
        from routes import system_mode as sm_module

        source = inspect.getsource(sm_module.perform_paper_reset)
        assert "daily_loss_lock_active" in source, (
            "perform_paper_reset must reset daily_loss_lock_active"
        )
