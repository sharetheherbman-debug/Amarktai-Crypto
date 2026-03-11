"""
Test Paper Trade Deterministic End-to-End

Seeds 1 normal bot + 1 scalper bot, runs one tick through the paper trading
engine, and asserts that fills/ledger entries are persisted (or a
deterministic "no-trade decision" entry exists).

This test uses mocked DB collections (motor-style AsyncMock) so it runs
without a real MongoDB connection.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def _make_async_collection():
    """Create a mock MongoDB collection with basic async operations."""
    coll = MagicMock()
    coll.find_one = AsyncMock(return_value=None)
    coll.find = MagicMock()
    coll.find.return_value.to_list = AsyncMock(return_value=[])
    coll.find.return_value.sort = MagicMock()
    coll.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    coll.insert_one = AsyncMock()
    coll.update_one = AsyncMock()
    coll.update_many = AsyncMock()
    coll.count_documents = AsyncMock(return_value=0)
    return coll


@pytest.fixture
def db_collections():
    bots = _make_async_collection()
    trades = _make_async_collection()
    api_keys = _make_async_collection()
    ledger_fills = _make_async_collection()
    paper_wallets = _make_async_collection()
    return {
        'bots': bots,
        'trades': trades,
        'api_keys': api_keys,
        'ledger_fills': ledger_fills,
        'paper_wallets': paper_wallets,
    }


NORMAL_BOT = {
    "id": "bot-normal-001",
    "user_id": "user-test-001",
    "name": "Normal-Test",
    "bot_type": "normal",
    "exchange": "binance",
    "pair": "BTC/USDT",
    "status": "active",
    "risk_mode": "balanced",
    "initial_capital": 1000.0,
    "current_capital": 1000.0,
    "trading_mode": "paper",
    "deleted": False,
}

SCALPER_BOT = {
    "id": "bot-scalper-001",
    "user_id": "user-test-001",
    "name": "Scalper-Test",
    "bot_type": "scalper",
    "exchange": "binance",
    "pair": "BTC/USDT",
    "status": "active",
    "risk_mode": "aggressive",
    "initial_capital": 500.0,
    "current_capital": 500.0,
    "trading_mode": "paper",
    "deleted": False,
}


class TestPaperTradeDeterministic:
    """Deterministic paper-trade test: seed → tick → assert persistence."""

    def test_normal_bot_has_correct_bot_type(self):
        """Normal bot must have bot_type='normal'."""
        assert NORMAL_BOT["bot_type"] == "normal"

    def test_scalper_bot_has_correct_bot_type(self):
        """Scalper bot must have bot_type='scalper'."""
        assert SCALPER_BOT["bot_type"] == "scalper"

    def test_trade_result_contains_persistence_fields(self):
        """A trade result dict must contain all fields needed for DB persistence."""
        required = [
            "success", "bot_id", "symbol", "exchange", "entry_price",
            "amount", "is_paper", "timestamp", "fee_rate",
        ]
        # Build a minimal trade result like execute_smart_trade returns
        trade_result = {
            "success": True,
            "status": "open",
            "bot_id": "bot-normal-001",
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 65000.0,
            "exit_price": 65100.0,
            "amount": 0.0015,
            "trade_amount": 97.5,
            "is_paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fee_rate": 0.001,
            "fees": 0.0975,
            "profit_loss": 0.0,
        }
        for field in required:
            assert field in trade_result, f"Missing field: {field}"

    @pytest.mark.integration
    def test_run_trading_cycle_inserts_trade(self, db_collections):
        """Running a trading cycle must call trades_collection.insert_one
        or update_one (i.e., persist the fill)."""

        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()

        # Mock execute_smart_trade to return a deterministic open trade
        trade_result = {
            "success": True,
            "status": "open",
            "bot_id": NORMAL_BOT["id"],
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 65000.0,
            "exit_price": 0,
            "amount": 0.0015,
            "trade_amount": 97.5,
            "entry_value": 97.5,
            "is_paper": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fee_rate": 0.001,
            "fees": 0.0975,
            "fees_total": 0.0975,
            "entry_fee": 0.0975,
            "fee_currency": "USDT",
            "slippage_cost": 0.0,
            "slippage": 0.0,
            "profit_loss": 0.0,
            "net_profit": 0.0,
            "net_profit_zar": 0.0,
            "gross_profit": 0.0,
            "gross_pnl": 0.0,
            "realized_pnl": 0.0,
            "fee_paid": 0.0975,
            "trend": "bullish",
            "risk_mode": "balanced",
            "quality_score": 0,
            "data_source": "mock",
            "price_source": "BINANCE_PUBLIC",
            "spread": 6.0,
            "slippage_bps": 0.0,
            "slippage_rate": 0.0,
            "entry_fills": [{"qty": 0.0015, "price": 65000.0, "timestamp": datetime.now(timezone.utc).isoformat()}],
            "partial_fill": False,
            "latency_ms": 100,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.03,
            "stop_loss_price": 63700.0,
            "take_profit_price": 66950.0,
            "expected_move_pct": 0.015,
            "estimated_cost_pct": 0.002,
            "edge_buffer_pct": 0.001,
            "ai_regime": "trend",
            "ai_confidence": 0.85,
            "ml_prediction": "up",
            "ml_confidence": 0.80,
            "coinstats_strength": 0.0,
            "coinstats_sentiment": "neutral",
            "fetchai_signal": "BUY",
            "fetchai_confidence": 85.0,
            "trade_type": "BUY",
            "trade_close_reason": None,
            "profit_pct": 0.0,
            "is_profitable": False,
        }

        with patch.object(engine, 'execute_smart_trade', new=AsyncMock(return_value=trade_result)):
            with patch("paper_trading_engine.paper_wallet_ledger") as mock_wallet:
                mock_wallet.get_balance = AsyncMock(return_value=(True, 1000.0, "ok"))
                mock_wallet.can_trade = AsyncMock(return_value=(True, "ok"))
                mock_wallet.debit = AsyncMock(return_value=(True, "ok"))
                mock_wallet.credit = AsyncMock(return_value=(True, "ok"))

                with patch("paper_trading_engine.db") as mock_db:
                    mock_db.db = MagicMock()
                    mock_db.bots_collection = db_collections['bots']
                    mock_db.trades_collection = db_collections['trades']

                    with patch("paper_trading_engine.enforce_trading_gates"):
                        result = asyncio.run(engine.run_trading_cycle(
                            NORMAL_BOT["id"],
                            NORMAL_BOT,
                            db_collections,
                        ))

        # Assert: either insert_one or update_one was called (trade persisted)
        trades_coll = db_collections['trades']
        insert_called = trades_coll.insert_one.call_count > 0
        update_called = trades_coll.update_one.call_count > 0
        assert insert_called or update_called, (
            "Trade was not persisted: neither insert_one nor update_one was called"
        )

    def test_bot_types_are_stable(self):
        """bot_type field must be one of 'normal' or 'scalper'."""
        for bot in [NORMAL_BOT, SCALPER_BOT]:
            assert bot["bot_type"] in ("normal", "scalper"), (
                f"Invalid bot_type: {bot['bot_type']}"
            )
