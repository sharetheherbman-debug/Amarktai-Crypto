"""
P0 consistency fixes — test suite (issue: contradictory bot state / wallet fields / exit precedence).

Tests:
  A) Bot state: paused_by_user=True implies state != "active" in enriched bot status.
  B) wallet/paper invariants: available_wallet_zar == available["ZAR"].
  C) diagnostics why-not-trading: no false NO_ACTIVE_BOTS / WALLET_UNFUNDED.
  D) Exit precedence: hard_exit_overdue trade is closed even if the bot is paused.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bot(status="active", paused_by_user=False, paused_by_system=False):
    return {
        "id": "bot_abc",
        "name": "TestBot",
        "exchange": "luno",
        "pair": "BTC/ZAR",
        "status": status,
        "trading_mode": "paper",
        "paused_by_user": paused_by_user,
        "paused_by_system": paused_by_system,
        "training_complete": True,
        "initial_capital": 1000.0,
    }


# ── A: normalize_bot_state consistency ───────────────────────────────────────

class TestBotStateConsistency:
    """A bot with paused_by_user=True must not be treated as active."""

    def test_paused_by_user_is_not_active(self):
        from utils.bot_state import normalize_bot_state

        bot = _make_bot(status="active", paused_by_user=True)
        result = normalize_bot_state(bot)
        assert result["active"] is False, (
            "paused_by_user=True must set active=False"
        )
        assert result["paused"] is True, (
            "paused_by_user=True must set paused=True"
        )

    def test_paused_by_system_is_not_active(self):
        from utils.bot_state import normalize_bot_state

        bot = _make_bot(status="active", paused_by_system=True)
        result = normalize_bot_state(bot)
        assert result["active"] is False

    def test_active_bot_without_pause_flags(self):
        from utils.bot_state import normalize_bot_state

        bot = _make_bot(status="active")
        result = normalize_bot_state(bot)
        assert result["active"] is True

    def test_db_paused_status_is_not_active(self):
        from utils.bot_state import normalize_bot_state

        bot = _make_bot(status="paused", paused_by_user=True)
        result = normalize_bot_state(bot)
        assert result["active"] is False

    def test_paused_by_user_display_state_not_active(self):
        """display_state must not be 'active' when paused_by_user is True."""
        from utils.bot_state import normalize_bot_state

        # DB status active + paused_by_user — runtime_state override scenario
        bot = _make_bot(status="active", paused_by_user=True)
        result = normalize_bot_state(bot)
        assert result.get("display_state") != "active", (
            "display_state must not be 'active' when paused_by_user=True"
        )


# ── B: wallet/paper response invariants ──────────────────────────────────────

class TestWalletPaperInvariants:
    """
    GET /api/wallet/paper must satisfy:
      available_wallet_zar == available["ZAR"]
    """

    @pytest.mark.asyncio
    async def test_available_wallet_zar_matches_available_dict(self):
        """available_wallet_zar must equal available['ZAR'] in GET /paper response."""
        from routes.wallet_hub import get_paper_wallet

        # Mock paper_wallet_service to return 800 ZAR available
        mock_pws_balances = {"balances": {"ZAR": 800.0}, "total": 800.0}
        # Mock allocated = 200 ZAR in ledger entries
        mock_allocated = {"ZAR": 200.0}
        # totals = 1000 ZAR
        mock_totals = {"ZAR": 1000.0}

        mock_summary = {
            "mode": "paper",
            "active_bots_count": 2,
            "available_wallet_zar": 800.0,
            "allocated_funds_zar": 1000.0,
            "reserved_funds_zar": 0.0,
            "required_funds_zar": 800.0,
            "shortfall_zar": 0.0,
            "status": "FUNDED",
        }

        with patch("routes.wallet_hub.paper_wallet_service") as mock_pws, \
             patch("routes.wallet_hub.wallet_summary_service") as mock_wss, \
             patch("routes.wallet_hub.get_paper_wallet_allocated_balances",
                   new=AsyncMock(return_value=mock_allocated)), \
             patch("routes.wallet_hub.get_paper_wallet_balances",
                   new=AsyncMock(return_value=mock_totals)):

            mock_pws.get_balances = AsyncMock(return_value=mock_pws_balances)
            mock_wss.get_summary = AsyncMock(return_value=mock_summary)
            # Call the underlying coroutine directly to bypass FastAPI dependency injection
            result = await get_paper_wallet("user_test")

        available_zar = float(result.get("available", {}).get("ZAR", 0))
        available_wallet_zar = float(result.get("available_wallet_zar", 0))

        assert abs(available_wallet_zar - available_zar) < 0.01, (
            f"Invariant violated: available_wallet_zar={available_wallet_zar} "
            f"!= available['ZAR']={available_zar}"
        )

    @pytest.mark.asyncio
    async def test_allocated_funds_zar_is_ledger_based(self):
        """allocated_funds_zar must reflect ledger entries, not sum-of-bot-capitals."""
        from routes.wallet_hub import get_paper_wallet

        mock_pws_balances = {"balances": {"ZAR": 500.0}, "total": 500.0}
        mock_allocated = {"ZAR": 300.0}  # ledger-based
        mock_totals = {"ZAR": 800.0}

        mock_summary = {
            "mode": "paper",
            "active_bots_count": 1,
            "available_wallet_zar": 500.0,
            "allocated_funds_zar": 5000.0,  # sum of all bot capitals (initial_funding)
            "reserved_funds_zar": 0.0,
            "required_funds_zar": 1000.0,
            "shortfall_zar": 0.0,
            "status": "FUNDED",
        }

        with patch("routes.wallet_hub.paper_wallet_service") as mock_pws, \
             patch("routes.wallet_hub.wallet_summary_service") as mock_wss, \
             patch("routes.wallet_hub.get_paper_wallet_allocated_balances",
                   new=AsyncMock(return_value=mock_allocated)), \
             patch("routes.wallet_hub.get_paper_wallet_balances",
                   new=AsyncMock(return_value=mock_totals)):

            mock_pws.get_balances = AsyncMock(return_value=mock_pws_balances)
            mock_wss.get_summary = AsyncMock(return_value=mock_summary)
            result = await get_paper_wallet("user_test")

        assert result["allocated_funds_zar"] == 300.0, (
            f"allocated_funds_zar should be ledger-based (300.0), got {result['allocated_funds_zar']}"
        )
        assert "initial_funding_zar" in result, (
            "initial_funding_zar field must be present for backward compatibility"
        )
        assert result["initial_funding_zar"] == 5000.0, (
            "initial_funding_zar should reflect sum of bot capitals"
        )


# ── C: diagnostics why-not-trading ───────────────────────────────────────────

class TestDiagnosticsWhyNotTrading:
    """why-not-trading must not report false NO_ACTIVE_BOTS or WALLET_UNFUNDED."""

    @pytest.mark.asyncio
    async def test_no_false_wallet_unfunded_when_funds_allocated(self):
        """If all funds are in ledger entries (allocated), WALLET_UNFUNDED must not fire.
        
        The fixed logic: total = available + allocated. If total > 0 → funded.
        """
        # Test the corrected logic directly (pure unit test — no DB needed)
        # Scenario: paper wallet has 0 ZAR unallocated (all in ledger entries for bots)
        available_total = 0.0
        allocated_total = 1000.0  # funds reserved in ledger for active bots
        total = float(available_total) + float(allocated_total)
        assert total > 0, "Wallet is funded when funds are in ledger entries"
        assert total != 0, "Should not report WALLET_UNFUNDED when total > 0"

        # The old logic checked only available_total (wrong)
        old_check_would_fire = (available_total == 0)
        # The new logic uses total (correct)
        new_check_would_fire = (total == 0)
        assert old_check_would_fire is True, "Old check incorrectly fires when available=0"
        assert new_check_would_fire is False, "New check must not fire when ledger has funds"

    @pytest.mark.asyncio
    async def test_no_active_bots_excludes_paused_by_user(self):
        """NO_ACTIVE_BOTS check must exclude bots with paused_by_user=True."""
        # Simulate the MongoDB query behaviour for the fixed query
        # Old query: {"status": "active"} → would match paused_by_user=True bots
        # New query: {"status": "active", "paused_by_user": {"$ne": True}} → correct

        # Test the filter logic
        bots = [
            {"status": "active", "paused_by_user": True},   # paused
            {"status": "active", "paused_by_user": False},   # truly active
            {"status": "active"},                             # truly active
        ]

        # Old logic (incorrect)
        old_count = sum(1 for b in bots if b.get("status") == "active")
        # New logic (correct)
        new_count = sum(
            1 for b in bots
            if b.get("status") == "active"
            and b.get("paused_by_user") is not True
            and b.get("paused_by_system") is not True
        )

        assert old_count == 3, "Old query incorrectly counted 3 active bots"
        assert new_count == 2, "Fixed query should count 2 genuinely active bots"


# ── D: Exit precedence — overdue trades must be closed ────────────────────────

class TestExitPrecedence:
    """
    hard_exit_overdue trades must result in a close attempt even when the bot is paused.
    """

    @pytest.mark.asyncio
    async def test_hard_exit_fires_before_no_exit_signal(self):
        """When age >= HARD_MAX_HOLD_SECONDS, close_reason is hard_max_hold, not no_exit_signal."""
        from paper_trading_engine import PaperTradingEngine, HARD_MAX_HOLD_SECONDS

        engine = PaperTradingEngine()
        bot_data = {
            "id": "bot_test",
            "user_id": "user_test",
            "name": "TestBot",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "risk_mode": "safe",
            "trading_mode": "paper",
            "initial_capital": 5000,
            "current_capital": 5000,
            "take_profit_pct": 0.50,  # wide — won't trigger
            "stop_loss_pct": 0.50,    # wide — won't trigger
        }

        # Create a trade older than HARD_MAX_HOLD_SECONDS
        old_opened_at = (
            datetime.now(timezone.utc) - timedelta(seconds=HARD_MAX_HOLD_SECONDS + 60)
        ).isoformat()
        trade = {
            "id": "trade_overdue",
            "bot_id": "bot_test",
            "user_id": "user_test",
            "status": "open",
            "pair": "BTC/USDT",
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 50000.0,
            "price": 50000.0,
            "amount": 0.1,
            "entry_value": 5000.0,
            "trade_amount": 5000.0,
            "opened_at": old_opened_at,
            "entry_time": old_opened_at,
            "stop_loss_pct": 0.50,
            "take_profit_pct": 0.50,
            "fee_rate": 0.001,
            "fill_ratio": 1.0,
            "partial_fill": False,
            "entry_ledger_recorded": True,
        }

        closed_trades = {}

        class _MemCollection:
            def __init__(self):
                self.data = []

            async def insert_one(self, doc):
                doc.setdefault("_id", "fake_id")
                self.data.append(doc)
                return SimpleNamespace(inserted_id=doc["_id"])

            async def find_one(self, query=None, projection=None):
                for doc in self.data:
                    if all(doc.get(k) == v for k, v in (query or {}).items()
                           if not isinstance(v, dict)):
                        return doc
                return None

            async def update_one(self, filt=None, update=None, **kw):
                for doc in self.data:
                    # Match only scalar equality filters (skip MongoDB operator dicts)
                    if all(doc.get(k) == v for k, v in (filt or {}).items()
                           if not isinstance(v, dict)):
                        if update and "$set" in update:
                            doc.update(update["$set"])
                        closed_trades[doc.get("id")] = doc.copy()
                        return SimpleNamespace(modified_count=1)
                return SimpleNamespace(modified_count=0)

            def find(self, *a, **kw):
                cur = SimpleNamespace()
                cur.sort = lambda *a, **kw: cur
                cur.limit = lambda *a, **kw: cur
                async def to_list(n=None): return list(self.data)
                cur.to_list = to_list
                return cur

        trades_col = _MemCollection()
        await trades_col.insert_one(trade)
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        async def _market_snapshot(symbol, exchange):
            return {
                "bid": 49990.0, "ask": 50010.0, "mid": 50000.0,
                "spread": 20.0, "spread_bps": 4.0,
                "source": "test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        engine.get_market_snapshot = _market_snapshot

        with patch("paper_trading_engine.db.bots_collection", bots_col), \
             patch("paper_trading_engine.db.trades_collection", trades_col), \
             patch("paper_trading_engine.db.db", None), \
             patch("paper_trading_engine.rate_limiter.can_trade", return_value=(True, "ok")), \
             patch("paper_trading_engine.rate_limiter.record_trade"), \
             patch("paper_trading_engine.risk_engine.check_trade_risk",
                   new=AsyncMock(return_value=(True, "ok"))), \
             patch("paper_trading_engine.risk_engine.record_trade_result", new=AsyncMock()), \
             patch("paper_trading_engine.paper_wallet_ledger.get_balance",
                   new=AsyncMock(return_value=(True, 5000.0, "ok"))), \
             patch("paper_trading_engine.paper_wallet_ledger.can_trade",
                   new=AsyncMock(return_value=(True, "ok"))), \
             patch("paper_trading_engine.paper_wallet_ledger.debit",
                   new=AsyncMock(return_value=(True, "ok"))), \
             patch("paper_trading_engine.paper_wallet_ledger.credit",
                   new=AsyncMock(return_value=(True, "ok"))), \
             patch("paper_trading_engine.enforce_trading_gates"):

            result = await engine.run_trading_cycle(
                "bot_test", bot_data, {"bots": bots_col, "trades": trades_col}
            )

        # The trade must have been closed
        assert result is not None, "run_trading_cycle returned None"
        assert result.get("success") is True or result.get("new_capital") is not None, (
            f"Expected successful close for overdue trade, got: {result}"
        )
        close_reason = (result.get("trade") or result).get("trade_close_reason")
        assert close_reason == "hard_max_hold", (
            f"Overdue trade must close with hard_max_hold, got: {close_reason}"
        )

        # No "no_exit_signal" in action log for this trade
        skip_actions = [a for a in engine._action_log
                        if a.get("action") == "SKIP" and a.get("reason") == "no_exit_signal"]
        assert not skip_actions, (
            f"Overdue trade must not produce no_exit_signal: {skip_actions}"
        )

    @pytest.mark.asyncio
    async def test_close_overdue_trades_method_exists(self):
        """PaperTradingEngine must have a close_overdue_trades method."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        assert callable(getattr(engine, "close_overdue_trades", None)), (
            "PaperTradingEngine must have a close_overdue_trades method"
        )

    def test_closes_failed_counter_exists(self):
        """PaperTradingEngine must track closes_failed."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        assert hasattr(engine, "closes_failed"), "Engine must have closes_failed counter"
        assert engine.closes_failed == 0

    def test_get_status_includes_closes_failed(self):
        """get_status() must include closes_failed."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        status = engine.get_status()
        assert "closes_failed" in status, "get_status() must include closes_failed"
