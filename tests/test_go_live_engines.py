"""
Tests for new engines: OpportunityScanner, CapitalEfficiency, TimeDecayExit,
and enhanced RegimeDetector.
"""

import pytest
import sys
import os
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ══════════════════════════════════════════════════════════════════════════════
# Regime Detector Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRegimeDetectorEnhanced:
    """Tests for the enhanced regime detector with full regime set."""

    def test_market_regime_enum_has_canonical_regimes(self):
        try:
            from engines.regime_detector import MarketRegime
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        canonical = {'trending', 'ranging', 'volatile', 'low_volatility', 'panic', 'accumulation'}
        values = {r.value for r in MarketRegime}
        for c in canonical:
            assert c in values, f"Missing canonical regime: {c}"

    def test_market_regime_enum_has_legacy_aliases(self):
        try:
            from engines.regime_detector import MarketRegime
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        assert MarketRegime.BULLISH_CALM.value == 'bullish_calm'
        assert MarketRegime.BEARISH_VOLATILE.value == 'bearish_volatile'
        assert MarketRegime.SQUEEZE.value == 'squeeze'

    def test_trading_params_for_trending(self):
        try:
            from engines.regime_detector import RegimeDetector, MarketRegime, RegimeState
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        from datetime import datetime, timezone
        detector = RegimeDetector()
        state = RegimeState(
            regime=MarketRegime.TRENDING,
            confidence=0.8,
            volatility=0.01,
            trend_strength=0.05,
            timestamp=datetime.now(timezone.utc),
            features={},
        )
        params = detector.get_trading_parameters(state)
        assert params['preferred_strategy'] == 'trend_following'
        assert params['position_size_multiplier'] == 1.2

    def test_trading_params_for_panic(self):
        try:
            from engines.regime_detector import RegimeDetector, MarketRegime, RegimeState
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        from datetime import datetime, timezone
        detector = RegimeDetector()
        state = RegimeState(
            regime=MarketRegime.PANIC,
            confidence=0.9,
            volatility=0.05,
            trend_strength=0.01,
            timestamp=datetime.now(timezone.utc),
            features={},
        )
        params = detector.get_trading_parameters(state)
        assert params['preferred_strategy'] == 'defensive'
        assert params['position_size_multiplier'] == 0.3

    def test_trading_params_for_ranging(self):
        try:
            from engines.regime_detector import RegimeDetector, MarketRegime, RegimeState
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        from datetime import datetime, timezone
        detector = RegimeDetector()
        state = RegimeState(
            regime=MarketRegime.RANGING,
            confidence=0.7,
            volatility=0.005,
            trend_strength=0.001,
            timestamp=datetime.now(timezone.utc),
            features={},
        )
        params = detector.get_trading_parameters(state)
        assert params['preferred_strategy'] == 'mean_reversion'

    def test_all_regimes_have_trading_params(self):
        try:
            from engines.regime_detector import RegimeDetector, MarketRegime, RegimeState
        except ImportError:
            pytest.skip("regime_detector has unmet dependency (numpy)")
            return
        from datetime import datetime, timezone
        detector = RegimeDetector()
        for regime in MarketRegime:
            state = RegimeState(
                regime=regime,
                confidence=0.5,
                volatility=0.01,
                trend_strength=0.01,
                timestamp=datetime.now(timezone.utc),
                features={},
            )
            params = detector.get_trading_parameters(state)
            assert 'position_size_multiplier' in params
            assert 'preferred_strategy' in params


# ══════════════════════════════════════════════════════════════════════════════
# Opportunity Scanner Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOpportunityScanner:
    """Tests for the opportunity scanner engine."""

    def test_creation(self):
        from engines.opportunity_scanner import OpportunityScanner
        scanner = OpportunityScanner()
        assert scanner.max_opportunities == 50
        assert len(scanner.get_active()) == 0

    def test_ingest_tick_stores_data(self):
        from engines.opportunity_scanner import OpportunityScanner
        scanner = OpportunityScanner()
        scanner.ingest_tick("BTCUSD", 50000.0, 100.0)
        assert "BTCUSD" in scanner._price_buffer
        assert len(scanner._price_buffer["BTCUSD"]) == 1

    def test_momentum_spike_detection(self):
        from engines.opportunity_scanner import OpportunityScanner, OpportunityType
        scanner = OpportunityScanner(momentum_threshold=0.01)

        # Feed stable prices, then a spike
        for i in range(20):
            scanner.ingest_tick("BTCUSD", 50000.0, 100.0)
        for i in range(5):
            scanner.ingest_tick("BTCUSD", 51500.0, 150.0)  # 3% spike

        opps = scanner.scan("BTCUSD")
        momentum_opps = [o for o in opps if o.type == OpportunityType.MOMENTUM_SPIKE]
        assert len(momentum_opps) >= 1
        assert momentum_opps[0].direction == "long"

    def test_whale_signal_registration(self):
        from engines.opportunity_scanner import OpportunityScanner, OpportunityType
        scanner = OpportunityScanner()
        scanner.add_whale_signal("BTCUSD", "inflow", 5_000_000, 0.8)
        active = scanner.get_active()
        assert len(active) == 1
        assert active[0].type == OpportunityType.WHALE_TRANSACTION

    def test_orderbook_imbalance_signal(self):
        from engines.opportunity_scanner import OpportunityScanner, OpportunityType
        scanner = OpportunityScanner(imbalance_threshold=0.2)
        scanner.add_orderbook_signal("BTCUSD", 0.5, 0.001)
        active = scanner.get_active()
        assert len(active) == 1
        assert active[0].type == OpportunityType.ORDERBOOK_IMBALANCE
        assert active[0].direction == "long"

    def test_low_confidence_whale_ignored(self):
        from engines.opportunity_scanner import OpportunityScanner
        scanner = OpportunityScanner()
        scanner.add_whale_signal("BTCUSD", "inflow", 1000, 0.2)
        assert len(scanner.get_active()) == 0

    def test_summary_format(self):
        from engines.opportunity_scanner import OpportunityScanner
        scanner = OpportunityScanner()
        scanner.add_whale_signal("BTCUSD", "outflow", 10_000_000, 0.9)
        summary = scanner.get_summary()
        assert "total_active" in summary
        assert "by_type" in summary
        assert "top_opportunities" in summary
        assert summary["total_active"] >= 1

    def test_deduplication(self):
        from engines.opportunity_scanner import OpportunityScanner, OpportunityType
        scanner = OpportunityScanner()
        scanner.add_whale_signal("BTCUSD", "inflow", 5_000_000, 0.8)
        scanner.add_whale_signal("BTCUSD", "outflow", 8_000_000, 0.9)
        # Same type+symbol → deduplicated to latest
        whale_opps = [o for o in scanner.get_active() if o.type == OpportunityType.WHALE_TRANSACTION]
        assert len(whale_opps) == 1
        assert whale_opps[0].details["value_usd"] == 8_000_000


# ══════════════════════════════════════════════════════════════════════════════
# Capital Efficiency Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalEfficiency:
    """Tests for the capital efficiency engine."""

    def test_evaluate_bot_positive(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        m = engine.evaluate_bot("bot-1", profit_pct=0.02, hold_seconds=3600, capital_allocated=1000)
        assert m.efficiency_score == pytest.approx(0.02, abs=0.001)  # 2%/hr

    def test_evaluate_bot_low_efficiency(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        m = engine.evaluate_bot("bot-2", profit_pct=0.001, hold_seconds=7200, capital_allocated=500)
        assert m.efficiency_score < 0.001

    def test_should_exit_idle(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        engine.evaluate_bot("bot-idle", profit_pct=0.005, hold_seconds=8000, capital_allocated=1000)
        assert engine.should_exit("bot-idle") is True

    def test_should_not_exit_profitable(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        engine.evaluate_bot("bot-good", profit_pct=0.05, hold_seconds=1800, capital_allocated=1000)
        assert engine.should_exit("bot-good") is False

    def test_evaluate_all_ranking(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        bots = [
            {"bot_id": "a", "profit_pct": 0.01, "hold_seconds": 3600},
            {"bot_id": "b", "profit_pct": 0.04, "hold_seconds": 3600},
            {"bot_id": "c", "profit_pct": 0.005, "hold_seconds": 7200},
        ]
        results = engine.evaluate_all(bots)
        assert results[0].bot_id == "b"  # highest efficiency
        assert results[0].rank == 1

    def test_reallocation_suggestions(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        bots = [
            {"bot_id": f"bot-{i}", "profit_pct": 0.01 * (i + 1), "hold_seconds": 3600}
            for i in range(8)
        ]
        engine.evaluate_all(bots)
        suggestions = engine.get_reallocation_suggestions()
        assert "increase_capital" in suggestions
        assert "decrease_capital" in suggestions

    def test_summary_format(self):
        from engines.capital_efficiency import CapitalEfficiencyEngine
        engine = CapitalEfficiencyEngine()
        engine.evaluate_bot("bot-x", profit_pct=0.02, hold_seconds=1800, capital_allocated=500)
        summary = engine.get_summary()
        assert "avg_efficiency" in summary
        assert "best_bot" in summary
        assert "idle_count" in summary


# ══════════════════════════════════════════════════════════════════════════════
# Time Decay Exit Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTimeDecayExit:
    """Tests for the time decay exit engine."""

    def test_scalper_not_exit_early(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        result = engine.evaluate("bot-1", "scalper", hold_seconds=30, profit_pct=0.003)
        assert result.should_exit is False

    def test_scalper_exit_on_time_decay(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        result = engine.evaluate("bot-2", "scalper", hold_seconds=150, profit_pct=0.001)
        assert result.should_exit is True
        assert "time_decay" in result.exit_reason

    def test_scalper_max_hold_force_exit(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        result = engine.evaluate("bot-3", "scalper", hold_seconds=400, profit_pct=0.01)
        assert result.should_exit is True
        assert "max_hold" in result.exit_reason

    def test_normal_bot_hold_ok(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        result = engine.evaluate("bot-4", "normal", hold_seconds=1800, profit_pct=0.01)
        assert result.should_exit is False

    def test_normal_bot_extended_no_profit(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        result = engine.evaluate("bot-5", "normal", hold_seconds=6000, profit_pct=-0.001)
        assert result.should_exit is True

    def test_decay_factor_increases_with_time(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        r1 = engine.evaluate("bot-6a", "normal", hold_seconds=600, profit_pct=0.005)
        r2 = engine.evaluate("bot-6b", "normal", hold_seconds=3600, profit_pct=0.005)
        assert r2.decay_factor > r1.decay_factor

    def test_adjusted_target_shrinks(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        r1 = engine.evaluate("bot-7a", "normal", hold_seconds=100, profit_pct=0.005)
        r2 = engine.evaluate("bot-7b", "normal", hold_seconds=3500, profit_pct=0.005)
        assert r2.adjusted_target_pct < r1.adjusted_target_pct

    def test_batch_evaluation(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        positions = [
            {"bot_id": "b1", "bot_class": "scalper", "hold_seconds": 30, "profit_pct": 0.005},
            {"bot_id": "b2", "bot_class": "scalper", "hold_seconds": 200, "profit_pct": 0.001},
            {"bot_id": "b3", "bot_class": "normal", "hold_seconds": 7200, "profit_pct": 0.01},
        ]
        results = engine.evaluate_batch(positions)
        assert len(results) == 3
        # b2 should exit (scalper held too long with tiny profit)
        b2_result = [r for r in results if r.bot_id == "b2"][0]
        assert b2_result.should_exit is True

    def test_summary_format(self):
        from engines.time_decay_exit import TimeDecayExitEngine
        engine = TimeDecayExitEngine()
        positions = [
            {"bot_id": "b1", "bot_class": "scalper", "hold_seconds": 200, "profit_pct": 0.001},
        ]
        summary = engine.get_summary(positions)
        assert "total_positions" in summary
        assert "exit_recommended" in summary
        assert summary["exit_recommended"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Radar Enhancement Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRadarEnhancements:
    """Tests for enhanced radar fields."""

    def test_radar_entry_has_intelligence_fields(self):
        """Verify _compute_radar_entry includes new intelligence fields."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        bot = {
            "_id": "test-bot-123",
            "bot_type": "scalper",
            "name": "TestBot",
            "exchange": "binance",
            "pair": "BTCUSDT",
            "risk_mode": "balanced",
            "current_capital": 1000,
            "market_regime": "trending",
            "confidence_score": 0.85,
            "strategy": "momentum_scalping",
        }
        now = datetime.now(timezone.utc)
        entry = _compute_radar_entry(bot, None, now)

        assert entry["confidence_score"] == 0.85
        assert entry["strategy_name"] == "momentum_scalping"
        assert entry["regime_tag"] == "trending"
        assert entry["capital_allocated"] == 1000
        assert entry["exposure_pct"] == 0.0
        assert entry["hold_timer_display"] is None  # no open trade

    def test_radar_hold_timer_format(self):
        try:
            from routes.radar import _format_hold_timer
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        assert _format_hold_timer(45) == "45s"
        assert _format_hold_timer(125) == "2m 5s"
        assert _format_hold_timer(7500) == "2h 5m"

    def test_radar_exit_forecast(self):
        try:
            from routes.radar import _compute_exit_forecast
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        # Close to target
        assert _compute_exit_forecast(100, 109, 110, 95, 3600, 9) == "likely_target"
        # Time running out
        assert _compute_exit_forecast(100, 101, 110, 95, 300, 1) == "likely_time_exit"
        # Losing money
        assert _compute_exit_forecast(100, 97, 110, 95, 3600, -3) == "at_risk"
        # Stable hold
        assert _compute_exit_forecast(100, 102, 110, 95, 3600, 2) == "likely_target"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Meta-Controller Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPortfolioMetaController:
    """Tests for the PortfolioMetaController engine."""

    def test_default_decision(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        out = mc.decide(MetaControllerInput())
        # Default regime is 'unknown' -> balanced-ish
        assert 0.0 <= out.scalper_weight <= 1.0
        assert 0.0 <= out.normal_weight <= 1.0
        assert abs(out.scalper_weight + out.normal_weight - 1.0) < 0.01
        assert out.risk_multiplier > 0

    def test_trending_regime_favours_normal(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        out = mc.decide(MetaControllerInput(market_regime="trending"))
        assert out.normal_weight > out.scalper_weight

    def test_ranging_regime_favours_scalper(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        out = mc.decide(MetaControllerInput(market_regime="ranging"))
        assert out.scalper_weight > out.normal_weight

    def test_panic_regime_defensive(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        out = mc.decide(MetaControllerInput(market_regime="panic"))
        assert out.risk_multiplier < 0.6
        assert out.preferred_bot_class == "normal"

    def test_scalper_priority_mode(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        base = mc.decide(MetaControllerInput(market_regime="ranging"))
        boosted = mc.decide(MetaControllerInput(market_regime="ranging", scalper_priority_mode=True))
        assert boosted.scalper_weight >= base.scalper_weight

    def test_high_drawdown_increases_scalper_weight(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        normal = mc.decide(MetaControllerInput(market_regime="trending", current_drawdown=0.01))
        stressed = mc.decide(MetaControllerInput(market_regime="trending", current_drawdown=0.08))
        assert stressed.scalper_weight >= normal.scalper_weight
        assert stressed.risk_multiplier <= normal.risk_multiplier

    def test_get_summary_returns_all_fields(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        summary = mc.get_summary(MetaControllerInput(market_regime="volatile"))
        required_keys = {
            "preferred_bot_class", "scalper_weight", "normal_weight",
            "exchange_exposure_limit", "pair_exposure_limit",
            "risk_multiplier", "hold_time_profile", "reasoning", "timestamp",
        }
        assert required_keys.issubset(set(summary.keys()))

    def test_all_regimes_produce_valid_output(self):
        from engines.portfolio_meta_controller import (
            PortfolioMetaController, MetaControllerInput,
        )
        mc = PortfolioMetaController()
        for regime in [
            "trending", "ranging", "volatile", "low_volatility",
            "panic", "accumulation", "bullish_calm", "bearish_volatile",
            "squeeze", "unknown",
        ]:
            out = mc.decide(MetaControllerInput(market_regime=regime))
            assert 0.0 <= out.scalper_weight <= 1.0
            assert 0.0 <= out.normal_weight <= 1.0
            assert 0.1 <= out.risk_multiplier <= 2.0
            assert out.hold_time_profile in ("ultra_short", "short", "medium", "long")


# ══════════════════════════════════════════════════════════════════════════════
# Order Flow Engine Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderFlowEngine:
    """Tests for the OrderFlowEngine microstructure scoring."""

    def test_empty_state(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        score = ofe.compute_score("BTCUSDT")
        # With no data: spread=0 contributes a small positive signal (0.2)
        assert -1.0 <= score.score <= 1.0
        assert score.confidence == 0.0

    def test_ingest_orderbook_and_compute(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        ofe.ingest_orderbook("BTCUSDT",
            bids=[[50000, 1.0], [49990, 2.0]],
            asks=[[50010, 0.5], [50020, 1.5]],
        )
        imb = ofe.compute_liquidity_imbalance("BTCUSDT")
        # More bids (3.0) than asks (2.0) -> positive imbalance
        assert imb > 0

    def test_aggressive_ratio_balanced(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        for i in range(50):
            ofe.ingest_trade("BTCUSDT", 50000 + i, 0.1, "buy" if i % 2 == 0 else "sell")
        ratio = ofe.compute_aggressive_ratio("BTCUSDT")
        assert 0.4 <= ratio <= 0.6

    def test_spread_calculation(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        ofe.ingest_orderbook("ETHUSDT",
            bids=[[3000, 5.0]],
            asks=[[3003, 5.0]],
        )
        spread = ofe.compute_spread("ETHUSDT")
        assert 0.09 < spread < 0.11  # ~0.1%

    def test_liquidity_vacuum_detection(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        # Create a gap > 0.5% between levels
        ofe.ingest_orderbook("BTCUSDT",
            bids=[[50000, 1.0], [49500, 1.0]],   # 1% gap
            asks=[[50010, 1.0], [50020, 1.0]],
        )
        assert ofe.detect_liquidity_vacuum("BTCUSDT") is True

    def test_composite_score_range(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        ofe.ingest_orderbook("BTCUSDT",
            bids=[[50000, 2.0], [49999, 3.0]],
            asks=[[50001, 1.0], [50002, 1.0]],
        )
        for i in range(30):
            ofe.ingest_trade("BTCUSDT", 50000, 0.1, "buy")
        score = ofe.compute_score("BTCUSDT")
        assert -1.0 <= score.score <= 1.0
        assert 0 <= score.confidence <= 1.0

    def test_get_summary(self):
        from engines.order_flow_engine import OrderFlowEngine
        ofe = OrderFlowEngine()
        ofe.ingest_orderbook("BTCUSDT", bids=[[50000, 1.0]], asks=[[50010, 1.0]])
        summary = ofe.get_summary()
        assert "symbols_tracked" in summary
        assert "scores" in summary
        assert "BTCUSDT" in summary["scores"]


# ══════════════════════════════════════════════════════════════════════════════
# Risk Management Drawdown Cap Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskDrawdownCap:
    """Verify drawdown is always clamped to [0.0, 1.0]."""

    def test_drawdown_capped_at_100_percent(self):
        try:
            from engines.risk_management import RiskManager
        except ImportError:
            pytest.skip("risk_management has unmet dependency")
            return
        # If equity goes deeply negative, drawdown must not exceed 1.0
        dd = RiskManager.compute_drawdown(current_equity=-500, peak_equity=1000)
        assert dd <= 1.0
        assert dd == 1.0  # capped

    def test_drawdown_zero_when_at_peak(self):
        try:
            from engines.risk_management import RiskManager
        except ImportError:
            pytest.skip("risk_management has unmet dependency")
            return
        dd = RiskManager.compute_drawdown(current_equity=1000, peak_equity=1000)
        assert dd == 0.0

    def test_drawdown_positive_when_below_peak(self):
        try:
            from engines.risk_management import RiskManager
        except ImportError:
            pytest.skip("risk_management has unmet dependency")
            return
        dd = RiskManager.compute_drawdown(current_equity=800, peak_equity=1000)
        assert dd == pytest.approx(0.2, abs=0.001)
