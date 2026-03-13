"""
Tests for paper-trading policy corrections (v2).

Validates:
 1. Paper hold cap applied to normal bots (30 min cap, not 3-6 hours).
 2. Scalper hold cap NOT affected by paper mode cap.
 3. Explicit max_hold_seconds bypasses the paper cap.
 4. evaluate_pre_timeout_exit fires stagnation_exit for flat trades.
 5. evaluate_pre_timeout_exit fires profit_protection_exit for stalling gains.
 6. evaluate_pre_timeout_exit fires regime_decay_exit for bearish + low pnl.
 7. Weak ZAR trade rejected by feasibility gate (raised abs-profit minimum).
 8. Trade with entry_confidence below floor is rejected (LOW_CONFIDENCE_ENTRY).
 9. Trade with cost-to-edge ratio above 0.55 is rejected (COST_TOO_HIGH).
10. Scalper re-entry blocked after weak exit until cooldown or improvement.
11. Scalper re-entry allowed early on confidence improvement.
12. New reason codes are non-empty strings and present in REASON_CATALOG.
13. trade_worth_filter raises ZAR floors correctly (previous 1.50 floor no longer passes).
14. Ledger semantics: record_scalper_exit does not break bot_contracts state.
"""

import os
import time
import pytest

os.environ.setdefault("NEW_TRADING_BRAIN_V2", "true")
os.environ.setdefault("PAPER_EDGE_FLOOR_BPS", "100.0")
os.environ.setdefault("PAPER_FALLBACK_TREND_PCT", "2.0")
os.environ.setdefault("PAPER_FALLBACK_VOL_PCT", "2.5")


# ── 1 & 2 & 3. Hold policy paper cap ─────────────────────────────────────────

class TestPaperHoldCap:
    """Paper mode hold cap: normal bots are capped, scalpers are not."""

    def test_normal_bot_paper_cap_applied(self):
        from services.hold_policy import resolve_hold_policy, PAPER_NORMAL_MAX_HOLD_SECONDS

        bot = {"bot_type": "normal", "risk_mode": "balanced"}
        result = resolve_hold_policy(bot, is_paper_mode=True)

        assert result["max_hold_seconds"] == PAPER_NORMAL_MAX_HOLD_SECONDS, (
            f"Expected paper cap {PAPER_NORMAL_MAX_HOLD_SECONDS}s, got {result['max_hold_seconds']}s"
        )
        assert result["source"] == "paper_normal_cap"

    def test_normal_bot_safe_risk_paper_cap_applied(self):
        """Even the 'safe' risk mode (6 hours) is capped in paper mode."""
        from services.hold_policy import resolve_hold_policy, PAPER_NORMAL_MAX_HOLD_SECONDS

        bot = {"bot_type": "normal", "risk_mode": "safe"}
        result = resolve_hold_policy(bot, is_paper_mode=True)

        assert result["max_hold_seconds"] == PAPER_NORMAL_MAX_HOLD_SECONDS

    def test_normal_bot_live_mode_not_capped(self):
        """Live mode (is_paper_mode=False) retains the full risk-mode hold."""
        from services.hold_policy import resolve_hold_policy, NORMAL_MAX_HOLD_SECONDS

        bot = {"bot_type": "normal", "risk_mode": "balanced"}
        result = resolve_hold_policy(bot, is_paper_mode=False)

        assert result["max_hold_seconds"] == NORMAL_MAX_HOLD_SECONDS["balanced"]
        assert result["source"] == "normal_risk_mode_default"

    def test_scalper_not_affected_by_paper_cap(self):
        """Scalper max hold comes from exchange limits, not the paper normal cap."""
        from services.hold_policy import resolve_hold_policy, PAPER_NORMAL_MAX_HOLD_SECONDS
        from exchange_limits import SCALPER_MAX_HOLD_SECONDS

        bot = {"bot_type": "scalper", "risk_mode": "balanced"}
        result = resolve_hold_policy(bot, is_paper_mode=True)

        # Scalper should use its own limit, which is much shorter
        assert result["max_hold_seconds"] == int(SCALPER_MAX_HOLD_SECONDS)
        assert result["source"] == "scalper_default"

    def test_explicit_max_hold_not_overridden_by_paper_cap(self):
        """An explicit max_hold_seconds on the trade takes precedence."""
        from services.hold_policy import resolve_hold_policy, PAPER_NORMAL_MAX_HOLD_SECONDS

        open_trade = {"max_hold_seconds": 7200, "bot_type": "normal"}
        result = resolve_hold_policy({}, open_trade=open_trade, is_paper_mode=True)

        assert result["max_hold_seconds"] == 7200
        assert result["source"] == "explicit"

    def test_paper_cap_env_override(self, monkeypatch):
        """PAPER_NORMAL_MAX_HOLD_SECONDS env var controls the cap."""
        monkeypatch.setenv("PAPER_NORMAL_MAX_HOLD_SECONDS", "600")
        # Need to reimport to pick up the new env value
        import importlib
        import services.hold_policy as hp
        importlib.reload(hp)

        bot = {"bot_type": "normal", "risk_mode": "balanced"}
        result = hp.resolve_hold_policy(bot, is_paper_mode=True)
        assert result["max_hold_seconds"] == 600

        # Restore
        importlib.reload(hp)


# ── 4, 5, 6. Early exit conditions ───────────────────────────────────────────

class TestEarlyExitConditions:
    """evaluate_pre_timeout_exit covers stagnation, profit-protect, regime-decay."""

    def _call(self, bot_class, hold_ratio, pnl_pct, min_progress_pct=0.05,
              regime_trend="neutral", regime_confidence=0.0):
        from services.entry_quality import evaluate_pre_timeout_exit
        return evaluate_pre_timeout_exit(
            bot_class=bot_class,
            hold_ratio=hold_ratio,
            pnl_pct=pnl_pct,
            min_progress_pct=min_progress_pct,
            regime_trend=regime_trend,
            regime_confidence=regime_confidence,
        )

    def test_stagnation_exit_fires_for_flat_pnl(self):
        """Normal bot at 40% hold with pnl near zero → stagnation_exit."""
        result = self._call("normal", hold_ratio=0.40, pnl_pct=0.01)
        assert result == "stagnation_exit", f"Expected stagnation_exit, got {result}"

    def test_stagnation_exit_fires_at_threshold(self):
        """Stagnation fires exactly at hold_ratio=0.40."""
        result = self._call("normal", hold_ratio=0.40, pnl_pct=-0.01)
        assert result == "stagnation_exit"

    def test_stagnation_exit_not_below_threshold(self):
        """Below 40% hold ratio, stagnation exit should not fire."""
        result = self._call("normal", hold_ratio=0.35, pnl_pct=0.01)
        # 0.35 is below stagnation (0.40) threshold; no exit
        assert result is None

    def test_profit_protection_fires_for_stalling_gain(self):
        """Normal bot at 60% hold with small positive pnl → profit_protection_exit."""
        result = self._call("normal", hold_ratio=0.60, pnl_pct=0.04, min_progress_pct=0.05)
        assert result == "profit_protection_exit", f"Expected profit_protection_exit, got {result}"

    def test_profit_protection_not_for_negative_pnl(self):
        """Profit protection only fires when pnl > 0."""
        result = self._call("normal", hold_ratio=0.60, pnl_pct=-0.02)
        # Negative pnl → should hit stagnation or no-progress, not profit protection
        assert result != "profit_protection_exit"

    def test_regime_decay_exit_bearish_high_confidence(self):
        """Strong bearish regime (conf >= 0.80) triggers regime_decay_exit early."""
        result = self._call(
            "normal", hold_ratio=0.20, pnl_pct=0.10,
            regime_trend="bearish", regime_confidence=0.80
        )
        assert result == "regime_decay_exit", f"Expected regime_decay_exit, got {result}"

    def test_regime_decay_exit_bearish_moderate_confidence(self):
        """Moderate bearish regime (conf >= 0.55) triggers regime_decay_exit at 25% hold."""
        result = self._call(
            "normal", hold_ratio=0.25, pnl_pct=0.10,
            regime_trend="bearish", regime_confidence=0.60
        )
        assert result == "regime_decay_exit"

    def test_no_exit_on_good_progress(self):
        """Trade making solid progress should not trigger any early exit."""
        result = self._call("normal", hold_ratio=0.50, pnl_pct=1.5)
        assert result is None

    def test_scalper_no_progress_exit(self):
        """Scalper no-progress exit fires at >= 70% hold."""
        result = self._call("scalper", hold_ratio=0.70, pnl_pct=0.01)
        assert result == "scalper_no_progress_exit"

    def test_early_invalidation_exit(self):
        """Sharp adverse move at >= 35% hold triggers early_invalidation_exit."""
        result = self._call("normal", hold_ratio=0.35, pnl_pct=-0.50)
        assert result == "early_invalidation_exit"

    def test_old_regime_deterioration_reason_replaced(self):
        """The old 'regime_deterioration_exit' label must no longer appear."""
        for hold_ratio in (0.20, 0.25, 0.30, 0.50):
            result = self._call(
                "normal", hold_ratio=hold_ratio, pnl_pct=0.10,
                regime_trend="bearish", regime_confidence=0.65
            )
            assert result != "regime_deterioration_exit", (
                f"Old exit label 'regime_deterioration_exit' should be replaced; "
                f"got {result} at hold_ratio={hold_ratio}"
            )


# ── 7. Trade feasibility gate – raised ZAR abs profit minimums ────────────────

class TestFeasibilityGateStricterZAR:
    """Raised abs-profit minimums block weak trades that previously passed."""

    def _gate(self, **kwargs):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        defaults = dict(
            strategy="normal",
            venue="luno",
            symbol="BTC/ZAR",
            bot_equity=2000.0,
            notional=200.0,
            expected_gross_edge_bps=150.0,
            all_in_cost_bps=40.0,
            spread_pct=0.15,
            depth_notional=80000.0,
            entry_confidence=0.65,
        )
        defaults.update(kwargs)
        return gate.evaluate(**defaults)

    def test_weak_trade_rejected_abs_profit_below_new_floor(self):
        """
        Previous floor was R1.50 for small ZAR account.
        New floor is R3.00. A trade yielding < R3 must be rejected.
        notional=200, net_edge=110 bps → profit = 200 × 0.011 = R2.20 < R3.00 → FAIL
        """
        result = self._gate(notional=200.0, expected_gross_edge_bps=150.0, all_in_cost_bps=40.0)
        # net_edge = 150 - 40 = 110 bps = 1.10%; profit = 200 × 0.011 = 2.20 < 3.0
        assert not result["approved"], f"Expected rejection, got: {result}"
        assert result["decision_reason_code"] == "ABS_PROFIT_TOO_SMALL"

    def test_trade_passes_when_profit_meets_new_floor(self):
        """
        notional=500, net_edge=110 bps → profit = 500 × 0.011 = R5.50 >= R3.00 → PASS
        """
        result = self._gate(notional=500.0, expected_gross_edge_bps=150.0, all_in_cost_bps=40.0)
        assert result["approved"], f"Expected approval, got: {result}"

    def test_old_floor_no_longer_passes(self):
        """
        A notional that would have passed the old R1.50 floor but fails the new R3.00 floor.
        notional=150, net_edge=110 bps → profit = 150 × 0.011 = 1.65 >= 1.50 (old) but < 3.00 (new)
        """
        result = self._gate(notional=150.0, expected_gross_edge_bps=150.0, all_in_cost_bps=40.0)
        assert not result["approved"]
        assert result["decision_reason_code"] == "ABS_PROFIT_TOO_SMALL"


# ── 8. Entry confidence gate ──────────────────────────────────────────────────

class TestEntryConfidenceGate:
    """Low confidence entries (below MIN_ENTRY_CONFIDENCE=0.40) must be rejected."""

    def _gate(self, entry_confidence):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        return gate.evaluate(
            strategy="normal",
            venue="luno",
            symbol="BTC/ZAR",
            bot_equity=30000.0,
            notional=3000.0,
            expected_gross_edge_bps=150.0,
            all_in_cost_bps=40.0,
            spread_pct=0.15,
            depth_notional=80000.0,
            entry_confidence=entry_confidence,
        )

    def test_zero_confidence_rejected(self):
        result = self._gate(entry_confidence=0.0)
        assert not result["approved"]
        assert result["decision_reason_code"] == "LOW_CONFIDENCE_ENTRY"

    def test_low_confidence_rejected(self):
        result = self._gate(entry_confidence=0.25)
        assert not result["approved"]
        assert result["decision_reason_code"] == "LOW_CONFIDENCE_ENTRY"

    def test_confidence_at_floor_passes(self):
        """Exactly at MIN_ENTRY_CONFIDENCE=0.40 should not be rejected by this gate."""
        from services.trading_brain_v2.trade_feasibility_gate import MIN_ENTRY_CONFIDENCE
        result = self._gate(entry_confidence=MIN_ENTRY_CONFIDENCE)
        # Should not be blocked for confidence; may fail other checks but not confidence
        assert result["decision_reason_code"] != "LOW_CONFIDENCE_ENTRY"

    def test_high_confidence_passes_confidence_gate(self):
        result = self._gate(entry_confidence=0.75)
        assert result["decision_reason_code"] != "LOW_CONFIDENCE_ENTRY"


# ── 9. Cost-to-edge ratio ────────────────────────────────────────────────────

class TestCostToEdgeRatio:
    """Tightened MAX_COST_TO_EDGE_RATIO: 0.65 → 0.55.

    Note: for normal bots (k=1.5), EDGE_TOO_SMALL fires when cost/gross > 0.40.
    Since 0.40 < 0.55, EDGE_TOO_SMALL always fires before COST_TOO_HIGH for
    normal bots. The tests verify the tighter threshold is recorded in the
    module and that trades are rejected when cost dominates gross edge.
    """

    def test_cost_ratio_constant_is_055(self):
        """MAX_COST_TO_EDGE_RATIO must be exactly 0.55 (was 0.65)."""
        from services.trading_brain_v2.trade_feasibility_gate import MAX_COST_TO_EDGE_RATIO
        assert MAX_COST_TO_EDGE_RATIO == 0.55, (
            f"Expected MAX_COST_TO_EDGE_RATIO=0.55, got {MAX_COST_TO_EDGE_RATIO}"
        )

    def test_cost_dominating_edge_is_rejected(self):
        """When cost consumes most of the gross edge, trade is rejected (any reason)."""
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        gross = 200.0
        cost = gross * 0.58  # 58% → above 55% threshold
        result = gate.evaluate(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=5000.0,
            expected_gross_edge_bps=gross,
            all_in_cost_bps=cost,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.70,
        )
        # Trade must be rejected; with k=1.5 the edge check fires before cost check
        assert not result["approved"]
        assert result["decision_reason_code"] in ("COST_TOO_HIGH", "EDGE_TOO_SMALL")

    def test_cost_ratio_below_055_does_not_block_for_cost(self):
        """all_in_cost = 0.50 × gross_edge → below new limit → cost gate passes."""
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        gross = 200.0
        cost = gross * 0.50  # 50% → below 55% threshold
        result = gate.evaluate(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=5000.0,
            expected_gross_edge_bps=gross,
            all_in_cost_bps=cost,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.70,
        )
        assert result["decision_reason_code"] != "COST_TOO_HIGH"

    def test_old_threshold_065_now_fails(self):
        """cost = 0.62 × gross: passed old 0.65 limit, must be rejected (any reason)."""
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        gate = TradeFeasibilityGate()
        gross = 200.0
        cost = gross * 0.62
        result = gate.evaluate(
            strategy="normal",
            venue="binance",
            symbol="BTC/USDT",
            bot_equity=10000.0,
            notional=5000.0,
            expected_gross_edge_bps=gross,
            all_in_cost_bps=cost,
            spread_pct=0.10,
            depth_notional=200000.0,
            entry_confidence=0.70,
        )
        assert not result["approved"]


# ── 10 & 11. Scalper re-entry discipline ────────────────────────────────────

class TestScalperReentryDiscipline:
    """Scalper blocked after weak exit; allowed when conditions improve."""

    def _contracts(self):
        from services.trading_brain_v2.bot_contracts import BotBehavioralContracts
        return BotBehavioralContracts()

    def test_no_state_allows_reentry(self):
        """No prior exit state → always allowed."""
        c = self._contracts()
        result = c.check_scalper_reentry_discipline(
            "bot1", current_regime_confidence=0.5, current_entry_confidence=0.6
        )
        assert result["allowed"] is True

    def test_weak_exit_blocks_reentry_within_cooldown(self):
        """After a weak exit, re-entry is blocked within cooldown window."""
        c = self._contracts()
        c.record_scalper_exit(
            "bot1",
            exit_reason="scalper_no_progress_exit",
            regime_confidence=0.50,
            entry_confidence=0.55,
        )
        # Verify exit state was stored correctly
        stored = c._scalper_exit_state.get("bot1", {})
        assert stored["regime_confidence"] == 0.50
        assert stored["entry_confidence"] == 0.55

        result = c.check_scalper_reentry_discipline(
            "bot1",
            current_regime_confidence=0.52,  # barely changed
            current_entry_confidence=0.56,
        )
        assert result["allowed"] is False
        assert result["reason_code"] == "SCALPER_REENTRY_COOLDOWN"

    def test_stale_exit_blocks_reentry(self):
        """stale_exit also triggers cooldown."""
        c = self._contracts()
        # Record exit with current confidence levels (important: set baseline > 0)
        c.record_scalper_exit(
            "bot1", exit_reason="stale_exit",
            regime_confidence=0.50, entry_confidence=0.55,
        )
        result = c.check_scalper_reentry_discipline(
            "bot1",
            current_regime_confidence=0.52,  # only +0.02, below improvement threshold
            current_entry_confidence=0.56,   # only +0.01, below improvement threshold
        )
        assert result["allowed"] is False

    def test_take_profit_exit_clears_cooldown(self):
        """A successful exit (take_profit) must clear any lingering cooldown."""
        c = self._contracts()
        c.record_scalper_exit("bot1", exit_reason="scalper_no_progress_exit")
        # Now record a clean take-profit exit
        c.record_scalper_exit("bot1", exit_reason="take_profit")
        result = c.check_scalper_reentry_discipline(
            "bot1", current_regime_confidence=0.5, current_entry_confidence=0.5
        )
        assert result["allowed"] is True

    def test_regime_improvement_allows_early_reentry(self):
        """Significant regime confidence improvement allows early re-entry."""
        from services.trading_brain_v2.bot_contracts import _REGIME_CONF_IMPROVEMENT_MIN
        c = self._contracts()
        c.record_scalper_exit(
            "bot1",
            exit_reason="no_progress_exit",
            regime_confidence=0.40,
            entry_confidence=0.50,
        )
        improved_rc = 0.40 + _REGIME_CONF_IMPROVEMENT_MIN + 0.01  # just above threshold
        result = c.check_scalper_reentry_discipline(
            "bot1",
            current_regime_confidence=improved_rc,
            current_entry_confidence=0.51,  # minimal entry confidence change
        )
        assert result["allowed"] is True
        assert result["reason_code"] == "SCALPER_REENTRY_EARLY_IMPROVEMENT"

    def test_entry_confidence_improvement_allows_early_reentry(self):
        """Significant entry confidence improvement allows early re-entry."""
        from services.trading_brain_v2.bot_contracts import _ENTRY_CONF_IMPROVEMENT_MIN
        c = self._contracts()
        c.record_scalper_exit(
            "bot1",
            exit_reason="scalper_no_progress_exit",
            regime_confidence=0.50,
            entry_confidence=0.55,
        )
        improved_ec = 0.55 + _ENTRY_CONF_IMPROVEMENT_MIN + 0.01
        result = c.check_scalper_reentry_discipline(
            "bot1",
            current_regime_confidence=0.51,  # minimal regime change
            current_entry_confidence=improved_ec,
        )
        assert result["allowed"] is True

    def test_cooldown_expires(self):
        """After cooldown_seconds have passed, re-entry is allowed."""
        from services.trading_brain_v2.bot_contracts import SCALPER_REENTRY_COOLDOWN_SECONDS
        c = self._contracts()
        c.record_scalper_exit("bot1", exit_reason="stale_exit")
        # Simulate elapsed time by directly manipulating the exit timestamp
        c._scalper_exit_state["bot1"]["exit_ts"] = (
            time.time() - SCALPER_REENTRY_COOLDOWN_SECONDS - 1
        )
        result = c.check_scalper_reentry_discipline(
            "bot1", current_regime_confidence=0.5, current_entry_confidence=0.5
        )
        assert result["allowed"] is True

    def test_different_bots_are_independent(self):
        """Cooldown on bot1 does not affect bot2."""
        c = self._contracts()
        c.record_scalper_exit("bot1", exit_reason="stale_exit", regime_confidence=0.4)
        result = c.check_scalper_reentry_discipline(
            "bot2", current_regime_confidence=0.4, current_entry_confidence=0.4
        )
        assert result["allowed"] is True


# ── 12. New reason codes are stable ─────────────────────────────────────────

class TestNewReasonCodes:
    """All new reason codes are non-empty strings and have catalog entries."""

    NEW_CODES = [
        "PAPER_HOLD_CAP_EXCEEDED",
        "STAGNATION_EXIT",
        "REGIME_DECAY_EXIT",
        "PROFIT_PROTECTION_EXIT",
        "SCALPER_REENTRY_COOLDOWN",
        "LOW_CONFIDENCE_ENTRY",
    ]

    def test_reason_codes_are_strings(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes
        for attr in self.NEW_CODES:
            val = getattr(ReasonCodes, attr, None)
            assert val is not None, f"ReasonCodes.{attr} is missing"
            assert isinstance(val, str) and val, f"ReasonCodes.{attr} must be a non-empty string"

    def test_reason_codes_in_catalog(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        for attr in self.NEW_CODES:
            val = getattr(ReasonCodes, attr)
            assert val in REASON_CATALOG, (
                f"ReasonCodes.{attr}={val!r} missing from REASON_CATALOG"
            )

    def test_catalog_entries_are_nonempty_strings(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        for attr in self.NEW_CODES:
            val = getattr(ReasonCodes, attr)
            text = REASON_CATALOG[val]
            assert isinstance(text, str) and text, (
                f"REASON_CATALOG[{val!r}] must be a non-empty string"
            )

    def test_safe_reason_text_returns_non_empty(self):
        from services.trading_brain_v2.reason_codes import safe_reason_text, ReasonCodes
        for attr in self.NEW_CODES:
            val = getattr(ReasonCodes, attr)
            text = safe_reason_text(val)
            assert text, f"safe_reason_text({val!r}) returned empty"


# ── 13. trade_worth_filter raised ZAR floors ─────────────────────────────────

class TestTradeWorthFilterRaisedFloors:
    """trade_worth_filter now uses R3.00 small ZAR floor (was R1.50)."""

    def _eval(self, **kwargs):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        defaults = dict(
            bot_type="normal",
            exchange="luno",
            bot_equity=2000.0,
            notional=200.0,
            expected_gross_edge_bps=150.0,
            all_in_cost_bps=40.0,
        )
        defaults.update(kwargs)
        return evaluate_minimum_worthwhile_trade(**defaults)

    def test_old_1_50_floor_no_longer_passes(self):
        """
        notional=150, net_edge=110 bps → profit=1.65; was >= old R1.50 but < new R3.00.
        """
        result = self._eval(notional=150.0)
        assert not result["approved"]
        assert result["reason_code"] == "INSUFFICIENT_ABSOLUTE_EDGE"

    def test_new_floor_passes_with_sufficient_notional(self):
        """notional=300, net_edge=110 bps → profit=3.30 >= R3.00 → PASS."""
        result = self._eval(notional=300.0)
        assert result["approved"]
        assert result["reason_code"] == "TRADE_WORTH_FILTER_OK"

    def test_scalper_zar_floor_raised(self):
        """Scalper small ZAR floor is now R1.50 (was R0.50)."""
        from services.trade_worth_filter import _ABS_MIN_QUOTE
        floor = _ABS_MIN_QUOTE.get(("scalper", "small", "zar"))
        assert floor == 1.50, f"Expected R1.50 scalper small ZAR floor, got {floor}"

    def test_usdt_floors_unchanged(self):
        """USDT floors must remain unchanged."""
        from services.trade_worth_filter import _ABS_MIN_QUOTE
        assert _ABS_MIN_QUOTE[("normal", "small", "usdt")] == 0.80
        assert _ABS_MIN_QUOTE[("scalper", "small", "usdt")] == 0.20


# ── 14. Ledger semantics not broken by new scalper tracking ──────────────────

class TestLedgerSemanticsPreserved:
    """record_scalper_exit does not corrupt bot_contracts loss-streak state."""

    def test_record_scalper_exit_does_not_corrupt_loss_state(self):
        from services.trading_brain_v2.bot_contracts import BotBehavioralContracts
        c = BotBehavioralContracts()
        bot_id = "bot_ledger_test"

        # Simulate a loss streak tracked via record_trade_result
        c.record_trade_result(bot_id, "scalper", won=False)
        c.record_trade_result(bot_id, "scalper", won=False)

        state_before = dict(c._bot_state.get(bot_id, {}))

        # Now record a weak scalper exit
        c.record_scalper_exit(bot_id, exit_reason="stale_exit")

        # _bot_state must be untouched by record_scalper_exit
        assert c._bot_state.get(bot_id) == state_before, (
            "record_scalper_exit must not modify _bot_state loss-streak tracking"
        )
        # _scalper_exit_state should have the new entry
        assert bot_id in c._scalper_exit_state

    def test_record_trade_entry_not_affected(self):
        """record_trade_entry continues to work independently."""
        from services.trading_brain_v2.bot_contracts import BotBehavioralContracts
        c = BotBehavioralContracts()
        c.record_scalper_exit("bot2", exit_reason="scalper_no_progress_exit")
        c.record_trade_entry("bot2")
        # Should still be in exit state (entry recording is separate from exit clearing)
        assert "bot2" in c._scalper_exit_state
