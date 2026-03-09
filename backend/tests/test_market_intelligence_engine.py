"""
Tests for Market Intelligence Engine, Bot Genetics, API Key Manager,
and Risk Management enhancements.

Run with:
  ENVIRONMENT=testing python -m pytest backend/tests/test_market_intelligence_engine.py -v
"""

import os
import sys
import time

# ------------------------------------------------------------------
# Path setup
# ------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("ENVIRONMENT", "testing")

import pytest


# ══════════════════════════════════════════════════════════════════════
#  LRU Cache
# ══════════════════════════════════════════════════════════════════════

class TestLRUCache:
    def test_set_and_get(self):
        from engines.market_intelligence_engine import LRUCache
        cache = LRUCache(max_size=10, ttl_seconds=60)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_ttl_expiry(self):
        from engines.market_intelligence_engine import LRUCache
        cache = LRUCache(max_size=10, ttl_seconds=1)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"
        time.sleep(1.1)
        assert cache.get("k1") is None

    def test_max_size_eviction(self):
        from engines.market_intelligence_engine import LRUCache
        cache = LRUCache(max_size=3, ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_clear(self):
        from engines.market_intelligence_engine import LRUCache
        cache = LRUCache()
        cache.set("x", 1)
        cache.clear()
        assert cache.get("x") is None


# ══════════════════════════════════════════════════════════════════════
#  Provider Scheduler
# ══════════════════════════════════════════════════════════════════════

class TestProviderScheduler:
    def test_default_priority_returns_first(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        assert sched.next_provider() == "cryptocompare"

    def test_record_call_increments(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        sched.record_call("cryptocompare")
        usage = sched.get_usage()
        assert usage["cryptocompare"]["monthly_calls"] == 1

    def test_switches_when_threshold_reached(self):
        from engines.market_intelligence_engine import ProviderScheduler, ProviderQuota
        sched = ProviderScheduler()
        # Manually exhaust primary
        q = sched._quotas["cryptocompare"]
        q.monthly_calls = int(q.monthly_limit * q.switch_threshold) + 1
        next_p = sched.next_provider()
        assert next_p == "coingecko"

    def test_per_minute_limit_triggers_rotation(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        q = sched._quotas["cryptocompare"]
        q.minute_calls = q.per_minute_limit  # exhaust per-minute
        q.minute_window_start = time.time()  # within current window
        next_p = sched.next_provider()
        assert next_p == "coingecko"

    def test_set_priority(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        sched.set_priority(["coinranking", "coingecko", "cryptocompare"])
        assert sched.next_provider() == "coinranking"

    def test_set_threshold(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        sched.set_threshold("cryptocompare", 0.50)
        assert sched._quotas["cryptocompare"].switch_threshold == 0.50

    def test_usage_percentages(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        sched.record_call("cryptocompare")
        sched.record_call("cryptocompare")
        usage = sched.get_usage()
        assert usage["cryptocompare"]["monthly_calls"] == 2
        assert usage["cryptocompare"]["monthly_pct"] >= 0

    def test_all_exhausted_returns_most_headroom(self):
        from engines.market_intelligence_engine import ProviderScheduler
        sched = ProviderScheduler()
        for name in ["cryptocompare", "coingecko", "coinranking"]:
            q = sched._quotas[name]
            q.monthly_calls = int(q.monthly_limit * q.switch_threshold) + 1
        # Should still return one (the one with most headroom)
        result = sched.next_provider()
        assert result is not None


# ══════════════════════════════════════════════════════════════════════
#  Order Book Analyzer
# ══════════════════════════════════════════════════════════════════════

class TestOrderBookAnalyzer:
    def test_imbalance_balanced(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        bids = [[100, 10], [99, 10]]
        asks = [[101, 10], [102, 10]]
        imb = OrderBookAnalyzer.compute_imbalance(bids, asks, depth=2)
        assert abs(imb) < 0.01  # balanced

    def test_imbalance_bid_heavy(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        bids = [[100, 100]]
        asks = [[101, 10]]
        imb = OrderBookAnalyzer.compute_imbalance(bids, asks, depth=1)
        assert imb > 0  # bid-heavy

    def test_imbalance_ask_heavy(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        bids = [[100, 10]]
        asks = [[101, 100]]
        imb = OrderBookAnalyzer.compute_imbalance(bids, asks, depth=1)
        assert imb < 0  # ask-heavy

    def test_imbalance_empty(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        assert OrderBookAnalyzer.compute_imbalance([], []) == 0.0

    def test_liquidity_walls(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        bids = [[100, 5], [99, 5], [98, 5], [97, 50]]  # wall at 97
        asks = [[101, 5], [102, 5], [103, 5], [104, 50]]  # wall at 104
        walls = OrderBookAnalyzer.find_liquidity_walls(bids, asks, wall_multiplier=2.0)
        assert len(walls["bid_walls"]) >= 1
        assert len(walls["ask_walls"]) >= 1

    def test_compute_spread(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        bids = [[100, 10]]
        asks = [[101, 10]]
        result = OrderBookAnalyzer.compute_spread(bids, asks)
        assert result is not None
        assert result["spread"] == 1.0
        assert result["best_bid"] == 100
        assert result["best_ask"] == 101

    def test_compute_spread_empty(self):
        from engines.market_intelligence_engine import OrderBookAnalyzer
        assert OrderBookAnalyzer.compute_spread([], []) is None


# ══════════════════════════════════════════════════════════════════════
#  Strategy Selector
# ══════════════════════════════════════════════════════════════════════

class TestStrategySelector:
    def test_bullish_calm_selects_trend(self):
        from engines.market_intelligence_engine import StrategySelector, StrategyType
        sel = StrategySelector()
        assert sel.select("bullish_calm") == StrategyType.TREND_FOLLOWING

    def test_bearish_volatile_selects_mean_reversion(self):
        from engines.market_intelligence_engine import StrategySelector, StrategyType
        sel = StrategySelector()
        assert sel.select("bearish_volatile") == StrategyType.MEAN_REVERSION

    def test_squeeze_selects_breakout(self):
        from engines.market_intelligence_engine import StrategySelector, StrategyType
        sel = StrategySelector()
        assert sel.select("squeeze") == StrategyType.BREAKOUT

    def test_unknown_defaults_to_trend(self):
        from engines.market_intelligence_engine import StrategySelector, StrategyType
        sel = StrategySelector()
        assert sel.select("unknown") == StrategyType.TREND_FOLLOWING
        assert sel.select("nonexistent") == StrategyType.TREND_FOLLOWING

    def test_strategy_params_returned(self):
        from engines.market_intelligence_engine import StrategySelector, StrategyType
        sel = StrategySelector()
        params = sel.get_strategy_params(StrategyType.TREND_FOLLOWING)
        assert "stop_loss_pct" in params
        assert "take_profit_pct" in params


# ══════════════════════════════════════════════════════════════════════
#  Bot Genetics
# ══════════════════════════════════════════════════════════════════════

class TestBotGenetics:
    def _make_bot(self, **overrides):
        bot = {
            "id": "bot_1",
            "name": "Test Bot",
            "user_id": "user_1",
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "bot_type": "normal",
            "strategy": "trend_following",
            "strategy_params": {"entry_lookback": 20, "stop_loss_pct": 2.0},
            "stop_loss_pct": 2.0,
            "take_profit_pct": 5.0,
            "initial_capital": 10000,
            "current_capital": 12000,
            "total_profit": 2000,
            "trades_count": 20,
            "win_count": 14,
            "loss_count": 6,
            "status": "active",
            "trading_mode": "paper",
            "generation": 0,
        }
        bot.update(overrides)
        return bot

    def test_is_fit_parent_true(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bot = self._make_bot()
        assert bg.is_fit_parent(bot) is True

    def test_is_fit_parent_low_win_rate(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bot = self._make_bot(win_count=2, trades_count=20)
        assert bg.is_fit_parent(bot) is False

    def test_is_fit_parent_too_few_trades(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bot = self._make_bot(trades_count=3, win_count=3)
        assert bg.is_fit_parent(bot) is False

    def test_is_fit_parent_negative_profit(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bot = self._make_bot(total_profit=-100)
        assert bg.is_fit_parent(bot) is False

    def test_is_fit_parent_inactive(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bot = self._make_bot(status="paused")
        assert bg.is_fit_parent(bot) is False

    def test_spawn_child(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        parent = self._make_bot()
        child = bg.spawn_child(parent)
        assert child is not None
        assert child["parent_id"] == "bot_1"
        assert child["generation"] == 1
        assert child["status"] == "paused"
        assert child["current_capital"] == 6000  # 50% of 12000

    def test_spawn_child_inherits_strategy(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        parent = self._make_bot()
        child = bg.spawn_child(parent)
        assert child["strategy"] == parent["strategy"]

    def test_spawn_child_mutates_params(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics(mutation_range=0.5)  # big mutation for test
        parent = self._make_bot()
        children = [bg.spawn_child(parent) for _ in range(5)]
        # At least one child should have different params
        original_sl = parent["stop_loss_pct"]
        sl_values = [c["stop_loss_pct"] for c in children if c]
        assert any(v != original_sl for v in sl_values)

    def test_population_cap(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics(max_population=2)
        parent = self._make_bot()
        c1 = bg.spawn_child(parent)
        c2 = bg.spawn_child(parent)
        c3 = bg.spawn_child(parent)
        assert c1 is not None
        assert c2 is not None
        assert c3 is None  # cap reached

    def test_population_count(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        parent = self._make_bot()
        bg.spawn_child(parent)
        assert bg.population_count() == 1

    def test_lineage(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        parent = self._make_bot()
        child = bg.spawn_child(parent)
        lineage = bg.get_lineage(child["id"])
        assert lineage[-1] == "bot_1"

    def test_unfit_parent_no_spawn(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        bad_bot = self._make_bot(total_profit=-500)
        assert bg.spawn_child(bad_bot) is None

    def test_mutate_params_preserves_non_numeric(self):
        from engines.bot_genetics import BotGenetics
        bg = BotGenetics()
        params = {"mode": "aggressive", "value": 10.0, "count": 5}
        mutated = bg.mutate_params(params)
        assert mutated["mode"] == "aggressive"
        assert isinstance(mutated["count"], int)


# ══════════════════════════════════════════════════════════════════════
#  API Key Manager
# ══════════════════════════════════════════════════════════════════════

class TestAPIKeyManager:
    def test_no_keys_configured_by_default(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        # In CI, no keys are set; all should be unconfigured
        status = mgr.get_status()
        assert isinstance(status, dict)
        assert "cryptocompare" in status

    def test_set_key(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        assert mgr.set_key("cryptocompare", "test_key_123")
        assert mgr.has_key("cryptocompare")
        assert mgr.get_key("cryptocompare") == "test_key_123"

    def test_set_key_unknown_provider(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        assert mgr.set_key("nonexistent_provider", "key") is False

    def test_configured_providers(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        mgr.set_key("coingecko", "test_key")
        assert "coingecko" in mgr.configured_providers()

    def test_has_key_false_when_empty(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        assert mgr.has_key("luzia") is False

    def test_status_structure(self):
        from services.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        status = mgr.get_status()
        for provider, info in status.items():
            assert "description" in info
            assert "configured" in info
            assert "validated" in info


# ══════════════════════════════════════════════════════════════════════
#  Risk Lock State
# ══════════════════════════════════════════════════════════════════════

class TestRiskLockState:
    def test_initial_state_unlocked(self):
        from engines.risk_management import RiskLockState
        state = RiskLockState()
        assert state.is_locked() is False
        assert state.highest_active_lock() is None

    def test_engage_lock(self):
        from engines.risk_management import RiskLockState
        state = RiskLockState()
        state.engage("emergency_stop", "Manual trigger")
        assert state.is_locked() is True
        assert state.highest_active_lock() == "emergency_stop"

    def test_release_lock(self):
        from engines.risk_management import RiskLockState
        state = RiskLockState()
        state.engage("daily_loss_lock", "Limit exceeded")
        state.release("daily_loss_lock")
        assert state.is_locked() is False

    def test_precedence_order(self):
        from engines.risk_management import RiskLockState
        state = RiskLockState()
        state.engage("training_gate", "Not trained")
        state.engage("circuit_breaker", "Rapid losses")
        # circuit_breaker has higher priority than training_gate
        assert state.highest_active_lock() == "circuit_breaker"

    def test_get_state(self):
        from engines.risk_management import RiskLockState
        state = RiskLockState()
        state.engage("bodyguard_lock", "Safety")
        info = state.get_state()
        assert info["locked"] is True
        assert info["highest_lock"] == "bodyguard_lock"
        assert "Safety" in info["reasons"].get("bodyguard_lock", "")


# ══════════════════════════════════════════════════════════════════════
#  Quarantine Manager
# ══════════════════════════════════════════════════════════════════════

class TestQuarantineManager:
    def test_quarantine_bot(self):
        from engines.risk_management import QuarantineManager
        qm = QuarantineManager()
        qm.quarantine("bot_1", "Hard stop")
        assert qm.is_quarantined("bot_1") is True

    def test_release_bot(self):
        from engines.risk_management import QuarantineManager
        qm = QuarantineManager()
        qm.quarantine("bot_1", "Stop")
        assert qm.release("bot_1") is True
        assert qm.is_quarantined("bot_1") is False

    def test_release_nonexistent(self):
        from engines.risk_management import QuarantineManager
        qm = QuarantineManager()
        assert qm.release("missing") is False

    def test_get_all(self):
        from engines.risk_management import QuarantineManager
        qm = QuarantineManager()
        qm.quarantine("b1", "r1")
        qm.quarantine("b2", "r2")
        all_q = qm.get_all()
        assert len(all_q) == 2
        assert "b1" in all_q


# ══════════════════════════════════════════════════════════════════════
#  Daily Loss Tracker
# ══════════════════════════════════════════════════════════════════════

class TestDailyLossTracker:
    def test_record_and_get(self):
        from engines.risk_management import DailyLossTracker
        dlt = DailyLossTracker()
        dlt.record_loss("user_1", 100)
        dlt.record_loss("user_1", 50)
        assert dlt.get_daily_loss("user_1") == 150

    def test_check_limit_below(self):
        from engines.risk_management import DailyLossTracker
        dlt = DailyLossTracker()
        dlt.record_loss("user_1", 10)
        assert dlt.check_limit("user_1", equity=10000) is False

    def test_check_limit_above(self):
        from engines.risk_management import DailyLossTracker
        dlt = DailyLossTracker()
        dlt.record_loss("user_1", 600)
        assert dlt.check_limit("user_1", equity=10000) is True  # 6% > 5%

    def test_reset(self):
        from engines.risk_management import DailyLossTracker
        dlt = DailyLossTracker()
        dlt.record_loss("user_1", 100)
        dlt.reset("user_1")
        assert dlt.get_daily_loss("user_1") == 0.0

    def test_zero_equity(self):
        from engines.risk_management import DailyLossTracker
        dlt = DailyLossTracker()
        dlt.record_loss("user_1", 100)
        assert dlt.check_limit("user_1", equity=0) is False


# ══════════════════════════════════════════════════════════════════════
#  Risk Management — Dynamic Thresholds
# ══════════════════════════════════════════════════════════════════════

class TestRiskManagementEnhancements:
    def test_compute_drawdown(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        dd = rm.compute_drawdown(current_equity=9000, peak_equity=10000)
        assert abs(dd - 0.10) < 0.001

    def test_compute_drawdown_zero_peak(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        assert rm.compute_drawdown(9000, 0) == 0.0

    def test_check_max_drawdown_triggers(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        assert rm.check_max_drawdown(8900, 10000) is True  # 11% > 10%

    def test_check_max_drawdown_ok(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        assert rm.check_max_drawdown(9500, 10000) is False  # 5% < 10%

    def test_check_risk_locks_clear(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        assert rm.check_risk_locks("bot_1") is None

    def test_check_risk_locks_quarantined(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        rm.quarantine.quarantine("bot_1", "test")
        result = rm.check_risk_locks("bot_1")
        assert result is not None
        assert result["lock"] == "quarantine"

    def test_check_risk_locks_emergency(self):
        from engines.risk_management import RiskManagement
        rm = RiskManagement()
        rm.lock_state.engage("emergency_stop", "Manual")
        result = rm.check_risk_locks("bot_2")
        assert result is not None
        assert result["lock"] == "emergency_stop"


# ══════════════════════════════════════════════════════════════════════
#  Config Settings — New Variables
# ══════════════════════════════════════════════════════════════════════

class TestConfigSettings:
    def test_new_provider_keys_defined(self):
        from config import settings
        assert hasattr(settings, 'CRYPTOCOMPARE_API_KEY')
        assert hasattr(settings, 'COINGECKO_API_KEY')
        assert hasattr(settings, 'COINRANKING_API_KEY')
        assert hasattr(settings, 'ETHERSCAN_API_KEY')
        assert hasattr(settings, 'GLASSNODE_API_KEY')
        assert hasattr(settings, 'WHALE_ALERT_API_KEY')

    def test_risk_thresholds_defined(self):
        from config import settings
        assert hasattr(settings, 'DAILY_LOSS_LIMIT')
        assert hasattr(settings, 'MAX_DRAW_DOWN')
        assert settings.DAILY_LOSS_LIMIT == 0.05
        assert settings.MAX_DRAW_DOWN == 0.10

    def test_bot_intelligence_flags(self):
        from config import settings
        assert hasattr(settings, 'BOT_GENETICS_ENABLED')
        assert hasattr(settings, 'HIVE_MIND_ENABLED')

    def test_feature_flags_include_new_flags(self):
        from config import settings
        flags = settings.get_feature_flags()
        assert 'BOT_GENETICS_ENABLED' in flags
        assert 'HIVE_MIND_ENABLED' in flags


# ══════════════════════════════════════════════════════════════════════
#  Market Intelligence Engine — Integration (no network)
# ══════════════════════════════════════════════════════════════════════

class TestMarketIntelligenceEngineUnit:
    def test_engine_instantiates(self):
        from engines.market_intelligence_engine import MarketIntelligenceEngine
        engine = MarketIntelligenceEngine()
        assert engine.scheduler is not None
        assert engine.aggregator is not None
        assert engine.whale_tracker is not None
        assert engine.strategy_selector is not None

    def test_select_strategy(self):
        from engines.market_intelligence_engine import MarketIntelligenceEngine
        engine = MarketIntelligenceEngine()
        result = engine.select_strategy("bullish_calm")
        assert result["strategy"] == "trend_following"
        assert "params" in result

    def test_get_provider_usage(self):
        from engines.market_intelligence_engine import MarketIntelligenceEngine
        engine = MarketIntelligenceEngine()
        usage = engine.get_provider_usage()
        assert "cryptocompare" in usage
        assert "coingecko" in usage
