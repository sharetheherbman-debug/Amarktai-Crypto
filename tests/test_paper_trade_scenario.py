import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from paper_trading_engine import PaperTradingEngine
from services import ledger_service as ledger_module
from services.ledger_service import LedgerService


class MockCollection:
    def __init__(self):
        self.data = []

    def create_index(self, *args, **kwargs):
        return None

    async def insert_one(self, doc):
        doc["_id"] = f"doc_{len(self.data)}"
        self.data.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def find_one(self, query=None, projection=None):
        if not query or not self.data:
            return None
        for doc in self.data:
            # Only match equality conditions; dict values are MongoDB operators
            # (e.g. $gte) which this simplified mock does not support.
            match = all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict))
            if match:
                return doc
        return None

    async def update_one(self, query, update, **kwargs):
        for doc in self.data:
            # Same simplified equality-only matching as find_one.
            match = all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict))
            if match:
                if "$set" in update:
                    doc.update(update["$set"])
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    def find(self, query=None, projection=None):
        cursor = SimpleNamespace()
        cursor.sort = lambda *args, **kwargs: cursor
        cursor.limit = lambda *args, **kwargs: cursor

        async def to_list(length=None):
            return list(self.data)

        cursor.to_list = to_list
        return cursor

    def aggregate(self, pipeline):
        cursor = SimpleNamespace()

        async def to_list(length=None):
            return []

        cursor.to_list = to_list
        return cursor


class MockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection()
        return self.collections[name]


@pytest.mark.asyncio
async def test_paper_trade_scenario_deterministic():
    ledger_module._ledger_service_instance = None
    engine = PaperTradingEngine()
    ledger_db = MockDatabase()

    bots_collection = AsyncMock()
    trades_collection = MockCollection()
    api_keys_collection = AsyncMock()
    api_keys_collection.find_one.return_value = None

    bot_data = {
        "id": "bot_1",
        "user_id": "user_1",
        "name": "PaperBot",
        "exchange": "binance",
        "pair": "BTC/USDT",
        "risk_mode": "safe",
        "trading_mode": "paper",
        "initial_capital": 10000,
        "current_capital": 10000,
    }

    bots_collection.find_one.return_value = bot_data
    bots_collection.update_one = AsyncMock()

    balance = {"value": 10000.0}

    async def get_balance(_):
        return True, balance["value"], "ok"

    async def credit(_, amount, reason):
        balance["value"] += amount
        return True, reason

    async def debit(_, amount, reason):
        balance["value"] -= amount
        return True, reason

    async def can_trade(_, amount):
        return balance["value"] >= amount, "ok"

    price_state = {"value": 10000.0}

    async def market_provider(symbol, exchange):
        # Increase by 5% each call so take-profit (3%) is quickly triggered on the exit cycle
        price_state["value"] *= 1.05
        mid = price_state["value"]
        return {
            "bid": mid - 1.0,
            "ask": mid + 1.0,
            "mid": mid,
            "spread": 2.0,
            "spread_bps": 2.0,
            "source": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    engine.market_data_provider = market_provider

    with patch("paper_trading_engine.db") as mock_db, \
        patch("paper_trading_engine.rate_limiter") as mock_rate_limiter, \
        patch("paper_trading_engine.risk_engine") as mock_risk_engine, \
        patch("market_regime.market_regime_detector") as mock_regime, \
        patch("ml_predictor.ml_predictor") as mock_predictor, \
        patch("flokx_integration.flokx") as mock_flokx, \
        patch("fetchai_integration.fetchai") as mock_fetchai, \
        patch("paper_trading_engine.paper_wallet_ledger") as mock_wallet, \
        patch("paper_trading_engine.enforce_trading_gates"), \
        patch("paper_trading_engine.trading_mode_validator") as mock_tv:
        mock_db.bots_collection = bots_collection
        mock_db.trades_collection = trades_collection
        mock_db.api_keys_collection = api_keys_collection
        mock_db.db = ledger_db

        mock_rate_limiter.can_trade.return_value = (True, "ok")
        mock_rate_limiter.record_trade = lambda *args, **kwargs: None

        mock_risk_engine.check_trade_risk = AsyncMock(return_value=(True, "ok"))
        mock_risk_engine.record_trade_result = AsyncMock()

        mock_regime.detect_regime = AsyncMock(return_value={"confidence": 0.9, "trend": "bullish", "regime": "trend"})
        mock_predictor.predict_price = AsyncMock(return_value={"confidence": 0.9, "direction": "up", "predicted_change": 1.0})
        mock_flokx.fetch_market_coefficients = AsyncMock(return_value={"strength": 90, "sentiment": "bullish", "volatility": 20})
        mock_fetchai.fetch_market_signals = AsyncMock(return_value={"confidence": 90, "signal": "BUY"})

        mock_wallet.get_balance = AsyncMock(side_effect=get_balance)
        mock_wallet.credit = AsyncMock(side_effect=credit)
        mock_wallet.debit = AsyncMock(side_effect=debit)
        mock_wallet.can_trade = AsyncMock(side_effect=can_trade)

        results = []
        for _ in range(20):
            result = await engine.run_trading_cycle(
                "bot_1",
                bot_data,
                {"bots": bots_collection, "trades": trades_collection}
            )
            if result:
                results.append(result)

    assert results, "Expected at least one paper trade result"
    trade_result = results[0]["trade"]
    assert trade_result["fees"] > 0, "Fees should be non-zero"

    entry_value = sum(fill["qty"] * fill["price"] for fill in trade_result["entry_fills"])
    exit_value = sum(fill["qty"] * fill["price"] for fill in trade_result["exit_fills"])
    expected_net = exit_value - entry_value - trade_result["fees"] - trade_result["slippage_cost"]
    assert pytest.approx(expected_net, rel=1e-3) == trade_result["profit_loss"]

    ledger = LedgerService(ledger_db)
    equity = await ledger.compute_equity(bot_id="bot_1")
    assert pytest.approx(results[-1]["new_capital"], rel=1e-3) == equity

    fills = await ledger.get_fills(bot_id="bot_1", limit=100)
    assert any(f["side"] == "buy" for f in fills)
    assert any(f["side"] == "sell" for f in fills)
