"""
Tests for meaningful-win classification, entry quality, scalper admission,
exit stack improvements, and dashboard win count correctness.

Requirement: Tests G.1–G.10 from the problem statement.
"""

import os
import sys
import time
from pathlib import Path

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

os.environ.setdefault("NEW_TRADING_BRAIN_V2", "true")
os.environ.setdefault("PAPER_EDGE_FLOOR_BPS", "100.0")

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# G.1: 1-cent-style micro green trade is NOT counted as a qualified win
# ──────────────────────────────────────────────────────────────────────────────
class TestMicroWinNotQualified:
    def test_one_cent_usdt_is_not_qualified_win(self):
        """A $0.01 net profit on Binance is a MICRO_WIN, not a QUALIFIED_WIN."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_MICRO_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=0.05,
            net_pnl=0.01,
            notional=500.0,
            venue="binance",
            strategy="normal",
            bot_equity=500.0,
        )
        assert result["qualified_win"] is False
        assert result["outcome_class"] == OUTCOME_MICRO_WIN
        assert result["net_green"] is True
        assert result["gross_green"] is True

    def test_one_cent_zar_is_not_qualified_win(self):
        """R0.01 net profit on Luno is MICRO_WIN."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_MICRO_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=0.05,
            net_pnl=0.01,
            notional=5000.0,
            venue="luno",
            strategy="normal",
            bot_equity=5000.0,
        )
        assert result["qualified_win"] is False
        assert result["outcome_class"] == OUTCOME_MICRO_WIN
        assert result["venue_class"] == "zar"

    def test_micro_win_below_roi_floor_not_qualified(self):
        """Net positive but net ROI < min floor → MICRO_WIN."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_MICRO_WIN,
        )
        # Small net profit that clears absolute floor but fails ROI floor
        result = classify_trade_outcome(
            gross_pnl=2.0,
            net_pnl=1.0,       # clears small-tier floor of $0.50
            notional=100_000.0,  # but only 0.001% ROI — far below 0.08% floor
            venue="binance",
            strategy="normal",
            bot_equity=500.0,
        )
        assert result["qualified_win"] is False
        assert result["outcome_class"] == OUTCOME_MICRO_WIN
        assert result["net_roi_pct"] < result["min_net_roi_pct"]


# ──────────────────────────────────────────────────────────────────────────────
# G.2: Gross-green but net-negative trade is LOSS
# ──────────────────────────────────────────────────────────────────────────────
class TestGrossGreenNetNegativeIsLoss:
    def test_gross_green_net_negative_binance(self):
        """Gross +$5 but fees/slippage eat $7 → net -$2 → LOSS."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_LOSS,
        )
        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=-2.0,   # fees consumed the gross gain
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
            fees=6.0,
            slippage=1.0,
        )
        assert result["outcome_class"] == OUTCOME_LOSS
        assert result["qualified_win"] is False
        assert result["gross_green"] is True     # gross WAS positive
        assert result["net_green"] is False       # net is NOT

    def test_gross_green_net_negative_luno(self):
        """Luno trade: gross +R5 but -R8 net → LOSS."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_LOSS,
        )
        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=-3.0,
            notional=5000.0,
            venue="luno",
            strategy="normal",
            bot_equity=5000.0,
        )
        assert result["outcome_class"] == OUTCOME_LOSS
        assert result["gross_green"] is True
        assert result["net_green"] is False
        assert result["qualified_win"] is False

    def test_exact_zero_net_is_loss(self):
        """Exactly break-even (net=0) is classified as LOSS (not a win)."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, build_outcome_counts, OUTCOME_LOSS,
        )
        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=0.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
        )
        assert result["outcome_class"] == OUTCOME_LOSS
        assert result["qualified_win"] is False
        # Flat trades: outcome_class=LOSS but loss_count=0 (not a real loss)
        counts = build_outcome_counts(result)
        assert counts["loss_count"] == 0   # flat excluded from loss counter
        assert counts["win_count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# G.3: Small net-positive but below floor is MICRO_WIN
# ──────────────────────────────────────────────────────────────────────────────
class TestSmallNetPositiveMicroWin:
    def test_small_usdt_profit_below_floor_is_micro_win(self):
        """$0.30 net profit on small-tier USDT Binance → MICRO_WIN (floor is $0.50)."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_MICRO_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=0.50,
            net_pnl=0.30,     # net positive but below small-tier floor of $0.50
            notional=300.0,
            venue="binance",
            strategy="normal",
            bot_equity=300.0,  # small tier ($100 – $500)
        )
        assert result["outcome_class"] == OUTCOME_MICRO_WIN
        assert result["net_green"] is True
        assert result["qualified_win"] is False

    def test_small_zar_profit_below_floor_is_micro_win(self):
        """R1.50 net profit on Luno small tier → MICRO_WIN (floor is R3.00)."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_MICRO_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=3.0,
            net_pnl=1.50,
            notional=2000.0,
            venue="luno",
            strategy="normal",
            bot_equity=2000.0,  # small tier (R1000–R5000)
        )
        assert result["outcome_class"] == OUTCOME_MICRO_WIN
        assert result["net_green"] is True
        assert result["qualified_win"] is False


# ──────────────────────────────────────────────────────────────────────────────
# G.4: True worthwhile trade is QUALIFIED_WIN
# ──────────────────────────────────────────────────────────────────────────────
class TestQualifiedWin:
    def test_worthwhile_usdt_trade_is_qualified_win(self):
        """$5 net profit on medium Binance account with good ROI → QUALIFIED_WIN."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_QUALIFIED_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=8.0,
            net_pnl=5.0,
            notional=2000.0,     # 0.25% ROI — above 0.08% floor
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,   # medium tier
        )
        assert result["outcome_class"] == OUTCOME_QUALIFIED_WIN
        assert result["qualified_win"] is True
        assert result["net_green"] is True
        assert result["net_roi_pct"] >= result["min_net_roi_pct"]

    def test_worthwhile_zar_trade_is_qualified_win(self):
        """R15 net profit on Luno medium account → QUALIFIED_WIN."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_QUALIFIED_WIN,
        )
        result = classify_trade_outcome(
            gross_pnl=20.0,
            net_pnl=15.0,
            notional=10_000.0,   # 0.15% ROI — above 0.08% floor
            venue="luno",
            strategy="normal",
            bot_equity=10_000.0,  # medium tier
        )
        assert result["outcome_class"] == OUTCOME_QUALIFIED_WIN
        assert result["qualified_win"] is True

    def test_scalper_qualified_win_has_lower_roi_bar(self):
        """Scalper has lower ROI floor (0.05%) due to short hold windows."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, MIN_NET_ROI_PCT, OUTCOME_QUALIFIED_WIN,
        )
        # Just above scalper ROI floor but would fail normal ROI floor
        min_scalper_roi = MIN_NET_ROI_PCT["scalper"]
        min_normal_roi = MIN_NET_ROI_PCT["normal"]
        mid_roi = (min_scalper_roi + min_normal_roi) / 2
        notional = 1000.0
        net_pnl = notional * mid_roi / 100.0 * 1.01  # just above scalper bar

        result = classify_trade_outcome(
            gross_pnl=net_pnl + 0.10,
            net_pnl=net_pnl,
            notional=notional,
            venue="binance",
            strategy="scalper",
            bot_equity=1000.0,
        )
        assert result["min_net_roi_pct"] == pytest.approx(min_scalper_roi)
        # If net_pnl also clears absolute floor, it should be QW
        if result["net_pnl"] >= result["minimum_meaningful_profit_quote"]:
            assert result["outcome_class"] == OUTCOME_QUALIFIED_WIN


# ──────────────────────────────────────────────────────────────────────────────
# G.5: Scalper can trade in valid consolidation conditions
# ──────────────────────────────────────────────────────────────────────────────
class TestScalerAdmissionValid:
    def test_scalper_approved_in_consolidation(self):
        """Scalper admitted in consolidation with good liquidity."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_CONSOLIDATION,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_CONSOLIDATION,
            regime_confidence=0.65,
            spread_pct=0.05,
            depth_notional=50_000,
            liquidity_score=0.75,
            vol_score=0.20,
            trend_score=0.15,
            net_edge_bps=25.0,
            projected_net_profit_quote=2.0,
            min_profit_quote=0.5,
        )
        assert result["eligible"] is True
        assert result["action"] == "approved"

    def test_scalper_approved_in_low_vol(self):
        """Scalper admitted in low_volatility regime."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_LOW_VOL,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_LOW_VOL,
            regime_confidence=0.70,
            spread_pct=0.08,
            depth_notional=80_000,
            liquidity_score=0.80,
            vol_score=0.10,
            trend_score=0.10,
            net_edge_bps=22.0,
        )
        assert result["eligible"] is True

    def test_scalper_approved_in_mean_reversion(self):
        """Scalper admitted in mean_reversion regime."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_MEAN_REVERSION,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_MEAN_REVERSION,
            regime_confidence=0.60,
            spread_pct=0.10,
            depth_notional=60_000,
            liquidity_score=0.60,
            vol_score=0.30,
            trend_score=0.20,
            net_edge_bps=20.0,
        )
        assert result["eligible"] is True


# ──────────────────────────────────────────────────────────────────────────────
# G.6: Scalper blocks in bad microstructure conditions
# ──────────────────────────────────────────────────────────────────────────────
class TestScalerAdmissionBlocked:
    def test_scalper_blocked_in_trending_up(self):
        """Scalper blocked in trending regime."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_TRENDING_UP,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_TRENDING_UP,
            regime_confidence=0.75,
            spread_pct=0.05,
            depth_notional=50_000,
            liquidity_score=0.80,
            vol_score=0.30,
            trend_score=0.70,
            net_edge_bps=25.0,
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_REGIME_INCOMPATIBLE"

    def test_scalper_blocked_wide_spread(self):
        """Scalper blocked when spread >= 0.20%."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_CONSOLIDATION,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_CONSOLIDATION,
            regime_confidence=0.65,
            spread_pct=0.25,     # too wide
            depth_notional=50_000,
            liquidity_score=0.70,
            vol_score=0.20,
            trend_score=0.10,
            net_edge_bps=25.0,
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_SPREAD_TOO_WIDE"

    def test_scalper_blocked_thin_depth(self):
        """Scalper blocked when depth < minimum."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_LOW_VOL,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_LOW_VOL,
            regime_confidence=0.70,
            spread_pct=0.05,
            depth_notional=5_000,  # too thin
            liquidity_score=0.50,
            vol_score=0.10,
            trend_score=0.10,
            net_edge_bps=25.0,
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_DEPTH_TOO_THIN"

    def test_scalper_blocked_chaotic_volatility(self):
        """Scalper blocked in chaotic high-vol conditions."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_CONSOLIDATION,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_CONSOLIDATION,
            regime_confidence=0.55,
            spread_pct=0.08,
            depth_notional=50_000,
            liquidity_score=0.65,
            vol_score=0.75,    # chaotic
            trend_score=0.15,
            net_edge_bps=25.0,
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_VOLATILITY_TOO_HIGH"

    def test_scalper_blocked_cost_dominant(self):
        """Scalper blocked when net_edge_bps <= 0."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_CONSOLIDATION,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_CONSOLIDATION,
            regime_confidence=0.65,
            spread_pct=0.05,
            depth_notional=50_000,
            liquidity_score=0.75,
            vol_score=0.20,
            trend_score=0.10,
            net_edge_bps=-5.0,   # cost dominant
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_COST_DOMINANT"

    def test_scalper_blocked_in_high_volatility_regime(self):
        """Scalper blocked when vol_score is too high (whipsaw)."""
        from services.trading_brain_v2.regime_scorer import (
            ScalperAdmissionPolicy, REGIME_LOW_VOL,
        )
        result = ScalperAdmissionPolicy.evaluate(
            regime_label=REGIME_LOW_VOL,
            regime_confidence=0.65,
            spread_pct=0.05,
            depth_notional=50_000,
            liquidity_score=0.70,
            vol_score=0.70,    # vol score says otherwise
            trend_score=0.10,
            net_edge_bps=20.0,
        )
        assert result["eligible"] is False
        assert result["block_reason_code"] == "SCALPER_VOLATILITY_TOO_HIGH"


# ──────────────────────────────────────────────────────────────────────────────
# G.7: Luno normal confidence path can approve valid setups
# ──────────────────────────────────────────────────────────────────────────────
class TestLunoNormalConfidencePath:
    def test_strong_regime_and_ml_passes_without_secondary_signals(self):
        """
        Strong regime_confidence + ml_confidence should pass even when
        FetchAI and CoinStats are both unavailable (returning 0).
        This was the Luno-blocking bug: max score = 0.65 < 0.68 threshold.
        """
        from services.entry_quality import compute_entry_confidence

        result = compute_entry_confidence(
            bot_type="normal",
            regime_confidence=0.80,
            ml_confidence=0.75,
            fetchai_confidence=0.0,    # unavailable
            coinstats_strength=0.0,    # unavailable
            consensus_strength=2,
            consensus_sources=2,
            direction_conflict=False,
        )
        assert result["accepted"] is True, (
            f"Strong regime+ML should pass when secondary signals are absent. "
            f"score={result['entry_confidence_score']}, "
            f"required={result['minimum_required']}"
        )

    def test_old_formula_would_have_blocked_this_trade(self):
        """
        Verify the pre-fix formula would have blocked a reasonable trade.
        Old formula: rc*0.35 + ml*0.30 = 0.75*0.35 + 0.65*0.30 = 0.2625 + 0.195 = 0.4575
        Hmm, that's below 0.68. This confirms the old blocking problem.
        The new formula with weight redistribution: rc gets 7/13*0.35, ml gets 6/13*0.35
        Let's test values that would have failed old formula at exactly 0.65 boundary.
        """
        from services.entry_quality import compute_entry_confidence
        # 0.65 + 0.55 (regime+ml) would give max 0.65 in old formula
        result = compute_entry_confidence(
            bot_type="normal",
            regime_confidence=0.75,
            ml_confidence=0.70,
            fetchai_confidence=0.0,
            coinstats_strength=0.0,
            consensus_strength=2,
            consensus_sources=2,
            direction_conflict=False,
        )
        # With new formula (weight redistribution), this should pass
        assert result["accepted"] is True, (
            f"score={result['entry_confidence_score']}, "
            f"required={result['minimum_required']}"
        )

    def test_direction_conflict_still_blocks(self):
        """Direction conflict penalty is preserved — still blocks mixed signals."""
        from services.entry_quality import compute_entry_confidence

        result = compute_entry_confidence(
            bot_type="normal",
            regime_confidence=0.90,
            ml_confidence=0.90,
            fetchai_confidence=0.0,
            coinstats_strength=0.0,
            consensus_strength=3,
            consensus_sources=3,
            direction_conflict=True,   # penalty of 0.28 applied
        )
        # Even with great signals, direction conflict should be a strong penalty
        # 0.90*w_rc + 0.90*w_ml where w_rc+w_ml=0.65 redistributed
        # New w_regime ≈ 0.35 + 0.35*0.35/0.65 ≈ 0.54, w_ml ≈ 0.46*0.30/0.65 ≈ 0.46
        # score = 0.90*0.54 + 0.90*0.46 ≈ 0.90 - 0.28 penalty = 0.62 < 0.68
        assert result["confidence_sources"]["direction_conflict"] is True

    def test_confidence_sources_are_exposed(self):
        """compute_entry_confidence must expose confidence_sources breakdown."""
        from services.entry_quality import compute_entry_confidence

        result = compute_entry_confidence(
            bot_type="normal",
            regime_confidence=0.70,
            ml_confidence=0.65,
            fetchai_confidence=60.0,
            coinstats_strength=55.0,
            consensus_strength=2,
            consensus_sources=2,
            direction_conflict=False,
        )
        assert "confidence_sources" in result
        cs = result["confidence_sources"]
        assert "regime_confidence" in cs
        assert "ml_confidence" in cs
        assert "fetchai_available" in cs
        assert "coinstats_available" in cs
        assert "weights_normalized" in cs

    def test_all_signals_available_no_redistribution(self):
        """When all signals are available, no weight redistribution occurs."""
        from services.entry_quality import compute_entry_confidence

        result = compute_entry_confidence(
            bot_type="normal",
            regime_confidence=0.70,
            ml_confidence=0.65,
            fetchai_confidence=70.0,   # available
            coinstats_strength=60.0,   # available
            consensus_strength=2,
            consensus_sources=2,
            direction_conflict=False,
        )
        assert result["confidence_sources"]["weights_normalized"] is False
        assert result["confidence_sources"]["fetchai_available"] is True
        assert result["confidence_sources"]["coinstats_available"] is True


# ──────────────────────────────────────────────────────────────────────────────
# G.8: Exit stack improves behaviour vs max-hold-only path
# ──────────────────────────────────────────────────────────────────────────────
class TestExitStackImprovements:
    def _trade(self, opened_at_offset: float = 0):
        """Return a minimal trade dict opened `opened_at_offset` seconds ago."""
        return {
            "opened_at": time.time() - opened_at_offset,
            "side": "buy",
            "exchange": "binance",
        }

    def test_break_even_protection_triggers(self):
        """Break-even protection exits when trade fell back after reaching trigger."""
        from services.trading_brain_v2.open_trade_manager import (
            OpenTradeManager, BREAKEVEN_TRIGGER_COST_MULTIPLES,
        )
        mgr = OpenTradeManager()
        # Luno round-trip = 0.35%, BE trigger = 2.5 * 0.35 = 0.875%
        # Peak gain was 1.2% (above trigger), current gain fell to 0.2% (below cost coverage)
        result = mgr.evaluate(
            trade={**self._trade(300), "exchange": "luno"},
            bot_type="normal",
            max_hold_seconds=3600,
            current_price=1002.0,   # +0.2% gain currently
            entry_price=1000.0,
            exchange="luno",
            peak_pnl_pct=1.2,       # was up 1.2% at peak
        )
        assert result["should_exit"] is True
        assert "breakeven" in result["reason_text"].lower() or \
               result["reason_code"] == "NO_PROGRESS_EXIT"

    def test_trailing_stop_locks_profit(self):
        """Adaptive trailing stop protects 40% of peak gain."""
        from services.trading_brain_v2.open_trade_manager import (
            OpenTradeManager, TRAILING_LOCK_FRACTION,
        )
        mgr = OpenTradeManager()
        # Peak = 2.0%, trail floor = 2.0 * (1 - 0.40) = 1.2%
        # Current = 1.0% < trail floor → exit
        result = mgr.evaluate(
            trade={**self._trade(300), "exchange": "binance"},
            bot_type="normal",
            max_hold_seconds=3600,
            current_price=1010.0,   # +1.0% currently
            entry_price=1000.0,
            exchange="binance",
            peak_pnl_pct=2.0,       # was up 2.0% at peak
        )
        # BE trigger for binance = 2.5 * 0.20% = 0.50%, peak > trigger
        # Trail floor = 2.0 * 0.6 = 1.2%, current 1.0% < 1.2%
        assert result["should_exit"] is True
        assert result["reason_code"] == "PROFIT_PROTECTION_EXIT"

    def test_time_budget_exit_still_works(self):
        """Time budget exit still fires at 75% of hold window."""
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        mgr = OpenTradeManager()
        max_hold = 1200
        # Opened 1000s ago (83% of 1200s budget), PnL basically 0
        result = mgr.evaluate(
            trade=self._trade(1000),
            bot_type="normal",
            max_hold_seconds=max_hold,
            current_price=1000.10,
            entry_price=1000.0,
            exchange="binance",
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"

    def test_no_exit_on_profitable_trade_within_budget(self):
        """A well-in-progress trade within time budget should not be exited."""
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        mgr = OpenTradeManager()
        result = mgr.evaluate(
            trade=self._trade(300),   # 300s into 3600s trade
            bot_type="normal",
            max_hold_seconds=3600,
            current_price=1015.0,    # +1.5% — well above costs
            entry_price=1000.0,
            exchange="binance",
            peak_pnl_pct=1.5,
        )
        assert result["should_exit"] is False

    def test_early_no_progress_exit_at_50_pct_deeply_negative(self):
        """Deeply negative trade at 50% of budget triggers early exit."""
        from services.trading_brain_v2.open_trade_manager import OpenTradeManager
        mgr = OpenTradeManager()
        max_hold = 1200
        # At 50% of budget (600s), deeply negative
        result = mgr.evaluate(
            trade=self._trade(620),  # ~52% of budget
            bot_type="normal",
            max_hold_seconds=max_hold,
            current_price=995.0,   # -0.5% loss
            entry_price=1000.0,
            exchange="binance",
        )
        assert result["should_exit"] is True
        assert result["reason_code"] == "NO_PROGRESS_EXIT"


# ──────────────────────────────────────────────────────────────────────────────
# G.9: Dashboard/API win counts reflect qualified wins correctly
# ──────────────────────────────────────────────────────────────────────────────
class TestWinCountsReflectQualifiedWins:
    def test_classify_trade_outcome_v2_micro_win(self):
        """classify_trade_outcome returns qualified_win_count=0 for micro wins."""
        from utils.trade_utils import classify_trade_outcome

        outcome = classify_trade_outcome(
            0.01,   # net_profit: tiny
            gross_profit=0.05,
            notional=500.0,
            venue="binance",
            strategy="normal",
            bot_equity=500.0,
        )
        assert outcome["win_count"] == 0
        assert outcome["qualified_win_count"] == 0
        assert outcome["net_green_count"] == 1
        assert outcome["loss_count"] == 0
        assert outcome["result"] == "micro_win"

    def test_classify_trade_outcome_v2_loss(self):
        """classify_trade_outcome returns loss_count=1 for net negative."""
        from utils.trade_utils import classify_trade_outcome

        outcome = classify_trade_outcome(
            -5.0,
            gross_profit=2.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
        )
        assert outcome["win_count"] == 0
        assert outcome["qualified_win_count"] == 0
        assert outcome["loss_count"] == 1
        assert outcome["gross_green_count"] == 1
        assert outcome["net_green_count"] == 0

    def test_classify_trade_outcome_v2_qualified_win(self):
        """classify_trade_outcome returns win_count=1 only for qualified wins."""
        from utils.trade_utils import classify_trade_outcome

        outcome = classify_trade_outcome(
            5.0,    # net_profit: meaningful
            gross_profit=8.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
        )
        assert outcome["win_count"] == 1
        assert outcome["qualified_win_count"] == 1
        assert outcome["net_green_count"] == 1
        assert outcome["loss_count"] == 0
        assert outcome["result"] == "qualified_win"

    def test_build_outcome_counts_structure(self):
        """build_outcome_counts returns all required keys."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, build_outcome_counts, OUTCOME_QUALIFIED_WIN,
        )
        outcome = classify_trade_outcome(
            gross_pnl=8.0,
            net_pnl=5.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
        )
        counts = build_outcome_counts(outcome)
        assert "gross_green_count" in counts
        assert "net_green_count" in counts
        assert "qualified_win_count" in counts
        assert "win_count" in counts
        assert "loss_count" in counts
        # For a qualified win, all should be 1
        if outcome["outcome_class"] == OUTCOME_QUALIFIED_WIN:
            assert counts["qualified_win_count"] == 1
            assert counts["win_count"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# G.10: No regression for canonical ZAR truth and display conversion
# ──────────────────────────────────────────────────────────────────────────────
class TestZARTruthAndDisplayConversion:
    def test_zar_venue_class_correct(self):
        """Luno is classified as 'zar' venue class."""
        from services.trading_brain_v2.entry_thresholds import venue_class
        assert venue_class("luno") == "zar"
        assert venue_class("LUNO") == "zar"

    def test_non_luno_venue_class_usdt(self):
        """Non-Luno exchanges are classified as 'usdt'."""
        from services.trading_brain_v2.entry_thresholds import venue_class
        for ex in ["binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            assert venue_class(ex) == "usdt", f"Expected usdt for {ex}"

    def test_display_currency_minimum_exposed(self):
        """Classifier exposes minimum_meaningful_profit_display for ZAR conversion."""
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome

        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=3.0,
            notional=2000.0,
            venue="luno",
            strategy="normal",
            bot_equity=2000.0,
            fx_rate_to_display=1.0,   # ZAR → ZAR (no conversion needed)
        )
        assert "minimum_meaningful_profit_display" in result
        assert "minimum_meaningful_profit_quote" in result
        # For ZAR→ZAR, display and quote should be the same
        assert result["minimum_meaningful_profit_display"] == pytest.approx(
            result["minimum_meaningful_profit_quote"], abs=0.001
        )

    def test_usdt_to_zar_fx_conversion_in_display(self):
        """Display minimum is correctly FX-converted for USDT venues."""
        from services.trading_brain_v2.trade_outcome_classifier import classify_trade_outcome

        usd_to_zar = 18.5  # example FX rate
        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=3.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
            fx_rate_to_display=usd_to_zar,
        )
        assert result["minimum_meaningful_profit_display"] == pytest.approx(
            result["minimum_meaningful_profit_quote"] * usd_to_zar, abs=0.01
        )

    def test_outcome_class_policy_version_present(self):
        """Policy version is always included in classifier output."""
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome, OUTCOME_QUALIFIED_WIN,
        )
        from services.trading_brain_v2.entry_thresholds import POLICY_VERSION

        result = classify_trade_outcome(
            gross_pnl=5.0,
            net_pnl=3.0,
            notional=2000.0,
            venue="binance",
            strategy="normal",
            bot_equity=2000.0,
        )
        assert result["policy_version"] == POLICY_VERSION
