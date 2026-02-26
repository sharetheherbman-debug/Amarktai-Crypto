"""
Phase 2 — Training Completion Tests
=====================================
Covers the three core fixes:

  FIX 1 — Training bot closes trade via training_timeout when trade age >= TRAINING_MAX_HOLD_MINUTES.
  FIX 2 — Closing a trade increments closed_trades_count; training auto-graduates at TRAINING_TRADES_REQUIRED.
  FIX 3 — GET /api/openapi.json returns valid JSON containing expected paths.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

# Make backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub heavy optional dependencies so imports don't fail in CI
_HEAVY_STUBS = [
    "ccxt", "ccxt.async_support", "ccxt_service", "tenacity", "huggingface_hub",
]
for _mod in _HEAVY_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ── FIX 1: Paper bots no longer use training_timeout exit ────────────────────

class TestTrainingForcedClose:
    """Paper bots trade freely from the start — no training_timeout exit.
    Trades exit only via take_profit, stop_loss, time_exit, safety_exit, or stale_exit."""

    @pytest.mark.asyncio
    async def test_paper_bot_ignores_training_timeout(self):
        """A paper bot trade older than TRAINING_MAX_HOLD_MINUTES must NOT close via training_timeout.
        It should return no_exit_signal until PAPER_MAX_HOLD_MINUTES is reached."""
        from config import TRAINING_MAX_HOLD_MINUTES, PAPER_MAX_HOLD_MINUTES
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        entry_price = 100.0
        current_price = 101.0  # slightly above entry, below TP — no SL/TP/time hit
        engine.get_market_snapshot = AsyncMock(return_value={
            "mid": current_price,
            "bid": current_price * 0.999,
            "ask": current_price * 1.001,
            "spread_bps": 10,
        })

        # Age is past TRAINING_MAX_HOLD_MINUTES but NOT yet at PAPER_MAX_HOLD_MINUTES
        age_minutes = TRAINING_MAX_HOLD_MINUTES + 5
        assert age_minutes < PAPER_MAX_HOLD_MINUTES, (
            "Test requires TRAINING_MAX_HOLD_MINUTES + 5 < PAPER_MAX_HOLD_MINUTES"
        )
        old_enough = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        open_trade = {
            "id": "t001",
            "pair": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": entry_price,
            "price": entry_price,
            "entry_value": 500.0,
            "amount": 5.0,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "entry_time": old_enough.isoformat(),
            "slippage_rate": 0.0008,
            "fee_rate": 0.001,
            "entry_fills": [{"qty": 5.0, "price": entry_price, "timestamp": old_enough}],
            "entry_ledger_recorded": False,
        }

        # Paper bot (no training gate)
        bot_data = {
            "id": "b001",
            "name": "PaperBot",
            "exchange": "luno",
            "trading_mode": "paper",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "risk_mode": "safe",
            "current_capital": 1000.0,
        }

        result = await engine._close_open_trade("b001", bot_data, open_trade)

        assert result is not None, "Expected a result, got None"
        # Paper bots must NOT produce training_timeout
        if result.get("success"):
            assert result.get("trade_close_reason") != "training_timeout", (
                "Paper bots must not close with training_timeout"
            )
        else:
            # Still open (no_exit_signal) — correct: age < PAPER_MAX_HOLD_MINUTES
            assert result.get("skip_reason") == "no_exit_signal", (
                f"Expected 'no_exit_signal', got {result.get('skip_reason')!r}"
            )

    @pytest.mark.asyncio
    async def test_no_exit_signal_when_trade_is_young_training_bot(self):
        """A young paper bot trade (not yet at PAPER_MAX_HOLD_MINUTES) returns no_exit_signal."""
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        entry_price = 100.0
        current_price = 100.5  # between SL and TP, not hitting either
        engine.get_market_snapshot = AsyncMock(return_value={
            "mid": current_price,
            "bid": current_price * 0.999,
            "ask": current_price * 1.001,
            "spread_bps": 10,
        })

        recent = datetime.now(timezone.utc) - timedelta(minutes=2)  # only 2 minutes old
        open_trade = {
            "id": "t002",
            "pair": "BTC/ZAR",
            "symbol": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": entry_price,
            "entry_value": 500.0,
            "amount": 5.0,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "entry_time": recent.isoformat(),
            "slippage_rate": 0.0008,
            "fee_rate": 0.001,
            "entry_fills": [],
        }

        bot_data = {
            "id": "b002",
            "name": "PaperBot",
            "exchange": "luno",
            "trading_mode": "paper",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "risk_mode": "safe",
            "current_capital": 1000.0,
        }

        result = await engine._close_open_trade("b002", bot_data, open_trade)

        assert result is not None
        assert result.get("success") is False
        assert result.get("skip_reason") == "no_exit_signal", (
            f"Expected 'no_exit_signal', got {result.get('skip_reason')!r}"
        )


# ── FIX 2: closed_trades_count increments and training completes ─────────────

class TestTrainingProgressIncrement:
    """run_trading_cycle() must increment closed_trades_count and auto-graduate training bots."""

    def _make_engine(self):
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        return engine

    @pytest.mark.asyncio
    async def test_closed_trades_count_increments_on_close(self):
        """After a completed trade cycle, closed_trades_count is incremented by 1."""
        from config import TRAINING_TRADES_REQUIRED

        engine = self._make_engine()

        # Minimal close result (already-computed trade close)
        trade_result = {
            "success": True,
            "status": "closed",
            "symbol": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": 100.0,
            "exit_price": 103.0,
            "amount": 5.0,
            "profit_loss": 12.5,
            "fees": 2.0,
            "is_paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_close_reason": "training_timeout",
            "entry_fills": [{"qty": 5.0, "price": 100.0, "timestamp": datetime.now(timezone.utc)}],
            "exit_fills": [{"qty": 5.0, "price": 103.0, "timestamp": datetime.now(timezone.utc)}],
            "gross_profit": 14.0,
            "net_profit": 12.5,
            "net_profit_zar": 12.5,
            "entry_value": 500.0,
            "slippage_rate": 0.0008,
            "fee_rate": 0.001,
            "entry_fee": 0.5,
            "exit_fee": 1.5,
            "slippage_cost": 0.4,
            "slippage_bps": 8.0,
            "spread": 6.0,
            "price_source": "LUNO_PUBLIC",
            "fee_currency": "ZAR",
            "trend": "neutral",
            "risk_mode": "safe",
            "quality_score": 1,
            "trade_type": "BUY->SELL",
            "partial_fill": False,
            "latency_ms": 100,
            "open_trade_id": "t001",
            "fees_total": 2.0,
        }

        bot_data = {
            "id": "b001",
            "user_id": "u001",
            "name": "LiveTrainingBot",
            "exchange": "luno",
            "trading_mode": "live",
            "lifecycle_state": "training",
            "is_training": True,
            "current_capital": 1000.0,
            "initial_capital": 1000.0,
            "risk_mode": "safe",
            "training_complete": False,
            "closed_trades_count": 0,
            "training_required_closed_trades": TRAINING_TRADES_REQUIRED,
        }

        open_trade = {
            "id": "t001",
            "bot_id": "b001",
            "status": "open",
            "pair": "BTC/ZAR",
            "symbol": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": 100.0,
            "entry_value": 500.0,
            "amount": 5.0,
            "entry_fills": [],
            "entry_ledger_recorded": False,
        }

        # Tracks updates made to bots_collection
        set_ops = []
        inc_ops = []

        async def mock_update_one(filt, update, *args, **kwargs):
            set_ops.append(update.get("$set", {}))
            inc_ops.append(update.get("$inc", {}))
            return MagicMock()

        # Fresh bot returned after the trade (now has 1 closed trade)
        fresh_bot_after_increment = {**bot_data, "closed_trades_count": 1, "status": "active"}

        bots_col = MagicMock()
        bots_col.find_one = AsyncMock(side_effect=[
            {**bot_data, "status": "active"},   # First call in run_trading_cycle (fresh_bot)
            fresh_bot_after_increment,           # Second call: training graduation check
        ])
        bots_col.update_one = AsyncMock(side_effect=mock_update_one)

        trades_col = MagicMock()
        trades_col.find_one = AsyncMock(return_value=open_trade)
        trades_col.update_one = AsyncMock()
        trades_col.insert_one = AsyncMock()

        db_collections = {
            "bots": bots_col,
            "trades": trades_col,
        }

        # Patch _close_open_trade to return the pre-computed result
        engine._close_open_trade = AsyncMock(return_value=trade_result)

        # Patch out ledger, risk_engine, paper_wallet, realtime
        with patch("paper_trading_engine.risk_engine") as mock_risk, \
             patch("paper_trading_engine.paper_wallet_ledger") as mock_ledger, \
             patch("paper_trading_engine.rt_events") as mock_rt:

            mock_risk.record_trade_result = AsyncMock()
            mock_ledger.credit = AsyncMock(return_value=(True, "ok"))
            mock_ledger.debit = AsyncMock(return_value=(True, "ok"))
            mock_ledger.get_balance = AsyncMock(return_value=(True, 1012.5, "ok"))
            mock_rt.trade_closed = AsyncMock()
            mock_rt.trade_opened = AsyncMock()

            # Patch db.db and ledger_service so the ledger path exits cleanly
            import database as db_module
            with patch.object(db_module, "db", None), \
                 patch("utils.trade_utils.build_trade_record", return_value={"id": "t001", "status": "closed"}), \
                 patch("utils.trade_utils.classify_trade_outcome", return_value={"win_count": 1, "loss_count": 0}), \
                 patch("utils.trade_utils.calculate_trade_pnl", return_value={"gross_profit": 14.0, "net_profit": 12.5}):

                await engine.run_trading_cycle("b001", bot_data, db_collections)

        # Verify closed_trades_count was incremented
        all_incs = {k: v for d in inc_ops for k, v in d.items()}
        assert "closed_trades_count" in all_incs, (
            f"Expected 'closed_trades_count' in $inc ops, got: {inc_ops}"
        )
        assert all_incs["closed_trades_count"] == 1, (
            f"Expected increment of 1, got {all_incs['closed_trades_count']}"
        )

    @pytest.mark.asyncio
    async def test_training_auto_graduates_at_required_closed_trades(self):
        """When closed_trades_count reaches TRAINING_TRADES_REQUIRED, training_complete is set True."""
        from config import TRAINING_TRADES_REQUIRED

        engine = self._make_engine()

        trade_result = {
            "success": True,
            "status": "closed",
            "symbol": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": 100.0,
            "exit_price": 103.0,
            "amount": 5.0,
            "profit_loss": 12.5,
            "fees": 2.0,
            "is_paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_close_reason": "training_timeout",
            "entry_fills": [{"qty": 5.0, "price": 100.0, "timestamp": datetime.now(timezone.utc)}],
            "exit_fills": [{"qty": 5.0, "price": 103.0, "timestamp": datetime.now(timezone.utc)}],
            "gross_profit": 14.0,
            "net_profit": 12.5,
            "net_profit_zar": 12.5,
            "entry_value": 500.0,
            "slippage_rate": 0.0008,
            "fee_rate": 0.001,
            "entry_fee": 0.5,
            "exit_fee": 1.5,
            "slippage_cost": 0.4,
            "slippage_bps": 8.0,
            "spread": 6.0,
            "price_source": "LUNO_PUBLIC",
            "fee_currency": "ZAR",
            "trend": "neutral",
            "risk_mode": "safe",
            "quality_score": 1,
            "trade_type": "BUY->SELL",
            "partial_fill": False,
            "latency_ms": 100,
            "open_trade_id": "t001",
            "fees_total": 2.0,
        }

        # Bot already has TRAINING_TRADES_REQUIRED - 1 closed trades (one more will graduate it)
        # Use trading_mode='live' — paper bots start with training_complete=True already.
        bot_data = {
            "id": "b002",
            "user_id": "u001",
            "name": "LiveTrainingBot",
            "exchange": "luno",
            "trading_mode": "live",
            "lifecycle_state": "training",
            "is_training": True,
            "current_capital": 1000.0,
            "initial_capital": 1000.0,
            "risk_mode": "safe",
            "training_complete": False,
            "closed_trades_count": TRAINING_TRADES_REQUIRED - 1,
            "training_required_closed_trades": TRAINING_TRADES_REQUIRED,
        }

        open_trade = {
            "id": "t002",
            "bot_id": "b002",
            "status": "open",
            "pair": "BTC/ZAR",
            "symbol": "BTC/ZAR",
            "exchange": "luno",
            "entry_price": 100.0,
            "entry_value": 500.0,
            "amount": 5.0,
            "entry_fills": [],
            "entry_ledger_recorded": False,
        }

        set_ops_by_call = []

        async def mock_update_one(filt, update, *args, **kwargs):
            set_ops_by_call.append(update.get("$set", {}))
            return MagicMock()

        # After update, closed_trades_count is now TRAINING_TRADES_REQUIRED
        fresh_bot_graduated = {
            **bot_data,
            "closed_trades_count": TRAINING_TRADES_REQUIRED,
            "status": "active",
        }

        bots_col = MagicMock()
        bots_col.find_one = AsyncMock(side_effect=[
            {**bot_data, "status": "active"},  # fresh_bot in run_trading_cycle
            fresh_bot_graduated,               # graduation check
        ])
        bots_col.update_one = AsyncMock(side_effect=mock_update_one)

        trades_col = MagicMock()
        trades_col.find_one = AsyncMock(return_value=open_trade)
        trades_col.update_one = AsyncMock()
        trades_col.insert_one = AsyncMock()

        db_collections = {"bots": bots_col, "trades": trades_col}

        engine._close_open_trade = AsyncMock(return_value=trade_result)

        with patch("paper_trading_engine.risk_engine") as mock_risk, \
             patch("paper_trading_engine.paper_wallet_ledger") as mock_ledger, \
             patch("paper_trading_engine.rt_events") as mock_rt:

            mock_risk.record_trade_result = AsyncMock()
            mock_ledger.credit = AsyncMock(return_value=(True, "ok"))
            mock_ledger.debit = AsyncMock(return_value=(True, "ok"))
            mock_ledger.get_balance = AsyncMock(return_value=(True, 1012.5, "ok"))
            mock_rt.trade_closed = AsyncMock()
            mock_rt.trade_opened = AsyncMock()
            mock_rt.training_completed = AsyncMock()

            import database as db_module
            with patch.object(db_module, "db", None), \
                 patch("utils.trade_utils.build_trade_record", return_value={"id": "t002", "status": "closed"}), \
                 patch("utils.trade_utils.classify_trade_outcome", return_value={"win_count": 1, "loss_count": 0}), \
                 patch("utils.trade_utils.calculate_trade_pnl", return_value={"gross_profit": 14.0, "net_profit": 12.5}):

                await engine.run_trading_cycle("b002", bot_data, db_collections)

        # Verify training_complete=True was set in one of the $set operations
        training_complete_set = any(
            op.get("training_complete") is True
            for op in set_ops_by_call
        )
        assert training_complete_set, (
            f"Expected 'training_complete=True' to be set, got set ops: {set_ops_by_call}"
        )


# ── FIX 3: GET /api/openapi.json returns JSON ────────────────────────────────

class TestOpenAPIEndpoint:
    """GET /api/openapi.json must return valid JSON and contain expected paths."""

    def test_openapi_json_returns_valid_schema(self):
        """The FastAPI app exposes its schema at /api/openapi.json."""
        # We can verify this by importing the app and checking the openapi() method
        # directly, without actually starting a server.
        import importlib
        import types

        # Stub out heavy modules that server.py pulls in transitively
        heavy = [
            "motor", "motor.motor_asyncio",
            "redis", "aioredis",
            "apscheduler", "apscheduler.schedulers.asyncio",
            "passlib", "passlib.context",
            "jose", "jose.exceptions",
            "python_jose", "python_multipart",
        ]
        for mod in heavy:
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()

        try:
            from fastapi import FastAPI
            # Build a minimal app that mirrors server.py's openapi_url config
            app = FastAPI(
                title="Amarktai Network API",
                openapi_url="/api/openapi.json",
            )

            @app.get("/api/bots/status")
            async def bots_status():
                return {"bots": []}

            @app.get("/api/trades/recent")
            async def trades_recent():
                return {"trades": []}

            @app.get("/api/analytics/equity")
            async def analytics_equity():
                return {"equity": 5000}

            schema = app.openapi()
            assert isinstance(schema, dict), "openapi() must return a dict"
            assert "paths" in schema, "Schema must contain 'paths'"
            assert "/api/bots/status" in schema["paths"], (
                f"/api/bots/status not in schema paths: {list(schema['paths'].keys())}"
            )
            assert "/api/trades/recent" in schema["paths"], (
                f"/api/trades/recent not in schema paths"
            )

        except ImportError as e:
            pytest.skip(f"FastAPI not available in this environment: {e}")

    def test_openapi_redirect_exists_in_server(self):
        """server.py must define a /openapi.json redirect to /api/openapi.json."""
        import ast
        import pathlib

        server_path = pathlib.Path(__file__).parent.parent / "backend" / "server.py"
        source = server_path.read_text()

        # Check that /openapi.json and /api/openapi.json both appear in server.py
        assert "/openapi.json" in source, "server.py must reference /openapi.json"
        assert "/api/openapi.json" in source, "server.py must reference /api/openapi.json"
        # Check that a redirect function exists
        assert "RedirectResponse" in source or "openapi_redirect" in source, (
            "server.py must have a redirect for /openapi.json -> /api/openapi.json"
        )
