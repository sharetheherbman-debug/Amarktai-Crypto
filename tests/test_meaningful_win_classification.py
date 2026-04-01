"""
Tests for meaningful-win classification, scalper regime diagnostics, and
canonical API truth fields.

Covers:
  1. Meaningful-win classification — LOSS / MICRO_WIN / QUALIFIED_WIN
  2. Tiny-win rejection (positive but below meaningful threshold → MICRO_WIN)
  3. Scalper regime allowance in valid consolidation/low_vol/mean_reversion
  4. Scalper regime blocking in trending/high-vol/breakout
  5. Paper-floor transparency in decision payload
  6. Normal-bot rejection of low-value trades
  7. Diagnostics: make_decision_payload canonical truth fields
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


# ══════════════════════════════════════════════════════════════════════════
# 1. Meaningful-win classification
# ══════════════════════════════════════════════════════════════════════════

class TestMeaningfulWinClassification:
    """classify_trade_outcome must produce correct LOSS / MICRO_WIN / QUALIFIED_WIN."""

    def _classify(self, gross_pnl, net_pnl, **kwargs):
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        return classify_trade_outcome(
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            bot_type=kwargs.get("bot_type", "normal"),
            exchange=kwargs.get("exchange", "binance"),
            bot_equity=kwargs.get("bot_equity", 2000.0),
            notional=kwargs.get("notional", 500.0),
            all_in_cost_bps=kwargs.get("all_in_cost_bps", 20.0),
        )

    def test_negative_net_pnl_is_loss(self):
        result = self._classify(gross_pnl=0.5, net_pnl=-0.20)
        assert result["outcome_class"] == "LOSS"
        assert result["is_net_win"] is False
        assert result["win_count"] == 0
        assert result["loss_count"] == 1

    def test_zero_net_pnl_is_flat_loss(self):
        """Zero net PnL → LOSS but loss_count=0 (not a real loss)."""
        result = self._classify(gross_pnl=0.0, net_pnl=0.0)
        assert result["outcome_class"] == "LOSS"
        assert result["loss_count"] == 0
        assert result["win_count"] == 0

    def test_tiny_positive_net_is_micro_win(self):
        """A tiny positive net that doesn't clear the meaningful threshold → MICRO_WIN."""
        # For binance small (equity=2000 USDT-class would be 'small'), floor ≈ $0.50
        # meaningful threshold = $0.50 × 1.5 = $0.75
        # net_pnl = $0.10 < $0.75 → MICRO_WIN
        result = self._classify(
            gross_pnl=0.30, net_pnl=0.10,
            bot_type="normal", exchange="binance",
            bot_equity=2000.0, notional=300.0, all_in_cost_bps=20.0,
        )
        assert result["outcome_class"] == "MICRO_WIN", (
            f"Expected MICRO_WIN but got {result['outcome_class']}; "
            f"threshold={result['meaningful_threshold']}"
        )
        assert result["is_gross_win"] is True
        assert result["is_net_win"] is True
        assert result["is_meaningful_win"] is False
        assert result["win_count"] == 0  # NOT a real win
        assert result["loss_count"] == 0  # NOT a loss either

    def test_meaningful_profit_is_qualified_win(self):
        """Net profit clearly above threshold → QUALIFIED_WIN."""
        # For luno small (equity=3000 ZAR, notional=1000 ZAR), cost_floor ≈ 3.0
        # meaningful threshold ≈ 3.0 × 1.5 = 4.5 ZAR
        # net_pnl = 15.0 ZAR >> 4.5 → QUALIFIED_WIN
        result = self._classify(
            gross_pnl=18.0, net_pnl=15.0,
            bot_type="normal", exchange="luno",
            bot_equity=3000.0, notional=1000.0, all_in_cost_bps=30.0,
        )
        assert result["outcome_class"] == "QUALIFIED_WIN"
        assert result["is_meaningful_win"] is True
        assert result["win_count"] == 1
        assert result["meaningful_win_count"] == 1

    def test_gross_win_but_net_loss_is_loss(self):
        """Gross profit but fees exceed profit → LOSS."""
        result = self._classify(gross_pnl=0.30, net_pnl=-0.05)
        assert result["outcome_class"] == "LOSS"
        assert result["is_gross_win"] is True
        assert result["is_net_win"] is False

    def test_outcome_class_constants_imported(self):
        """OUTCOME_* constants must be importable."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            OUTCOME_LOSS, OUTCOME_MICRO_WIN, OUTCOME_QUALIFIED_WIN
        )
        assert OUTCOME_LOSS == "LOSS"
        assert OUTCOME_MICRO_WIN == "MICRO_WIN"
        assert OUTCOME_QUALIFIED_WIN == "QUALIFIED_WIN"

    def test_result_has_required_fields(self):
        """classify_trade_outcome must return all required fields."""
        result = self._classify(gross_pnl=5.0, net_pnl=3.0)
        required = [
            "outcome_class", "is_gross_win", "is_net_win", "is_meaningful_win",
            "win_count", "loss_count", "meaningful_win_count", "gross_win_count",
            "net_win_count", "meaningful_threshold", "policy_version",
            "capital_tier", "venue_class", "strategy_class", "outcome_reason",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"


# ══════════════════════════════════════════════════════════════════════════
# 2. Tiny-win rejection
# ══════════════════════════════════════════════════════════════════════════

class TestTinyWinRejection:
    """Tiny positive trades must not be counted as meaningful wins."""

    def test_one_cent_usdt_is_micro_win(self):
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        result = classify_trade_outcome(
            gross_pnl=0.02, net_pnl=0.01,
            bot_type="normal", exchange="binance",
            bot_equity=5000.0, notional=1000.0, all_in_cost_bps=20.0,
        )
        assert result["outcome_class"] == "MICRO_WIN"
        assert result["win_count"] == 0

    def test_one_rand_luno_is_micro_win(self):
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        result = classify_trade_outcome(
            gross_pnl=1.50, net_pnl=1.00,
            bot_type="normal", exchange="luno",
            bot_equity=2000.0, notional=300.0, all_in_cost_bps=30.0,
        )
        # meaningful_threshold = 1.5 × meaningful_multiple; 1.0 < threshold → MICRO_WIN
        assert result["outcome_class"] in ("MICRO_WIN", "LOSS"), (
            f"R1.00 should not be a qualified win; got {result['outcome_class']} "
            f"(threshold={result['meaningful_threshold']})"
        )
        assert result["win_count"] == 0

    def test_build_outcome_counts_separates_micro_from_qualified(self):
        """build_outcome_counts must keep micro wins separate from qualified wins."""
        from services.trading_brain_v2.trade_outcome_classifier import build_outcome_counts, OUTCOME_MICRO_WIN, OUTCOME_QUALIFIED_WIN

        trades = [
            {"outcome_class": OUTCOME_QUALIFIED_WIN, "gross_pnl": 10.0, "net_pnl": 8.0},
            {"outcome_class": OUTCOME_MICRO_WIN,     "gross_pnl": 0.5,  "net_pnl": 0.1},
            {"outcome_class": OUTCOME_MICRO_WIN,     "gross_pnl": 0.3,  "net_pnl": 0.05},
            {"outcome_class": "LOSS",                "gross_pnl": -1.0, "net_pnl": -2.0},
        ]
        counts = build_outcome_counts(trades)
        assert counts["win_count"] == 1
        assert counts["micro_win_count"] == 2
        assert counts["loss_count"] == 1
        assert counts["qualified_win_count"] == 1
        assert counts["meaningful_win_rate_pct"] == 25.0  # 1/4

    def test_micro_wins_do_not_inflate_win_rate(self):
        from services.trading_brain_v2.trade_outcome_classifier import build_outcome_counts, OUTCOME_MICRO_WIN, OUTCOME_QUALIFIED_WIN

        trades = [
            {"outcome_class": OUTCOME_MICRO_WIN, "gross_pnl": 0.2, "net_pnl": 0.05},
            {"outcome_class": OUTCOME_MICRO_WIN, "gross_pnl": 0.1, "net_pnl": 0.02},
            {"outcome_class": OUTCOME_MICRO_WIN, "gross_pnl": 0.3, "net_pnl": 0.07},
        ]
        counts = build_outcome_counts(trades)
        assert counts["win_count"] == 0, "Micro wins must not inflate win_count"
        assert counts["meaningful_win_rate_pct"] == 0.0
        assert counts["gross_win_rate_pct"] == 100.0  # all gross positive


# ══════════════════════════════════════════════════════════════════════════
# 3. Scalper regime allowance in valid regimes
# ══════════════════════════════════════════════════════════════════════════

class TestScalperRegimeAllowance:
    """Scalpers must be allowed in consolidation/low_volatility/mean_reversion."""

    def _scorer(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        return RegimeScorerV2()

    def test_scalper_allowed_in_consolidation(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "consolidation", "regime_confidence": 0.7})
        assert result["eligible"] is True, f"Scalper should be allowed in consolidation: {result}"

    def test_scalper_allowed_in_low_volatility(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "low_volatility", "regime_confidence": 0.8})
        assert result["eligible"] is True, f"Scalper should be allowed in low_volatility: {result}"

    def test_scalper_allowed_in_mean_reversion(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "mean_reversion", "regime_confidence": 0.65})
        assert result["eligible"] is True, f"Scalper should be allowed in mean_reversion: {result}"

    def test_scalper_eligibility_includes_reason_code(self):
        """is_eligible must return compatibility_reason_code for diagnostics."""
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "consolidation", "regime_confidence": 0.7})
        assert "compatibility_reason_code" in result
        assert "compatibility_reason_text" in result
        assert result["bot_type_specific"] is True
        assert "allowed_regimes" in result

    def test_scalper_allowed_regimes_are_correct(self):
        """Scalper's allowed_regimes must be consolidation/low_vol/mean_reversion."""
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "consolidation", "regime_confidence": 0.7})
        allowed = set(result["allowed_regimes"])
        assert "consolidation" in allowed
        assert "low_volatility" in allowed
        assert "mean_reversion" in allowed
        assert "high_volatility" not in allowed
        assert "breakout" not in allowed

    def test_strategy_regime_map_scalper_correct(self):
        """STRATEGY_REGIME_MAP scalper set must not include high_volatility or breakout."""
        from services.trading_brain_v2.regime_scorer import STRATEGY_REGIME_MAP
        scalper_allowed = STRATEGY_REGIME_MAP["scalper"]
        assert "high_volatility" not in scalper_allowed, (
            "Scalpers must not be allowed in high_volatility — short holds are too risky"
        )
        assert "breakout" not in scalper_allowed, (
            "Scalpers must not be allowed in breakout — momentum overwhelms microstructure edge"
        )
        assert "consolidation" in scalper_allowed
        assert "low_volatility" in scalper_allowed
        assert "mean_reversion" in scalper_allowed


# ══════════════════════════════════════════════════════════════════════════
# 4. Scalper regime blocking in invalid regimes
# ══════════════════════════════════════════════════════════════════════════

class TestScalperRegimeBlocking:
    """Scalpers must be blocked in trending/high-vol/breakout regimes."""

    def _scorer(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        return RegimeScorerV2()

    def test_scalper_blocked_in_trending_up(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "trending_up", "regime_confidence": 0.8})
        assert result["eligible"] is False
        assert result["compatibility_reason_code"] == "REGIME_BLOCK"

    def test_scalper_blocked_in_trending_down(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "trending_down", "regime_confidence": 0.8})
        assert result["eligible"] is False
        assert result["compatibility_reason_code"] == "REGIME_BLOCK"

    def test_scalper_blocked_in_high_volatility(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "high_volatility", "regime_confidence": 0.85})
        assert result["eligible"] is False, (
            "Scalper must be blocked in high_volatility — short holds are too risky"
        )

    def test_scalper_blocked_in_breakout(self):
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "breakout", "regime_confidence": 0.8})
        assert result["eligible"] is False, "Scalper must be blocked in breakout"

    def test_scalper_blocked_includes_allowed_regimes_in_reason(self):
        """Block response must include allowed_regimes for diagnostics."""
        scorer = self._scorer()
        result = scorer.is_eligible("scalper", {"regime_label": "trending_up", "regime_confidence": 0.8})
        assert "allowed_regimes" in result
        assert len(result["allowed_regimes"]) > 0

    def test_regime_classifier_scalper_blocked_in_trending(self):
        """regime_classifier.strategy_regime_allowed must also block scalpers in trending."""
        from services.regime_classifier import strategy_regime_allowed
        result = strategy_regime_allowed("scalper", "trending_up", 0.8)
        assert result["allowed"] is False
        assert result["reason_code"] == "REGIME_BLOCK"
        assert result["bot_type_specific"] is True

    def test_regime_classifier_scalper_allowed_in_consolidation(self):
        """regime_classifier.strategy_regime_allowed must allow scalpers in consolidation."""
        from services.regime_classifier import strategy_regime_allowed
        result = strategy_regime_allowed("scalper", "consolidation", 0.75)
        assert result["allowed"] is True
        assert result["reason_code"] == "REGIME_ALLOWED"


# ══════════════════════════════════════════════════════════════════════════
# 5. Paper-floor transparency
# ══════════════════════════════════════════════════════════════════════════

class TestPaperFloorTransparency:
    """make_decision_payload must expose paper_edge_floor_applied and raw_gross_edge_bps."""

    def test_decision_payload_exposes_paper_floor_fields(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            paper_edge_floor_applied=True,
            raw_gross_edge_bps=5.0,
            expected_gross_edge_bps=100.0,  # inflated by floor
            policy_version="v2",
        )
        assert payload["paper_edge_floor_applied"] is True
        assert payload["raw_gross_edge_bps"] == 5.0
        assert payload["expected_gross_edge_bps"] == 100.0  # floored value
        assert payload["policy_version"] == "v2"

    def test_decision_payload_false_floor_by_default(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(ReasonCodes.ENTRY_APPROVED, True)
        assert payload["paper_edge_floor_applied"] is False
        assert payload["raw_gross_edge_bps"] == 0.0

    def test_feasibility_gate_exposes_paper_floor(self):
        """TradeFeasibilityGate must pass paper floor truth through to output."""
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
            raw_gross_edge_bps=5.0,
            paper_edge_floor_applied=True,
        )
        # paper_edge_floor_applied should be in result (either directly or via extra)
        assert result.get("paper_edge_floor_applied") is True
        assert result.get("raw_gross_edge_bps") == 5.0

    def test_decision_payload_regime_compatibility_reason(self):
        """make_decision_payload must expose regime_compatibility_reason."""
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            regime_compatibility_reason="scalper allowed in consolidation (confidence 75%)",
        )
        assert payload["regime_compatibility_reason"] == "scalper allowed in consolidation (confidence 75%)"


# ══════════════════════════════════════════════════════════════════════════
# 6. Normal-bot low-value trade rejection
# ══════════════════════════════════════════════════════════════════════════

class TestNormalBotLowValueRejection:
    """Normal bots must reject trades whose projected net profit is economically trivial."""

    def _gate(self, **kwargs):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        return gate.evaluate(
            strategy=kwargs.get("strategy", "normal"),
            venue=kwargs.get("venue", "luno"),
            symbol=kwargs.get("symbol", "BTC/ZAR"),
            bot_equity=kwargs.get("bot_equity", 2000.0),
            notional=kwargs.get("notional", 100.0),
            expected_gross_edge_bps=kwargs.get("expected_gross_edge_bps", 80.0),
            all_in_cost_bps=kwargs.get("all_in_cost_bps", 30.0),
            spread_pct=kwargs.get("spread_pct", 0.05),
            depth_notional=kwargs.get("depth_notional", 200000.0),
            entry_confidence=kwargs.get("entry_confidence", 0.75),
            regime_result=kwargs.get("regime_result", {"regime_label": "trending_up", "regime_confidence": 0.8}),
            regime_eligibility=kwargs.get("regime_eligibility", {
                "eligible": True, "action": "full",
                "edge_multiplier": 1.0, "size_multiplier": 1.0,
            }),
        )

    def test_normal_bot_rejects_near_breakeven_zar_trade(self):
        """notional=100, net_edge=50bps → profit=R0.50 < R3.00 floor → REJECTED.
        Strategy floor (3.00) > cost_floor (~0.40) → ABS_PROFIT_TOO_SMALL.
        """
        result = self._gate(
            venue="luno", bot_equity=2000.0,
            notional=100.0,
            expected_gross_edge_bps=80.0, all_in_cost_bps=30.0,
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ABS_PROFIT_TOO_SMALL", (
            f"Near-breakeven trade should be rejected; got {result['decision_reason_code']}"
        )

    def test_normal_bot_approves_meaningful_zar_profit(self):
        """notional=2000, net_edge=100bps → profit=R20 >> floor → APPROVED."""
        result = self._gate(
            venue="luno", bot_equity=10000.0,
            notional=2000.0,
            expected_gross_edge_bps=130.0, all_in_cost_bps=30.0,
        )
        assert result["approved"] is True
        assert result["decision_reason_code"] == "ENTRY_APPROVED"

    def test_decision_payload_has_projected_profit_quote(self):
        """Decision payload must expose projected_net_profit_quote for dashboard."""
        result = self._gate(
            venue="luno", bot_equity=10000.0,
            notional=1000.0,
            expected_gross_edge_bps=130.0, all_in_cost_bps=30.0,
        )
        assert "projected_net_profit_quote" in result
        pnl = result["projected_net_profit_quote"]
        assert isinstance(pnl, (int, float))
        assert pnl > 0, "Approved trade must have positive projected profit"


# ══════════════════════════════════════════════════════════════════════════
# 7. Canonical API truth fields in make_decision_payload
# ══════════════════════════════════════════════════════════════════════════

class TestCanonicalApiTruth:
    """make_decision_payload must include all canonical truth fields."""

    def test_payload_has_win_classification(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            win_classification="QUALIFIED_WIN",
        )
        assert payload["win_classification"] == "QUALIFIED_WIN"

    def test_payload_win_classification_empty_by_default(self):
        """win_classification defaults to empty string (not None)."""
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(ReasonCodes.REGIME_BLOCK, False)
        assert "win_classification" in payload
        assert payload["win_classification"] == ""

    def test_payload_has_projected_net_profit_display(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            projected_net_profit_quote=15.0,
            projected_net_profit_display=0.83,  # $0.83 USD
        )
        assert payload["projected_net_profit_display"] == pytest.approx(0.83, abs=1e-6)
        assert payload["projected_net_profit_quote"] == pytest.approx(15.0, abs=1e-6)

    def test_new_fields_do_not_break_existing_fields(self):
        """Adding new fields must not change existing field values."""
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            confidence=0.82,
            expected_gross_edge_bps=50.0,
            all_in_cost_bps=20.0,
            expected_net_edge_bps=30.0,
            projected_net_profit_quote=15.0,
            regime_label="consolidation",
            regime_confidence=0.75,
        )
        # All existing fields must still be present and correct
        assert payload["approved"] is True
        assert payload["entry_confidence_score"] == pytest.approx(0.82, abs=1e-6)
        assert payload["expected_gross_edge_bps"] == pytest.approx(50.0, abs=1e-6)
        assert payload["expected_net_edge_bps"] == pytest.approx(30.0, abs=1e-6)
        assert payload["regime_label"] == "consolidation"
        assert payload["regime_confidence"] == pytest.approx(0.75, abs=1e-6)
        # New fields present
        assert "paper_edge_floor_applied" in payload
        assert "raw_gross_edge_bps" in payload
        assert "regime_compatibility_reason" in payload
        assert "policy_version" in payload
        assert "win_classification" in payload
        assert "projected_net_profit_display" in payload

    def test_no_none_in_payload(self):
        """No field in the payload should be None."""
        import math
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(ReasonCodes.ENTRY_APPROVED, True)
        for key, val in payload.items():
            assert val is not None, f"Field '{key}' is None"
            if isinstance(val, float):
                assert not math.isnan(val), f"Field '{key}' is NaN"


# ══════════════════════════════════════════════════════════════════════════
# 8. Meaningful-win threshold is configurable
# ══════════════════════════════════════════════════════════════════════════

class TestMeaningfulWinThreshold:
    """MEANINGFUL_WIN_THRESHOLD_MULTIPLE must be configurable and exported."""

    def test_threshold_multiple_exported(self):
        from services.trading_brain_v2.entry_thresholds import MEANINGFUL_WIN_THRESHOLD_MULTIPLE
        assert isinstance(MEANINGFUL_WIN_THRESHOLD_MULTIPLE, float)
        assert MEANINGFUL_WIN_THRESHOLD_MULTIPLE > 1.0, (
            "Threshold multiple must be > 1.0 to ensure wins are truly above cost floor"
        )

    def test_qualifier_uses_threshold_multiple(self):
        """The classifier must use the canonical threshold multiple."""
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        from services.trading_brain_v2.entry_thresholds import (
            MEANINGFUL_WIN_THRESHOLD_MULTIPLE,
            compute_min_net_profit_required,
        )
        # Compute what the threshold should be for this trade profile
        policy = compute_min_net_profit_required(
            strategy="normal", venue="binance",
            notional=1000.0, bot_equity=2000.0,
            all_in_cost_bps=20.0, exchange="binance",
        )
        expected_threshold = policy["min_net_profit_quote"] * MEANINGFUL_WIN_THRESHOLD_MULTIPLE

        result = classify_trade_outcome(
            gross_pnl=10.0, net_pnl=10.0,
            bot_type="normal", exchange="binance",
            bot_equity=2000.0, notional=1000.0, all_in_cost_bps=20.0,
        )
        assert abs(result["meaningful_threshold"] - expected_threshold) < 1e-4
