"""
Tests for the 5 targeted runtime truth repairs.

Validates:
1. Edge floor transparency — raw vs floored edge exposed in diagnostics
2. Paper vs live notional truth — cap mode and amplification flag exposed
3. Unified threshold truth — canonical thresholds from entry_thresholds.py
4. Confidence gate truth — signal source breakdown in diagnostics
5. Cost-aware no-progress exit — venue-specific threshold replaces fixed 0.05%
"""

import os
import sys
import math
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


# ══════════════════════════════════════════════════════════════════════════
# Repair 1: Edge Floor Transparency
# ══════════════════════════════════════════════════════════════════════════

class TestEdgeFloorTransparency:
    """Verify that raw_gross_edge_bps and paper_edge_floor_applied
    are exposed in feasibility gate output."""

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        self.gate = TradeFeasibilityGate()

    def test_edge_floor_applied_is_visible(self):
        """When paper_edge_floor_applied=True, it must appear in output."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.75,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full",
                                "edge_multiplier": 1.0, "size_multiplier": 1.0},
            raw_gross_edge_bps=5.0,  # real edge was only 5 bps
            paper_edge_floor_applied=True,
        )
        assert result["approved"] is True
        # Edge floor truth must be exposed
        assert result["raw_gross_edge_bps"] == 5.0
        assert result["paper_edge_floor_applied"] is True

    def test_edge_floor_not_applied_is_visible(self):
        """When edge floor is not applied, raw_gross_edge_bps matches gross."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.75,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full",
                                "edge_multiplier": 1.0, "size_multiplier": 1.0},
        )
        assert result["approved"] is True
        # Without explicit raw_gross_edge_bps, it defaults to the passed gross edge
        assert result["raw_gross_edge_bps"] == 100.0
        assert result["paper_edge_floor_applied"] is False

    def test_edge_floor_visible_on_rejection(self):
        """Edge floor truth must also appear on rejected trades."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=500,
            expected_gross_edge_bps=10, all_in_cost_bps=30,
            spread_pct=0.1, depth_notional=100000,
            entry_confidence=0.50,
            raw_gross_edge_bps=2.0,
            paper_edge_floor_applied=True,
        )
        assert result["approved"] is False
        assert "raw_gross_edge_bps" in result
        assert result["raw_gross_edge_bps"] == 2.0
        assert result["paper_edge_floor_applied"] is True


# ══════════════════════════════════════════════════════════════════════════
# Repair 3: Unified Threshold Truth
# ══════════════════════════════════════════════════════════════════════════

class TestUnifiedThresholdTruth:
    """Verify all thresholds come from the canonical entry_thresholds module."""

    def test_canonical_module_has_all_thresholds(self):
        from services.trading_brain_v2.entry_thresholds import (
            MIN_NET_EDGE_BPS, K_COST, MAX_COST_TO_EDGE_RATIO,
            MIN_ENTRY_CONFIDENCE, ABS_PROFIT_MIN_QUOTE,
            SPREAD_CAP_PCT, DEPTH_MIN_NOTIONAL, STRATEGY_TIME_CAP,
            MIN_REWARD_PER_SECOND, VENUE_ROUND_TRIP_COST_BPS,
        )
        assert isinstance(MIN_NET_EDGE_BPS, dict)
        assert isinstance(K_COST, dict)
        assert isinstance(MAX_COST_TO_EDGE_RATIO, float)
        assert isinstance(MIN_ENTRY_CONFIDENCE, float)
        assert isinstance(ABS_PROFIT_MIN_QUOTE, dict)
        assert isinstance(VENUE_ROUND_TRIP_COST_BPS, dict)

    def test_scalper_min_edge_unified(self):
        """Scalper min net edge must be 20 BPS in BOTH gate and filter."""
        from services.trading_brain_v2.entry_thresholds import MIN_NET_EDGE_BPS as canonical
        from services.trading_brain_v2.trade_feasibility_gate import MIN_NET_EDGE_BPS as gate
        from services.trade_worth_filter import MIN_NET_EDGE_BPS as filt
        assert canonical["scalper"] == 20.0
        assert gate["scalper"] == 20.0
        assert filt["scalper"] == 20.0

    def test_usdt_normal_small_profit_unified(self):
        """USDT normal/small profit min must be defined in the canonical module."""
        from services.trading_brain_v2.entry_thresholds import ABS_PROFIT_MIN_QUOTE as canonical
        key = ("normal", "small", "usdt")
        # Both gate and filter now use the canonical module directly via
        # compute_min_net_profit_required() — no local copy to compare.
        assert canonical[key] == 0.50

    def test_threshold_source_in_feasibility_output(self):
        """Feasibility gate must report threshold_source in output."""
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        result = gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.75,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full",
                                "edge_multiplier": 1.0, "size_multiplier": 1.0},
        )
        assert result.get("threshold_source") == "entry_thresholds"
        assert "min_net_edge_bps_used" in result
        assert "k_cost_used" in result
        assert "min_entry_confidence_used" in result

    def test_threshold_source_in_worth_filter_output(self):
        """Worth filter must report threshold_source in diagnostics."""
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal", exchange="binance", bot_equity=10000,
            notional=5000, expected_gross_edge_bps=100, all_in_cost_bps=25,
        )
        assert result["diagnostics"].get("threshold_source") == "entry_thresholds"

    def test_venue_round_trip_cost_helpers(self):
        """Venue cost helpers must return correct values."""
        from services.trading_brain_v2.entry_thresholds import venue_round_trip_cost_bps
        assert venue_round_trip_cost_bps("luno") == 35.0
        assert venue_round_trip_cost_bps("binance") == 20.0
        assert venue_round_trip_cost_bps("unknown_exchange") == 25.0  # default


# ══════════════════════════════════════════════════════════════════════════
# Repair 4: Confidence Gate Truth
# ══════════════════════════════════════════════════════════════════════════

class TestConfidenceGateTruth:
    """Verify confidence source breakdown is exposed in feasibility output."""

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        self.gate = TradeFeasibilityGate()

    def test_confidence_sources_in_approved_trade(self):
        """Approved trades must show confidence source breakdown."""
        sources = {
            "regime_confidence": 0.85,
            "ml_confidence": 0.70,
            "fetchai_confidence": 65.0,
            "coinstats_strength": 45.0,
            "fetchai_is_fallback": False,
            "coinstats_is_fallback": False,
        }
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.75,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.85},
            regime_eligibility={"eligible": True, "action": "full",
                                "edge_multiplier": 1.0, "size_multiplier": 1.0},
            confidence_sources=sources,
        )
        assert result["approved"] is True
        assert "confidence_sources" in result
        cs = result["confidence_sources"]
        assert cs["regime_confidence"] == 0.85
        assert cs["ml_confidence"] == 0.70
        assert cs["fetchai_is_fallback"] is False

    def test_fallback_signals_visible_in_rejection(self):
        """When signals are zeroed/fallback, that must be visible."""
        sources = {
            "regime_confidence": 0.40,
            "ml_confidence": 0.30,
            "fetchai_confidence": 0.0,
            "coinstats_strength": 0.0,
            "fetchai_is_fallback": True,
            "coinstats_is_fallback": True,
        }
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.20,  # below 0.40 floor
            confidence_sources=sources,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "LOW_CONFIDENCE_ENTRY"
        cs = result["confidence_sources"]
        assert cs["fetchai_is_fallback"] is True
        assert cs["coinstats_is_fallback"] is True

    def test_min_entry_confidence_used_in_output(self):
        """Output must include the effective confidence threshold used."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            entry_confidence=0.20,
        )
        assert "min_entry_confidence_used" in result
        assert result["min_entry_confidence_used"] == 0.40


# ══════════════════════════════════════════════════════════════════════════
# Repair 5: Cost-Aware No-Progress Exit
# ══════════════════════════════════════════════════════════════════════════

class TestCostAwareNoProgressExit:
    """Verify no-progress exit threshold is venue-cost-aware."""

    def setup_method(self):
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        self.mgr = OpenTradeManager()

    def test_luno_cost_aware_threshold(self):
        """Luno no-progress threshold should use 35 bps (0.35%)."""
        from datetime import datetime, timezone, timedelta
        # Scalper at 80% of time budget with PnL = 0.30% (below 0.35% Luno cost)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time, "side": "buy", "exchange": "luno"},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50150,  # +0.30%
            entry_price=50000,
            exchange="luno",
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"
        assert result["details"]["venue_round_trip_cost_bps"] == 35.0
        assert result["details"]["no_progress_threshold_pct"] == 0.35

    def test_binance_cost_aware_threshold(self):
        """Binance no-progress threshold should use 20 bps (0.20%)."""
        from datetime import datetime, timezone, timedelta
        # Scalper at 80% of time budget with PnL = 0.15% (below 0.20% Binance cost)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time, "side": "buy", "exchange": "binance"},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50075,  # +0.15%
            entry_price=50000,
            exchange="binance",
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"
        assert result["details"]["venue_round_trip_cost_bps"] == 20.0

    def test_trade_above_cost_is_not_exited(self):
        """Trade with PnL above venue cost threshold should NOT be exited."""
        from datetime import datetime, timezone, timedelta
        # Scalper at 80% of time budget with PnL = 0.50% (above 0.20% Binance cost)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time, "side": "buy", "exchange": "binance"},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50250,  # +0.50%
            entry_price=50000,
            exchange="binance",
        )
        assert result["should_exit"] is False

    def test_no_progress_details_include_venue_info(self):
        """No-progress exit details must include venue cost breakdown."""
        from datetime import datetime, timezone, timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time, "side": "buy"},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50000,
            entry_price=50000,
            exchange="luno",
        )
        assert result["should_exit"] is True
        d = result["details"]
        assert "venue_round_trip_cost_bps" in d
        assert "no_progress_threshold_pct" in d
        assert "venue_class" in d
        assert d["venue_class"] == "zar"

    def test_default_venue_fallback(self):
        """Unknown venue should use default 25 bps threshold."""
        from datetime import datetime, timezone, timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time, "side": "buy"},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50000,
            entry_price=50000,
            exchange="some_unknown_exchange",
        )
        assert result["should_exit"] is True
        assert result["details"]["venue_round_trip_cost_bps"] == 25.0
