"""
Tests for paper trading engine close lifecycle (A3).

Validates:
 - time_exit fires after PAPER_MAX_HOLD_MINUTES using mock time + mock price feed
 - PRICE_MISSING is recorded and engine does not crash or close incorrectly
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from paper_trading_engine import PaperTradingEngine, PAPER_MAX_HOLD_MINUTES


# ── Minimal in-memory collection ──────────────────────────────────────────────

class _MemCollection:
    def __init__(self):
        self.data: list = []

    async def insert_one(self, doc):
        doc.setdefault("_id", f"id_{len(self.data)}")
        self.data.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def find_one(self, query=None, projection=None):
        if not self.data:
            return None
        for doc in self.data:
            match = all(
                doc.get(k) == v
                for k, v in (query or {}).items()
                if not isinstance(v, dict)
            )
            if match:
                return doc
        return None

    async def update_one(self, filt=None, update=None, **kw):
        for doc in self.data:
            if all(doc.get(k) == v for k, v in (filt or {}).items() if not isinstance(v, dict)):
                if update and "$set" in update:
                    doc.update(update["$set"])
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    def find(self, query=None, projection=None):
        data = list(self.data)
        cur = SimpleNamespace()
        cur.sort = lambda *a, **kw: cur
        cur.limit = lambda *a, **kw: cur

        async def to_list(length=None):
            return data
        cur.to_list = to_list
        return cur


# ── Shared bot fixture ────────────────────────────────────────────────────────

def _make_bot():
    return {
        "id": "bot_test",
        "user_id": "user_test",
        "name": "TestBot",
        "exchange": "binance",
        "pair": "BTC/USDT",
        "risk_mode": "safe",
        "trading_mode": "paper",
        "initial_capital": 5000,
        "current_capital": 5000,
        "take_profit_pct": 0.50,  # very wide — won't trigger on small moves
        "stop_loss_pct": 0.50,    # very wide — won't trigger on small moves
    }


def _make_open_trade(opened_minutes_ago: float, bot_id: str = "bot_test"):
    opened_at = (
        datetime.now(timezone.utc) - timedelta(minutes=opened_minutes_ago)
    ).isoformat()
    return {
        "id": "trade_001",
        "bot_id": bot_id,
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
        "opened_at": opened_at,
        "entry_time": opened_at,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.50,
        "fee_rate": 0.001,
        "fill_ratio": 1.0,
        "partial_fill": False,
        "entry_ledger_recorded": True,
    }


# ── Patched context helpers ───────────────────────────────────────────────────

def _patch_engine_deps(bots_col, trades_col, price=50100.0):
    """Return a context manager that patches all external engine dependencies."""
    async def _market_snapshot(symbol, exchange):
        return {
            "bid": price - 10,
            "ask": price + 10,
            "mid": price,
            "spread": 20.0,
            "spread_bps": 4.0,
            "source": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    patches = [
        patch("paper_trading_engine.db.bots_collection", bots_col),
        patch("paper_trading_engine.db.trades_collection", trades_col),
        patch("paper_trading_engine.db.db", None),
        patch("paper_trading_engine.rate_limiter.can_trade", return_value=(True, "ok")),
        patch("paper_trading_engine.rate_limiter.record_trade"),
        patch("paper_trading_engine.risk_engine.check_trade_risk",
              new=AsyncMock(return_value=(True, "ok"))),
        patch("paper_trading_engine.risk_engine.record_trade_result", new=AsyncMock()),
        patch("paper_trading_engine.paper_wallet_ledger.get_balance",
              new=AsyncMock(return_value=(True, 5000.0, "ok"))),
        patch("paper_trading_engine.paper_wallet_ledger.can_trade",
              new=AsyncMock(return_value=(True, "ok"))),
        patch("paper_trading_engine.paper_wallet_ledger.debit",
              new=AsyncMock(return_value=(True, "ok"))),
        patch("paper_trading_engine.paper_wallet_ledger.credit",
              new=AsyncMock(return_value=(True, "ok"))),
        patch("paper_trading_engine.enforce_trading_gates"),
    ]

    class _CM:
        def __init__(self):
            self._active = []
            self._eng: PaperTradingEngine | None = None

        def set_engine(self, eng):
            self._eng = eng
            eng.get_market_snapshot = _market_snapshot

        def __enter__(self):
            for p in patches:
                self._active.append(p.__enter__())
            return self

        def __exit__(self, *exc):
            for ctx in reversed(self._active):
                ctx.__exit__(*exc) if hasattr(ctx, "__exit__") else None
            for p in patches:
                try:
                    p.__exit__(*exc)
                except Exception:
                    pass
    return _CM()


# ── Test: time_exit triggers after max hold ───────────────────────────────────

@pytest.mark.asyncio
async def test_time_exit_closes_trade():
    """Engine tick must close a trade older than PAPER_MAX_HOLD_MINUTES with reason time_exit."""
    engine = PaperTradingEngine()
    bot_data = _make_bot()
    bots_col = AsyncMock()
    bots_col.find_one = AsyncMock(return_value=bot_data)
    bots_col.update_one = AsyncMock()

    trades_col = _MemCollection()
    # Insert a trade that is already older than PAPER_MAX_HOLD_MINUTES
    old_trade = _make_open_trade(opened_minutes_ago=PAPER_MAX_HOLD_MINUTES + 10)
    await trades_col.insert_one(old_trade)

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

        async def _snapshot(symbol, exchange):
            return {
                "bid": 49990.0,
                "ask": 50010.0,
                "mid": 50000.0,
                "spread": 20.0,
                "spread_bps": 4.0,
                "source": "test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        engine.get_market_snapshot = _snapshot

        result = await engine.run_trading_cycle(
            "bot_test",
            bot_data,
            {"bots": bots_col, "trades": trades_col},
        )

    # The trade must have been closed with time_exit
    assert result is not None, "run_trading_cycle returned None"
    # Successful close returns {"bot_id": ..., "new_capital": ..., "trade": {...}}
    assert "new_capital" in result, f"Expected successful close result, got: {result}"
    trade = result.get("trade") or result
    assert trade.get("trade_close_reason") == "time_exit", (
        f"Expected time_exit, got: {trade.get('trade_close_reason')}"
    )

    # The trade record in memory should be updated to closed
    closed = await trades_col.find_one({"id": "trade_001", "status": "closed"})
    assert closed is not None, "Trade should be marked closed in DB"

    # Action log must contain a CLOSE entry
    actions = [a for a in engine._action_log if a["action"] == "CLOSE"]
    assert actions, "Expected CLOSE in action log"
    assert any(a["reason"] == "time_exit" for a in actions), "Expected time_exit reason in action log"


# ── Test: PRICE_MISSING does not crash and records action ─────────────────────

@pytest.mark.asyncio
async def test_price_missing_does_not_crash():
    """When price feed returns no mid price the engine should not crash,
    should record PRICE_MISSING in the action log, and must not close the trade."""
    engine = PaperTradingEngine()
    bot_data = _make_bot()
    bots_col = AsyncMock()
    bots_col.find_one = AsyncMock(return_value=bot_data)
    bots_col.update_one = AsyncMock()

    trades_col = _MemCollection()
    trade = _make_open_trade(opened_minutes_ago=5)
    await trades_col.insert_one(trade)

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

        # Price feed returns empty snapshot (simulates exchange timeout)
        async def _no_price(symbol, exchange):
            return {"source": "test", "timestamp": datetime.now(timezone.utc).isoformat()}

        engine.get_market_snapshot = _no_price

        result = await engine.run_trading_cycle(
            "bot_test",
            bot_data,
            {"bots": bots_col, "trades": trades_col},
        )

    # Engine must not crash and must return a skipped result
    assert result is not None, "run_trading_cycle returned None"
    assert result.get("success") is False, "Should not succeed when price is missing"
    assert result.get("skip_reason") == "no_price_data", (
        f"Expected no_price_data skip_reason, got: {result.get('skip_reason')}"
    )

    # Trade must still be open (not incorrectly closed)
    still_open = await trades_col.find_one({"id": "trade_001", "status": "open"})
    assert still_open is not None, "Trade should remain open when price is missing"

    # Action log must contain PRICE_MISSING
    actions = [a for a in engine._action_log if a["action"] == "PRICE_MISSING"]
    assert actions, "Expected PRICE_MISSING in action log"
