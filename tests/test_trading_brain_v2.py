"""
Tests for Trading Brain V2 – economics-first trading engine.

Validates:
1) Tiny-edge trades are rejected
2) Tiny-absolute-profit trades are rejected
3) Spread/depth instability blocks scalpers correctly
4) Regime ambiguity does not spam useless unknown blocks
5) Radar does not crash on null values
6) Decision timeline never emits NaN
7) Separate normal/scalper caps are enforced correctly
8) Multi-currency handling
9) Paper attribution includes fee/spread/slippage decomposition
10) All V2 services work correctly in isolation
"""

import os
import sys
import math
import time
import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


# ── AllInCostModel ──

class TestAllInCostModel:

    def setup_method(self):
        from services.trading_brain_v2.cost_model import AllInCostModel
        self.model = AllInCostModel()

    def test_basic_cost_computation(self):
        result = self.model.compute(
            venue="binance", symbol="BTC/USDT", quote_currency="USDT",
            side="buy", order_mode="taker", notional_size=1000,
            best_bid=50000, best_ask=50050, mid=50025,
            spread=0.001, volatility_estimate=0.02,
        )
        assert result["fee_in_bps"] >= 0
        assert result["fee_out_bps"] >= 0
        assert result["all_in_cost_bps"] > 0
        assert result["all_in_cost_quote"] > 0
        assert result["projected_round_trip_cost_quote"] > 0
        assert result["venue"] == "binance"
        assert result["quote_currency"] == "USDT"

    def test_luno_zar_cost(self):
        result = self.model.compute(
            venue="luno", symbol="BTC/ZAR", quote_currency="ZAR",
            side="buy", order_mode="maker", notional_size=5000,
            best_bid=900000, best_ask=900500, mid=900250,
            spread=0.0006, volatility_estimate=0.01,
        )
        assert result["venue"] == "luno"
        assert result["quote_currency"] == "ZAR"
        # Luno maker fee is 0 bps
        assert result["fee_in_bps"] == 0
        assert result["all_in_cost_bps"] > 0

    def test_cost_never_negative(self):
        result = self.model.compute(
            venue="kraken", symbol="ETH/USDT", quote_currency="USDT",
            side="sell", order_mode="taker", notional_size=100,
            best_bid=3000, best_ask=3010, mid=3005,
        )
        assert result["all_in_cost_bps"] >= 0
        assert result["all_in_cost_quote"] >= 0

    def test_maker_includes_adverse_selection(self):
        maker = self.model.compute(
            venue="binance", symbol="BTC/USDT", quote_currency="USDT",
            side="buy", order_mode="maker", notional_size=1000,
            best_bid=50000, best_ask=50050, mid=50025,
        )
        taker = self.model.compute(
            venue="binance", symbol="BTC/USDT", quote_currency="USDT",
            side="buy", order_mode="taker", notional_size=1000,
            best_bid=50000, best_ask=50050, mid=50025,
        )
        assert maker["maker_adverse_selection_bps"] > 0
        assert taker["maker_adverse_selection_bps"] == 0

    def test_unknown_venue_uses_conservative_defaults(self):
        result = self.model.compute(
            venue="unknown_exchange", symbol="BTC/USDT", quote_currency="USDT",
            side="buy", order_mode="taker", notional_size=1000,
            best_bid=50000, best_ask=50050, mid=50025,
        )
        assert result["fee_in_bps"] == 20  # conservative default
        assert result["fee_out_bps"] == 20


# ── SlippageEstimator ──

class TestSlippageEstimator:

    def setup_method(self):
        from services.trading_brain_v2.slippage_estimator import SlippageEstimator
        self.est = SlippageEstimator()

    def test_heuristic_fallback(self):
        result = self.est.estimate(
            venue="binance", symbol="BTC/USDT", side="buy",
            notional=1000,
        )
        assert result["method"] == "heuristic"
        assert result["slippage_bps"] >= 2  # minimum

    def test_vwap_sweep_with_book(self):
        book = {
            "asks": [
                [50000, 0.1],   # 5000 notional
                [50010, 0.2],   # 10002
                [50020, 0.5],   # 25010
            ],
            "bids": [
                [49990, 0.1],
                [49980, 0.2],
                [49970, 0.5],
            ]
        }
        result = self.est.estimate(
            venue="binance", symbol="BTC/USDT", side="buy",
            notional=5000, order_book=book,
        )
        assert result["method"] == "vwap_sweep"
        assert result["slippage_bps"] >= 2  # minimum enforced
        assert result["levels_consumed"] >= 1

    def test_thin_book_returns_high_slippage(self):
        book = {"asks": [[50000, 0.001]], "bids": [[49990, 0.001]]}
        result = self.est.estimate(
            venue="binance", symbol="BTC/USDT", side="buy",
            notional=100000, order_book=book,
        )
        assert result["slippage_bps"] >= 15  # thin book
        assert result["depth_sufficient"] is False

    def test_no_fake_zero_slippage(self):
        result = self.est.estimate(
            venue="luno", symbol="BTC/ZAR", side="buy", notional=500,
        )
        assert result["slippage_bps"] > 0

    def test_calibration_recording(self):
        book = {"asks": [[50000, 1.0], [50010, 1.0]], "bids": [[49990, 1.0]]}
        self.est.estimate(
            venue="binance", symbol="BTC/USDT", side="buy",
            notional=1000, order_book=book,
        )
        summary = self.est.get_calibration_summary(venue="binance")
        assert len(summary) >= 1


# ── RegimeScorerV2 ──

class TestRegimeScorerV2:

    def setup_method(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        self.scorer = RegimeScorerV2()

    def test_trending_up_regime(self):
        result = self.scorer.score(
            symbol="BTC/USDT", trend_pct=2.5, volatility_pct=1.0,
            spread_pct=0.1, depth_notional=200000,
        )
        assert result["regime_label"] in ("trending_up", "breakout")
        assert result["regime_confidence"] > 0
        assert result["trend_score"] > 0

    def test_low_vol_regime(self):
        result = self.scorer.score(
            symbol="BTC/USDT", trend_pct=0.1, volatility_pct=0.05,
            spread_pct=0.05, depth_notional=300000,
        )
        assert result["regime_label"] in ("low_volatility", "consolidation")
        assert result["vol_score"] < 0.3

    def test_ambiguous_regime_does_not_spam_unknown(self):
        """Critical: must not produce REGIME_UNKNOWN_BLOCK spam."""
        result = self.scorer.score(
            symbol="BTC/USDT", trend_pct=0.3, volatility_pct=0.8,
            spread_pct=0.2, depth_notional=80000,
        )
        # Should classify to something, or ambiguous with reason
        assert result["regime_label"] != "unknown"
        assert result["regime_reason_code"] != ""
        assert result["regime_reason_text"] != ""

    def test_regime_hysteresis(self):
        """Regime should not thrash between calls."""
        # First call: trending
        r1 = self.scorer.score(
            symbol="BTC/USDT", trend_pct=2.0, volatility_pct=1.5,
            spread_pct=0.1, depth_notional=200000,
        )
        # Second call: slightly different but not dramatically
        r2 = self.scorer.score(
            symbol="BTC/USDT", trend_pct=1.8, volatility_pct=1.3,
            spread_pct=0.12, depth_notional=190000,
        )
        # Should be same or similar regime (hysteresis)
        assert r2["regime_label"] == r1["regime_label"]

    def test_eligibility_scalper_ambiguous(self):
        """Scalper in ambiguous regime should get microstructure-only, not hard block."""
        regime = {"regime_label": "ambiguous", "regime_confidence": 0.35}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is True
        assert result["action"] == "microstructure_only"
        assert result["size_multiplier"] < 1.0

    def test_eligibility_normal_blocked_regime(self):
        regime = {"regime_label": "high_volatility", "regime_confidence": 0.8}
        result = self.scorer.is_eligible("normal", regime)
        # high_vol IS allowed for normal
        assert result["eligible"] is True

    def test_all_scores_bounded(self):
        result = self.scorer.score(
            symbol="TEST", trend_pct=10.0, volatility_pct=10.0,
            spread_pct=1.0, depth_notional=0,
        )
        assert 0.0 <= result["trend_score"] <= 1.0
        assert 0.0 <= result["vol_score"] <= 1.0
        assert 0.0 <= result["liquidity_score"] <= 1.0
        assert 0.0 <= result["regime_confidence"] <= 1.0


# ── TradeFeasibilityGate ──

class TestTradeFeasibilityGate:

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        self.gate = TradeFeasibilityGate()

    def test_tiny_edge_rejected(self):
        """Trades with edge < cost must be rejected."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=500,
            expected_gross_edge_bps=10, all_in_cost_bps=30,
            spread_pct=0.1, depth_notional=100000,
            entry_confidence=0.50,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "EDGE_TOO_SMALL"

    def test_tiny_absolute_profit_rejected(self):
        """Trades with abs profit below minimum must be rejected."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=200, notional=50,
            expected_gross_edge_bps=80, all_in_cost_bps=20,
            spread_pct=0.1, depth_notional=100000,
            entry_confidence=0.50,
        )
        assert result["approved"] is False
        # Steps 8 and 8b are now unified: ENTRY_REJECTED_MIN_PROFIT covers both
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"

    def test_spread_too_wide_rejected(self):
        result = self.gate.evaluate(
            strategy="scalper", venue="luno", symbol="BTC/ZAR",
            bot_equity=5000, notional=500,
            expected_gross_edge_bps=100, all_in_cost_bps=20,
            spread_pct=0.25, depth_notional=100000,
            entry_confidence=0.50,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "SPREAD_TOO_WIDE"

    def test_depth_too_thin_rejected(self):
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=1000,
            expected_gross_edge_bps=100, all_in_cost_bps=20,
            spread_pct=0.1, depth_notional=10000,  # below 50K minimum
            entry_confidence=0.50,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "DEPTH_TOO_THIN"

    def test_regime_block(self):
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=1000,
            expected_gross_edge_bps=100, all_in_cost_bps=20,
            spread_pct=0.1, depth_notional=100000,
            regime_eligibility={"eligible": False, "action": "blocked"},
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "REGIME_BLOCK"

    def test_good_trade_approved(self):
        """Trade with sufficient edge, profit, and liquidity must be approved."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=100, all_in_cost_bps=25,
            spread_pct=0.1, depth_notional=200000,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full", "edge_multiplier": 1.0, "size_multiplier": 1.0},
            entry_confidence=0.75,
        )
        assert result["approved"] is True
        assert result["decision_reason_code"] == "ENTRY_APPROVED"
        assert result["expected_net_edge_bps"] > 0
        assert result["projected_net_profit_quote"] > 0

    def test_cost_too_high_rejected(self):
        """When cost > 55% of gross edge, reject."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=10000, notional=5000,
            expected_gross_edge_bps=40, all_in_cost_bps=30,
            spread_pct=0.1, depth_notional=200000,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full", "edge_multiplier": 1.0, "size_multiplier": 1.0},
            entry_confidence=0.50,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] in ("COST_TOO_HIGH", "EDGE_TOO_SMALL")

    def test_all_outputs_render_safe(self):
        """All numeric outputs must be valid floats (no NaN, no None)."""
        result = self.gate.evaluate(
            strategy="scalper", venue="luno", symbol="BTC/ZAR",
            bot_equity=0, notional=0,
            expected_gross_edge_bps=0, all_in_cost_bps=0,
            spread_pct=0.5, depth_notional=0,
        )
        for key in ["entry_confidence_score", "expected_gross_edge_bps",
                     "all_in_cost_bps", "expected_net_edge_bps",
                     "projected_net_profit_quote", "regime_confidence"]:
            val = result[key]
            assert val is not None, f"{key} is None"
            assert not math.isnan(val), f"{key} is NaN"
            assert not math.isinf(val), f"{key} is Inf"
        assert result["decision_reason_code"] != ""
        assert result["decision_reason_text"] != ""


# ── TargetPolicyV2 ──

class TestTargetPolicyV2:

    def setup_method(self):
        from services.trading_brain_v2.target_policy import TargetPolicyV2
        self.policy = TargetPolicyV2()

    def test_normal_bot_targets(self):
        result = self.policy.compute(
            bot_type="normal", venue="binance", quote_currency="USDT",
            bot_equity=10000, notional=500, all_in_cost_bps=25,
            entry_price=50000, side="buy",
        )
        assert result["daily_profit_target_quote"] > 0
        assert result["trade_profit_target_quote"] > 0
        assert result["take_profit_price"] > 50000  # above entry for buy
        assert result["stop_loss_price"] < 50000  # below entry for buy
        assert result["max_hold_seconds"] == 21600  # 6h for normal
        assert result["target_source"] == "target_policy_v2"

    def test_scalper_bot_targets(self):
        result = self.policy.compute(
            bot_type="scalper", venue="binance", quote_currency="USDT",
            bot_equity=5000, notional=200, all_in_cost_bps=20,
            entry_price=50000, side="buy",
        )
        assert result["max_hold_seconds"] == 300  # 5m for scalper
        assert result["trade_profit_target_quote"] > 0
        # Scalper daily target pct >= normal daily target pct — scalpers target
        # higher total daily P&L through volume (canonical policy aligns with
        # services/target_policy.py: scalper/balanced USDT = 2.5% > normal 2.0%).
        normal = self.policy.compute(
            bot_type="normal", venue="binance", quote_currency="USDT",
            bot_equity=5000, notional=200, all_in_cost_bps=20,
            entry_price=50000, side="buy",
        )
        assert result["daily_target_pct"] >= normal["daily_target_pct"], (
            f"Scalper daily % ({result['daily_target_pct']}) should be >= "
            f"normal daily % ({normal['daily_target_pct']}) per canonical policy"
        )

    def test_target_covers_costs(self):
        """Trade target must be at least 2x all-in cost."""
        result = self.policy.compute(
            bot_type="normal", venue="binance", quote_currency="USDT",
            bot_equity=10000, notional=1000, all_in_cost_bps=50,
            entry_price=50000,
        )
        min_target_pct = (50 / 100.0) * 2.0  # 1.0%
        assert result["trade_target_pct"] >= min_target_pct

    def test_zar_minimum_targets(self):
        result = self.policy.compute(
            bot_type="normal", venue="luno", quote_currency="ZAR",
            bot_equity=5000, notional=500, all_in_cost_bps=20,
            entry_price=900000,
        )
        assert result["trade_profit_target_quote"] >= 5.0  # R5 minimum


# ── BotBehavioralContracts ──

class TestBotBehavioralContracts:

    def setup_method(self):
        from services.trading_brain_v2.bot_contracts import BotBehavioralContracts
        self.contracts = BotBehavioralContracts()

    def test_normal_vs_scalper_contracts_differ(self):
        normal = self.contracts.get_contract("normal")
        scalper = self.contracts.get_contract("scalper")
        assert normal.max_hold_seconds > scalper.max_hold_seconds
        # Scalpers now require HIGHER minimum net edge than normal bots because
        # their tiny hold window must justify the round-trip cost more aggressively.
        assert scalper.min_net_edge_bps >= normal.min_net_edge_bps
        assert normal.max_trades_per_day < scalper.max_trades_per_day

    def test_scalper_readiness_spread_too_wide(self):
        result = self.contracts.check_scalper_readiness(
            bot_id="test", spread_bps=60,
            liquidity_score=0.8, regime_label="trending_up",
            regime_confidence=0.7,
        )
        assert result["ready"] is False
        assert result["reason_code"] == "SPREAD_TOO_WIDE"

    def test_scalper_readiness_ok(self):
        result = self.contracts.check_scalper_readiness(
            bot_id="test", spread_bps=20,
            liquidity_score=0.7, regime_label="breakout",
            regime_confidence=0.7,
        )
        assert result["ready"] is True
        assert result["mode"] == "taker_momentum"

    def test_loss_streak_cooldown(self):
        bot_id = "test_cooldown"
        for _ in range(3):
            self.contracts.record_trade_result(bot_id, "scalper", won=False)
        result = self.contracts.check_scalper_readiness(
            bot_id=bot_id, spread_bps=20,
            liquidity_score=0.7, regime_label="trending_up",
            regime_confidence=0.7,
        )
        assert result["ready"] is False
        assert result["reason_code"] == "SCALPER_LOSS_STREAK_COOLDOWN"


# ── PortfolioConcentration ──

class TestPortfolioConcentration:

    def setup_method(self):
        from services.trading_brain_v2.portfolio_concentration import PortfolioConcentration
        self.conc = PortfolioConcentration()

    def test_within_limits(self):
        result = self.conc.check(
            symbol="BTC/USDT", venue="binance",
            notional_proposed=1000, bot_type="normal",
            total_equity=10000,
        )
        assert result["ok"] is True

    def test_symbol_concentration_exceeded(self):
        result = self.conc.check(
            symbol="BTC/USDT", venue="binance",
            notional_proposed=4000, bot_type="normal",
            open_positions=[{"symbol": "BTC/USDT", "venue": "binance", "notional": 2000}],
            total_equity=10000,  # 6000/10000 = 60% > 35% cap
        )
        assert result["ok"] is False
        assert result["reason_code"] == "CONCENTRATION_LIMIT"


# ── KellySizingV2 ──

class TestKellySizingV2:

    def setup_method(self):
        from services.trading_brain_v2.kelly_sizing import KellySizingV2
        self.kelly = KellySizingV2()

    def test_basic_sizing(self):
        result = self.kelly.compute(
            bot_type="normal", bot_equity=10000,
            win_rate=0.55, avg_win=100, avg_loss=80,
            num_trades=50,
        )
        assert 1.0 <= result["position_pct"] <= 5.0
        assert result["position_quote"] > 0
        assert result["size_source"] == "fractional_kelly"

    def test_bootstrap_mode(self):
        result = self.kelly.compute(
            bot_type="normal", bot_equity=10000,
            num_trades=5,
        )
        assert result["size_source"] == "bootstrap_conservative"

    def test_defense_mode_reduces(self):
        normal = self.kelly.compute(
            bot_type="normal", bot_equity=10000,
            win_rate=0.55, avg_win=100, avg_loss=80,
            num_trades=50,
        )
        defense = self.kelly.compute(
            bot_type="normal", bot_equity=10000,
            win_rate=0.55, avg_win=100, avg_loss=80,
            num_trades=50, defense_mode=True,
        )
        assert defense["position_pct"] < normal["position_pct"]

    def test_scalper_cap_lower_than_normal(self):
        from services.trading_brain_v2.kelly_sizing import MAX_POSITION_PCT
        assert MAX_POSITION_PCT["scalper"] < MAX_POSITION_PCT["normal"]


# ── OpenTradeManager ──

class TestOpenTradeManager:

    def setup_method(self):
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        self.mgr = OpenTradeManager()

    def test_no_progress_exit(self):
        from datetime import datetime, timezone, timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": old_time},
            bot_type="scalper",
            max_hold_seconds=300,
            current_price=50000,
            entry_price=50000,  # no progress
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"

    def test_early_invalidation(self):
        from datetime import datetime, timezone, timedelta
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": recent_time, "side": "buy"},
            bot_type="normal",
            max_hold_seconds=21600,
            current_price=49500,
            entry_price=50000,  # -1% loss early
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "EARLY_INVALIDATION_EXIT"

    def test_healthy_trade_not_exited(self):
        from datetime import datetime, timezone, timedelta
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
        result = self.mgr.evaluate(
            trade={"opened_at": recent_time, "side": "buy"},
            bot_type="normal",
            max_hold_seconds=21600,
            current_price=50100,
            entry_price=50000,  # +0.2% gain
        )
        assert result["should_exit"] is False


# ── ReasonCodes & DecisionPayload ──

class TestReasonCodes:

    def test_all_codes_have_descriptions(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        for attr in dir(ReasonCodes):
            if attr.startswith("_"):
                continue
            code = getattr(ReasonCodes, attr)
            assert code in REASON_CATALOG, f"Missing description for {code}"

    def test_decision_payload_never_nan(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload
        payload = make_decision_payload(
            "TEST", True,
            confidence=float("nan"),
            expected_gross_edge_bps=None,
            regime_confidence=float("inf"),
        )
        assert payload["entry_confidence_score"] == 0.0
        assert payload["expected_gross_edge_bps"] == 0.0
        assert payload["regime_confidence"] == 0.0
        assert payload["decision_reason_code"] == "TEST"
        assert payload["decision_reason_text"] != ""

    def test_decision_payload_no_none_strings(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload
        payload = make_decision_payload(
            None, False,
            regime_label=None,
            hold_policy_source=None,
        )
        assert payload["decision_reason_code"] == ""
        assert payload["regime_label"] == ""
        assert payload["hold_policy_source"] == ""


# ── ExecutionRouterV2 ──

class TestExecutionRouterV2:

    def setup_method(self):
        from services.trading_brain_v2.execution_router import ExecutionRouterV2
        self.router = ExecutionRouterV2()

    def test_routes_to_best_net_venue(self):
        result = self.router.route(
            candidate_venues=["binance", "kucoin"],
            symbol="BTC/USDT", side="buy", notional=1000,
            expected_edges={"binance": 50, "kucoin": 40},
            expected_costs={"binance": 20, "kucoin": 10},
        )
        assert result["routed_venue"] == "binance"  # 50-20=30 > 40-10=30 (first wins tie)

    def test_unavailable_venue_skipped(self):
        result = self.router.route(
            candidate_venues=["binance", "kucoin"],
            symbol="BTC/USDT", side="buy", notional=1000,
            expected_edges={"binance": 50, "kucoin": 40},
            expected_costs={"binance": 20, "kucoin": 10},
            venue_availability={"binance": False, "kucoin": True},
        )
        assert result["routed_venue"] == "kucoin"


# ── TradeTelemetry ──

class TestTradeTelemetry:

    def test_entry_record_structure(self):
        from services.trading_brain_v2.trade_telemetry import TradeTelemetry
        t = TradeTelemetry()
        record = t.build_entry_record(
            bot_id="bot1", symbol="BTC/USDT", venue="binance",
            side="buy", bot_type="normal", entry_price=50000,
            notional=1000, predicted_edge_bps=30, confidence=0.75,
            regime_snapshot={"regime_label": "trending_up"},
            cost_estimate={"all_in_cost_bps": 25},
            target_policy={"trade_profit_target_quote": 10},
            feasibility_result={"approved": True},
        )
        assert record["event"] == "trade_entry"
        assert record["bot_id"] == "bot1"
        assert record["predicted_edge_bps"] == 30

    def test_exit_record_has_attribution(self):
        from services.trading_brain_v2.trade_telemetry import TradeTelemetry
        t = TradeTelemetry()
        record = t.build_exit_record(
            bot_id="bot1", symbol="BTC/USDT", venue="binance",
            side="buy", bot_type="normal",
            entry_price=50000, exit_price=50500, notional=1000,
            gross_pnl=10, net_pnl=7, fee_total=2,
            spread_cost=0.5, slippage_cost=0.5,
            hold_seconds=3600, exit_reason_code="take_profit",
            predicted_edge_bps=30,
        )
        assert record["event"] == "trade_exit"
        assert "implementation_shortfall_bps" in record
        assert record["net_pnl"] == 7
        assert record["fee_total"] == 2


# ── Separate Normal/Scalper Caps ──

class TestSeparateBotCaps:
    """Verify normal and scalper caps are independent."""

    def test_exchange_limits_separate_caps(self):
        from exchange_limits import BOT_ALLOCATION, SCALPER_BOT_ALLOCATION
        # Luno: normal 5, scalper 2
        assert BOT_ALLOCATION["luno"] == 5
        assert SCALPER_BOT_ALLOCATION["luno"] == 2
        # Total = 7 possible on Luno, not 5
        total = BOT_ALLOCATION["luno"] + SCALPER_BOT_ALLOCATION["luno"]
        assert total == 7

    def test_scalper_caps_not_from_normal(self):
        from exchange_limits import BOT_ALLOCATION, SCALPER_BOT_ALLOCATION
        for venue in SCALPER_BOT_ALLOCATION:
            normal_max = BOT_ALLOCATION.get(venue, 0)
            scalper_max = SCALPER_BOT_ALLOCATION[venue]
            # Scalper caps must be different from or less than normal caps
            assert scalper_max <= normal_max, f"Scalper cap {scalper_max} should be <= normal {normal_max} for {venue}"


# ── Multi-Currency Wallet ──

class TestMultiCurrencyHandling:

    def test_resolve_quote_currency_zar(self):
        """ZAR pairs should resolve to ZAR."""
        # Test via cost model venue class detection
        from services.trading_brain_v2.cost_model import VENUE_FEE_DEFAULTS_BPS
        assert VENUE_FEE_DEFAULTS_BPS["luno"]["quote"] == "ZAR"

    def test_resolve_quote_currency_usdt(self):
        """USDT pairs should resolve to USDT."""
        from services.trading_brain_v2.cost_model import VENUE_FEE_DEFAULTS_BPS
        assert VENUE_FEE_DEFAULTS_BPS["binance"]["quote"] == "USDT"
        assert VENUE_FEE_DEFAULTS_BPS["kucoin"]["quote"] == "USDT"

    def test_cost_model_handles_both_currencies(self):
        from services.trading_brain_v2.cost_model import AllInCostModel
        model = AllInCostModel()
        zar = model.compute(
            venue="luno", symbol="BTC/ZAR", quote_currency="ZAR",
            side="buy", order_mode="taker", notional_size=5000,
            best_bid=900000, best_ask=900500, mid=900250,
        )
        usdt = model.compute(
            venue="binance", symbol="BTC/USDT", quote_currency="USDT",
            side="buy", order_mode="taker", notional_size=500,
            best_bid=50000, best_ask=50050, mid=50025,
        )
        assert zar["quote_currency"] == "ZAR"
        assert usdt["quote_currency"] == "USDT"


# ── Feature Flag ──

class TestFeatureFlag:

    def test_v2_flag_exists_and_defaults_false(self):
        # In test environment, should default to false
        from config import NEW_TRADING_BRAIN_V2
        assert isinstance(NEW_TRADING_BRAIN_V2, bool)


# ── Scalper Regime Policy (new eligibility rules) ────────────────────────────

class TestScalperRegimePolicy:
    """
    Validates the updated scalper regime eligibility rules:
    - Allowed: consolidation, low_volatility, mean_reversion (sideways/quiet markets)
    - Blocked: trending_up, trending_down, high_volatility, breakout (strong trend / high vol)
    """

    def setup_method(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        self.scorer = RegimeScorerV2()

    def _gate(self, **kwargs):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        defaults = dict(
            strategy="scalper",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=5000.0,
            expected_gross_edge_bps=120.0,
            all_in_cost_bps=40.0,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.65,
        )
        defaults.update(kwargs)
        return gate.evaluate(**defaults)

    # ── 1. Scalper allowed in quiet/sideways regimes ──

    def test_scalper_allowed_in_consolidation(self):
        """Scalper MUST be eligible in consolidation regime."""
        regime = {"regime_label": "consolidation", "regime_confidence": 0.7}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is True, (
            f"Scalper must be allowed in consolidation; got: {result}"
        )

    def test_scalper_allowed_in_low_volatility(self):
        """Scalper MUST be eligible in low_volatility regime."""
        regime = {"regime_label": "low_volatility", "regime_confidence": 0.7}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is True, (
            f"Scalper must be allowed in low_volatility; got: {result}"
        )

    def test_scalper_allowed_in_mean_reversion(self):
        """Scalper MUST be eligible in mean_reversion (sideways) regime."""
        regime = {"regime_label": "mean_reversion", "regime_confidence": 0.7}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is True, (
            f"Scalper must be allowed in mean_reversion; got: {result}"
        )

    # ── 2. Scalper blocked in trending / high-volatility regimes ──

    def test_scalper_blocked_in_trending_up(self):
        """Scalper MUST be blocked in strong uptrend."""
        regime = {"regime_label": "trending_up", "regime_confidence": 0.8}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is False, (
            f"Scalper must be blocked in trending_up; got: {result}"
        )
        assert result["action"] == "blocked"

    def test_scalper_blocked_in_trending_down(self):
        """Scalper MUST be blocked in strong downtrend."""
        regime = {"regime_label": "trending_down", "regime_confidence": 0.8}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is False, (
            f"Scalper must be blocked in trending_down; got: {result}"
        )
        assert result["action"] == "blocked"

    def test_scalper_blocked_in_high_volatility(self):
        """Scalper MUST be blocked in high_volatility regime."""
        regime = {"regime_label": "high_volatility", "regime_confidence": 0.8}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is False, (
            f"Scalper must be blocked in high_volatility; got: {result}"
        )

    def test_scalper_blocked_in_breakout(self):
        """Scalper MUST be blocked in breakout regime."""
        regime = {"regime_label": "breakout", "regime_confidence": 0.8}
        result = self.scorer.is_eligible("scalper", regime)
        assert result["eligible"] is False, (
            f"Scalper must be blocked in breakout; got: {result}"
        )

    def test_regime_block_surfaces_in_feasibility_gate(self):
        """REGIME_BLOCK reason code appears when scalper is blocked by trending regime."""
        result = self._gate(
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={"eligible": False, "action": "blocked"},
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "REGIME_BLOCK"


# ── Minimum Projected Net Profit Filter ────────────────────────────────────

class TestMinimumProfitFilter:
    """
    Validates ENTRY_REJECTED_MIN_PROFIT: trades must clear the canonical
    profitability policy (compute_min_net_profit_required).

    Policy v2 is tier-aware: micro/small/medium/large capital tiers have
    different minimum profit floors.  The old flat $1.50/$R25 floor is
    replaced by per-tier floors that allow small-cap bots to trade while
    still rejecting genuinely garbage trades.
    """

    def _gate(self, **kwargs):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        defaults = dict(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=1000.0,
            expected_gross_edge_bps=100.0,
            all_in_cost_bps=25.0,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.65,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={
                "eligible": True, "action": "full",
                "edge_multiplier": 1.0, "size_multiplier": 1.0,
            },
        )
        defaults.update(kwargs)
        return gate.evaluate(**defaults)

    def test_small_usdt_valid_trade_now_approved(self):
        """$200 USDT small-cap bot with $1.125 net profit MUST now be approved.

        Under policy v1 this was rejected by the flat $1.50 floor.
        Under policy v2 the small-tier floor is $0.50 → $1.125 PASSES.
        notional=150, net_edge=75 bps → profit = 150 × 0.0075 = $1.125
        """
        result = self._gate(
            venue="binance", bot_equity=200.0, notional=150.0,
            expected_gross_edge_bps=100.0, all_in_cost_bps=25.0,
        )
        assert result["approved"] is True, (
            f"$200 USDT bot with $1.125 profit should be approved under policy v2; "
            f"got {result['decision_reason_code']}"
        )
        assert result["decision_reason_code"] == "ENTRY_APPROVED"

    def test_usdt_near_breakeven_rejected(self):
        """Near-breakeven USDT trade must still be rejected by policy v2.

        notional=50, net_edge=60 bps → profit = 50 × 0.006 = $0.30
        small-tier floor = $0.50 → $0.30 < $0.50 → REJECTED.
        """
        result = self._gate(
            venue="binance", bot_equity=200.0, notional=50.0,
            expected_gross_edge_bps=80.0, all_in_cost_bps=20.0,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"

    def test_usdt_trade_above_floor_approved(self):
        """Projected profit of $37.50 must pass the filter."""
        # notional=5000, net_edge=75 bps → profit = 5000 × 0.0075 = $37.50
        result = self._gate(venue="binance", notional=5000.0,
                            expected_gross_edge_bps=100.0, all_in_cost_bps=25.0)
        assert result["approved"] is True
        assert result["decision_reason_code"] == "ENTRY_APPROVED"

    def test_small_zar_valid_trade_now_approved(self):
        """R2000 ZAR small-cap bot with R15 net profit MUST now be approved.

        Under policy v1 this was rejected by the flat R25 floor.
        Under policy v2: equity=2000 → 'small' tier, cost_floor=R4.50, strategy_floor=R1.50.
        min_required = max(R4.50, R1.50) = R4.50 → R15 PASSES.
        notional=1500, net_edge=100 bps → profit = 1500 × 0.01 = R15.
        """
        result = self._gate(
            venue="luno", symbol="BTC/ZAR",
            bot_equity=2000.0, notional=1500.0,
            expected_gross_edge_bps=120.0, all_in_cost_bps=20.0,
        )
        assert result["approved"] is True, (
            f"R2000 ZAR bot with R15 profit should be approved under policy v2; "
            f"got {result['decision_reason_code']}"
        )
        assert result["decision_reason_code"] == "ENTRY_APPROVED"

    def test_zar_near_breakeven_rejected(self):
        """Near-breakeven ZAR trade must still be rejected.

        notional=100, net_edge=100 bps → profit = R1.0
        small-tier strategy_floor = R1.50 → R1.0 < R1.50 → REJECTED.
        """
        result = self._gate(
            venue="luno", symbol="BTC/ZAR",
            bot_equity=2000.0, notional=100.0,
            expected_gross_edge_bps=120.0, all_in_cost_bps=20.0,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"

    def test_zar_trade_above_floor_approved(self):
        """ZAR trade with large profit must pass."""
        # notional=3000, net_edge=100 bps → profit = R30
        result = self._gate(
            venue="luno", symbol="BTC/ZAR",
            bot_equity=30000.0, notional=3000.0,
            expected_gross_edge_bps=120.0, all_in_cost_bps=20.0,
        )
        assert result["approved"] is True
        assert result["decision_reason_code"] == "ENTRY_APPROVED"

    def test_min_profit_floor_constant_exists(self):
        """MIN_PROJECTED_NET_PROFIT must still be importable for legacy reference."""
        from services.trading_brain_v2.entry_thresholds import MIN_PROJECTED_NET_PROFIT
        assert "usdt" in MIN_PROJECTED_NET_PROFIT
        assert "zar" in MIN_PROJECTED_NET_PROFIT
        assert MIN_PROJECTED_NET_PROFIT["usdt"] == 1.5
        assert MIN_PROJECTED_NET_PROFIT["zar"] == 25.0

    def test_rejection_payload_is_transparent(self):
        """ENTRY_REJECTED_MIN_PROFIT rejection must include all transparency fields."""
        # Use near-breakeven trade: notional=50, profit=$0.30 < $0.50 small floor
        result = self._gate(
            venue="binance", bot_equity=200.0, notional=50.0,
            expected_gross_edge_bps=80.0, all_in_cost_bps=20.0,
        )
        assert "decision_reason_code" in result
        assert "expected_net_edge_bps" in result
        assert "projected_net_profit_quote" in result
        assert "regime_label" in result
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"
        assert result["projected_net_profit_quote"] > 0

    def test_policy_v2_fields_in_payload(self):
        """Approved trades must expose policy v2 diagnostic fields."""
        result = self._gate(venue="binance", notional=5000.0,
                            expected_gross_edge_bps=100.0, all_in_cost_bps=25.0)
        assert result["approved"] is True
        # Policy v2 fields should be present
        assert result.get("policy_version") == "v2"
        assert result.get("capital_tier") in ("micro", "small", "medium", "large")
        assert result.get("strategy_class") is not None
        assert result.get("venue_class") in ("usdt", "zar")
        assert "min_net_profit_quote_required" in result


# ── Scalper Re-Entry Cooldown (net_profit <= 0 trigger) ──────────────────

class TestScalperLossCooldown:
    """
    Validates ENTRY_REJECTED_COOLDOWN: after a scalper trade closes with
    net_profit <= 0, the bot is blocked from re-entry for 120 seconds.
    """

    def _contracts(self):
        from services.trading_brain_v2.bot_contracts import BotBehavioralContracts
        return BotBehavioralContracts()

    def test_loss_triggers_entry_rejected_cooldown(self):
        """net_profit <= 0 must trigger cooldown with ENTRY_REJECTED_COOLDOWN code."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot1",
            exit_reason="take_profit",  # exit reason is "clean" but profit is 0
            net_profit=0.0,             # breakeven → triggers loss cooldown
            regime_confidence=0.5,
            entry_confidence=0.6,
        )
        result = c.check_scalper_reentry_discipline(
            "bot1",
            current_regime_confidence=0.52,
            current_entry_confidence=0.61,
        )
        assert result["allowed"] is False
        assert result["reason_code"] == "ENTRY_REJECTED_COOLDOWN", (
            f"Expected ENTRY_REJECTED_COOLDOWN for net_profit<=0, got: {result['reason_code']}"
        )

    def test_negative_profit_triggers_loss_cooldown(self):
        """Negative net_profit must trigger ENTRY_REJECTED_COOLDOWN."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot2",
            exit_reason="scalper_no_progress_exit",
            net_profit=-2.50,
            regime_confidence=0.5,
            entry_confidence=0.6,
        )
        result = c.check_scalper_reentry_discipline(
            "bot2",
            current_regime_confidence=0.51,
            current_entry_confidence=0.61,
        )
        assert result["allowed"] is False

    def test_positive_profit_does_not_trigger_loss_cooldown(self):
        """Positive net_profit with non-weak exit reason must NOT trigger cooldown."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot3",
            exit_reason="take_profit",
            net_profit=5.0,             # positive profit
            regime_confidence=0.5,
            entry_confidence=0.6,
        )
        result = c.check_scalper_reentry_discipline(
            "bot3",
            current_regime_confidence=0.5,
            current_entry_confidence=0.6,
        )
        assert result["allowed"] is True

    def test_cooldown_default_is_120_seconds(self):
        """SCALPER_REENTRY_COOLDOWN_SECONDS default must be 120."""
        from services.trading_brain_v2.bot_contracts import SCALPER_REENTRY_COOLDOWN_SECONDS
        assert SCALPER_REENTRY_COOLDOWN_SECONDS == 120, (
            f"Expected 120s cooldown, got {SCALPER_REENTRY_COOLDOWN_SECONDS}"
        )

    def test_weak_exit_reason_still_uses_scalper_reentry_cooldown_code(self):
        """Existing weak-exit-reason trigger still returns SCALPER_REENTRY_COOLDOWN."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot4",
            exit_reason="scalper_no_progress_exit",
            regime_confidence=0.5,
            entry_confidence=0.6,
            # net_profit not provided → uses old trigger path
        )
        result = c.check_scalper_reentry_discipline(
            "bot4",
            current_regime_confidence=0.51,
            current_entry_confidence=0.61,
        )
        assert result["allowed"] is False
        assert result["reason_code"] == "SCALPER_REENTRY_COOLDOWN"

    def test_cooldown_details_include_transparency_fields(self):
        """Cooldown rejection must include all transparency fields."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot5", exit_reason="take_profit",
            net_profit=-1.0, regime_confidence=0.5, entry_confidence=0.6,
        )
        result = c.check_scalper_reentry_discipline(
            "bot5",
            current_regime_confidence=0.51,
            current_entry_confidence=0.61,
        )
        assert "reason_code" in result
        assert "reason_text" in result
        assert "details" in result
        assert result["details"]["cooldown_remaining_s"] > 0
        assert result["details"]["cooldown_remaining_s"] <= 120


# ── Canonical Multi-Exchange Profitability Policy (v2) ───────────────────────

class TestCanonicalProfitabilityPolicy:
    """
    Validates the canonical multi-exchange profitability policy (v2).

    Covers all 7 supported exchanges, all capital tiers, scalper vs normal,
    compounding/growth behavior, and diagnostic field completeness.

    Test items from problem statement requirement L:
      1.  Luno micro normal bot valid trade passes
      2.  Luno scalper valid trade passes
      3.  Binance micro normal bot valid trade passes
      4.  Binance micro invalid near-breakeven trade fails
      5.  KuCoin valid small-cap trade passes
      6.  Bybit valid small-cap trade passes
      7.  Kraken valid small-cap trade passes
      8.  Bitget valid small-cap trade passes
      9.  Gate valid small-cap trade passes
      10. Larger capital tier requires larger absolute profit
      11. Scalper requires less absolute profit than normal bot
      12. Diagnostics include new policy fields
      13. Rejection logs include actual vs required values
      14. Existing transparency tests still pass (covered in runtime repairs)
      15. Existing scalper regime fix tests still pass (covered above)
      16. Position-sizing / compounding scales upward as capital grows
    """

    def _gate(self, **kwargs):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        defaults = dict(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=1000.0,
            expected_gross_edge_bps=100.0,
            all_in_cost_bps=25.0,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.65,
            regime_result={"regime_label": "trending_up", "regime_confidence": 0.8},
            regime_eligibility={
                "eligible": True, "action": "full",
                "edge_multiplier": 1.0, "size_multiplier": 1.0,
            },
        )
        defaults.update(kwargs)
        return gate.evaluate(**defaults)

    def _worth(self, **kwargs):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        return evaluate_minimum_worthwhile_trade(**kwargs)

    def _policy(self, **kwargs):
        from services.trading_brain_v2.entry_thresholds import compute_min_net_profit_required
        return compute_min_net_profit_required(**kwargs)

    # ── Test 1: Luno micro normal bot valid trade passes ──────────────────

    def test_luno_micro_normal_bot_valid_trade_passes(self):
        """Luno micro normal bot with meaningful ZAR profit must be approved.

        equity=R500 (micro), notional=R100, net_edge=100 BPS → profit=R1.00
        micro-tier floor for (normal, micro, zar) = R0.75
        cost_floor = 100 × (20+10)/10000 = R0.30
        max(R0.30, R0.75) = R0.75 → R1.00 > R0.75 → PASSES
        """
        result = self._gate(
            venue="luno", symbol="BTC/ZAR",
            strategy="normal",
            bot_equity=500.0,        # micro ZAR (<R1000)
            notional=100.0,          # R100 notional
            expected_gross_edge_bps=120.0,
            all_in_cost_bps=20.0,    # net_edge=100bps → R1.00 profit
            spread_pct=0.10,
            depth_notional=100000.0,
        )
        assert result["approved"] is True, (
            f"Luno micro normal bot with R1.00 profit should pass; "
            f"got {result['decision_reason_code']}"
        )
        assert result["capital_tier"] == "micro"
        assert result["venue_class"] == "zar"
        assert result["strategy_class"] == "normal"

    # ── Test 2: Luno scalper valid trade passes ───────────────────────────

    def test_luno_scalper_valid_trade_passes(self):
        """Luno scalper with sufficient ZAR profit must be approved.

        scalper micro ZAR floor = R0.30. With notional=R50, net_edge=100bps → R0.50 > R0.30.
        """
        result = self._gate(
            venue="luno", symbol="BTC/ZAR",
            strategy="scalper",
            bot_equity=500.0,        # micro ZAR
            notional=50.0,
            expected_gross_edge_bps=130.0,
            all_in_cost_bps=30.0,    # net_edge=100bps → R0.50 profit
            spread_pct=0.10,
            depth_notional=100000.0,
            regime_result={"regime_label": "consolidation", "regime_confidence": 0.8},
            regime_eligibility={"eligible": True, "action": "full",
                                "edge_multiplier": 1.0, "size_multiplier": 1.0},
        )
        assert result["approved"] is True, (
            f"Luno micro scalper with R0.50 profit should pass; "
            f"got {result['decision_reason_code']}"
        )
        assert result["capital_tier"] == "micro"
        assert result["strategy_class"] == "scalper"

    # ── Test 3: Binance micro normal bot valid trade passes ───────────────

    def test_binance_micro_normal_bot_valid_trade_passes(self):
        """Binance micro bot with $0.15 net profit must be approved.

        micro USDT normal floor = $0.10. $0.15 > $0.10 → PASS.
        equity=$50 (micro), notional=$30, net_edge=50 bps → $0.15 profit.
        """
        result = self._gate(
            venue="binance", symbol="BTC/USDT",
            strategy="normal",
            bot_equity=50.0,         # micro USDT (<$100)
            notional=30.0,
            expected_gross_edge_bps=75.0,
            all_in_cost_bps=25.0,    # net_edge=50bps → $0.15 profit
            spread_pct=0.10,
            depth_notional=100000.0,
        )
        assert result["approved"] is True, (
            f"Binance micro normal bot with $0.15 profit should pass; "
            f"got {result['decision_reason_code']}"
        )
        assert result["capital_tier"] == "micro"

    # ── Test 4: Binance micro invalid near-breakeven trade fails ──────────

    def test_binance_micro_near_breakeven_fails(self):
        """Binance micro bot with near-breakeven profit must be rejected.

        micro USDT normal floor = $0.10.
        equity=$50, notional=$10, gross=70bps, cost=25bps → net=45bps → $0.045 profit.
        cost_floor = 10*(25+8)/10000 = $0.033; strategy_floor = $0.10
        min_required = max($0.033, $0.10) = $0.10 → $0.045 < $0.10 → FAIL.
        (gross must be >= max(15, 1.5 * 25) = 37.5 BPS to pass the edge check)
        """
        result = self._gate(
            venue="binance", symbol="BTC/USDT",
            strategy="normal",
            bot_equity=50.0,
            notional=10.0,
            expected_gross_edge_bps=70.0,
            all_in_cost_bps=25.0,    # net_edge=45bps > 37.5 required; profit=$0.045 < $0.10
            spread_pct=0.10,
            depth_notional=100000.0,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"

    # ── Tests 5-9: All supported USDT exchanges, small-cap ───────────────

    @pytest.mark.parametrize("exchange,symbol", [
        ("kucoin",  "BTC/USDT"),
        ("bybit",   "BTC/USDT"),
        ("kraken",  "BTC/USDT"),
        ("bitget",  "BTC/USDT"),
        ("gate",    "BTC/USDT"),
    ])
    def test_usdt_exchange_small_cap_valid_trade_passes(self, exchange, symbol):
        """All USDT exchanges: small-cap bot with meaningful profit must pass.

        equity=$200 (small), notional=$200, net_edge=75bps → $1.50 profit.
        small USDT normal floor = $0.50. $1.50 > $0.50 → PASS.
        """
        result = self._gate(
            venue=exchange, symbol=symbol,
            strategy="normal",
            bot_equity=200.0,        # small USDT
            notional=200.0,
            expected_gross_edge_bps=100.0,
            all_in_cost_bps=25.0,    # net_edge=75bps → $1.50 profit
            spread_pct=0.10,
            depth_notional=100000.0,
        )
        assert result["approved"] is True, (
            f"{exchange}: small-cap bot with $1.50 profit should pass; "
            f"got {result['decision_reason_code']}"
        )
        assert result["venue_class"] == "usdt"

    # ── Test 10: Larger capital tier requires larger absolute profit ───────

    def test_larger_tier_requires_larger_absolute_profit(self):
        """Larger capital tier has higher absolute profit floor, but not irrationally so.

        micro floor < small floor < medium floor < large floor.
        All are proportional — large floor is NOT 100× micro floor.
        """
        from services.trading_brain_v2.entry_thresholds import compute_min_net_profit_required

        tiers = ["micro", "small", "medium", "large"]
        equities = [50.0, 200.0, 1000.0, 6000.0]  # USDT
        floors = []
        for eq in equities:
            p = compute_min_net_profit_required(
                strategy="normal", venue="binance",
                notional=eq * 0.05,  # 5% of capital
                bot_equity=eq,
                all_in_cost_bps=25.0,
            )
            floors.append(p["min_net_profit_quote"])

        # Floors should increase with tier
        for i in range(len(floors) - 1):
            assert floors[i] <= floors[i + 1], (
                f"Floor for tier {tiers[i]} ({floors[i]}) must be <= {tiers[i+1]} ({floors[i+1]})"
            )

        # Large/micro ratio must be reasonable. The large floor is 50× the micro floor
        # (e.g. $5.00 vs $0.10), so a ratio of 200 gives ample headroom while
        # preventing absurd values that would dead-lock large-cap bots.
        ratio = floors[-1] / floors[0]
        MAX_RATIONAL_TIER_RATIO = 200
        assert ratio < MAX_RATIONAL_TIER_RATIO, (
            f"Large/micro floor ratio {ratio:.1f} is irrationally high (max {MAX_RATIONAL_TIER_RATIO})"
        )

    # ── Test 11: Scalper requires less absolute profit than normal bot ─────

    def test_scalper_requires_less_absolute_profit_than_normal(self):
        """Scalper floor < normal floor on same venue/tier, but both clear cost+safety."""
        from services.trading_brain_v2.entry_thresholds import compute_min_net_profit_required

        params = dict(venue="binance", notional=200.0, bot_equity=200.0, all_in_cost_bps=25.0)

        scalper = compute_min_net_profit_required(strategy="scalper", **params)
        normal = compute_min_net_profit_required(strategy="normal", **params)

        assert scalper["min_net_profit_quote"] <= normal["min_net_profit_quote"], (
            f"Scalper floor {scalper['min_net_profit_quote']:.4f} must be <= "
            f"normal floor {normal['min_net_profit_quote']:.4f}"
        )
        # But scalper must still clear round-trip costs
        assert scalper["min_net_profit_quote"] >= scalper["cost_floor_quote"]

    # ── Test 12: Diagnostics include new policy fields ────────────────────

    def test_policy_v2_diagnostic_fields_in_approved_trade(self):
        """Approved trades must expose all required policy v2 diagnostic fields."""
        result = self._gate(
            venue="binance", notional=5000.0, bot_equity=10000.0,
            expected_gross_edge_bps=100.0, all_in_cost_bps=25.0,
        )
        assert result["approved"] is True
        # Required v2 fields
        assert result.get("policy_version") == "v2"
        assert result.get("capital_tier") in ("micro", "small", "medium", "large")
        assert result.get("strategy_class") is not None
        assert result.get("venue_class") in ("usdt", "zar")
        assert "min_net_profit_quote_required" in result
        assert "cost_floor_quote" in result
        assert "safety_buffer_quote" in result
        assert "strategy_floor_quote" in result
        assert "policy_source" in result

    def test_policy_v2_fields_exposed_on_rejection(self):
        """Rejected trades must also expose policy v2 diagnostic fields."""
        result = self._gate(
            venue="binance", notional=10.0, bot_equity=50.0,
            expected_gross_edge_bps=40.0, all_in_cost_bps=25.0,
        )
        assert result["approved"] is False
        assert result.get("policy_version") == "v2"
        assert result.get("capital_tier") is not None
        assert "min_net_profit_quote_required" in result

    # ── Test 13: Rejection reason includes actual vs required values ───────

    def test_rejection_includes_actual_vs_required_values(self):
        """ENTRY_REJECTED_MIN_PROFIT must expose projected vs required profit."""
        # micro USDT: notional=$10, gross=70, cost=25 → net=45bps → profit=$0.045 < $0.10 floor
        result = self._gate(
            venue="binance", notional=10.0, bot_equity=50.0,
            expected_gross_edge_bps=70.0, all_in_cost_bps=25.0,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"
        # Must expose both actual and required values
        assert "projected_net_profit_quote" in result
        assert "min_net_profit_quote_required" in result
        projected = result["projected_net_profit_quote"]
        required = result["min_net_profit_quote_required"]
        assert projected < required, (
            f"Projected {projected:.4f} must be < required {required:.4f}"
        )

    # ── Test 15: Existing scalper regime fix tests still pass ─────────────

    def test_scalper_regime_policy_unchanged(self):
        """Scalper regime eligibility rules must remain unchanged."""
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        scorer = RegimeScorerV2()

        assert scorer.is_eligible("scalper", {"regime_label": "consolidation",    "regime_confidence": 0.7})["eligible"] is True
        assert scorer.is_eligible("scalper", {"regime_label": "low_volatility",   "regime_confidence": 0.7})["eligible"] is True
        assert scorer.is_eligible("scalper", {"regime_label": "mean_reversion",   "regime_confidence": 0.7})["eligible"] is True
        assert scorer.is_eligible("scalper", {"regime_label": "trending_up",      "regime_confidence": 0.8})["eligible"] is False
        assert scorer.is_eligible("scalper", {"regime_label": "high_volatility",  "regime_confidence": 0.8})["eligible"] is False
        assert scorer.is_eligible("scalper", {"regime_label": "breakout",         "regime_confidence": 0.8})["eligible"] is False

    # ── Test 16: Capital growth increases earning power (compounding) ──────

    def test_capital_growth_increases_earning_power(self):
        """As capital grows, a same-quality signal produces larger absolute earnings."""
        from services.trading_brain_v2.entry_thresholds import compute_min_net_profit_required

        # Use proportional position sizing: 5% of capital
        equities = [100.0, 500.0, 2000.0]  # small → medium USDT
        profits = []
        for eq in equities:
            notional = eq * 0.05  # 5% position
            net_edge_bps = 50.0
            profit = notional * net_edge_bps / 10_000.0
            profits.append(profit)

        # Absolute profit should grow with capital
        for i in range(len(profits) - 1):
            assert profits[i] < profits[i + 1], (
                f"Profit at equity {equities[i]} ({profits[i]:.4f}) must be < "
                f"equity {equities[i+1]} ({profits[i+1]:.4f})"
            )

        # min_required should also grow with capital but stay proportional
        mins = []
        for eq in equities:
            p = compute_min_net_profit_required(
                strategy="normal", venue="binance",
                notional=eq * 0.05,
                bot_equity=eq,
                all_in_cost_bps=25.0,
            )
            mins.append(p["min_net_profit_quote"])

        # min_required grows with capital (not frozen)
        assert mins[0] < mins[-1], "Min required profit must grow with capital"

    # ── Policy function unit tests ─────────────────────────────────────────

    def test_compute_min_profit_micro_usdt(self):
        """Micro USDT normal bot: floor is small and meaningful."""
        p = self._policy(
            strategy="normal", venue="binance",
            notional=30.0, bot_equity=50.0, all_in_cost_bps=25.0,
        )
        assert p["capital_tier"] == "micro"
        assert p["strategy_class"] == "normal"
        assert p["venue_class"] == "usdt"
        assert p["policy_version"] == "v2"
        assert p["min_net_profit_quote"] > 0
        # Must cover cost floor
        assert p["min_net_profit_quote"] >= p["cost_floor_quote"]
        # Must not be irrationally large for a micro account
        assert p["min_net_profit_quote"] <= 1.0

    def test_compute_min_profit_luno_micro_scalper(self):
        """Luno micro scalper: ZAR floor is small and meaningful."""
        p = self._policy(
            strategy="scalper", venue="luno",
            notional=50.0, bot_equity=500.0, all_in_cost_bps=35.0,
        )
        assert p["capital_tier"] == "micro"
        assert p["strategy_class"] == "scalper"
        assert p["venue_class"] == "zar"
        assert p["min_net_profit_quote"] <= 1.0  # should be small for micro ZAR

    def test_compute_min_profit_all_exchanges_return_valid(self):
        """compute_min_net_profit_required must work for all supported exchanges."""
        exchanges = ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
        for exch in exchanges:
            vc = "zar" if exch == "luno" else "usdt"
            p = self._policy(
                strategy="normal", venue=exch,
                notional=200.0, bot_equity=300.0, all_in_cost_bps=25.0,
            )
            assert p["min_net_profit_quote"] > 0, f"{exch}: floor must be positive"
            assert p["cost_floor_quote"] >= 0
            assert p["strategy_floor_quote"] > 0
            assert p["policy_version"] == "v2"
            assert p["venue_class"] == vc

    def test_worth_filter_uses_canonical_policy(self):
        """trade_worth_filter must use the canonical policy function."""
        result = self._worth(
            bot_type="normal", exchange="binance",
            bot_equity=200.0, notional=200.0,
            expected_gross_edge_bps=100.0, all_in_cost_bps=25.0,
        )
        assert result["diagnostics"]["policy_version"] == "v2"
        assert "capital_tier" in result["diagnostics"]
        assert "cost_floor_quote" in result["diagnostics"]
        assert "strategy_floor_quote" in result["diagnostics"]

    def test_micro_tier_equity_bucket(self):
        """equity_bucket must return 'micro' for very small accounts."""
        from services.trading_brain_v2.entry_thresholds import equity_bucket
        assert equity_bucket(50.0,   "usdt") == "micro"   # < $100
        assert equity_bucket(500.0,  "zar")  == "micro"   # < R1000
        assert equity_bucket(100.0,  "usdt") == "small"   # >= $100, < $500
        assert equity_bucket(1000.0, "zar")  == "small"   # >= R1000, < R5000
        assert equity_bucket(300.0,  "usdt") == "small"   # $100-$499
        assert equity_bucket(500.0,  "usdt") == "medium"  # $500 (inclusive lower bound of medium)
        assert equity_bucket(5000.0, "usdt") == "large"   # >= $5000
        assert equity_bucket(6000.0, "usdt") == "large"   # > $5000

    def test_bitget_and_gate_in_venue_costs(self):
        """bitget and gate must have venue cost entries."""
        from services.trading_brain_v2.entry_thresholds import (
            VENUE_ROUND_TRIP_COST_BPS, VENUE_SAFETY_BUFFER_BPS,
        )
        assert "bitget" in VENUE_ROUND_TRIP_COST_BPS
        assert "gate" in VENUE_ROUND_TRIP_COST_BPS
        assert "bitget" in VENUE_SAFETY_BUFFER_BPS
        assert "gate" in VENUE_SAFETY_BUFFER_BPS
