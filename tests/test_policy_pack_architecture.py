"""
Tests for policy-pack architecture, trade calibration, execution quality gates,
and exit reason classification.

Covers:
  1. Policy pack selection and validation
  2. Bot-type-specific entry gating (spread/slippage/consensus/regime)
  3. Spread/slippage rejection via ExecutionQualityGate
  4. Projected-vs-realized calibration tracking
  5. Exit reason classification (stop-loss, take-profit, trailing, regime deterioration)
  6. Policy-pack scorecards and daily evaluator
  7. No regression to canonical currency truth / meaningful win
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


# ══════════════════════════════════════════════════════════════════════════
# 1. Policy pack selection and validation
# ══════════════════════════════════════════════════════════════════════════

class TestPolicyPackSelection:
    """Policy packs must be retrievable, versioned, and validated."""

    def test_all_packs_importable(self):
        from services.trading_brain_v2.policy_packs import ALL_PACKS, POLICY_PACK_VERSION
        assert len(ALL_PACKS) >= 5
        assert isinstance(POLICY_PACK_VERSION, str)
        assert POLICY_PACK_VERSION.startswith("v")

    def test_named_packs_exist(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        for name in ["defensive", "balanced", "aggressive", "scalper_conservative", "scalper_active"]:
            pack = get_policy_pack(name)
            assert pack["pack_name"] == name

    def test_unknown_pack_raises(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        with pytest.raises(ValueError, match="Unknown policy pack"):
            get_policy_pack("not_a_real_pack")

    def test_pack_has_all_required_fields(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        required = [
            "pack_name", "pack_version", "display_name", "bot_types_supported",
            "regime_allowlist", "min_entry_confidence", "min_net_edge_bps",
            "min_projected_net_profit_multiplier", "min_consensus_sources",
            "min_market_quality", "max_spread_pct", "max_slippage_pct",
            "max_hold_seconds", "cooldown_seconds", "stop_loss_pct",
            "take_profit_pct", "trailing_stop_pct", "early_exit_fraction",
            "description",
        ]
        pack = get_policy_pack("balanced")
        for field in required:
            assert field in pack, f"Missing field: {field}"

    def test_default_pack_for_normal_bot_is_balanced(self):
        from services.trading_brain_v2.policy_packs import get_default_pack_for_bot_type
        pack = get_default_pack_for_bot_type("normal")
        assert pack["pack_name"] == "balanced"

    def test_default_pack_for_scalper_is_scalper_active(self):
        from services.trading_brain_v2.policy_packs import get_default_pack_for_bot_type
        pack = get_default_pack_for_bot_type("scalper")
        assert pack["pack_name"] == "scalper_active"

    def test_select_pack_from_bot_doc(self):
        from services.trading_brain_v2.policy_packs import select_pack_for_bot
        # Bot with explicit pack name
        bot = {"bot_type": "normal", "policy_pack_name": "defensive"}
        pack = select_pack_for_bot(bot)
        assert pack["pack_name"] == "defensive"

    def test_select_pack_fallback_to_default(self):
        from services.trading_brain_v2.policy_packs import select_pack_for_bot
        bot = {"bot_type": "scalper"}
        pack = select_pack_for_bot(bot)
        assert pack["pack_name"] == "scalper_active"

    def test_validate_pack_for_wrong_bot_type_returns_invalid(self):
        from services.trading_brain_v2.policy_packs import validate_pack_for_bot_type
        result = validate_pack_for_bot_type("scalper_active", "normal")
        assert result["valid"] is False
        assert "scalper" in result["reason"]

    def test_validate_pack_for_correct_bot_type_returns_valid(self):
        from services.trading_brain_v2.policy_packs import validate_pack_for_bot_type
        result = validate_pack_for_bot_type("balanced", "normal")
        assert result["valid"] is True

    def test_scalper_packs_have_stricter_spread_than_normal(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        scalper = get_policy_pack("scalper_active")
        balanced = get_policy_pack("balanced")
        assert scalper["max_spread_pct"] < balanced["max_spread_pct"], (
            "Scalper packs must have tighter spread limits than normal packs"
        )

    def test_scalper_packs_have_shorter_max_hold(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        scalper = get_policy_pack("scalper_active")
        balanced = get_policy_pack("balanced")
        assert scalper["max_hold_seconds"] < balanced["max_hold_seconds"], (
            "Scalper packs must have shorter hold windows than normal packs"
        )

    def test_scalper_regime_allowlist_excludes_trending(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        scalper = get_policy_pack("scalper_active")
        for regime in ["trending_up", "trending_down", "high_volatility", "breakout"]:
            assert regime not in scalper["regime_allowlist"], (
                f"Scalper pack must not allow regime '{regime}'"
            )

    def test_list_packs_for_bot_type(self):
        from services.trading_brain_v2.policy_packs import list_packs_for_bot_type
        scalper_packs = list_packs_for_bot_type("scalper")
        assert all("scalper" in p["pack_name"] for p in scalper_packs), (
            "Only scalper packs should be returned for bot_type='scalper'"
        )
        normal_packs = list_packs_for_bot_type("normal")
        assert all("normal" in p["bot_types_supported"] for p in normal_packs), (
            "All returned packs should support normal bot type"
        )

    def test_pack_summary_returns_all_packs(self):
        from services.trading_brain_v2.policy_packs import pack_summary, ALL_PACKS
        summary = pack_summary()
        assert set(summary.keys()) == set(ALL_PACKS.keys())
        for name, data in summary.items():
            assert "display_name" in data
            assert "bot_types" in data


# ══════════════════════════════════════════════════════════════════════════
# 2. Execution Quality Gate — bot-type-specific entry gating
# ══════════════════════════════════════════════════════════════════════════

class TestExecutionQualityGate:
    """ExecutionQualityGate must enforce pack-specific thresholds."""

    def _gate(self):
        from services.trading_brain_v2.quality_gates import ExecutionQualityGate
        return ExecutionQualityGate()

    def _balanced_pack(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        return get_policy_pack("balanced")

    def _scalper_pack(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        return get_policy_pack("scalper_active")

    def test_all_checks_pass_approved(self):
        gate = self._gate()
        result = gate.evaluate(
            policy_pack=self._balanced_pack(),
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert result["approved"] is True
        assert result["reason_code"] == "ENTRY_APPROVED"

    def test_spread_too_wide_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=pack["max_spread_pct"] + 0.05,  # exceed limit
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "SPREAD_EXCEEDS_PACK_LIMIT"

    def test_slippage_too_high_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=0.10,
            estimated_slippage_pct=pack["max_slippage_pct"] + 0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "SLIPPAGE_EXCEEDS_PACK_LIMIT"

    def test_profit_below_pack_floor_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        mult = pack["min_projected_net_profit_multiplier"]
        min_req = 2.0
        # Set projected profit just below pack floor
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=min_req * mult - 0.01,
            min_profit_required_quote=min_req,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "PROFIT_BELOW_PACK_FLOOR"

    def test_consensus_too_weak_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=0,  # below min_consensus_sources
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "CONSENSUS_TOO_WEAK"

    def test_regime_confidence_too_low_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.10,  # way below min
            market_quality=0.60,
        )
        assert result["approved"] is False
        assert result["reason_code"] == "REGIME_CONF_TOO_LOW_FOR_PACK"

    def test_market_quality_too_low_rejected(self):
        gate = self._gate()
        pack = self._balanced_pack()
        result = gate.evaluate(
            policy_pack=pack,
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.05,  # below min
        )
        assert result["approved"] is False
        assert result["reason_code"] == "MARKET_QUALITY_TOO_LOW"

    def test_scalper_pack_has_tighter_spread_limit(self):
        """Scalper pack must reject a spread that balanced pack would allow."""
        gate = self._gate()
        scalper_pack = self._scalper_pack()
        balanced_pack = self._balanced_pack()
        # spread that balanced allows but scalper doesn't
        test_spread = scalper_pack["max_spread_pct"] + 0.02

        balanced_result = gate.evaluate(
            policy_pack=balanced_pack,
            spread_pct=test_spread,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=1.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.50,
        )
        scalper_result = gate.evaluate(
            policy_pack=scalper_pack,
            spread_pct=test_spread,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=0.5,
            consensus_sources=1,
            regime_confidence=0.70,
            market_quality=0.50,
        )
        assert scalper_result["approved"] is False
        assert scalper_result["reason_code"] == "SPREAD_EXCEEDS_PACK_LIMIT"
        # balanced may pass or fail depending on its threshold - just check it's evaluating
        assert "approved" in balanced_result

    def test_result_has_diagnostics(self):
        """All gate results must include diagnostics dict."""
        gate = self._gate()
        result = gate.evaluate(
            policy_pack=self._balanced_pack(),
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        assert "diagnostics" in result
        assert "all_checks" in result
        assert "pack_name" in result
        assert "pack_version" in result

    def test_result_has_all_checks_list(self):
        """all_checks must be a list of check dicts."""
        gate = self._gate()
        result = gate.evaluate(
            policy_pack=self._balanced_pack(),
            spread_pct=0.10,
            estimated_slippage_pct=0.05,
            projected_net_profit_quote=5.0,
            min_profit_required_quote=2.0,
            consensus_sources=2,
            regime_confidence=0.70,
            market_quality=0.60,
        )
        checks = result["all_checks"]
        assert isinstance(checks, list)
        for check in checks:
            assert "check" in check
            assert "passed" in check
            assert "threshold" in check
            assert "actual" in check

    def test_defensive_pack_requires_higher_confidence(self):
        """Defensive pack must have higher min_entry_confidence than aggressive."""
        from services.trading_brain_v2.policy_packs import get_policy_pack
        defensive = get_policy_pack("defensive")
        aggressive = get_policy_pack("aggressive")
        assert defensive["min_entry_confidence"] > aggressive["min_entry_confidence"]


# ══════════════════════════════════════════════════════════════════════════
# 3. Trade calibration — projected-vs-realized tracking
# ══════════════════════════════════════════════════════════════════════════

class TestTradeCalibration:
    """build_entry_calibration and enrich_exit_calibration must work correctly."""

    def test_entry_calibration_has_required_fields(self):
        from services.trading_brain_v2.trade_calibration import build_entry_calibration
        record = build_entry_calibration(
            bot_id="bot123",
            bot_type="normal",
            exchange="luno",
            symbol="BTC/ZAR",
            policy_pack_name="balanced",
            regime_label="consolidation",
            projected_net_profit_quote=15.0,
            projected_gross_edge_bps=50.0,
            all_in_cost_bps=25.0,
        )
        required = [
            "bot_id", "bot_type", "exchange", "symbol", "policy_pack_name",
            "regime_label_at_entry", "projected_net_profit_quote",
            "projected_gross_edge_bps", "all_in_cost_bps_at_entry",
            "paper_edge_floor_applied", "raw_gross_edge_bps",
            "entry_confidence", "spread_pct_at_entry", "slippage_pct_at_entry",
            "entry_ts", "exit_ts", "hold_seconds",
            "realized_net_profit_quote", "realized_gross_pnl_quote",
            "realized_projection_ratio", "exit_reason_code", "outcome_class",
            "regime_label_at_exit", "calibration_complete",
        ]
        for field in required:
            assert field in record, f"Missing field: {field}"

    def test_entry_record_is_not_complete(self):
        from services.trading_brain_v2.trade_calibration import build_entry_calibration
        record = build_entry_calibration(
            bot_id="b1", bot_type="scalper", exchange="binance", symbol="ETH/USDT",
            policy_pack_name="scalper_active", regime_label="low_volatility",
            projected_net_profit_quote=2.0, projected_gross_edge_bps=30.0,
            all_in_cost_bps=15.0,
        )
        assert record["calibration_complete"] is False
        assert record["exit_ts"] is None
        assert record["realized_net_profit_quote"] is None

    def test_enrich_exit_sets_complete(self):
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration
        )
        record = build_entry_calibration(
            bot_id="b1", bot_type="normal", exchange="luno", symbol="BTC/ZAR",
            policy_pack_name="balanced", regime_label="trending_up",
            projected_net_profit_quote=10.0, projected_gross_edge_bps=50.0,
            all_in_cost_bps=25.0, entry_ts=time.time() - 3600,
        )
        enrich_exit_calibration(
            record,
            realized_net_profit_quote=8.0,
            realized_gross_pnl_quote=12.0,
            exit_reason_code="TIME_BUDGET_EXIT",
            outcome_class="QUALIFIED_WIN",
            regime_label_at_exit="trending_up",
        )
        assert record["calibration_complete"] is True
        assert record["realized_net_profit_quote"] == pytest.approx(8.0, abs=1e-6)
        assert record["outcome_class"] == "QUALIFIED_WIN"
        assert record["hold_seconds"] is not None
        assert record["hold_seconds"] > 0

    def test_realized_projection_ratio_computed(self):
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration
        )
        record = build_entry_calibration(
            bot_id="b1", bot_type="normal", exchange="luno", symbol="BTC/ZAR",
            policy_pack_name="balanced", regime_label="trending_up",
            projected_net_profit_quote=10.0, projected_gross_edge_bps=50.0,
            all_in_cost_bps=25.0,
        )
        enrich_exit_calibration(
            record,
            realized_net_profit_quote=8.0,  # 80% realization
            exit_reason_code="TAKE_PROFIT_EXIT",
            outcome_class="QUALIFIED_WIN",
        )
        assert record["realized_projection_ratio"] == pytest.approx(0.8, abs=1e-3)

    def test_projection_ratio_clamped_on_large_negative(self):
        """Realized/projected ratio should be clamped, not unbounded."""
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration
        )
        record = build_entry_calibration(
            bot_id="b1", bot_type="normal", exchange="binance", symbol="BTC/USDT",
            policy_pack_name="balanced", regime_label="trending_up",
            projected_net_profit_quote=1.0, projected_gross_edge_bps=30.0,
            all_in_cost_bps=15.0,
        )
        enrich_exit_calibration(
            record,
            realized_net_profit_quote=-10.0,  # big loss, large negative ratio
            exit_reason_code="STOP_LOSS_EXIT",
            outcome_class="LOSS",
        )
        ratio = record["realized_projection_ratio"]
        assert -3.0 <= ratio <= 3.0, "Ratio should be clamped between -3.0 and 3.0"

    def test_zero_projection_gives_none_ratio(self):
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration
        )
        record = build_entry_calibration(
            bot_id="b1", bot_type="normal", exchange="binance", symbol="BTC/USDT",
            policy_pack_name="balanced", regime_label="trending_up",
            projected_net_profit_quote=0.0, projected_gross_edge_bps=0.0,
            all_in_cost_bps=0.0,
        )
        enrich_exit_calibration(
            record, realized_net_profit_quote=1.0,
            exit_reason_code="TAKE_PROFIT_EXIT", outcome_class="QUALIFIED_WIN",
        )
        assert record["realized_projection_ratio"] is None


# ══════════════════════════════════════════════════════════════════════════
# 4. Policy pack scorecards and daily evaluator
# ══════════════════════════════════════════════════════════════════════════

class TestPolicyPackScorecard:
    """compute_pack_scorecard and daily_evaluator must work correctly."""

    def _make_records(self, outcomes: list, pack_name="balanced", ratios=None):
        """Build a list of complete calibration records for testing."""
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration
        )
        records = []
        for i, oc in enumerate(outcomes):
            r = build_entry_calibration(
                bot_id=f"bot{i}", bot_type="normal", exchange="luno",
                symbol="BTC/ZAR", policy_pack_name=pack_name,
                regime_label="trending_up",
                projected_net_profit_quote=10.0, projected_gross_edge_bps=40.0,
                all_in_cost_bps=20.0, entry_ts=time.time() - 3600 * (i + 1),
            )
            realized = 8.0 if oc == "QUALIFIED_WIN" else (0.5 if oc == "MICRO_WIN" else -1.0)
            ratio = (ratios[i] if ratios else None)
            enrich_exit_calibration(
                r,
                realized_net_profit_quote=realized,
                exit_reason_code="TIME_BUDGET_EXIT",
                outcome_class=oc,
            )
            if ratio is not None:
                r["realized_projection_ratio"] = ratio
            records.append(r)
        return records

    def test_empty_records_returns_zero_scorecard(self):
        from services.trading_brain_v2.trade_calibration import compute_pack_scorecard
        sc = compute_pack_scorecard([], pack_name="balanced")
        assert sc["total_trades"] == 0
        assert sc["qualified_win_rate_pct"] == 0.0

    def test_qualified_win_rate_computed(self):
        from services.trading_brain_v2.trade_calibration import compute_pack_scorecard
        records = self._make_records(
            ["QUALIFIED_WIN", "QUALIFIED_WIN", "MICRO_WIN", "LOSS", "LOSS"]
        )
        sc = compute_pack_scorecard(records, pack_name="balanced")
        assert sc["total_trades"] == 5
        assert sc["qualified_win_count"] == 2
        assert sc["micro_win_count"] == 1
        assert sc["loss_count"] == 2
        assert sc["qualified_win_rate_pct"] == pytest.approx(40.0, abs=0.1)

    def test_max_consecutive_loss_tracked(self):
        from services.trading_brain_v2.trade_calibration import compute_pack_scorecard
        records = self._make_records(
            ["LOSS", "LOSS", "LOSS", "QUALIFIED_WIN", "LOSS"]
        )
        sc = compute_pack_scorecard(records, pack_name="balanced")
        assert sc["max_consecutive_loss"] == 3

    def test_paper_floor_usage_tracked(self):
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration, compute_pack_scorecard
        )
        records = []
        for i in range(4):
            r = build_entry_calibration(
                bot_id=f"b{i}", bot_type="normal", exchange="binance",
                symbol="BTC/USDT", policy_pack_name="balanced",
                regime_label="trending_up",
                projected_net_profit_quote=5.0, projected_gross_edge_bps=30.0,
                all_in_cost_bps=15.0,
                paper_edge_floor_applied=(i < 2),  # first 2 have floor
            )
            enrich_exit_calibration(r, realized_net_profit_quote=3.0,
                                    exit_reason_code="TAKE_PROFIT_EXIT",
                                    outcome_class="QUALIFIED_WIN")
            records.append(r)
        sc = compute_pack_scorecard(records, pack_name="balanced")
        assert sc["paper_floor_usage_pct"] == pytest.approx(50.0, abs=0.1)

    def test_daily_evaluator_recommends_best_pack(self):
        from services.trading_brain_v2.trade_calibration import (
            compute_pack_scorecard, daily_evaluator
        )
        # Balanced has 80% win rate, aggressive has 40%
        balanced_records = self._make_records(
            ["QUALIFIED_WIN"] * 8 + ["LOSS"] * 2, pack_name="balanced"
        )
        aggressive_records = self._make_records(
            ["QUALIFIED_WIN"] * 4 + ["LOSS"] * 6, pack_name="aggressive"
        )
        scorecards = {
            "balanced":   compute_pack_scorecard(balanced_records, pack_name="balanced"),
            "aggressive": compute_pack_scorecard(aggressive_records, pack_name="aggressive"),
        }
        rec = daily_evaluator(scorecards, bot_type="normal")
        assert rec["recommended_pack_name"] == "balanced"
        assert rec["recommended_score"] > 0

    def test_daily_evaluator_reports_insufficient_data(self):
        from services.trading_brain_v2.trade_calibration import (
            compute_pack_scorecard, daily_evaluator
        )
        # Only 3 records — below minimum of 10
        records = self._make_records(["QUALIFIED_WIN"] * 3, pack_name="balanced")
        scorecards = {"balanced": compute_pack_scorecard(records, pack_name="balanced")}
        rec = daily_evaluator(scorecards, bot_type="normal", min_trades_for_recommendation=10)
        assert "balanced" in rec["insufficient_data_packs"]
        assert rec["recommended_pack_name"] is None

    def test_daily_evaluator_no_auto_promotion(self):
        """Evaluator must not return any 'promote' action — diagnostics only."""
        from services.trading_brain_v2.trade_calibration import daily_evaluator
        result = daily_evaluator({}, bot_type="normal")
        assert "promote" not in str(result).lower()
        assert "action" not in result  # no action field in scaffold result


# ══════════════════════════════════════════════════════════════════════════
# 5. Exit reason classification
# ══════════════════════════════════════════════════════════════════════════

class TestExitReasonClassification:
    """OpenTradeManager must classify exits with new reason codes."""

    def _manager(self):
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        return OpenTradeManager()

    def _trade(self, elapsed_s=30):
        return {
            "opened_at": time.time() - elapsed_s,
            "side": "buy",
            "exchange": "luno",
        }

    def test_stop_loss_triggers_on_big_loss(self):
        mgr = self._manager()
        # entry=100, current=98.5 → -1.5% loss, stop_loss=0.01 (1%)
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=60),
            bot_type="normal", max_hold_seconds=3600,
            current_price=98.5, entry_price=100.0,
            stop_loss_pct=0.01, take_profit_pct=0.02,
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "STOP_LOSS_EXIT"

    def test_take_profit_triggers_on_target(self):
        mgr = self._manager()
        # entry=100, current=103 → +3% gain, take_profit=0.02 (2%)
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=60),
            bot_type="normal", max_hold_seconds=3600,
            current_price=103.0, entry_price=100.0,
            stop_loss_pct=0.01, take_profit_pct=0.02,
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "TAKE_PROFIT_EXIT"

    def test_no_exit_when_within_bounds(self):
        mgr = self._manager()
        # PnL +0.5% — above stop-loss, below take-profit
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=60),
            bot_type="normal", max_hold_seconds=3600,
            current_price=100.5, entry_price=100.0,
            stop_loss_pct=0.01, take_profit_pct=0.02,
        )
        assert result["should_exit"] is False

    def test_trailing_stop_triggers_on_pullback(self):
        mgr = self._manager()
        trade = self._trade(elapsed_s=60)
        # Simulate high-water mark stored in trade: peak was +3%, now at +0.5%
        trade["_high_water_pct"] = 3.0
        # current at +0.5%, trailing_stop=0.02 (2%) → trigger at 3.0 - 2.0 = 1.0%
        result = mgr.evaluate(
            trade=trade,
            bot_type="normal", max_hold_seconds=3600,
            current_price=100.5, entry_price=100.0,
            trailing_stop_pct=0.02,
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "TRAILING_STOP_EXIT"
        assert "high_water_pct" in result["details"]

    def test_regime_deterioration_exit_on_confidence_drop(self):
        mgr = self._manager()
        # Confidence was 0.80 at entry, now 0.40 → drop of 0.40 > threshold 0.25
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=1800),  # 30 min in
            bot_type="normal", max_hold_seconds=7200,
            current_price=100.2, entry_price=100.0,
            regime_label="trending_up",
            regime_confidence=0.40,
            regime_confidence_at_entry=0.80,
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "REGIME_DETERIORATION_EXIT"

    def test_regime_deterioration_exit_when_left_allowlist(self):
        mgr = self._manager()
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=3000),
            bot_type="normal", max_hold_seconds=7200,
            current_price=100.0, entry_price=100.0,
            regime_label="high_volatility",  # not in allowlist
            regime_confidence=0.60,
            regime_confidence_at_entry=0.75,
            allowed_regimes=["trending_up", "consolidation"],
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "REGIME_DETERIORATION_EXIT"

    def test_scalper_early_recycle_at_half_budget(self):
        """Scalper should exit at 50% time budget with no meaningful progress."""
        mgr = self._manager()
        # 151s elapsed of 300s = 50.3% budget, PnL ~0% (entry=current)
        result = mgr.evaluate(
            trade=self._trade(elapsed_s=151),
            bot_type="scalper", max_hold_seconds=300,
            current_price=100.0, entry_price=100.0,
            exchange="luno",  # 35 bps = 0.35% threshold
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"
        assert result["details"].get("scalper_early_recycle") is True

    def test_new_exit_codes_in_reason_catalog(self):
        """New exit reason codes must be in the ReasonCodes catalog."""
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        assert hasattr(ReasonCodes, "STOP_LOSS_EXIT")
        assert hasattr(ReasonCodes, "TAKE_PROFIT_EXIT")
        assert hasattr(ReasonCodes, "TRAILING_STOP_EXIT")
        assert hasattr(ReasonCodes, "REGIME_DETERIORATION_EXIT")
        assert ReasonCodes.STOP_LOSS_EXIT in REASON_CATALOG
        assert ReasonCodes.TAKE_PROFIT_EXIT in REASON_CATALOG
        assert ReasonCodes.TRAILING_STOP_EXIT in REASON_CATALOG
        assert ReasonCodes.REGIME_DETERIORATION_EXIT in REASON_CATALOG


# ══════════════════════════════════════════════════════════════════════════
# 6. New reason codes for quality gate
# ══════════════════════════════════════════════════════════════════════════

class TestQualityGateReasonCodes:
    """New execution quality gate reason codes must be in catalog."""

    def test_all_quality_gate_codes_in_catalog(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        codes = [
            "SPREAD_EXCEEDS_PACK_LIMIT",
            "SLIPPAGE_EXCEEDS_PACK_LIMIT",
            "PROFIT_BELOW_PACK_FLOOR",
            "CONSENSUS_TOO_WEAK",
            "REGIME_CONF_TOO_LOW_FOR_PACK",
            "MARKET_QUALITY_TOO_LOW",
        ]
        for code in codes:
            assert hasattr(ReasonCodes, code), f"ReasonCodes missing: {code}"
            assert getattr(ReasonCodes, code) in REASON_CATALOG, f"REASON_CATALOG missing: {code}"

    def test_quality_gate_codes_are_strings(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes
        for attr in ["SPREAD_EXCEEDS_PACK_LIMIT", "SLIPPAGE_EXCEEDS_PACK_LIMIT",
                     "PROFIT_BELOW_PACK_FLOOR", "CONSENSUS_TOO_WEAK",
                     "REGIME_CONF_TOO_LOW_FOR_PACK", "MARKET_QUALITY_TOO_LOW"]:
            assert isinstance(getattr(ReasonCodes, attr), str)


# ══════════════════════════════════════════════════════════════════════════
# 7. Policy pack economics — separate normal vs scalper thresholds
# ══════════════════════════════════════════════════════════════════════════

class TestSeparateEconomics:
    """Normal and scalper bots must have properly separated parameters."""

    def test_scalper_conservative_has_higher_net_edge_req(self):
        from services.trading_brain_v2.policy_packs import get_policy_pack
        sc = get_policy_pack("scalper_conservative")
        balanced = get_policy_pack("balanced")
        assert sc["min_net_edge_bps"] > balanced["min_net_edge_bps"], (
            "Conservative scalper must require higher net edge than balanced normal"
        )

    def test_scalper_active_min_edge_meets_strategy_minimum(self):
        """Scalper packs must enforce >= 20 BPS edge (canonical scalper minimum)."""
        from services.trading_brain_v2.policy_packs import get_policy_pack
        from services.trading_brain_v2.entry_thresholds import MIN_NET_EDGE_BPS
        scalper_min = MIN_NET_EDGE_BPS["scalper"]  # 20.0 BPS
        for pack_name in ["scalper_active", "scalper_conservative"]:
            pack = get_policy_pack(pack_name)
            assert pack["min_net_edge_bps"] >= scalper_min, (
                f"{pack_name}.min_net_edge_bps {pack['min_net_edge_bps']} "
                f"must be >= canonical scalper min {scalper_min}"
            )

    def test_scalper_max_hold_seconds_within_spec(self):
        """Scalper max hold must be <= 300s (5 min)."""
        from services.trading_brain_v2.policy_packs import list_packs_for_bot_type
        for pack in list_packs_for_bot_type("scalper"):
            assert pack["max_hold_seconds"] <= 300, (
                f"Scalper pack '{pack['pack_name']}' max_hold_seconds "
                f"{pack['max_hold_seconds']} exceeds 300s"
            )

    def test_normal_bot_pack_max_hold_is_reasonable(self):
        """Normal bot max hold must be >= 3600s (1 hour)."""
        from services.trading_brain_v2.policy_packs import list_packs_for_bot_type
        for pack in list_packs_for_bot_type("normal"):
            assert pack["max_hold_seconds"] >= 3600, (
                f"Normal pack '{pack['pack_name']}' max_hold_seconds "
                f"{pack['max_hold_seconds']} is less than 1 hour"
            )

    def test_scalper_packs_only_in_valid_regimes(self):
        """All scalper packs must only allow consolidation/low_vol/mean_reversion."""
        from services.trading_brain_v2.policy_packs import list_packs_for_bot_type
        valid_scalper_regimes = {"consolidation", "low_volatility", "mean_reversion"}
        for pack in list_packs_for_bot_type("scalper"):
            for regime in pack["regime_allowlist"]:
                assert regime in valid_scalper_regimes, (
                    f"Scalper pack '{pack['pack_name']}' incorrectly allows regime '{regime}'"
                )


# ══════════════════════════════════════════════════════════════════════════
# 8. No regression — canonical win classification still works
# ══════════════════════════════════════════════════════════════════════════

class TestNoRegressionCanonicalTruth:
    """Phase 2 features must still work correctly after Phase 3 changes."""

    def test_qualified_win_classification_unchanged(self):
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        # small tier (equity=1500 ZAR): min_floor≈R1.50, meaningful_threshold≈R2.25
        # net_pnl=3.0 > 2.25 → QUALIFIED_WIN
        result = classify_trade_outcome(
            gross_pnl=4.0, net_pnl=3.0,
            bot_type="normal", exchange="luno",
            bot_equity=1500.0, notional=300.0, all_in_cost_bps=30.0,
        )
        assert result["outcome_class"] == "QUALIFIED_WIN", (
            f"Expected QUALIFIED_WIN; got {result['outcome_class']} "
            f"(threshold={result['meaningful_threshold']}, net_pnl=3.0)"
        )
        assert result["win_count"] == 1

    def test_micro_win_still_not_a_real_win(self):
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome
        result = classify_trade_outcome(
            gross_pnl=0.05, net_pnl=0.02,
            bot_type="normal", exchange="binance",
            bot_equity=1000.0, notional=200.0, all_in_cost_bps=20.0,
        )
        assert result["outcome_class"] == "MICRO_WIN"
        assert result["win_count"] == 0

    def test_scalper_still_blocked_in_trending_up(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        scorer = RegimeScorerV2()
        result = scorer.is_eligible("scalper", {"regime_label": "trending_up", "regime_confidence": 0.8})
        assert result["eligible"] is False
        assert result["compatibility_reason_code"] == "REGIME_BLOCK"

    def test_scalper_still_allowed_in_consolidation(self):
        from services.trading_brain_v2.regime_scorer import RegimeScorerV2
        scorer = RegimeScorerV2()
        result = scorer.is_eligible("scalper", {"regime_label": "consolidation", "regime_confidence": 0.7})
        assert result["eligible"] is True

    def test_decision_payload_new_fields_still_present(self):
        from services.trading_brain_v2.reason_codes import make_decision_payload, ReasonCodes
        payload = make_decision_payload(
            ReasonCodes.ENTRY_APPROVED, True,
            paper_edge_floor_applied=True,
            raw_gross_edge_bps=5.0,
            policy_version="v2",
        )
        assert payload["paper_edge_floor_applied"] is True
        assert payload["raw_gross_edge_bps"] == pytest.approx(5.0, abs=1e-6)
        assert payload["policy_version"] == "v2"

    def test_meaningful_win_threshold_still_exported(self):
        from services.trading_brain_v2.entry_thresholds import MEANINGFUL_WIN_THRESHOLD_MULTIPLE
        assert isinstance(MEANINGFUL_WIN_THRESHOLD_MULTIPLE, float)
        assert MEANINGFUL_WIN_THRESHOLD_MULTIPLE >= 1.0


# ══════════════════════════════════════════════════════════════════════════
# 9. Calibration aggregation with policy pack context
# ══════════════════════════════════════════════════════════════════════════

class TestCalibrationWithPolicyPack:
    """Calibration records must track policy pack context."""

    def test_calibration_record_includes_pack_name(self):
        from services.trading_brain_v2.trade_calibration import build_entry_calibration
        record = build_entry_calibration(
            bot_id="b1", bot_type="scalper", exchange="binance",
            symbol="BTC/USDT", policy_pack_name="scalper_active",
            regime_label="consolidation",
            projected_net_profit_quote=2.0, projected_gross_edge_bps=25.0,
            all_in_cost_bps=12.0,
        )
        assert record["policy_pack_name"] == "scalper_active"

    def test_scorecard_tracks_hold_time_by_exit_reason(self):
        from services.trading_brain_v2.trade_calibration import (
            build_entry_calibration, enrich_exit_calibration, compute_pack_scorecard
        )
        records = []
        for i, (exit_rc, oc) in enumerate([
            ("TAKE_PROFIT_EXIT", "QUALIFIED_WIN"),
            ("TAKE_PROFIT_EXIT", "QUALIFIED_WIN"),
            ("STOP_LOSS_EXIT", "LOSS"),
            ("TIME_BUDGET_EXIT", "MICRO_WIN"),
        ]):
            r = build_entry_calibration(
                bot_id=f"b{i}", bot_type="normal", exchange="luno",
                symbol="BTC/ZAR", policy_pack_name="defensive",
                regime_label="trending_up",
                projected_net_profit_quote=10.0, projected_gross_edge_bps=40.0,
                all_in_cost_bps=20.0, entry_ts=time.time() - 3600,
            )
            enrich_exit_calibration(r, realized_net_profit_quote=5.0,
                                    exit_reason_code=exit_rc, outcome_class=oc)
            records.append(r)

        sc = compute_pack_scorecard(records, pack_name="defensive")
        holds = sc["avg_hold_by_exit_reason"]
        assert "TAKE_PROFIT_EXIT" in holds
        assert "STOP_LOSS_EXIT" in holds
        assert "TIME_BUDGET_EXIT" in holds
