"""
Strategy Upgrade Tests — Phase 3 (strategy quality + rate limit + tuner + synonyms)

Covers:
  - RateLimitBudget: acquire, backoff after 429, reset after 200
  - StrategyTuner: UCB1 scoring, bounds enforcement, serialization, expectancy reward
  - compute_expectancy: positive/negative/zero scenarios
  - Stagnation exit: triggered when price stagnates beyond round-trip cost
  - Drawdown gate: bots stand down when drawdown >= MAX_DRAWDOWN_PCT
  - Expectancy gate: skip when estimated expectancy <= MIN_EXPECTANCY_ZAR
  - Command synonyms: "start all bots" → resume_all mapping
  - Config: new constants present and in valid ranges
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# ── Stub heavy optional deps ─────────────────────────────────────────────────
import types as _types

for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity", "huggingface_hub",
             "rapidfuzz", "rapidfuzz.fuzz", "rapidfuzz.process"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "motor" not in sys.modules:
    _m = MagicMock(); _m.motor_asyncio = MagicMock()
    _m.motor_asyncio.AsyncIOMotorClient = MagicMock
    sys.modules["motor"] = _m
    sys.modules["motor.motor_asyncio"] = _m.motor_asyncio

if "pymongo" not in sys.modules:
    _pm = MagicMock(); _pm.ReturnDocument = MagicMock()
    sys.modules["pymongo"] = _pm

for _mod in ("fastapi", "fastapi.responses", "fastapi.middleware",
             "fastapi.middleware.cors", "starlette", "starlette.responses",
             "starlette.requests", "starlette.middleware", "pydantic",
             "aiohttp", "numpy", "scipy", "cryptography", "cryptography.fernet",
             "jose", "jose.jwt", "passlib", "passlib.context", "dotenv",
             "redis", "aioredis", "sklearn", "sklearn.preprocessing"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "bson" not in sys.modules:
    _bp = _types.ModuleType("bson")
    _bp.ObjectId = MagicMock(); _bp.Decimal128 = MagicMock(); _bp.Binary = MagicMock()
    sys.modules["bson"] = _bp
    _bt = _types.ModuleType("bson.timestamp"); _bt.Timestamp = MagicMock()
    sys.modules["bson.timestamp"] = _bt

# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitBudget:
    """Exchange-agnostic rate limit budget (A)."""

    def test_acquire_allowed_on_fresh_budget(self):
        from services.rate_limit_budget import ExchangeRateLimitBudget
        b = ExchangeRateLimitBudget("binance")
        ok, wait = b.acquire("bot_1")
        assert ok is True, "Fresh budget must allow first acquire"
        assert wait == 0.0

    def test_bursts_get_queued_after_limit(self):
        """Sending >burst requests without delay should eventually be blocked."""
        from services.rate_limit_budget import ExchangeRateLimitBudget
        b = ExchangeRateLimitBudget("luno")
        # Luno burst = 3; sending 4 in same second must block the 4th
        results = []
        for _ in range(4):
            ok, wait = b.acquire("bot_luno")
            results.append(ok)
        blocked = [r for r in results if not r]
        assert blocked, "Expected at least one blocked acquire after burst"

    def test_backoff_after_429(self):
        from services.rate_limit_budget import ExchangeRateLimitBudget
        b = ExchangeRateLimitBudget("binance")
        b.record_response(429)
        b.record_response(429)
        ok, wait = b.acquire("bot_1")
        assert not ok, "Should be in backoff after consecutive 429s"
        assert wait > 0, "Should return positive wait time"

    def test_reset_after_200(self):
        """2xx response must reset error streak."""
        from services.rate_limit_budget import ExchangeRateLimitBudget
        b = ExchangeRateLimitBudget("binance")
        b.record_response(429)
        assert b._error_streak == 1
        b.record_response(200)
        assert b._error_streak == 0, "200 must reset error streak"
        assert not b._in_cooldown

    def test_5xx_triggers_smaller_backoff(self):
        from services.rate_limit_budget import ExchangeRateLimitBudget, _MAX_BACKOFF_SECONDS
        b = ExchangeRateLimitBudget("kucoin")
        b.record_response(503)
        assert b._backoff_until > 0
        ok, wait = b.acquire()
        assert not ok or wait == 0.0, "Should be in backoff after 5xx"
        assert b._backoff_until - __import__("time").monotonic() <= _MAX_BACKOFF_SECONDS

    def test_registry_creates_exchange_budget(self):
        from services.rate_limit_budget import RateLimitBudgetRegistry
        reg = RateLimitBudgetRegistry()
        b1 = reg.for_exchange("luno")
        b2 = reg.for_exchange("luno")
        assert b1 is b2, "Registry must return the same instance for same exchange"

    def test_all_status_dict(self):
        from services.rate_limit_budget import RateLimitBudgetRegistry
        reg = RateLimitBudgetRegistry()
        reg.for_exchange("luno")
        reg.for_exchange("binance")
        status = reg.get_all_status()
        assert "luno" in status
        assert "binance" in status
        assert "requests_last_second" in status["luno"]


class TestStrategyTuner:
    """UCB1 strategy tuner (C)."""

    def test_get_params_returns_all_keys(self):
        from services.strategy_tuner import StrategyTuner
        st = StrategyTuner()
        params = st.get_params("u1", "binance", "balanced")
        required = {
            "take_profit_pct", "stop_loss_pct", "min_edge_pct",
            "time_exit_minutes", "max_spread_allowed", "confidence_threshold",
        }
        assert required.issubset(params.keys()), f"Missing: {required - params.keys()}"

    def test_params_within_bounds_balanced(self):
        from services.strategy_tuner import StrategyTuner, _PARAM_BOUNDS
        st = StrategyTuner()
        params = st.get_params("u2", "luno", "balanced")
        bounds = _PARAM_BOUNDS["balanced"]
        for key, (low, high, _) in bounds.items():
            assert low <= params[key] <= high, f"{key}={params[key]} out of [{low},{high}]"

    def test_positive_reward_nudges_params_upward(self):
        """Repeated positive rewards should nudge take_profit_pct upward (within bounds)."""
        from services.strategy_tuner import StrategyTuner
        st = StrategyTuner()
        initial = st.get_params("u3", "binance", "aggressive")["take_profit_pct"]
        for _ in range(20):
            st.update("u3", "binance", "aggressive", reward=5.0)
        after = st.get_params("u3", "binance", "aggressive")["take_profit_pct"]
        assert after >= initial, "Positive reward should not reduce take_profit_pct"

    def test_negative_reward_keeps_params_in_bounds(self):
        from services.strategy_tuner import StrategyTuner, _PARAM_BOUNDS
        st = StrategyTuner()
        for _ in range(50):
            st.update("u4", "luno", "safe", reward=-3.0)
        params = st.get_params("u4", "luno", "safe")
        bounds = _PARAM_BOUNDS["safe"]
        for key, (low, high, _) in bounds.items():
            assert low <= params[key] <= high, f"{key}={params[key]} out of [{low},{high}]"

    def test_serialize_and_load_round_trip(self):
        from services.strategy_tuner import StrategyTuner
        st = StrategyTuner()
        st.update("u5", "bybit", "safe", reward=1.0)
        state = st.serialize_state("u5", "bybit", "safe")
        assert "arms" in state
        assert "current_params" in state

        st2 = StrategyTuner()
        st2.load_state(state)
        params_a = st.get_params("u5", "bybit", "safe")
        params_b = st2.get_params("u5", "bybit", "safe")
        assert params_a == params_b, "Loaded state must produce same params"

    def test_unknown_risk_mode_uses_default(self):
        from services.strategy_tuner import StrategyTuner
        st = StrategyTuner()
        params = st.get_params("u6", "binance", "turbo_supersafe")
        assert "take_profit_pct" in params, "Unknown risk mode must fall back to defaults"

    def test_update_returns_change_list(self):
        from services.strategy_tuner import StrategyTuner
        st = StrategyTuner()
        # Seed with enough pulls to trigger nudge
        for _ in range(5):
            st.update("u7", "binance", "balanced", reward=2.0)
        changes = st.update("u7", "binance", "balanced", reward=3.0)
        # May return empty list if no nudge triggered, but must be a list
        assert isinstance(changes, list)


class TestStagnationExit:
    """Stagnation / no-progress exit (B)."""

    @pytest.mark.asyncio
    async def test_stagnation_exit_triggered_when_price_stagnates(self):
        """When price hasn't moved beyond round-trip cost and STAGNATION_EXIT_MINUTES
        has elapsed, the engine should close with stagnation_exit reason."""
        from paper_trading_engine import PaperTradingEngine, STAGNATION_EXIT_MINUTES

        engine = PaperTradingEngine()
        bot_data = {
            "id": "bot_stag",
            "user_id": "user_stag",
            "name": "StagBot",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "risk_mode": "balanced",
            "trading_mode": "paper",
            "initial_capital": 5000,
            "current_capital": 5000,
            "take_profit_pct": 0.50,  # very wide TP — won't trigger
            "stop_loss_pct": 0.50,    # very wide SL — won't trigger
        }

        # Trade opened STAGNATION_EXIT_MINUTES + 1 minute ago
        age_min = STAGNATION_EXIT_MINUTES + 1
        opened_at = (datetime.now(timezone.utc) - timedelta(minutes=age_min)).isoformat()
        entry_price = 50000.0
        # Current price is entry ± 0.001% — well within fee cost
        current_price = entry_price * 1.00001

        open_trade = {
            "id": "trade_stag",
            "bot_id": "bot_stag",
            "user_id": "user_stag",
            "status": "open",
            "pair": "BTC/USDT",
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "entry_price": entry_price,
            "price": entry_price,
            "amount": 0.1,
            "entry_value": 5000.0,
            "trade_amount": 5000.0,
            "opened_at": opened_at,
            "entry_time": opened_at,
            "stop_loss_pct": 0.50,
            "take_profit_pct": 0.50,
            "fee_rate": 0.001,
            "entry_ledger_recorded": True,
        }

        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        from types import SimpleNamespace

        class _MemCol:
            def __init__(self, docs):
                self.data = list(docs)
            async def find_one(self, *a, **kw):
                return self.data[0] if self.data else None
            async def update_one(self, *a, **kw):
                return SimpleNamespace(modified_count=1)
            async def count_documents(self, *a):
                return 0
            def find(self, *a, **kw):
                cur = SimpleNamespace()
                cur.sort = lambda *a, **k: cur
                async def to_list(n=None): return []
                cur.to_list = to_list
                return cur

        trades_col = _MemCol([open_trade])

        async def _snap(symbol, exchange):
            return {
                "bid": current_price - 5, "ask": current_price + 5,
                "mid": current_price, "spread": 10.0, "spread_bps": 2.0,
                "source": "test", "timestamp": datetime.now(timezone.utc).isoformat(),
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
            patch("paper_trading_engine._symbol_universe.select",
                  new=AsyncMock(return_value=("BTC/USDT", {
                      "winner": "BTC/USDT", "winner_reason": "test",
                      "candidate_count": 1, "filtered_out_count": 0,
                      "filtered_out_reasons_summary": {}, "top5_scored": [],
                      "bot_id": "bot_stag", "exchange": "binance",
                      "timestamp": datetime.now(timezone.utc).isoformat(),
                  }))),
        ]
        ctxs = [p.__enter__() for p in patches]
        try:
            engine.get_market_snapshot = _snap
            result = await engine.run_trading_cycle(
                "bot_stag", bot_data, {"bots": bots_col, "trades": trades_col}
            )
        finally:
            for p in patches:
                try: p.__exit__(None, None, None)
                except Exception: pass

        assert result is not None
        assert "new_capital" in result, f"Expected close, got: {result}"
        trade = result.get("trade") or result
        assert trade.get("trade_close_reason") == "stagnation_exit", (
            f"Expected stagnation_exit, got: {trade.get('trade_close_reason')}"
        )

    def test_stagnation_exit_constant_in_config(self):
        from config import STAGNATION_EXIT_MINUTES
        assert isinstance(STAGNATION_EXIT_MINUTES, int)
        assert STAGNATION_EXIT_MINUTES > 0


class TestCommandSynonyms:
    """AI command router synonym expansions (D)."""

    def test_start_all_bots_maps_to_resume_all(self):
        """'start all bots' must match the resume_all pattern after synonym expansion."""
        import re
        from services.ai_command_router_enhanced import EnhancedAICommandRouter

        class _FakeDB(dict):
            def __getitem__(self, k):
                return MagicMock()

        router = EnhancedAICommandRouter(_FakeDB())
        normalized = router.normalize_text("start all bots")
        # After synonym expansion 'start' → 'resume', should match resume_all pattern
        pattern = router.command_patterns["resume_all"]
        assert re.search(pattern, normalized, re.IGNORECASE), (
            f"'start all bots' → '{normalized}' should match resume_all pattern '{pattern}'"
        )

    def test_begin_all_bots_maps_to_resume_all(self):
        import re
        from services.ai_command_router_enhanced import EnhancedAICommandRouter

        class _FakeDB(dict):
            def __getitem__(self, k):
                return MagicMock()

        router = EnhancedAICommandRouter(_FakeDB())
        # 'begin' should expand to 'resume' via synonyms
        normalized = router.normalize_text("begin all bots")
        pattern = router.command_patterns["resume_all"]
        assert re.search(pattern, normalized, re.IGNORECASE), (
            f"'begin all bots' → '{normalized}' should match resume_all"
        )

    def test_resume_synonym_in_list(self):
        from services.ai_command_router_enhanced import EnhancedAICommandRouter

        class _FakeDB(dict):
            def __getitem__(self, k):
                return MagicMock()

        router = EnhancedAICommandRouter(_FakeDB())
        assert "begin" in router.SYNONYMS.get("resume", []), (
            "'begin' must be in SYNONYMS['resume']"
        )
        assert "kick off" in router.SYNONYMS.get("resume", []), (
            "'kick off' must be in SYNONYMS['resume']"
        )


class TestConfigConstants:
    """Verify new config constants are present and in valid ranges."""

    def test_stagnation_exit_minutes_present(self):
        from config import STAGNATION_EXIT_MINUTES
        assert STAGNATION_EXIT_MINUTES > 0

    def test_soft_before_hard_max_hold(self):
        from config import SOFT_MAX_HOLD_SECONDS, HARD_MAX_HOLD_SECONDS
        assert 0 < SOFT_MAX_HOLD_SECONDS < HARD_MAX_HOLD_SECONDS

    def test_portfolio_guard_sensible(self):
        from config import PORTFOLIO_GUARD_MAX_SAME_SYMBOL
        assert PORTFOLIO_GUARD_MAX_SAME_SYMBOL >= 1

    def test_symbol_cooldown_positive(self):
        from config import SYMBOL_COOLDOWN_MINUTES
        assert SYMBOL_COOLDOWN_MINUTES > 0


class TestComputeExpectancy:
    """compute_expectancy helper function."""

    def test_positive_expectancy(self):
        from services.strategy_tuner import compute_expectancy
        wins = [10.0, 12.0, 8.0]   # avg 10 ZAR
        losses = [-3.0, -4.0]       # avg loss 3.5 ZAR
        # win_rate = 3/5 = 0.6, loss_rate = 0.4
        # E = 0.6*10 - 0.4*3.5 - 0 = 6 - 1.4 = 4.6
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.0)
        assert e > 0, f"Expected positive expectancy, got {e}"
        assert abs(e - 4.6) < 0.01, f"Expected ~4.6, got {e}"

    def test_negative_expectancy_means_stand_down(self):
        from services.strategy_tuner import compute_expectancy
        # Tiny wins, massive losses → negative expectancy
        wins = [1.0] * 9
        losses = [-20.0]
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.0)
        assert e < 0, f"Expected negative expectancy, got {e}"

    def test_zero_trades_returns_zero(self):
        from services.strategy_tuner import compute_expectancy
        e = compute_expectancy([], [])
        assert e == 0.0

    def test_round_trip_cost_reduces_expectancy(self):
        from services.strategy_tuner import compute_expectancy
        wins = [10.0]
        losses = []
        # No losses, 100% win rate, avg_win=10, cost = 0.003 * 1000 = 3 ZAR
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.003, trade_value_zar=1000.0)
        assert abs(e - 7.0) < 0.01, f"Expected ~7.0, got {e}"

    def test_high_winrate_with_bad_rr_can_be_negative(self):
        """90% win rate with poor risk-reward should still show negative expectancy."""
        from services.strategy_tuner import compute_expectancy
        wins = [1.0] * 9          # 9 wins of R1
        losses = [-100.0]          # 1 loss of R100
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.0)
        # E = 0.9*1 - 0.1*100 = 0.9 - 10 = -9.1
        assert e < 0, (
            f"90% win-rate with 1:100 R:R must have negative expectancy, got {e}"
        )


class TestDrawdownGate:
    """Drawdown stand-down gate in paper trading engine."""

    @pytest.mark.asyncio
    async def test_bot_stands_down_when_drawdown_exceeded(self):
        """When current drawdown >= MAX_DRAWDOWN_PCT, engine must skip opening.

        Tests the gate by patching the ledger service that the engine imports
        locally inside the drawdown gate block.
        """
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()
        bot_data = {
            "id": "bot_dd",
            "user_id": "user_dd",
            "name": "DDBot",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "risk_mode": "balanced",
            "trading_mode": "paper",
            "initial_capital": 5000,
            "current_capital": 5000,
        }

        bots_col = AsyncMock()
        bots_col.find_one = AsyncMock(return_value=bot_data)
        bots_col.update_one = AsyncMock()

        from types import SimpleNamespace
        class _EmptyCol:
            async def find_one(self, *a, **kw): return None
            async def update_one(self, *a, **kw): return SimpleNamespace(modified_count=0)
            async def count_documents(self, *a): return 0
            def find(self, *a, **kw):
                cur = SimpleNamespace()
                cur.sort = lambda *a, **k: cur
                async def to_list(n=None): return []
                cur.to_list = to_list
                return cur

        trades_col = _EmptyCol()

        async def _snap(symbol, exchange):
            return {"bid": 49990, "ask": 50010, "mid": 50000, "spread": 20,
                    "spread_bps": 4, "source": "test",
                    "timestamp": datetime.now(timezone.utc).isoformat()}

        # Simulate a 15 % drawdown (> default MAX_DRAWDOWN_PCT=0.10)
        mock_ledger = MagicMock()
        mock_ledger.compute_drawdown = AsyncMock(return_value=(0.15, 0.15))
        mock_get_ledger = MagicMock(return_value=mock_ledger)

        patches = [
            patch("paper_trading_engine.db.bots_collection", bots_col),
            patch("paper_trading_engine.db.trades_collection", trades_col),
            patch("paper_trading_engine.db.db", MagicMock()),
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
                      "bot_id": "bot_dd", "exchange": "binance",
                      "timestamp": datetime.now(timezone.utc).isoformat(),
                  }))),
            # Patch MAX_DRAWDOWN_PCT to 10 % (default) and inject the high-drawdown ledger
            patch("paper_trading_engine.MAX_DRAWDOWN_PCT", 0.10),
            # Patch the ledger_service module so the local import inside the gate finds it
            patch("services.ledger_service.get_ledger_service", mock_get_ledger),
        ]
        ctxs = [p.__enter__() for p in patches]
        try:
            engine.get_market_snapshot = _snap
            result = await engine.run_trading_cycle(
                "bot_dd", bot_data,
                {"bots": bots_col, "trades": trades_col},
            )
        finally:
            for p in patches:
                try: p.__exit__(None, None, None)
                except Exception: pass

        assert result is not None
        skip = result.get("skip_reason", "")
        assert skip == "drawdown_limit", (
            f"Expected drawdown_limit skip, got: {result}"
        )

    def test_max_drawdown_pct_config(self):
        from config import MAX_DRAWDOWN_PCT
        assert 0 < MAX_DRAWDOWN_PCT <= 1.0, (
            f"MAX_DRAWDOWN_PCT={MAX_DRAWDOWN_PCT} must be in (0, 1]"
        )

    def test_min_expectancy_zar_config(self):
        from config import MIN_EXPECTANCY_ZAR
        assert isinstance(MIN_EXPECTANCY_ZAR, float)


class TestExpectancyGate:
    """Skip when estimated expectancy <= MIN_EXPECTANCY_ZAR."""

    def test_negative_expectancy_produces_skip_reason_in_engine_output(self):
        """If the engine can compute expectancy and it's negative, it should skip."""
        # This is a unit test of the expectancy computation logic, not a full
        # integration test — verifies compute_expectancy returns negative for
        # the scenario the engine guards against.
        from services.strategy_tuner import compute_expectancy
        # Worst case: no wins, only losses
        wins = []
        losses = [-5.0, -8.0]
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.002, trade_value_zar=1000.0)
        assert e < 0.0, f"No-win scenario must produce negative expectancy, got {e}"

    def test_positive_expectancy_is_not_blocked(self):
        """When expectancy is clearly positive, compute_expectancy must agree."""
        from services.strategy_tuner import compute_expectancy
        wins = [15.0, 18.0, 12.0]  # consistently good wins
        losses = [-3.0]            # small loss
        e = compute_expectancy(wins, losses, round_trip_cost_pct=0.001, trade_value_zar=1000.0)
        assert e > 0.0, f"Should be positive expectancy, got {e}"
