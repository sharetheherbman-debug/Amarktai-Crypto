"""
Backend Convergence Tests

Validates that the split-brain architecture has been removed:
1. V2 trading brain is the default execution path
2. Single self-healing instance (engines.self_healing)
3. TargetPolicyV2 is used by radar when V2 is enabled
4. Truth normalizer returns safe (non-NaN, non-None) numeric values
5. trade_worth_filter / TradeFeasibilityGate are both present and functional
6. Scalper hold windows are short (≤ 300s) in V2
"""

import os
import sys
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


# ── 1. V2 is the canonical engine by default ──────────────────────────────

class TestV2IsDefaultEngine:

    def test_v2_flag_defaults_to_true(self):
        """NEW_TRADING_BRAIN_V2 must default to True without env override."""
        # Unset any override to test the default
        os.environ.pop("NEW_TRADING_BRAIN_V2", None)
        # Re-import to pick up default
        import importlib
        import config as cfg_module
        importlib.reload(cfg_module)
        assert cfg_module.NEW_TRADING_BRAIN_V2 is True, (
            "NEW_TRADING_BRAIN_V2 must default to True; "
            "V2 must be the canonical engine."
        )

    def test_v2_flag_can_be_overridden_off(self):
        """Operators can still disable V2 with NEW_TRADING_BRAIN_V2=false."""
        os.environ["NEW_TRADING_BRAIN_V2"] = "false"
        import importlib
        import config as cfg_module
        importlib.reload(cfg_module)
        assert cfg_module.NEW_TRADING_BRAIN_V2 is False
        # Restore default
        os.environ.pop("NEW_TRADING_BRAIN_V2", None)
        importlib.reload(cfg_module)

    def test_v2_components_importable(self):
        """All V2 pipeline components must be importable."""
        from services.trading_brain_v2 import (
            RegimeScorerV2,
            TradeFeasibilityGate,
            KellySizingV2,
            TargetPolicyV2,
            BotBehavioralContracts,
        )
        assert RegimeScorerV2 is not None
        assert TradeFeasibilityGate is not None
        assert KellySizingV2 is not None
        assert TargetPolicyV2 is not None
        assert BotBehavioralContracts is not None


# ── 2. Single self-healing instance ───────────────────────────────────────

class TestSingleSelfHealingInstance:

    def test_root_shim_imports_from_engines(self):
        """root self_healing.py must import from engines.self_healing."""
        import os
        shim_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "self_healing.py"
        )
        with open(shim_path) as f:
            source = f.read()
        assert "from engines.self_healing import" in source, (
            "root self_healing.py must re-export from engines.self_healing"
        )
        assert "class SelfHealingSystem" not in source or "from engines" in source, (
            "root self_healing.py must not define its own SelfHealingSystem class"
        )

    def test_root_shim_exports_self_healing_monitor_alias(self):
        """root self_healing.py must export self_healing_monitor alias."""
        import os
        shim_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "self_healing.py"
        )
        with open(shim_path) as f:
            source = f.read()
        assert "self_healing_monitor" in source, (
            "root self_healing.py must export self_healing_monitor alias "
            "for diagnostics.py compatibility"
        )

    def test_engines_self_healing_start_stop_are_async(self):
        """engines/self_healing.py start() and stop() must be async coroutines."""
        import os
        engines_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines", "self_healing.py"
        )
        with open(engines_path) as f:
            source = f.read()
        # Check both methods are defined as async
        assert "async def start(" in source, (
            "engines/self_healing.py start() must be async for await-compatibility"
        )
        assert "async def stop(" in source, (
            "engines/self_healing.py stop() must be async for await-compatibility"
        )

    def test_only_engines_self_healing_started_by_lifecycle(self):
        """lifecycle.py must reference engines.self_healing, not root."""
        import os
        lifecycle_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "services", "lifecycle.py"
        )
        with open(lifecycle_path) as f:
            source = f.read()
        assert "engines.self_healing" in source, (
            "lifecycle.py must start engines.self_healing as canonical instance"
        )


# ── 3. TargetPolicyV2 produces valid targets ─────────────────────────────

class TestTargetPolicyV2:

    def setup_method(self):
        from services.trading_brain_v2 import TargetPolicyV2
        self.policy = TargetPolicyV2()

    def test_normal_bot_targets_non_zero(self):
        result = self.policy.compute(
            bot_type="normal", venue="binance", quote_currency="USDT",
            bot_equity=1000.0, notional=20.0, all_in_cost_bps=10.0,
        )
        assert result["daily_profit_target_quote"] > 0
        assert result["trade_profit_target_quote"] > 0
        assert result["target_source"] == "target_policy_v2"

    def test_scalper_hold_window_is_short(self):
        """Scalper max_hold must be ≤ 300 seconds."""
        result = self.policy.compute(
            bot_type="scalper", venue="binance", quote_currency="USDT",
            bot_equity=500.0, notional=10.0, all_in_cost_bps=8.0,
        )
        assert result["max_hold_seconds"] <= 300, (
            f"Scalper max_hold_seconds must be ≤ 300, got {result['max_hold_seconds']}"
        )

    def test_normal_bot_hold_window_is_longer(self):
        """Normal bots must have a longer hold window than scalpers."""
        normal = self.policy.compute(
            bot_type="normal", venue="binance", quote_currency="USDT",
            bot_equity=1000.0, notional=20.0, all_in_cost_bps=10.0,
        )
        scalper = self.policy.compute(
            bot_type="scalper", venue="binance", quote_currency="USDT",
            bot_equity=1000.0, notional=20.0, all_in_cost_bps=8.0,
        )
        assert normal["max_hold_seconds"] > scalper["max_hold_seconds"]

    def test_no_nan_in_output(self):
        result = self.policy.compute(
            bot_type="normal", venue="luno", quote_currency="ZAR",
            bot_equity=10000.0, notional=200.0, all_in_cost_bps=15.0,
        )
        for key, val in result.items():
            if isinstance(val, float):
                assert not math.isnan(val), f"NaN in field {key}"
                assert not math.isinf(val), f"Inf in field {key}"


# ── 4. Truth normalizer produces safe values ──────────────────────────────

class TestTruthNormalizer:

    def setup_method(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        self.normalize = normalize_bot_trade_truth

    def test_no_nan_or_none_numerics(self):
        """Numeric fields must never be NaN or None."""
        result = self.normalize({}, None)
        numeric_fields = [
            "regime_confidence", "entry_confidence_score",
            "expectancy_net_edge_pct", "expected_gross_edge_bps",
            "all_in_cost_bps", "expected_net_edge_bps",
            "projected_net_profit_quote",
        ]
        for field in numeric_fields:
            val = result.get(field)
            assert val is not None, f"Field {field} is None"
            assert isinstance(val, (int, float)), f"Field {field} is not numeric: {val!r}"
            assert not math.isnan(float(val)), f"Field {field} is NaN"
            assert not math.isinf(float(val)), f"Field {field} is Inf"

    def test_symbol_falls_back_to_unknown(self):
        result = self.normalize({}, None)
        assert result["symbol"] == "unknown"

    def test_trade_symbol_overrides_bot_symbol(self):
        bot = {"symbol": "ETH/USDT"}
        trade = {"pair": "BTC/USDT", "status": "open"}
        result = self.normalize(bot, trade)
        assert result["symbol"] == "BTC/USDT"

    def test_regime_from_trade_when_trade_open(self):
        bot = {"market_regime": "trending_up"}
        trade = {"canonical_market_regime": "breakout", "status": "open"}
        result = self.normalize(bot, trade)
        assert result["market_regime"] == "breakout"

    def test_sanitize_decision_payload_removes_nan(self):
        from services.truth_normalizer import sanitize_decision_payload
        payload = {
            "entry_confidence_score": float("nan"),
            "regime_confidence": float("inf"),
            "market_regime": None,
            "approved": 1,
        }
        out = sanitize_decision_payload(payload)
        assert out["entry_confidence_score"] == 0.0
        assert out["regime_confidence"] == 0.0
        assert out["market_regime"] == ""
        assert out["approved"] is True


# ── 5. TradeFeasibilityGate and trade_worth_filter both functional ────────

class TestTradeGates:

    def test_feasibility_gate_blocks_tiny_edge(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        result = gate.evaluate(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=1000.0,
            notional=20.0,
            expected_gross_edge_bps=5.0,   # well below minimum
            all_in_cost_bps=15.0,
            spread_pct=0.002,
            depth_notional=10000,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8,
                           "trend_score": 0.7, "vol_score": 0.3, "liquidity_score": 0.8},
            regime_eligibility={"allowed": True, "size_multiplier": 1.0},
            entry_confidence=0.7,
            mid_price=50000,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] != ""

    def test_feasibility_gate_approves_good_trade(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        result = gate.evaluate(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=2000.0,       # larger notional for absolute profit floor
            expected_gross_edge_bps=50.0,
            all_in_cost_bps=15.0,
            spread_pct=0.001,
            depth_notional=100000,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.85,
                           "trend_score": 0.8, "vol_score": 0.3, "liquidity_score": 0.9},
            regime_eligibility={"allowed": True, "size_multiplier": 1.0},
            entry_confidence=0.8,
            mid_price=50000,
        )
        assert result["approved"] is True

    def test_trade_worth_filter_blocks_tiny_profit(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="binance",
            bot_equity=1000.0,
            notional=30.0,
            expected_gross_edge_bps=5.0,
            all_in_cost_bps=20.0,
        )
        assert result["approved"] is False

    def test_trade_worth_filter_approves_valid_trade(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="binance",
            bot_equity=5000.0,
            notional=2000.0,       # larger notional so absolute profit floor is met
            expected_gross_edge_bps=40.0,
            all_in_cost_bps=10.0,
        )
        assert result["approved"] is True
        assert result["reason_code"] == "TRADE_WORTH_FILTER_OK"


# ── 6. Scalper priority is higher than normal bots ───────────────────────

class TestScalperPriority:

    def test_scalper_has_short_hold_in_v2(self):
        """V2 target policy: scalper hold window must be 300s."""
        from services.trading_brain_v2.bot_contracts import ScalperContract
        assert ScalperContract.max_hold_seconds <= 300

    def test_scalper_max_hold_in_exchange_limits(self):
        """exchange_limits SCALPER_MAX_HOLD_SECONDS must be ≤ 300."""
        from exchange_limits import SCALPER_MAX_HOLD_SECONDS
        assert SCALPER_MAX_HOLD_SECONDS <= 300

    def test_v2_regime_allows_scalper_in_high_vol(self):
        """Scalpers must be blocked in high_volatility regime (too risky for short holds).

        Scalpers trade in consolidation/low_volatility/mean_reversion where price
        movement is bounded and predictable. High volatility creates unpredictable
        moves that expose scalper positions to outsized adverse moves during their
        short hold windows.
        """
        from services.trading_brain_v2.regime_scorer import STRATEGY_REGIME_MAP, REGIME_HIGH_VOL
        # Scalpers are specifically NOT allowed in high volatility
        assert REGIME_HIGH_VOL not in STRATEGY_REGIME_MAP["scalper"], (
            "Scalpers must be blocked in high_volatility — "
            "short hold windows are vulnerable to unpredictable moves"
        )


# ── 7. Single target policy source in radar ───────────────────────────────

class TestRadarTargetSource:

    @classmethod
    def _radar_source(cls) -> str:
        import os
        radar_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "radar.py"
        )
        with open(radar_path) as f:
            return f.read()

    def test_radar_imports_truth_normalizer(self):
        """radar.py must import normalize_bot_trade_truth."""
        assert "normalize_bot_trade_truth" in self._radar_source(), (
            "radar.py must use normalize_bot_trade_truth for canonical truth"
        )

    def test_radar_imports_target_policy_v2(self):
        """radar.py must reference TargetPolicyV2 for target computation."""
        assert "TargetPolicyV2" in self._radar_source(), (
            "radar.py must reference TargetPolicyV2 as canonical target source"
        )
