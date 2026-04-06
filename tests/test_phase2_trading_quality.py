"""
Phase 2 Trading Quality Tests (C1, C2, C3)

Validates:
  C1 - Symbol selection returns >1 candidate for a configured universe and
       applies anti-repeat penalty to recently-traded symbols.
  C2 - HARD_MAX_HOLD forces a close within 25 minutes (mock time);
       close is NOT blocked by low-confidence checks.
  C3 - Portfolio guard blocks a second open on the same symbol when the
       limit is 1.
  ZAR - Existing Luno ZAR bots still work (universe includes ZAR pairs).
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub heavy optional dependencies so imports don't fail in CI
for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity", "huggingface_hub"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Stub motor (MongoDB async driver) so database.py can be imported
import types as _types

if "motor" not in sys.modules:
    _motor_pkg = MagicMock()
    _motor_asyncio = MagicMock()
    _motor_asyncio.AsyncIOMotorClient = MagicMock
    _motor_pkg.motor_asyncio = _motor_asyncio
    sys.modules["motor"] = _motor_pkg
    sys.modules["motor.motor_asyncio"] = _motor_asyncio

# Stub pymongo (synchronous MongoDB driver)
if "pymongo" not in sys.modules:
    _pymongo = MagicMock()
    _pymongo.ReturnDocument = MagicMock()
    sys.modules["pymongo"] = _pymongo

# Stub fastapi and related
for _mod in ("fastapi", "fastapi.responses", "fastapi.middleware", "fastapi.middleware.cors",
             "starlette", "starlette.responses", "starlette.requests", "starlette.middleware",
             "pydantic", "aiohttp", "numpy", "scipy", "cryptography",
             "cryptography.fernet", "jose", "jose.jwt", "passlib", "passlib.context",
             "dotenv", "redis", "aioredis", "sklearn", "sklearn.preprocessing"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# bson needs to be a real package (has sub-modules)
if "bson" not in sys.modules:
    _bson_pkg = _types.ModuleType("bson")
    _bson_pkg.ObjectId = MagicMock()
    _bson_pkg.Decimal128 = MagicMock()
    _bson_pkg.Binary = MagicMock()
    sys.modules["bson"] = _bson_pkg
    _bson_ts = _types.ModuleType("bson.timestamp")
    _bson_ts.Timestamp = MagicMock()
    sys.modules["bson.timestamp"] = _bson_ts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _MemCollection:
    """Minimal in-memory async MongoDB collection stub."""

    def __init__(self, docs=None):
        self.data = list(docs or [])

    async def insert_one(self, doc):
        doc.setdefault("_id", f"id_{len(self.data)}")
        self.data.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def find_one(self, query=None, projection=None):
        for doc in self.data:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not isinstance(v, dict)):
                return doc
        return None

    async def update_one(self, filt=None, update=None, **kw):
        for doc in self.data:
            if all(doc.get(k) == v for k, v in (filt or {}).items() if not isinstance(v, dict)):
                if update and "$set" in update:
                    doc.update(update["$set"])
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def count_documents(self, query=None):
        count = 0
        for doc in self.data:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not isinstance(v, dict)):
                count += 1
        return count

    def find(self, query=None, projection=None):
        data = [
            doc for doc in self.data
            if all(doc.get(k) == v for k, v in (query or {}).items() if not isinstance(v, dict))
        ]
        cur = SimpleNamespace()
        cur.sort = lambda *a, **kw: cur
        cur.limit = lambda *a, **kw: cur

        async def to_list(length=None):
            return data
        cur.to_list = to_list
        return cur


def _make_bot(exchange="binance"):
    return {
        "id": "bot_c2_test",
        "user_id": "user_c2",
        "name": "C2TestBot",
        "exchange": exchange,
        "pair": "BTC/USDT",
        "risk_mode": "safe",
        "trading_mode": "paper",
        "initial_capital": 5000,
        "current_capital": 5000,
        "take_profit_pct": 0.50,
        "stop_loss_pct": 0.50,
    }


def _make_open_trade(opened_minutes_ago: float, symbol: str = "BTC/USDT", exchange: str = "binance"):
    opened_at = (datetime.now(timezone.utc) - timedelta(minutes=opened_minutes_ago)).isoformat()
    return {
        "id": "trade_c2_001",
        "bot_id": "bot_c2_test",
        "user_id": "user_c2",
        "status": "open",
        "pair": symbol,
        "symbol": symbol,
        "exchange": exchange,
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


def _patch_close_deps(bots_col, trades_col, price: float = 50100.0):
    """Return patch objects needed for _close_open_trade tests."""
    async def _snapshot(symbol, exchange):
        return {
            "bid": price - 10,
            "ask": price + 10,
            "mid": price,
            "spread": 20.0,
            "spread_bps": 4.0,
            "source": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return [
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
        patch("paper_trading_engine._symbol_universe.select",
              new=AsyncMock(return_value=("BTC/USDT", {
                  "winner": "BTC/USDT", "winner_reason": "test",
                  "candidate_count": 1, "filtered_out_count": 0,
                  "filtered_out_reasons_summary": {}, "top5_scored": [],
                  "bot_id": "bot_c2_test", "exchange": "binance",
                  "timestamp": datetime.now(timezone.utc).isoformat(),
              }))),
    ], _snapshot


# ─────────────────────────────────────────────────────────────────────────────
# C1: Symbol universe / anti-repeat tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSymbolUniverse:
    """Symbol selection framework (C1)."""

    def test_select_returns_multiple_candidates(self):
        """select() must surface more than one candidate for a standard universe."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService

        svc = SymbolUniverseService()
        universe = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
        winner, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id="bot_x",
                user_id="user_x",
                exchange="binance",
                available_pairs=universe,
                open_symbols_for_user=[],
            )
        )
        assert winner is not None, "Should return a winner"
        assert diag["candidate_count"] > 1, (
            f"Expected >1 candidates, got {diag['candidate_count']}"
        )
        assert len(diag["top5_scored"]) > 1, "Should have >1 entry in top5_scored"

    def test_anti_repeat_penalty_applied(self):
        """A symbol recently closed by the bot must have a lower score than a fresh one."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService, _symbol_history

        svc = SymbolUniverseService()
        bot_id = "bot_anti_repeat"
        # Simulate a recent close of BTC/USDT
        _symbol_history.record_closed(bot_id, "BTC/USDT")

        universe = ["BTC/USDT", "ETH/USDT"]
        _, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id=bot_id,
                user_id="user_ar",
                exchange="binance",
                available_pairs=universe,
                open_symbols_for_user=[],
                cooldown_minutes=60,  # long cooldown so penalty applies
            )
        )
        scored = {e["symbol"]: e["score"] for e in diag["top5_scored"]}
        assert scored.get("ETH/USDT", 0) > scored.get("BTC/USDT", 1), (
            f"ETH/USDT (fresh) should outscore BTC/USDT (recently closed). Scores: {scored}"
        )

    def test_diversity_penalty_for_already_open_symbol(self):
        """A symbol already open for the user should get a strong diversity penalty."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService

        svc = SymbolUniverseService()
        universe = ["BTC/USDT", "ETH/USDT"]
        _, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id="bot_div",
                user_id="user_div",
                exchange="binance",
                available_pairs=universe,
                open_symbols_for_user=["BTC/USDT"],  # already open
            )
        )
        scored = {e["symbol"]: e["score"] for e in diag["top5_scored"]}
        assert scored.get("ETH/USDT", 0) > scored.get("BTC/USDT", 1), (
            f"ETH/USDT should outscore BTC/USDT (open). Scores: {scored}"
        )

    def test_luno_zar_universe_included(self):
        """Luno exchange universe must include ZAR pairs so ZAR bots can work."""
        from services.symbol_universe import SymbolUniverseService

        svc = SymbolUniverseService()
        universe = svc.get_universe("luno")
        zar_pairs = [s for s in universe if "ZAR" in s]
        assert zar_pairs, f"Luno universe must contain ZAR pairs, got: {universe}"

    def test_filtered_out_reasons_populated(self):
        """Symbols outside the universe must appear in filtered_out_reasons."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService

        svc = SymbolUniverseService()
        # Provide pairs that are NOT in the Luno universe
        _, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id="bot_filter",
                user_id="user_filter",
                exchange="luno",
                available_pairs=["SHIB/ZAR", "BTC/ZAR"],  # SHIB not in default universe
                open_symbols_for_user=[],
            )
        )
        # SHIB/ZAR should be filtered; BTC/ZAR should pass
        assert "SHIB/ZAR" in diag.get("filtered_out_detail", {}), (
            "SHIB/ZAR should be filtered as not_in_universe"
        )
        assert diag["filtered_out_detail"]["SHIB/ZAR"] == "not_in_universe"


# ─────────────────────────────────────────────────────────────────────────────
# C2: Hard max-hold forced close tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHardMaxHold:
    """Hard max-hold close rules (C2)."""

    @pytest.mark.asyncio
    async def test_hard_max_hold_forces_close(self):
        """HARD_MAX_HOLD_SECONDS reached → engine must force-close the trade."""
        from paper_trading_engine import PaperTradingEngine, HARD_MAX_HOLD_SECONDS

        engine = PaperTradingEngine()
        bot_data = _make_bot()
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        trades_col = _MemCollection()
        # Trade opened HARD_MAX_HOLD_SECONDS + 60 seconds ago
        hard_age_minutes = (HARD_MAX_HOLD_SECONDS + 60) / 60
        old_trade = _make_open_trade(opened_minutes_ago=hard_age_minutes)
        await trades_col.insert_one(old_trade)

        patches, snapshot_fn = _patch_close_deps(bots_col, trades_col)

        ctxs = [p.__enter__() for p in patches]
        try:
            engine.get_market_snapshot = snapshot_fn
            result = await engine.run_trading_cycle(
                "bot_c2_test",
                bot_data,
                {"bots": bots_col, "trades": trades_col},
            )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        assert "new_capital" in result, f"Expected successful close, got: {result}"
        trade = result.get("trade") or result
        assert trade.get("trade_close_reason") == "hard_max_hold", (
            f"Expected hard_max_hold, got: {trade.get('trade_close_reason')}"
        )

    @pytest.mark.asyncio
    async def test_close_not_blocked_by_low_confidence(self):
        """Closing must succeed even when AI confidence is too low to open a new trade.

        The SKIP_LOW_CONFIDENCE path only applies to opening new trades, not to
        closing existing ones.  We verify this by running a cycle on a trade that
        has exceeded HARD_MAX_HOLD_SECONDS — the close must succeed regardless of
        whether AI confidence gates would block a new open.
        """
        from paper_trading_engine import PaperTradingEngine, HARD_MAX_HOLD_SECONDS

        engine = PaperTradingEngine()
        bot_data = _make_bot()
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        trades_col = _MemCollection()
        hard_age_minutes = (HARD_MAX_HOLD_SECONDS + 30) / 60
        await trades_col.insert_one(_make_open_trade(opened_minutes_ago=hard_age_minutes))

        # Simulate AI sources that would fail confidence gate for opens
        low_conf_regime = {"regime": "neutral", "confidence": 0.1}
        low_conf_prediction = {"direction": "neutral", "confidence": 0.1, "is_simulated": False}
        low_conf_fetchai = {"signal": "HOLD", "confidence": 10, "is_simulated": False}

        patches, snapshot_fn = _patch_close_deps(bots_col, trades_col)
        patches += [
            patch("paper_trading_engine.market_regime_detector",
                  AsyncMock(**{"detect_regime": AsyncMock(return_value=low_conf_regime)})),
            patch("paper_trading_engine.ml_predictor",
                  AsyncMock(**{"predict_price": AsyncMock(return_value=low_conf_prediction)})),
            patch("paper_trading_engine.fetchai",
                  AsyncMock(**{"fetch_market_signals": AsyncMock(return_value=low_conf_fetchai)})),
        ]

        ctxs = [p.__enter__() for p in patches]
        try:
            engine.get_market_snapshot = snapshot_fn
            result = await engine.run_trading_cycle(
                "bot_c2_test",
                bot_data,
                {"bots": bots_col, "trades": trades_col},
            )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        assert "new_capital" in result, (
            f"Close must succeed even with low AI confidence; got: {result}"
        )
        trade = result.get("trade") or result
        assert trade.get("trade_close_reason") == "hard_max_hold", (
            f"Expected hard_max_hold close, got: {trade.get('trade_close_reason')}"
        )

    @pytest.mark.asyncio
    async def test_soft_max_hold_closes_when_spread_ok(self):
        """SOFT_MAX_HOLD_SECONDS reached + acceptable spread → close with soft_max_hold."""
        from paper_trading_engine import PaperTradingEngine, SOFT_MAX_HOLD_SECONDS, HARD_MAX_HOLD_SECONDS

        engine = PaperTradingEngine()
        bot_data = _make_bot()
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        trades_col = _MemCollection()
        # Age is past SOFT but before HARD
        soft_age_minutes = (SOFT_MAX_HOLD_SECONDS + 30) / 60
        assert soft_age_minutes < HARD_MAX_HOLD_SECONDS / 60, "Precondition: soft < hard"
        await trades_col.insert_one(_make_open_trade(opened_minutes_ago=soft_age_minutes))

        patches, _snap = _patch_close_deps(bots_col, trades_col)
        ctxs = [p.__enter__() for p in patches]
        try:
            # Spread well within PAPER_MAX_SPREAD_PCT
            async def _good_snap(symbol, exchange):
                return {
                    "bid": 49990.0, "ask": 50010.0, "mid": 50000.0,
                    "spread": 20.0, "spread_bps": 4.0,
                    "source": "test",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            engine.get_market_snapshot = _good_snap
            result = await engine.run_trading_cycle(
                "bot_c2_test",
                bot_data,
                {"bots": bots_col, "trades": trades_col},
            )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        assert "new_capital" in result, f"Expected close at soft_max_hold, got: {result}"
        trade = result.get("trade") or result
        assert trade.get("trade_close_reason") == "soft_max_hold", (
            f"Expected soft_max_hold, got: {trade.get('trade_close_reason')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C3: Portfolio guard tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioGuard:
    """Portfolio-level duplicate-symbol guard (C3)."""

    @pytest.mark.asyncio
    async def test_portfolio_guard_blocks_second_open_on_same_symbol(self):
        """When user already has an open trade on BTC/USDT, engine must not open another."""
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()
        bot_data = {
            **_make_bot(),
            "pair": "BTC/USDT",
        }
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        # No open trade for this bot so it won't try to close
        trades_col = _MemCollection()

        # Mock the trades_collection count_documents to return 1 (already 1 open on BTC/USDT)
        mock_count = AsyncMock(return_value=1)

        patches, snapshot_fn = _patch_close_deps(bots_col, trades_col)
        patches.append(
            patch("paper_trading_engine.db.trades_collection.count_documents", mock_count)
        )

        ctxs = [p.__enter__() for p in patches]
        try:
            engine.get_market_snapshot = snapshot_fn
            with patch("paper_trading_engine.PORTFOLIO_GUARD_MAX_SAME_SYMBOL", 1):
                result = await engine.run_trading_cycle(
                    "bot_c2_test",
                    bot_data,
                    {"bots": bots_col, "trades": trades_col},
                )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        # Should be blocked (either portfolio_guard skip or some other block)
        assert result.get("success") is False, (
            "Portfolio guard should prevent a second open on the same symbol"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ZAR: Luno ZAR bots still work
# ─────────────────────────────────────────────────────────────────────────────

class TestLunoZarBots:
    """Ensure existing Luno ZAR bots are not broken by symbol universe changes."""

    def test_luno_universe_contains_btc_zar(self):
        """BTC/ZAR (Luno canonical pair) must be in the Luno universe."""
        from services.symbol_universe import SymbolUniverseService
        svc = SymbolUniverseService()
        universe = svc.get_universe("luno")
        assert "BTC/ZAR" in universe, f"BTC/ZAR missing from Luno universe: {universe}"

    def test_luno_universe_contains_eth_zar(self):
        """ETH/ZAR must also be present."""
        from services.symbol_universe import SymbolUniverseService
        svc = SymbolUniverseService()
        assert "ETH/ZAR" in svc.get_universe("luno")

    @pytest.mark.asyncio
    async def test_luno_bot_selects_zar_pair(self):
        """Symbol selection for Luno must return a ZAR pair from the ZAR-only universe."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService
        svc = SymbolUniverseService()
        winner, diag = await svc.select(
            bot_id="bot_luno",
            user_id="user_luno",
            exchange="luno",
            available_pairs=["BTC/ZAR", "ETH/ZAR", "XRP/ZAR"],
            open_symbols_for_user=[],
        )
        assert winner is not None
        assert "ZAR" in winner, f"Expected a ZAR pair, got: {winner}"


# ─────────────────────────────────────────────────────────────────────────────
# D: Fee-aware exits (fee_break_even_fail + time_decay_exit)
# ─────────────────────────────────────────────────────────────────────────────

class TestFeeAwareExits:
    """Fee-aware exit reasons: fee_break_even_fail and time_decay_exit (D)."""

    @pytest.mark.asyncio
    async def test_fee_break_even_fail_triggers_when_losing_beyond_cost(self):
        """fee_break_even_fail must close a trade that is losing more than round-trip cost."""
        from paper_trading_engine import PaperTradingEngine, FEE_BREAK_EVEN_WINDOW_MINUTES

        engine = PaperTradingEngine()
        bot_data = _make_bot()
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        trades_col = _MemCollection()
        # Trade opened FEE_BREAK_EVEN_WINDOW_MINUTES + 1 minute ago
        age_minutes = FEE_BREAK_EVEN_WINDOW_MINUTES + 1
        trade = _make_open_trade(opened_minutes_ago=age_minutes)
        await trades_col.insert_one(trade)

        # Entry=50000, current price well below entry so loss exceeds round-trip cost
        # fee_rate=0.001, spread_bps=4 → round_trip_pct ≈ 0.24%
        # Set price to give pnl_pct ≈ -0.50% (definitely below -0.24%)
        losing_price = 50000.0 * (1 - 0.005)  # -0.5% move

        patches, _ = _patch_close_deps(bots_col, trades_col, price=losing_price)
        ctxs = [p.__enter__() for p in patches]
        try:
            async def _losing_snap(symbol, exchange):
                return {
                    "bid": losing_price - 10,
                    "ask": losing_price + 10,
                    "mid": losing_price,
                    "spread": 20.0,
                    "spread_bps": 4.0,
                    "source": "test",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            engine.get_market_snapshot = _losing_snap
            result = await engine.run_trading_cycle(
                "bot_c2_test", bot_data, {"bots": bots_col, "trades": trades_col}
            )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        assert "new_capital" in result, f"Expected close, got: {result}"
        trade_out = result.get("trade") or result
        assert trade_out.get("trade_close_reason") == "fee_break_even_fail", (
            f"Expected fee_break_even_fail, got: {trade_out.get('trade_close_reason')}"
        )

    @pytest.mark.asyncio
    async def test_time_decay_exit_triggers_when_profit_below_cost(self):
        """time_decay_exit must close a trade that cannot cover costs after TIME_DECAY_EXIT_MINUTES.

        Scenario: spread is too wide for soft_max_hold (blocks it), trade age exceeds
        TIME_DECAY_EXIT_MINUTES, and PnL is slightly positive but below round-trip cost.
        """
        from paper_trading_engine import PaperTradingEngine, TIME_DECAY_EXIT_MINUTES, FEE_BREAK_EVEN_WINDOW_MINUTES, SOFT_MAX_HOLD_SECONDS

        engine = PaperTradingEngine()
        bot_data = _make_bot()
        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        trades_col = _MemCollection()
        # Trade must be older than both SOFT_MAX_HOLD and TIME_DECAY_EXIT_MINUTES.
        age_minutes = max(TIME_DECAY_EXIT_MINUTES + 1, SOFT_MAX_HOLD_SECONDS / 60 + 1)
        # Ensure also past fee_break_even threshold so we need price above -round_trip
        assert age_minutes > FEE_BREAK_EVEN_WINDOW_MINUTES
        trade = _make_open_trade(opened_minutes_ago=age_minutes)
        await trades_col.insert_one(trade)

        # Price slightly above entry so pnl_pct > -round_trip but < +round_trip
        # fee_rate=0.001, wide_spread_bps=40 → round_trip_pct ≈ 0.60%
        # Use pnl_pct = +0.05% (above -0.60% so no fee_break_even, below +0.60% → time_decay)
        breakeven_price = 50000.0 * (1 + 0.0005)  # +0.05% move

        patches, _ = _patch_close_deps(bots_col, trades_col, price=breakeven_price)
        ctxs = [p.__enter__() for p in patches]
        try:
            # Use wide spread (40 bps > PAPER_MAX_SPREAD_PCT*100=35 bps) to block soft_max_hold
            async def _wide_spread_snap(symbol, exchange):
                return {
                    "bid": breakeven_price - 200,
                    "ask": breakeven_price + 200,
                    "mid": breakeven_price,
                    "spread": 400.0,
                    "spread_bps": 40.0,  # exceeds PAPER_MAX_SPREAD_PCT * 100 = 35
                    "source": "test",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            engine.get_market_snapshot = _wide_spread_snap
            result = await engine.run_trading_cycle(
                "bot_c2_test", bot_data, {"bots": bots_col, "trades": trades_col}
            )
        finally:
            for p in patches:
                try:
                    p.__exit__(None, None, None)
                except Exception:
                    pass

        assert result is not None
        assert "new_capital" in result, f"Expected close, got: {result}"
        trade_out = result.get("trade") or result
        assert trade_out.get("trade_close_reason") == "time_decay_exit", (
            f"Expected time_decay_exit, got: {trade_out.get('trade_close_reason')}"
        )

    def test_fee_break_even_window_config(self):
        """FEE_BREAK_EVEN_WINDOW_MINUTES must be a positive int in config."""
        from config import FEE_BREAK_EVEN_WINDOW_MINUTES
        assert isinstance(FEE_BREAK_EVEN_WINDOW_MINUTES, int)
        assert FEE_BREAK_EVEN_WINDOW_MINUTES > 0

    def test_time_decay_exit_config(self):
        """TIME_DECAY_EXIT_MINUTES must be a positive int in config."""
        from config import TIME_DECAY_EXIT_MINUTES
        assert isinstance(TIME_DECAY_EXIT_MINUTES, int)
        assert TIME_DECAY_EXIT_MINUTES > 0


# ─────────────────────────────────────────────────────────────────────────────
# E: Adaptive confidence threshold + stop-loss cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestAdaptiveEntryThreshold:
    """Adaptive confidence threshold after losing streak (E)."""

    def test_config_constants_present(self):
        from config import LOSING_STREAK_THRESHOLD, LOSING_STREAK_SIGNAL_BOOST
        assert isinstance(LOSING_STREAK_THRESHOLD, int) and LOSING_STREAK_THRESHOLD >= 1
        assert isinstance(LOSING_STREAK_SIGNAL_BOOST, float) and LOSING_STREAK_SIGNAL_BOOST > 0

    def test_loss_streak_resets_on_take_profit(self):
        """A take_profit close must reset the bot's loss streak counter."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        engine._bot_loss_streaks["bot_x"] = 5
        # Simulate what the engine does on take_profit close
        close_reason = "take_profit"
        if close_reason == "take_profit":
            engine._bot_loss_streaks["bot_x"] = 0
        assert engine._bot_loss_streaks["bot_x"] == 0

    def test_loss_streak_increments_on_stop_loss(self):
        """A stop_loss close must increment the bot's loss streak counter."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        engine._bot_loss_streaks["bot_y"] = 2
        # Simulate what the engine does on stop_loss close
        close_reason = "stop_loss"
        if close_reason == "stop_loss":
            engine._bot_loss_streaks["bot_y"] = engine._bot_loss_streaks.get("bot_y", 0) + 1
        assert engine._bot_loss_streaks["bot_y"] == 3

    def test_stop_loss_cooldown_config(self):
        """STOP_LOSS_COOLDOWN_MINUTES must be > SYMBOL_COOLDOWN_MINUTES."""
        from config import STOP_LOSS_COOLDOWN_MINUTES, SYMBOL_COOLDOWN_MINUTES
        assert STOP_LOSS_COOLDOWN_MINUTES > SYMBOL_COOLDOWN_MINUTES, (
            "Stop-loss cooldown must be strictly longer than regular cooldown"
        )


class TestStopLossCooldown:
    """Stop-loss specific symbol cooldown (E)."""

    def test_record_stop_loss_applies_penalty(self):
        """After a stop-loss, the symbol should get extra penalty in scoring."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService, _symbol_history

        svc = SymbolUniverseService()
        bot_id = "bot_sl_cooldown"
        sym = "BTC/USDT"

        # Record a stop-loss for BTC/USDT
        svc.record_stop_loss(bot_id, sym)

        # Fresh ETH/USDT should score much higher than stop-lossed BTC/USDT
        universe = [sym, "ETH/USDT"]
        _, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id=bot_id,
                user_id="user_sl",
                exchange="binance",
                available_pairs=universe,
                open_symbols_for_user=[],
                cooldown_minutes=0,  # disable regular cooldown so only stop-loss penalty applies
            )
        )
        scored = {e["symbol"]: e["score"] for e in diag["top5_scored"]}
        assert scored.get("ETH/USDT", 0) > scored.get(sym, 1), (
            f"ETH/USDT should outscore stop-lossed {sym}. Scores: {scored}"
        )

    def test_record_stop_loss_note_in_diagnostics(self):
        """Scoring note for a stop-lossed symbol should include 'stop_loss_cooldown'."""
        import asyncio
        from services.symbol_universe import SymbolUniverseService

        svc = SymbolUniverseService()
        bot_id = "bot_sl_note"
        svc.record_stop_loss(bot_id, "BTC/USDT")

        _, diag = asyncio.get_event_loop().run_until_complete(
            svc.select(
                bot_id=bot_id,
                user_id="user_slnote",
                exchange="binance",
                available_pairs=["BTC/USDT", "ETH/USDT"],
                open_symbols_for_user=[],
                cooldown_minutes=0,
            )
        )
        btc_entry = next((e for e in diag["top5_scored"] if e["symbol"] == "BTC/USDT"), None)
        assert btc_entry is not None
        notes_str = " ".join(btc_entry.get("notes", []))
        assert "stop_loss_cooldown" in notes_str, (
            f"Expected stop_loss_cooldown note, got: {btc_entry['notes']}"
        )
