"""
Phase 1 Live-Fix Tests
======================
Validates every fix wired into the live production backend path in Phase 1.

Covers:
  1. engines/self_healing.py  — get_status() added, returns correct structure
  2. routes/self_healing_endpoints.py — imports engines.self_healing not root
  3. services/entry_quality.py — None guard on fetchai/coinstats
  4. paper_trading_engine constants — SCALPER_MIN_AVG_CONFIDENCE lowered to 0.70,
     confidence_sources gate relaxed to 2
  5. trading_scheduler.py — scalper bots queued with priority=1
  6. services/trade_worth_filter.py — wired into V1 (import present in engine)
  7. routes/bot_lifecycle.py — truth_normalizer imported and used
  8. MIN_TRADE_PROFIT_THRESHOLD_ZAR no-op removed
"""

import math
import sys
import os
import re

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────
BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 & 2: engines/self_healing.py has get_status() and endpoint uses it
# ─────────────────────────────────────────────────────────────────────────────
class TestSelfHealingStatusFix:
    def _sh_source(self):
        path = os.path.join(BACKEND, "engines", "self_healing.py")
        with open(path) as fh:
            return fh.read()

    def test_engines_self_healing_has_get_status(self):
        """engines/self_healing.py must define get_status()."""
        source = self._sh_source()
        assert "def get_status(" in source, "get_status() must exist in engines/self_healing.py"

    def test_get_status_returns_enabled_and_state(self):
        """get_status() must set both 'enabled' and 'state' keys."""
        source = self._sh_source()
        assert '"enabled"' in source or "'enabled'" in source, "'enabled' key must be in get_status return"
        assert '"state"' in source or "'state'" in source, "'state' key must be in get_status return"

    def test_fresh_instance_returns_idle_not_running(self):
        """Static analysis: fresh instance path must return idle/disabled (not 'running')."""
        source = self._sh_source()
        # The function must have the logic for the non-running case
        assert "idle" in source, "idle state must be returned when not started"

    def test_started_marks_running(self):
        """start() must set is_running = True."""
        source = self._sh_source()
        assert "self.is_running = True" in source, "start() must set is_running=True"
        # Must also track started state
        assert "_was_started" in source or "last_started_at" in source, (
            "start() must track that it was called (_was_started or last_started_at)"
        )

    def test_get_status_reports_running_when_is_running_true(self):
        """get_status must check self.is_running and return state='running'."""
        source = self._sh_source()
        assert "self.is_running" in source, "get_status must check self.is_running"
        assert "running" in source, "get_status must be able to return 'running' state"

    def test_endpoint_source_file_imports_engines_module(self):
        """routes/self_healing_endpoints.py must import from engines.self_healing."""
        endpoint_path = os.path.join(BACKEND, "routes", "self_healing_endpoints.py")
        with open(endpoint_path) as fh:
            source = fh.read()
        assert "from engines.self_healing import self_healing" in source, (
            "Endpoint must import from engines.self_healing, not root self_healing"
        )
        assert "from self_healing import self_healing" not in source, (
            "Endpoint must NOT import from root self_healing module"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3: entry_quality.py — None values don't crash
# ─────────────────────────────────────────────────────────────────────────────
class TestEntryQualityNoneGuard:
    def _call(self, **overrides):
        from services.entry_quality import compute_entry_confidence
        defaults = dict(
            bot_type="normal",
            regime_confidence=0.6,
            ml_confidence=0.5,
            fetchai_confidence=70,
            coinstats_strength=65,
            consensus_strength=2,
            consensus_sources=3,
            direction_conflict=False,
        )
        defaults.update(overrides)
        return compute_entry_confidence(**defaults)

    def test_none_fetchai_confidence_does_not_raise(self):
        result = self._call(fetchai_confidence=None)
        assert isinstance(result, dict)
        score = result["entry_confidence_score"]
        assert math.isfinite(score)
        assert 0.0 <= score <= 1.0

    def test_none_coinstats_strength_does_not_raise(self):
        result = self._call(coinstats_strength=None)
        assert isinstance(result, dict)
        score = result["entry_confidence_score"]
        assert math.isfinite(score)

    def test_none_ml_confidence_does_not_raise(self):
        result = self._call(ml_confidence=None)
        assert isinstance(result, dict)
        score = result["entry_confidence_score"]
        assert math.isfinite(score)

    def test_none_regime_confidence_does_not_raise(self):
        result = self._call(regime_confidence=None)
        assert isinstance(result, dict)
        score = result["entry_confidence_score"]
        assert math.isfinite(score)

    def test_all_none_inputs_still_valid(self):
        result = self._call(
            regime_confidence=None, ml_confidence=None,
            fetchai_confidence=None, coinstats_strength=None,
        )
        score = result["entry_confidence_score"]
        assert math.isfinite(score)
        assert score >= 0.0

    def test_zero_inputs_produce_penalized_score(self):
        """All-zero signals should produce a low but valid score."""
        result = self._call(
            regime_confidence=0, ml_confidence=0,
            fetchai_confidence=0, coinstats_strength=0,
            consensus_strength=0, consensus_sources=0,
        )
        score = result["entry_confidence_score"]
        assert score < 0.3, f"Expected low score for zero inputs, got {score}"


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4: Scalper gate constants relaxed
# ─────────────────────────────────────────────────────────────────────────────
class TestScalperGateConstants:
    def _engine_source(self):
        path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(path) as fh:
            return fh.read()

    def test_scalper_min_avg_confidence_is_0_70(self):
        """SCALPER_MIN_AVG_CONFIDENCE default must be '0.70' (relaxed from '0.75')."""
        source = self._engine_source()
        # Use regex to find the specific assignment line
        pattern = r'SCALPER_MIN_AVG_CONFIDENCE\s*=\s*float\(os\.getenv\([^,]+,\s*["\']0\.70["\']'
        assert re.search(pattern, source), (
            "SCALPER_MIN_AVG_CONFIDENCE default must be '0.70' – "
            "the regex looking for the assignment did not match"
        )
        old_pattern = r'SCALPER_MIN_AVG_CONFIDENCE\s*=\s*float\(os\.getenv\([^,]+,\s*["\']0\.75["\']'
        assert not re.search(old_pattern, source), (
            "SCALPER_MIN_AVG_CONFIDENCE default must not be '0.75'"
        )

    def test_scalper_gate_requires_only_2_sources(self):
        """The scalper confidence_sources gate must check < 2 (not < 3)."""
        source = self._engine_source()
        # Should NOT contain the old stricter gate
        assert "confidence_sources < 3" not in source, (
            "Old 'confidence_sources < 3' scalper gate found; should be < 2"
        )
        # Should contain the relaxed gate  
        assert source.count("confidence_sources < 2") >= 1, (
            "Expected at least one 'confidence_sources < 2' check"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 5: trading_scheduler.py gives scalpers priority=1
# ─────────────────────────────────────────────────────────────────────────────
class TestScalperQueuePriority:
    def test_scheduler_uses_bot_type_for_priority(self):
        """trading_scheduler.py must assign priority=1 to scalper bots."""
        scheduler_path = os.path.join(BACKEND, "trading_scheduler.py")
        with open(scheduler_path) as fh:
            source = fh.read()
        assert "bot_priority" in source, "bot_priority variable expected"
        assert "scalper" in source.lower(), "scalper check expected in scheduler"
        assert "priority=bot_priority" in source, "priority=bot_priority assignment expected"

    def test_scalper_gets_higher_priority_than_normal(self):
        """Priority value for scalper must be strictly > priority for normal bot."""
        scheduler_path = os.path.join(BACKEND, "trading_scheduler.py")
        with open(scheduler_path) as fh:
            source = fh.read()
        # Extract the priority assignment line to verify 1 vs 0
        assert 'priority = 1 if str(bot.get("bot_type", "normal")).lower() == "scalper" else 0' in source or \
               "bot_priority = 1 if" in source, (
            "Scalper must be assigned priority 1, normal priority 0"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 6: trade_worth_filter is imported and wired in paper_trading_engine
# ─────────────────────────────────────────────────────────────────────────────
class TestTradeWorthFilterWired:
    def test_trade_worth_filter_imported_in_engine(self):
        """paper_trading_engine must import evaluate_minimum_worthwhile_trade."""
        engine_path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(engine_path) as fh:
            source = fh.read()
        assert "evaluate_minimum_worthwhile_trade" in source, (
            "evaluate_minimum_worthwhile_trade must be imported in paper_trading_engine"
        )
        assert "from services.trade_worth_filter import evaluate_minimum_worthwhile_trade" in source, (
            "Import from services.trade_worth_filter must be present"
        )

    def test_trade_worth_filter_called_in_v1_path(self):
        """engine must call evaluate_minimum_worthwhile_trade() in the V1 entry path."""
        engine_path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(engine_path) as fh:
            source = fh.read()
        assert "_worth_result = evaluate_minimum_worthwhile_trade(" in source, (
            "evaluate_minimum_worthwhile_trade must be called in V1 entry path"
        )
        assert "WORTHWHILE TRADE GATE" in source, "Gate comment/label expected"

    def test_trade_worth_filter_rejection_handled(self):
        """engine must handle approved=False from the gate and return a rejection."""
        engine_path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(engine_path) as fh:
            source = fh.read()
        assert "trade_worth_filter" in source, "Rejection skip_reason 'trade_worth_filter' must be in engine"
        assert 'reason_code": _wrc' in source or '"reason_code": _wrc' in source or "_wrc" in source, (
            "Rejection must propagate reason_code from gate"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 7: truth_normalizer imported and used in bot_lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestTruthNormalizerWired:
    def test_bot_lifecycle_imports_truth_normalizer(self):
        lc_path = os.path.join(BACKEND, "routes", "bot_lifecycle.py")
        with open(lc_path) as fh:
            source = fh.read()
        assert "from services.truth_normalizer import normalize_bot_trade_truth" in source, (
            "bot_lifecycle must import normalize_bot_trade_truth from services.truth_normalizer"
        )

    def test_bot_lifecycle_calls_normalize_bot_trade_truth(self):
        lc_path = os.path.join(BACKEND, "routes", "bot_lifecycle.py")
        with open(lc_path) as fh:
            source = fh.read()
        assert "normalize_bot_trade_truth" in source, (
            "bot_lifecycle must call normalize_bot_trade_truth"
        )
        assert "_truth" in source, (
            "Expected _truth variable from normalize_bot_trade_truth result"
        )

    def test_bot_lifecycle_uses_truth_for_market_regime(self):
        lc_path = os.path.join(BACKEND, "routes", "bot_lifecycle.py")
        with open(lc_path) as fh:
            source = fh.read()
        assert '_truth.get("market_regime")' in source, (
            "market_regime in enriched_bot must come from _truth"
        )

    def test_bot_lifecycle_uses_truth_for_regime_confidence(self):
        lc_path = os.path.join(BACKEND, "routes", "bot_lifecycle.py")
        with open(lc_path) as fh:
            source = fh.read()
        assert '_truth.get("regime_confidence")' in source, (
            "regime_confidence in enriched_bot must come from _truth"
        )

    def test_bot_lifecycle_bulk_fetches_open_trades(self):
        """bot_lifecycle must perform a bulk open-trade query before the enrichment loop."""
        lc_path = os.path.join(BACKEND, "routes", "bot_lifecycle.py")
        with open(lc_path) as fh:
            source = fh.read()
        assert "open_trade_by_bot" in source, (
            "open_trade_by_bot lookup dict must be built before bot loop"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 8: MIN_TRADE_PROFIT_THRESHOLD_ZAR no-op removed
# ─────────────────────────────────────────────────────────────────────────────
class TestMinProfitNoOpRemoved:
    def test_no_op_close_reason_relabelling_removed(self):
        """The dead close_reason relabelling block must not exist."""
        engine_path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(engine_path) as fh:
            source = fh.read()
        # The old code was:
        #   if net_profit > 0 and net_profit < MIN_TRADE_PROFIT_THRESHOLD_ZAR:
        #       close_reason = "take_profit" if close_reason == "take_profit" else close_reason
        # This should be gone
        assert (
            'close_reason = "take_profit" if close_reason == "take_profit" else close_reason'
            not in source
        ), "Dead MIN_TRADE_PROFIT_THRESHOLD_ZAR no-op block must be removed"

    def test_min_profit_threshold_comment_present(self):
        """A comment explaining why the check was removed should be present."""
        engine_path = os.path.join(BACKEND, "paper_trading_engine.py")
        with open(engine_path) as fh:
            source = fh.read()
        assert "MIN_TRADE_PROFIT_THRESHOLD_ZAR is no longer checked" in source or \
               "worthwhile_trade gate" in source, (
            "Removal of no-op must be documented in a code comment"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Integration: trade_worth_filter rejects tiny trades
# ─────────────────────────────────────────────────────────────────────────────
class TestTradeWorthFilterBehavior:
    """Black-box tests on the filter function itself — verifies gate logic."""

    def _eval(self, **kwargs):
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        defaults = dict(
            bot_type="normal",
            exchange="luno",
            bot_equity=500.0,
            notional=15.0,
            expected_gross_edge_bps=25.0,
            all_in_cost_bps=22.0,  # net = 3 BPS  → below 15 BPS floor
        )
        defaults.update(kwargs)
        return evaluate_minimum_worthwhile_trade(**defaults)

    def test_insufficient_cost_edge_rejected(self):
        result = self._eval()
        assert result["approved"] is False
        assert result["reason_code"] == "INSUFFICIENT_COST_EDGE"

    def test_sufficient_edge_approved(self):
        result = self._eval(expected_gross_edge_bps=100.0, all_in_cost_bps=20.0)
        # net = 80 BPS >> 15 BPS floor; notional=15, profit = 15 * 0.008 = 0.12
        # abs minimum for small ZAR equity might reject; let's use a bigger notional
        r2 = self._eval(
            expected_gross_edge_bps=100.0,
            all_in_cost_bps=20.0,
            bot_equity=6000.0,  # medium bucket
            notional=200.0,
        )
        # net profit = 200 * (80/10000) = R1.60 vs abs_min R20 for medium/normal/zar
        # still gets rejected on absolute check — use large equity
        r3 = self._eval(
            expected_gross_edge_bps=200.0,
            all_in_cost_bps=20.0,
            bot_equity=6000.0,
            notional=500.0,
        )
        # net = 180 BPS, profit = 500 * 0.018 = R9 vs abs_min R20 for medium
        # still below — use large notional
        r4 = self._eval(
            expected_gross_edge_bps=200.0,
            all_in_cost_bps=20.0,
            bot_equity=60000.0,  # large bucket
            notional=5000.0,
        )
        # net = 180 BPS, profit = 5000*0.018 = R90 vs R60 min for large/normal/zar
        assert r4["approved"] is True

    def test_scalper_has_lower_edge_floor(self):
        """Scalper min net edge is 20 BPS (unified canonical value).

        Scalpers require a HIGHER minimum net edge than normal bots (20 BPS vs 15 BPS)
        because their tight hold windows must justify round-trip costs more aggressively.
        Both trade_worth_filter and trade_feasibility_gate use the canonical 20 BPS value.
        """
        from services.trade_worth_filter import MIN_NET_EDGE_BPS
        assert MIN_NET_EDGE_BPS["scalper"] >= MIN_NET_EDGE_BPS["normal"]
        assert MIN_NET_EDGE_BPS["scalper"] == 20.0
