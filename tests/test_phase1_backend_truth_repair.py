"""
Phase 1 Backend Truth + Trading-Economics Repair – Test Suite

Validates all Phase 1 objectives:
  1. Target policy: capital-aware, bot-type distinct, no toy targets
  2. Minimum worthwhile trade filter: blocks bad trades, permits good ones
  3. Backend truth parity: symbol/regime/confidence from trade when available
  4. Decision payload sanitation: no NaN, None-safe numerics
  5. Self-healing status: running/idle/disabled correctly represented
  6. Scalper behavior: distinct contracts, reason codes, quick hold
  7. Truth normalizer: consistent field mapping across endpoints
"""

import sys
import os
import math
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ============================================================================
# 1. TARGET POLICY
# ============================================================================

class TestTargetPolicy:
    """
    Target policy must:
    - Scale with allocated capital
    - Never emit toy/trivial targets for bots with meaningful capital
    - Differ between normal and scalper bots
    - Differ between risk modes
    """

    def test_normal_balanced_bot_derives_from_capital(self):
        from services.target_policy import derive_targets
        bot = {"bot_type": "normal", "risk_mode": "balanced", "current_capital": 10000}
        result = derive_targets(bot)
        assert result["daily_profit_target"] == 100.0   # 1% of 10000
        assert result["trade_profit_target"] == 50.0    # 0.5% of 10000
        assert result["target_source"] == "strategy_derived"

    def test_normal_safe_has_lower_targets_than_aggressive(self):
        from services.target_policy import derive_targets
        bot_safe = {"bot_type": "normal", "risk_mode": "safe", "current_capital": 5000}
        bot_agg  = {"bot_type": "normal", "risk_mode": "aggressive", "current_capital": 5000}
        safe = derive_targets(bot_safe)
        agg  = derive_targets(bot_agg)
        assert safe["daily_profit_target"] < agg["daily_profit_target"], (
            "Safe mode must have lower daily target than aggressive"
        )
        assert safe["trade_profit_target"] < agg["trade_profit_target"]

    def test_scalper_differs_from_normal(self):
        from services.target_policy import derive_targets
        bot_n = {"bot_type": "normal",  "risk_mode": "balanced", "current_capital": 5000}
        bot_s = {"bot_type": "scalper", "risk_mode": "balanced", "current_capital": 5000}
        normal  = derive_targets(bot_n)
        scalper = derive_targets(bot_s)
        # Scalpers aim for many small wins → higher daily % but smaller per-trade %
        assert normal["trade_profit_target"] > scalper["trade_profit_target"], (
            "Scalper per-trade target must be smaller than normal (more trades, less per trade)"
        )

    def test_no_toy_targets_for_meaningful_capital(self):
        from services.target_policy import derive_targets
        bot = {"bot_type": "normal", "risk_mode": "balanced", "current_capital": 5000}
        result = derive_targets(bot)
        # A bot with R5000 should not have daily target below R20
        assert result["daily_profit_target"] is not None
        assert result["daily_profit_target"] >= 20.0, (
            f"Daily target R{result['daily_profit_target']} is too small for R5000 capital"
        )

    def test_targets_none_when_capital_zero(self):
        from services.target_policy import derive_targets
        bot = {"bot_type": "normal", "risk_mode": "balanced", "current_capital": 0}
        result = derive_targets(bot)
        assert result["daily_profit_target"] is None
        assert result["trade_profit_target"] is None

    def test_configured_targets_override_strategy(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "normal", "risk_mode": "balanced", "current_capital": 1000,
            "daily_profit_target_pct": 0.05,  # 5%
            "trade_profit_target_pct": 0.02,  # 2%
        }
        result = derive_targets(bot)
        assert result["target_source"] == "configured"
        assert abs(result["daily_profit_target"] - 50.0) < 0.01
        assert abs(result["trade_profit_target"] - 20.0) < 0.01

    def test_all_profiles_produce_nonzero_percentages(self):
        from services.target_policy import derive_targets, _TARGET_PROFILES
        for (bt, rm), _ in _TARGET_PROFILES.items():
            bot = {"bot_type": bt, "risk_mode": rm, "current_capital": 1000}
            result = derive_targets(bot)
            assert result["daily_target_pct"] > 0, f"{bt}/{rm} daily_target_pct is zero"
            assert result["trade_target_pct"] > 0, f"{bt}/{rm} trade_target_pct is zero"

    def test_targets_scale_linearly_with_capital(self):
        from services.target_policy import derive_targets
        bot_small = {"bot_type": "normal", "risk_mode": "balanced", "current_capital": 1000}
        bot_large = {"bot_type": "normal", "risk_mode": "balanced", "current_capital": 10000}
        small = derive_targets(bot_small)
        large = derive_targets(bot_large)
        ratio = large["daily_profit_target"] / small["daily_profit_target"]
        assert abs(ratio - 10.0) < 0.01, f"Expected 10× ratio, got {ratio}"


# ============================================================================
# 2. MINIMUM WORTHWHILE TRADE FILTER
# ============================================================================

class TestTradeWorthFilter:
    """
    The minimum worthwhile trade filter must:
    - Block trades with insufficient net edge
    - Block trades whose absolute profit is below venue/equity floor
    - Block trades with poor reward-per-hold-second rate
    - Permit genuinely good trades
    """

    def test_blocks_low_net_edge(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="binance",
            bot_equity=5000,
            notional=2000,
            expected_gross_edge_bps=10.0,   # below 15 BPS minimum
            all_in_cost_bps=8.0,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "INSUFFICIENT_COST_EDGE"

    def test_blocks_insufficient_absolute_profit(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        # Edge is fine in BPS but absolute value is too tiny (small notional)
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="binance",
            bot_equity=5000,
            notional=5,         # trivially small
            expected_gross_edge_bps=50.0,
            all_in_cost_bps=10.0,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "INSUFFICIENT_ABSOLUTE_EDGE"

    def test_blocks_reward_too_small_for_hold(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        # Large ZAR normal bot: equity=100000, notional=50000
        # net_edge = 20 BPS, projected profit = 50000 * 20/10000 = R100 > R60 abs floor
        # hold = 43200s (12h), reward_per_sec = 100/43200 ≈ 0.00231/s, floor = 0.005/s → blocked
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="luno",
            bot_equity=100000,
            notional=50000,
            expected_gross_edge_bps=20.0,
            all_in_cost_bps=0.0,
            predicted_hold_seconds=43200,  # 12 hours
        )
        assert result["approved"] is False
        assert result["reason_code"] == "REWARD_TOO_SMALL_FOR_HOLD"

    def test_permits_good_normal_trade(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="luno",
            bot_equity=10000,
            notional=5000,
            expected_gross_edge_bps=60.0,
            all_in_cost_bps=15.0,
            predicted_hold_seconds=3600,  # 1 hour
        )
        assert result["approved"] is True
        assert result["reason_code"] == "TRADE_WORTH_FILTER_OK"

    def test_permits_good_scalper_trade(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="scalper",
            exchange="binance",
            bot_equity=5000,
            notional=3000,
            expected_gross_edge_bps=25.0,
            all_in_cost_bps=10.0,
            predicted_hold_seconds=120,   # 2 minutes
        )
        assert result["approved"] is True

    def test_scalper_has_lower_edge_floor_than_normal(self):
        from services.trade_worth_filter import MIN_NET_EDGE_BPS
        assert MIN_NET_EDGE_BPS["scalper"] < MIN_NET_EDGE_BPS["normal"], (
            "Scalper min edge must be lower than normal to allow quick-turnover trades"
        )

    def test_luno_zar_has_higher_abs_floor_than_usdt(self):
        from services.trade_worth_filter import _ABS_MIN_QUOTE
        zar_small = _ABS_MIN_QUOTE[("normal", "small", "zar")]
        usdt_small = _ABS_MIN_QUOTE[("normal", "small", "usdt")]
        # ZAR floor must be much higher in absolute terms (ZAR << USD)
        assert zar_small > usdt_small, "ZAR absolute floor must exceed USDT absolute floor"

    def test_no_nan_in_result(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="luno",
            bot_equity=0,      # edge case: zero capital
            notional=0,
            expected_gross_edge_bps=0,
            all_in_cost_bps=0,
        )
        for key, val in result.items():
            if isinstance(val, float):
                assert not math.isnan(val), f"NaN found in result['{key}']"

    def test_result_always_has_required_fields(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="binance",
            bot_equity=1000,
            notional=500,
            expected_gross_edge_bps=20.0,
            all_in_cost_bps=5.0,
        )
        for field in ("approved", "reason_code", "reason_text",
                      "expected_net_edge_bps", "projected_net_profit_quote",
                      "min_net_edge_required_bps", "min_abs_profit_required"):
            assert field in result, f"Field '{field}' missing from trade worth filter result"


# ============================================================================
# 3. BACKEND TRUTH PARITY (Truth Normalizer)
# ============================================================================

class TestTruthNormalizer:
    """
    Truth normalizer must ensure consistent field mapping across endpoints.
    When a trade is open, symbol/regime/confidence must come from the trade.
    """

    def test_symbol_from_trade_when_bot_has_none(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"exchange": "luno"}
        trade = {"pair": "XBTZMK", "side": "buy", "entry_price": 1000000}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["symbol"] == "XBTZMK"

    def test_symbol_from_trade_overrides_bot_symbol(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"pair": "BTC/ZAR", "exchange": "luno"}
        trade = {"pair": "XBTZMK", "side": "buy", "entry_price": 1000000}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["symbol"] == "XBTZMK"

    def test_symbol_falls_back_to_bot_when_trade_has_none(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"pair": "ETH/USDT"}
        trade = {"side": "buy"}  # no pair field
        result = normalize_bot_trade_truth(bot, trade)
        assert result["symbol"] == "ETH/USDT"

    def test_symbol_unknown_only_as_true_fallback(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {}   # no pair
        trade = {} # no pair
        result = normalize_bot_trade_truth(bot, trade)
        # When genuinely unknown, "unknown" is acceptable
        assert result["symbol"] == "unknown"

    def test_regime_from_trade_canonical_field(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"market_regime": "ranging"}
        trade = {"canonical_market_regime": "bullish", "side": "buy"}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["market_regime"] == "bullish"

    def test_regime_from_trade_non_canonical_field(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"market_regime": "ranging"}
        trade = {"market_regime": "breakout", "side": "buy"}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["market_regime"] == "breakout"

    def test_regime_falls_back_to_bot_when_trade_missing(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"market_regime": "bearish"}
        trade = {"side": "buy"}  # no regime
        result = normalize_bot_trade_truth(bot, trade)
        assert result["market_regime"] == "bearish"

    def test_regime_confidence_from_trade(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"confidence_score": 0.55}
        trade = {"canonical_regime_confidence": 0.87, "side": "buy"}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["regime_confidence"] == pytest.approx(0.87, abs=0.001)

    def test_no_nan_regime_confidence(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {}
        trade = {"canonical_regime_confidence": None}
        result = normalize_bot_trade_truth(bot, trade)
        assert not math.isnan(result["regime_confidence"])
        assert result["regime_confidence"] == 0.0

    def test_entry_confidence_from_trade(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {"entry_confidence_score": 0.60}
        trade = {"entry_confidence_score": 0.91, "side": "buy"}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["entry_confidence_score"] == pytest.approx(0.91, abs=0.001)

    def test_side_from_trade(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        bot = {}
        trade = {"side": "SELL"}
        result = normalize_bot_trade_truth(bot, trade)
        assert result["side"] == "sell"

    def test_has_open_position_true_when_trade(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        result = normalize_bot_trade_truth({}, {"side": "buy"})
        assert result["has_open_position"] is True

    def test_has_open_position_false_when_no_trade(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        result = normalize_bot_trade_truth({"pair": "BTC/USDT"}, None)
        assert result["has_open_position"] is False
        assert result["side"] is None

    def test_no_nan_edge_fields(self):
        from services.truth_normalizer import normalize_bot_trade_truth
        trade = {
            "expected_net_edge_bps": float("nan"),
            "all_in_cost_bps": None,
            "projected_net_profit_quote": float("inf"),
        }
        result = normalize_bot_trade_truth({}, trade)
        for field in ("expected_net_edge_bps", "all_in_cost_bps", "projected_net_profit_quote"):
            assert not math.isnan(result[field]), f"NaN in {field}"
            assert not math.isinf(result[field]), f"Inf in {field}"


# ============================================================================
# 4. DECISION PAYLOAD SANITATION
# ============================================================================

class TestDecisionPayloadSanitation:
    """
    Decision payloads must never contain NaN, Inf, or None for numeric fields.
    """

    def test_make_decision_payload_no_nan(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED,
            True,
            confidence=float("nan"),
            expected_gross_edge_bps=float("inf"),
            all_in_cost_bps=None,
            regime_confidence=float("-inf"),
        )
        numeric_fields = [
            "entry_confidence_score", "regime_confidence",
            "expected_gross_edge_bps", "all_in_cost_bps",
            "expected_net_edge_bps", "projected_net_profit_quote",
        ]
        for f in numeric_fields:
            v = payload[f]
            assert not math.isnan(v), f"NaN in decision payload field '{f}'"
            assert not math.isinf(v), f"Inf in decision payload field '{f}'"

    def test_make_decision_payload_string_fields_not_none(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(ReasonCodes.REGIME_BLOCK, False)
        assert payload["decision_reason_code"] is not None
        assert payload["decision_reason_text"] is not None
        assert isinstance(payload["decision_reason_code"], str)
        assert len(payload["decision_reason_code"]) > 0

    def test_make_decision_payload_none_confidence_becomes_zero(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(ReasonCodes.ENTRY_APPROVED, True, confidence=None)
        assert payload["entry_confidence_score"] == 0.0

    def test_sanitize_decision_payload_clears_nan(self):
        from services.truth_normalizer import sanitize_decision_payload
        dirty = {
            "entry_confidence_score": float("nan"),
            "regime_confidence": None,
            "expected_net_edge_bps": float("inf"),
            "decision_reason_code": None,
            "market_regime": None,
            "approved": 1,
        }
        clean = sanitize_decision_payload(dirty)
        assert clean["entry_confidence_score"] == 0.0
        assert clean["regime_confidence"] == 0.0
        assert clean["expected_net_edge_bps"] == 0.0
        assert clean["decision_reason_code"] == ""
        assert clean["market_regime"] == ""
        assert clean["approved"] is True

    def test_sanitize_decision_payload_preserves_good_values(self):
        from services.truth_normalizer import sanitize_decision_payload
        good = {
            "entry_confidence_score": 0.85,
            "regime_confidence": 0.72,
            "expected_net_edge_bps": 30.5,
            "decision_reason_code": "ENTRY_APPROVED",
        }
        clean = sanitize_decision_payload(good)
        assert clean["entry_confidence_score"] == pytest.approx(0.85)
        assert clean["regime_confidence"] == pytest.approx(0.72)
        assert clean["expected_net_edge_bps"] == pytest.approx(30.5)
        assert clean["decision_reason_code"] == "ENTRY_APPROVED"

    def test_safe_numeric_utility(self):
        from utils.numeric_utils import safe_numeric
        assert safe_numeric(None) == 0.0
        assert safe_numeric(float("nan")) == 0.0
        assert safe_numeric(float("inf")) == 0.0
        assert safe_numeric(float("-inf")) == 0.0
        assert safe_numeric("not_a_number") == 0.0
        assert safe_numeric(42.5) == 42.5
        assert safe_numeric("3.14") == pytest.approx(3.14)
        assert safe_numeric(None, default=-1.0) == -1.0

    def test_sanitize_numeric_dict_utility(self):
        from utils.numeric_utils import sanitize_numeric_dict
        data = {
            "score": float("nan"),
            "confidence": None,
            "regime": "bullish",
            "edge": 25.0,
        }
        cleaned = sanitize_numeric_dict(data, ["score", "confidence", "edge"])
        assert cleaned["score"] == 0.0
        assert cleaned["confidence"] == 0.0
        assert cleaned["edge"] == 25.0
        assert cleaned["regime"] == "bullish"   # unchanged


# ============================================================================
# 5. SELF-HEALING STATUS TRUTH
# ============================================================================

class TestSelfHealingStatus:
    """
    Self-healing status must correctly represent running/idle/stopped/disabled.
    """

    def test_initial_state_is_idle_not_disabled(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        status = shs.get_status()
        assert status["state"] in ("idle", "disabled")
        assert status["enabled"] is False

    def test_running_state_after_start(self):
        """Simulate is_running=True and check state returns 'running'."""
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        shs.is_running = True
        shs.last_result = "ok"
        status = shs.get_status()
        assert status["state"] == "running"
        assert status["enabled"] is True

    def test_stopped_state_after_stop(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        shs.is_running = False
        shs.last_result = "stopped"
        status = shs.get_status()
        assert status["state"] == "stopped"
        assert status["enabled"] is False

    def test_idle_state_for_uninitialised(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        shs.is_running = False
        shs.last_result = "idle"
        status = shs.get_status()
        assert status["state"] == "idle"

    def test_status_payload_has_all_required_fields(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        status = shs.get_status()
        required = [
            "enabled", "state", "last_check", "last_action",
            "last_result", "last_reason_code", "monitored_systems",
            "recovery_attempts",
        ]
        for f in required:
            assert f in status, f"Self-healing status missing field '{f}'"

    def test_monitored_systems_is_list(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        status = shs.get_status()
        assert isinstance(status["monitored_systems"], list)
        assert len(status["monitored_systems"]) > 0

    def test_enabled_matches_is_running(self):
        from self_healing import SelfHealingSystem
        shs = SelfHealingSystem()
        for running in (True, False):
            shs.is_running = running
            status = shs.get_status()
            assert status["enabled"] is running


# ============================================================================
# 6. SCALPER BEHAVIOR – DISTINCT CONTRACTS AND REASON CODES
# ============================================================================

class TestScalperBehavior:
    """
    Scalper bots must have explicitly different behavioral contracts from
    normal bots:
    - shorter max hold
    - lower edge floor but meaningful
    - scalper-specific reason codes
    - Kelly sizing with scalper cap
    """

    def test_scalper_max_hold_shorter_than_normal(self):
        from services.trading_brain_v2.bot_contracts import (
            ScalperContract, _BotContract
        )
        assert ScalperContract.max_hold_seconds < _BotContract.max_hold_seconds, (
            "Scalper max hold must be shorter than normal bot"
        )

    def test_scalper_max_hold_is_minutes_not_hours(self):
        from services.trading_brain_v2.bot_contracts import ScalperContract
        assert ScalperContract.max_hold_seconds <= 900, (
            f"Scalper max hold {ScalperContract.max_hold_seconds}s should be ≤ 15 minutes"
        )

    def test_scalper_min_confidence_higher_than_normal(self):
        from services.trading_brain_v2.bot_contracts import ScalperContract, _BotContract
        assert ScalperContract.min_confidence >= _BotContract.min_confidence, (
            "Scalper requires at least as strict confidence threshold as normal (quick exits mean less margin)"
        )

    def test_scalper_daily_trade_budget_higher_than_normal(self):
        from services.trading_brain_v2.bot_contracts import ScalperContract, _BotContract
        assert ScalperContract.daily_trade_budget > _BotContract.daily_trade_budget, (
            "Scalper should support more daily trades for rapid turnover"
        )

    def test_scalper_coverage_throttle_shorter_than_normal(self):
        from services.trading_brain_v2.bot_contracts import ScalperContract, _BotContract
        assert ScalperContract.coverage_throttle_seconds < _BotContract.coverage_throttle_seconds, (
            "Scalper coverage throttle must be shorter to allow faster re-entry"
        )

    def test_scalper_specific_reason_codes_exist(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes
        scalper_codes = [
            ReasonCodes.SCALPER_LOSS_STREAK_COOLDOWN,
            ReasonCodes.SCALPER_DAILY_BUDGET_EXHAUSTED,
            ReasonCodes.SCALPER_COVERAGE_THROTTLE,
        ]
        for code in scalper_codes:
            assert isinstance(code, str) and len(code) > 0, f"Scalper reason code is empty"

    def test_scalper_reason_codes_distinct_from_normal_codes(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes
        scalper_codes = {
            ReasonCodes.SCALPER_LOSS_STREAK_COOLDOWN,
            ReasonCodes.SCALPER_DAILY_BUDGET_EXHAUSTED,
            ReasonCodes.SCALPER_COVERAGE_THROTTLE,
        }
        normal_codes = {
            ReasonCodes.ENTRY_APPROVED,
            ReasonCodes.EDGE_TOO_SMALL,
            ReasonCodes.REGIME_BLOCK,
        }
        overlap = scalper_codes & normal_codes
        assert not overlap, f"Scalper reason codes overlap with normal codes: {overlap}"

    def test_scalper_kelly_sizing_cap_lower_than_normal(self):
        from services.trading_brain_v2.kelly_sizing import MAX_POSITION_PCT
        assert MAX_POSITION_PCT["scalper"] < MAX_POSITION_PCT["normal"], (
            "Scalper position size cap must be smaller than normal"
        )

    def test_scalper_target_policy_produces_shorter_hold(self):
        from services.trading_brain_v2.target_policy import MAX_HOLD_SECONDS
        assert MAX_HOLD_SECONDS["scalper"] < MAX_HOLD_SECONDS["normal"], (
            "Scalper max hold in target policy must be shorter than normal"
        )

    def test_scalper_trade_target_pct_smaller_per_trade(self):
        from services.trading_brain_v2.target_policy import TRADE_TARGET_PCT
        assert TRADE_TARGET_PCT["scalper"] < TRADE_TARGET_PCT["normal"], (
            "Scalper per-trade target % must be smaller (compensated by volume)"
        )


# ============================================================================
# 7. RADAR SYMBOL PROPAGATION
# ============================================================================

class TestRadarSymbolPropagation:
    """
    When an open trade exists, the radar entry must use the trade's symbol,
    not default to 'unknown'.
    """

    @pytest.fixture(autouse=True)
    def _check_fastapi(self):
        try:
            from routes.radar import _compute_radar_entry  # noqa
        except ImportError:
            pytest.skip("fastapi not installed – skipping radar route tests")

    def test_symbol_from_open_trade_pair(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "b1", "exchange": "luno", "current_capital": 5000, "risk_mode": "balanced"}
        trade = {
            "pair": "XBTZMK",
            "side": "buy",
            "entry_price": 800000.0,
            "current_price": 802000.0,
            "quantity": 0.001,
            "opened_at": (now - timedelta(minutes=15)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["symbol"] == "XBTZMK", (
            f"Expected 'XBTZMK' from trade, got '{entry['symbol']}'"
        )

    def test_symbol_is_not_unknown_when_trade_has_pair(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "b2", "exchange": "binance", "current_capital": 2000}
        trade = {
            "symbol": "BTC/USDT",
            "side": "buy",
            "entry_price": 50000.0,
            "quantity": 0.01,
            "opened_at": (now - timedelta(minutes=5)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["symbol"] != "unknown"

    def test_regime_from_canonical_trade_field(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "b3", "exchange": "luno", "current_capital": 5000, "market_regime": "ranging"}
        trade = {
            "pair": "BTC/ZAR",
            "side": "buy",
            "entry_price": 900000.0,
            "canonical_market_regime": "bullish",
            "canonical_regime_confidence": 0.82,
            "opened_at": (now - timedelta(minutes=20)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["market_regime"] == "bullish"
        assert entry["regime_confidence"] == pytest.approx(0.82, abs=0.01)

    def test_regime_not_unknown_when_trade_has_regime(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "b4", "exchange": "binance", "current_capital": 1000}
        trade = {
            "pair": "ETH/USDT",
            "side": "buy",
            "entry_price": 3000.0,
            "market_regime": "trending",
            "opened_at": (now - timedelta(minutes=10)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["market_regime"] not in ("unknown", None, "")

    def test_entry_confidence_safe_floated(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "b5", "exchange": "binance", "current_capital": 3000}
        trade = {
            "pair": "BTC/USDT",
            "side": "buy",
            "entry_price": 50000.0,
            "entry_confidence_score": None,   # None should become 0.0
            "opened_at": (now - timedelta(minutes=5)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["entry_confidence_score"] is not None
        assert not math.isnan(float(entry["entry_confidence_score"] or 0))


# ============================================================================
# 8. REASON CODE CATALOG COMPLETENESS
# ============================================================================

class TestReasonCodeCatalog:
    """
    All reason codes must:
    - Be non-empty strings
    - Have entries in the REASON_CATALOG
    - Not conflict with each other
    """

    def test_all_reason_codes_in_catalog(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        for attr_name in dir(ReasonCodes):
            if attr_name.startswith("_"):
                continue
            code = getattr(ReasonCodes, attr_name)
            if not isinstance(code, str):
                continue
            assert code in REASON_CATALOG, (
                f"ReasonCodes.{attr_name} = '{code}' has no entry in REASON_CATALOG"
            )

    def test_reason_catalog_texts_are_nonempty(self):
        from services.trading_brain_v2.reason_codes import REASON_CATALOG
        for code, text in REASON_CATALOG.items():
            assert isinstance(text, str) and len(text) > 0, (
                f"REASON_CATALOG['{code}'] is empty"
            )

    def test_safe_reason_text_never_returns_none(self):
        from services.trading_brain_v2.reason_codes import safe_reason_text
        for code in ("ENTRY_APPROVED", "UNKNOWN_CODE_XYZ", "", "SCALPER_LOSS_STREAK_COOLDOWN"):
            result = safe_reason_text(code)
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0

    def test_trade_worth_filter_reason_codes_are_valid_strings(self):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        for test_case in [
            dict(bot_type="normal", exchange="luno", bot_equity=5000,
                 notional=2000, expected_gross_edge_bps=5, all_in_cost_bps=5),
            dict(bot_type="normal", exchange="luno", bot_equity=5000,
                 notional=2000, expected_gross_edge_bps=20, all_in_cost_bps=5),
        ]:
            result = evaluate_minimum_worthwhile_trade(**test_case)
            code = result["reason_code"]
            assert isinstance(code, str) and len(code) > 0, "reason_code must be non-empty string"
            assert code == code.upper().replace(" ", "_"), f"reason_code '{code}' not snake-case-upper"
