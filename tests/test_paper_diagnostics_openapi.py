"""
Tests for:
  B) /api/diagnostics/paper endpoint (alias of /paper-engine)
  C) /openapi.json always returns valid JSON and includes /api/diagnostics/paper
  D) TP / SL close logic with mocked price feed
"""
import os
import sys
import json
import contextlib
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from paper_trading_engine import PaperTradingEngine, PAPER_MAX_HOLD_MINUTES


# ── Minimal in-memory collection (shared with test_paper_engine_closes) ───────

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


def _make_bot(tp_pct: float = 0.03, sl_pct: float = 0.02):
    return {
        "id": "bot_diag",
        "user_id": "user_diag",
        "name": "DiagBot",
        "exchange": "binance",
        "pair": "BTC/USDT",
        "risk_mode": "safe",
        "trading_mode": "paper",
        "initial_capital": 5000,
        "current_capital": 5000,
        "take_profit_pct": tp_pct,
        "stop_loss_pct": sl_pct,
    }


def _make_open_trade(entry_price: float = 50000.0, opened_minutes_ago: float = 5.0):
    opened_at = (
        datetime.now(timezone.utc) - timedelta(minutes=opened_minutes_ago)
    ).isoformat()
    return {
        "id": "trade_diag",
        "bot_id": "bot_diag",
        "user_id": "user_diag",
        "status": "open",
        "pair": "BTC/USDT",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "entry_price": entry_price,
        "price": entry_price,
        "amount": 0.1,
        "entry_value": entry_price * 0.1,
        "trade_amount": entry_price * 0.1,
        "opened_at": opened_at,
        "entry_time": opened_at,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.03,
        "fee_rate": 0.001,
        "fill_ratio": 1.0,
        "partial_fill": False,
        "entry_ledger_recorded": True,
    }


_MOCK_SPREAD_OFFSET = 10  # bid = mid - offset, ask = mid + offset


def _common_patches(bots_col, trades_col, price: float):
    async def _snapshot(symbol, exchange):
        return {
            "bid": price - _MOCK_SPREAD_OFFSET,
            "ask": price + _MOCK_SPREAD_OFFSET,
            "mid": price,
            "spread": _MOCK_SPREAD_OFFSET * 2.0,
            "spread_bps": 4.0,
            "source": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    patch_defs = [
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

    @contextlib.contextmanager
    def _stack():
        with contextlib.ExitStack() as stack:
            for p in patch_defs:
                stack.enter_context(p)
            yield

    return _stack, _snapshot


# ── D1: take_profit close ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_take_profit_closes_trade():
    """Engine must close a trade when price hits take_profit_price."""
    engine = PaperTradingEngine()
    entry_price = 50000.0
    # Take-profit is 3% above entry → 51500
    tp_price = entry_price * 1.03
    # Set current price above TP
    current_price = tp_price + 100

    bot_data = _make_bot(tp_pct=0.03, sl_pct=0.50)
    bots_col = AsyncMock()
    bots_col.find_one = AsyncMock(return_value=bot_data)
    bots_col.update_one = AsyncMock()

    trades_col = _MemCollection()
    trade = _make_open_trade(entry_price=entry_price)
    await trades_col.insert_one(trade)

    patches, _snapshot = _common_patches(bots_col, trades_col, current_price)

    with patches():
        engine.get_market_snapshot = _snapshot

        result = await engine.run_trading_cycle(
            "bot_diag", bot_data, {"bots": bots_col, "trades": trades_col}
        )

    assert result is not None, "run_trading_cycle returned None"
    assert "new_capital" in result, f"Expected successful close, got: {result}"
    trade_result = result.get("trade") or result
    assert trade_result.get("trade_close_reason") == "take_profit", (
        f"Expected take_profit, got: {trade_result.get('trade_close_reason')}"
    )
    closed = await trades_col.find_one({"id": "trade_diag", "status": "closed"})
    assert closed is not None, "Trade should be marked closed"

    actions = [a for a in engine._action_log if a["action"] == "CLOSE" and a["reason"] == "take_profit"]
    assert actions, "Expected take_profit CLOSE in action log"


# ── D2: stop_loss close ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_loss_closes_trade():
    """Engine must close a trade when price drops to stop_loss_price."""
    engine = PaperTradingEngine()
    entry_price = 50000.0
    # SL is 2% below entry → 49000
    sl_price = entry_price * (1 - 0.02)
    # Set current price below SL
    current_price = sl_price - 100

    bot_data = _make_bot(tp_pct=0.50, sl_pct=0.02)
    bots_col = AsyncMock()
    bots_col.find_one = AsyncMock(return_value=bot_data)
    bots_col.update_one = AsyncMock()

    trades_col = _MemCollection()
    trade = _make_open_trade(entry_price=entry_price)
    await trades_col.insert_one(trade)

    patches, _snapshot = _common_patches(bots_col, trades_col, current_price)

    with patches():
        engine.get_market_snapshot = _snapshot

        result = await engine.run_trading_cycle(
            "bot_diag", bot_data, {"bots": bots_col, "trades": trades_col}
        )

    assert result is not None, "run_trading_cycle returned None"
    assert "new_capital" in result, f"Expected successful close, got: {result}"
    trade_result = result.get("trade") or result
    assert trade_result.get("trade_close_reason") == "stop_loss", (
        f"Expected stop_loss, got: {trade_result.get('trade_close_reason')}"
    )
    closed = await trades_col.find_one({"id": "trade_diag", "status": "closed"})
    assert closed is not None, "Trade should be marked closed"

    actions = [a for a in engine._action_log if a["action"] == "CLOSE" and a["reason"] == "stop_loss"]
    assert actions, "Expected stop_loss CLOSE in action log"


# ── D3: last_close_time is updated after a close ─────────────────────────────

@pytest.mark.asyncio
async def test_last_close_time_updated_after_close():
    """Engine.last_close_time must be set after a successful close."""
    engine = PaperTradingEngine()
    assert engine.last_close_time is None, "Should start as None"

    entry_price = 50000.0
    current_price = entry_price * 1.05  # above TP (3%)

    bot_data = _make_bot(tp_pct=0.03, sl_pct=0.50)
    bots_col = AsyncMock()
    bots_col.find_one = AsyncMock(return_value=bot_data)
    bots_col.update_one = AsyncMock()

    trades_col = _MemCollection()
    await trades_col.insert_one(_make_open_trade(entry_price=entry_price))

    patches, _snapshot = _common_patches(bots_col, trades_col, current_price)

    with patches():
        engine.get_market_snapshot = _snapshot
        await engine.run_trading_cycle(
            "bot_diag", bot_data, {"bots": bots_col, "trades": trades_col}
        )

    assert engine.last_close_time is not None, "last_close_time should be set after close"
    status = engine.get_status()
    assert status["last_close_time"] == engine.last_close_time


# ── B: /api/diagnostics/paper route is in OpenAPI schema ────────────────────

def test_diagnostics_paper_in_openapi():
    """GET /api/diagnostics/paper must appear in the OpenAPI schema paths."""
    from fastapi import FastAPI
    from routes.diagnostics import router as diag_router

    mini_app = FastAPI(openapi_url="/openapi.json")
    mini_app.include_router(diag_router)

    schema = mini_app.openapi()
    paths = schema.get("paths", {})
    assert "/api/diagnostics/paper" in paths, (
        f"/api/diagnostics/paper not found in OpenAPI paths. "
        f"Available paths with 'diag': {[p for p in paths if 'diag' in p]}"
    )
    assert "get" in paths["/api/diagnostics/paper"], (
        "GET method not registered for /api/diagnostics/paper"
    )


# ── C: /openapi.json returns valid JSON (no redirect, no empty body) ─────────

def test_openapi_json_returns_valid_json():
    """/openapi.json on a minimal app must return a dict with 'paths' (not empty)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.diagnostics import router as diag_router

    mini_app = FastAPI(openapi_url="/api/openapi.json")
    mini_app.include_router(diag_router)

    # Add the same /openapi.json fix that server.py now provides
    from fastapi.responses import JSONResponse as _JSONResponse

    @mini_app.get("/openapi.json", include_in_schema=False)
    async def _openapi_json():
        return _JSONResponse(content=mini_app.openapi())

    client = TestClient(mini_app, raise_server_exceptions=False)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    try:
        data = resp.json()
    except Exception as exc:
        pytest.fail(f"/openapi.json body is not valid JSON: {exc}\nBody: {resp.text[:200]}")

    assert "paths" in data, f"OpenAPI JSON missing 'paths' key. Keys: {list(data.keys())}"


def test_openapi_json_includes_diagnostics_paper():
    """/openapi.json must include /api/diagnostics/paper in the paths."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse as _JSONResponse
    from routes.diagnostics import router as diag_router

    mini_app = FastAPI(openapi_url="/api/openapi.json")
    mini_app.include_router(diag_router)

    @mini_app.get("/openapi.json", include_in_schema=False)
    async def _openapi_json():
        return _JSONResponse(content=mini_app.openapi())

    client = TestClient(mini_app, raise_server_exceptions=False)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    data = resp.json()
    paths = data.get("paths", {})
    assert "/api/diagnostics/paper" in paths, (
        f"/api/diagnostics/paper missing from /openapi.json paths. "
        f"Diag paths: {[p for p in paths if 'diag' in p]}"
    )
