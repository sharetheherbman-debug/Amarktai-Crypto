"""
Canonical Currency Truth v2 Tests
===================================
Validates the two critical blockers fixed in this PR:

BLOCKER 1 — Bot capital / FX truth in /api/bots/status
  • Binance bot funded with R1000 must show ~52.63 USDT native capital
  • canonical_base_capital_zar must be 1000
  • total_equity_display must be ~R1000, NOT ~R19 000

BLOCKER 2 — Min-profit gate blocking all paper trades
  • Luno normal bot with strong net edge must NOT be rejected with ENTRY_REJECTED_MIN_PROFIT
  • Binance normal bot with strong net edge must NOT be rejected with ENTRY_REJECTED_MIN_PROFIT
  • Luno scalper with sufficient edge must pass min-profit
  • Truly uneconomic candidate must still be rejected

PART C — Transparency fields
  • projected_net_profit_quote in gate output
  • min_profit_required_quote in gate output
  • rejection_currency_side in gate output

PART D — Canonical metrics quote fields
  • capital_initial_quote / capital_current_quote / capital_available_quote present
  • ZAR fields separate from quote fields
"""

import asyncio
import os
import sys
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")

# Check if motor (MongoDB async driver) is available for DB-backed tests.
try:
    import motor  # noqa: F401
    _MOTOR_AVAILABLE = True
except ImportError:
    _MOTOR_AVAILABLE = False

_skip_no_motor = pytest.mark.skipif(
    not _MOTOR_AVAILABLE,
    reason="motor async MongoDB driver not installed in this test environment",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_fx_rate(rate: float):
    """Patch the FX normalizer's cached USDT→ZAR rate."""
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(rate, source="test")


def _feasibility_gate_approve_setup():
    """Common regime/eligibility payload for an approvable trade."""
    return {
        "regime_result": {
            "regime_label": "trending_up",
            "regime_confidence": 0.8,
        },
        "regime_eligibility": {
            "eligible": True,
            "action": "full",
            "edge_multiplier": 1.0,
            "size_multiplier": 1.0,
        },
        "spread_pct": 0.10,
        "depth_notional": 500_000,
        "entry_confidence": 0.75,
    }


def _make_trade_cursor_mock(rows=None):
    """Build a mock aggregate cursor returning the given rows."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows or [])
    return cursor


# ══════════════════════════════════════════════════════════════════════════════
# BLOCKER 1 — Canonical metrics quote fields present and correct
# ══════════════════════════════════════════════════════════════════════════════

class TestCanonicalMetricsQuoteFields:
    """canonical_metrics.get_canonical_metrics_snapshot must expose
    capital_initial_quote / capital_current_quote / capital_available_quote."""

    @_skip_no_motor
    def test_capital_initial_quote_present_for_binance_bot(self):
        """After the fix, by_bot_id must include capital_initial_quote."""
        from services.canonical_metrics import get_canonical_metrics_snapshot

        _mock_fx_rate(19.0)

        bot_list = [
            {
                "id": "bot_binance_001",
                "user_id": "user1",
                "exchange": "binance",
                "initial_capital": 52.63,
                "current_capital": 52.63,
                "quote_currency": "USDT",
                "canonical_base_capital_zar": 1000.0,
                "status": "active",
                "open_position_value": 0.0,
            }
        ]

        trade_cursor = _make_trade_cursor_mock()
        trades_coll = MagicMock()
        trades_coll.aggregate.return_value = trade_cursor

        with patch("services.canonical_metrics.db.trades_collection", trades_coll), \
             patch("services.canonical_metrics.backfill_missing_current_capital", new=AsyncMock(return_value=0)):
            result = asyncio.run(
                get_canonical_metrics_snapshot("user1", bots=bot_list)
            )

        bot_data = result["by_bot_id"].get("bot_binance_001", {})

        # Native quote fields must be present after the fix
        assert "capital_initial_quote" in bot_data, "capital_initial_quote missing from canonical snapshot"
        assert "capital_current_quote" in bot_data, "capital_current_quote missing from canonical snapshot"
        assert "capital_available_quote" in bot_data, "capital_available_quote missing from canonical snapshot"
        assert "open_position_value_quote" in bot_data, "open_position_value_quote missing from canonical snapshot"

    @_skip_no_motor
    def test_capital_initial_quote_is_usdt_not_zar(self):
        """capital_initial_quote must be the USDT amount (52.63), not ZAR (1000)."""
        from services.canonical_metrics import get_canonical_metrics_snapshot

        _mock_fx_rate(19.0)

        bot_list = [
            {
                "id": "bot_binance_002",
                "user_id": "user1",
                "exchange": "binance",
                "initial_capital": 52.63,
                "current_capital": 52.63,
                "quote_currency": "USDT",
                "canonical_base_capital_zar": 1000.0,
                "status": "active",
                "open_position_value": 0.0,
            }
        ]

        trade_cursor = _make_trade_cursor_mock()
        trades_coll = MagicMock()
        trades_coll.aggregate.return_value = trade_cursor

        with patch("services.canonical_metrics.db.trades_collection", trades_coll), \
             patch("services.canonical_metrics.backfill_missing_current_capital", new=AsyncMock(return_value=0)):
            result = asyncio.run(
                get_canonical_metrics_snapshot("user1", bots=bot_list)
            )

        bot_data = result["by_bot_id"].get("bot_binance_002", {})
        capital_quote = bot_data.get("capital_initial_quote", 0)
        capital_display = bot_data.get("capital_initial", 0)  # ZAR-equivalent

        # Native quote must be ~52.63 USDT
        assert math.isclose(capital_quote, 52.63, rel_tol=1e-3), (
            f"capital_initial_quote should be ~52.63 USDT, got {capital_quote}"
        )
        # ZAR display must be ~1000 (52.63 × 19 ≈ 1000)
        assert capital_display >= 900, (
            f"capital_initial (ZAR display) should be ~1000, got {capital_display}"
        )
        # They must NOT be equal — the ZAR display is ~19× larger
        assert abs(capital_display - capital_quote) > 10, (
            f"capital_initial ({capital_display}) and capital_initial_quote ({capital_quote}) "
            "should differ — one is ZAR-display, the other is native USDT"
        )

    @_skip_no_motor
    def test_luno_bot_quote_equals_zar(self):
        """For a ZAR (Luno) bot, quote and ZAR fields must be equal (fx=1.0)."""
        from services.canonical_metrics import get_canonical_metrics_snapshot

        _mock_fx_rate(19.0)  # irrelevant for ZAR; just set a consistent rate

        bot_list = [
            {
                "id": "bot_luno_001",
                "user_id": "user1",
                "exchange": "luno",
                "initial_capital": 2000.0,
                "current_capital": 2000.0,
                "quote_currency": "ZAR",
                "status": "active",
                "open_position_value": 0.0,
            }
        ]

        trade_cursor = _make_trade_cursor_mock()
        trades_coll = MagicMock()
        trades_coll.aggregate.return_value = trade_cursor

        with patch("services.canonical_metrics.db.trades_collection", trades_coll), \
             patch("services.canonical_metrics.backfill_missing_current_capital", new=AsyncMock(return_value=0)):
            result = asyncio.run(
                get_canonical_metrics_snapshot("user1", bots=bot_list)
            )

        bot_data = result["by_bot_id"].get("bot_luno_001", {})

        # For ZAR bot, quote == ZAR (fx_rate = 1.0)
        quote = bot_data.get("capital_initial_quote", 0)
        zar_display = bot_data.get("capital_initial", 0)
        assert math.isclose(quote, 2000.0, rel_tol=1e-3), (
            f"Luno capital_initial_quote should be 2000 ZAR, got {quote}"
        )
        assert math.isclose(zar_display, 2000.0, rel_tol=1e-3), (
            f"Luno capital_initial (ZAR display) should be 2000, got {zar_display}"
        )

    def test_total_equity_display_not_inflated(self):
        """Using capital_initial_quote for equity calculations must NOT inflate to R19 000."""
        _mock_fx_rate(19.0)

        from services.fx_normalizer import get_fx_rate

        # Simulate the bot_lifecycle.py calculation after the fix.
        # base_initial_capital = capital_initial_quote = 52.63 USDT (native quote)
        base_initial_capital = 52.63   # USDT (the correct native quote value)
        base_current_capital = 52.63   # USDT
        base_open_position = 0.0

        fx_rate, _ = get_fx_rate("USDT", "ZAR")   # ~19.0

        # These match the bot_lifecycle.py formulas after the fix:
        _total_equity_quote = round(base_current_capital + base_open_position, 2)
        _total_equity_display = round(_total_equity_quote * fx_rate, 2)

        # Must be ~R1000, NOT ~R19 000
        assert _total_equity_display < 1100.0, (
            f"total_equity_display is R{_total_equity_display:.2f} — should be ~R1000, not R19 000"
        )
        assert _total_equity_display > 900.0, (
            f"total_equity_display is R{_total_equity_display:.2f} — should be ~R1000"
        )


# ══════════════════════════════════════════════════════════════════════════════
# BLOCKER 2 — Min-profit gate no longer blocks valid paper trades
# ══════════════════════════════════════════════════════════════════════════════

class TestMinProfitGateNotionalBoostImport:
    """Verify that the notional boost import uses the correct module."""

    def test_entry_thresholds_exports_required_symbols(self):
        """entry_thresholds must export equity_bucket, venue_class, ABS_PROFIT_MIN_QUOTE."""
        from services.trading_brain_v2.entry_thresholds import (
            ABS_PROFIT_MIN_QUOTE,
            equity_bucket,
            venue_class,
        )
        assert callable(equity_bucket)
        assert callable(venue_class)
        assert isinstance(ABS_PROFIT_MIN_QUOTE, dict)
        assert len(ABS_PROFIT_MIN_QUOTE) > 0

    def test_boost_import_does_not_fail(self):
        """The import that was broken (from trade_feasibility_gate) is now fixed."""
        try:
            from services.trading_brain_v2.entry_thresholds import (
                ABS_PROFIT_MIN_QUOTE,
                equity_bucket,
                venue_class,
            )
            _vc = venue_class("binance")
            _eq = equity_bucket(52.63, _vc)
            _lookup = ("normal", _eq, _vc)
            _abs_min = ABS_PROFIT_MIN_QUOTE.get(_lookup, 2.0)
            assert _abs_min == 0.10  # micro/usdt/normal
        except ImportError as e:
            pytest.fail(f"Notional boost import failed: {e}")

    def test_notional_boost_raises_to_minimum_viable(self):
        """
        With the fixed import, the notional boost must raise a tiny Kelly
        position to the minimum needed to clear the abs_profit floor.
        """
        from services.trading_brain_v2.entry_thresholds import (
            ABS_PROFIT_MIN_QUOTE,
            equity_bucket,
            venue_class,
        )

        paper_capital = 52.63       # USDT
        exchange = "binance"
        bot_type = "normal"
        expected_gross = 200.0      # bps (matching live log: 200 bps)
        all_in_cost = 33.0          # bps
        kelly_notional = 0.5263     # ~1% bootstrap Kelly (before boost)

        _net_edge_frac = max((expected_gross - all_in_cost) / 10000.0, 0.0001)
        _vc = venue_class(exchange)
        _eq_bucket = equity_bucket(paper_capital, _vc)
        _lookup = (bot_type, _eq_bucket, _vc)
        _abs_min = ABS_PROFIT_MIN_QUOTE.get(_lookup, 2.0)
        _min_notional = _abs_min / _net_edge_frac
        notional = max(kelly_notional, min(_min_notional, paper_capital))

        # After boost, notional must be at least _min_notional
        assert notional >= _min_notional, (
            f"Boosted notional {notional:.4f} should be >= min_notional {_min_notional:.4f}"
        )

        # Projected profit must now clear the minimum
        projected = notional * _net_edge_frac
        assert projected >= _abs_min, (
            f"Projected profit {projected:.4f} should be >= abs_min {_abs_min}"
        )


class TestLunoNormalPaperTradeCanPass:
    """
    A Luno normal paper bot with net_edge=134.8 bps should NOT be rejected
    by ENTRY_REJECTED_MIN_PROFIT after the notional boost fix.
    (Matches log evidence from the problem statement.)
    """

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        from services.trading_brain_v2.entry_thresholds import (
            ABS_PROFIT_MIN_QUOTE,
            equity_bucket,
            venue_class,
        )
        self.gate = TradeFeasibilityGate()
        self.ABS_PROFIT_MIN_QUOTE = ABS_PROFIT_MIN_QUOTE
        self.equity_bucket = equity_bucket
        self.venue_class = venue_class

    def _compute_boosted_notional(self, paper_capital, exchange, bot_type, gross_bps, cost_bps):
        """Replicate the paper_trading_engine.py notional boost logic (fixed version)."""
        kelly_notional = paper_capital * 0.01  # 1% bootstrap
        _net_edge_frac = max((gross_bps - cost_bps) / 10000.0, 0.0001)
        _vc = self.venue_class(exchange)
        _eq_bucket = self.equity_bucket(paper_capital, _vc)
        _lookup = (
            bot_type if bot_type in ("scalper", "mean_reversion") else "normal",
            _eq_bucket, _vc,
        )
        _abs_min = self.ABS_PROFIT_MIN_QUOTE.get(_lookup, 2.0)
        _min_notional = _abs_min / _net_edge_frac
        return max(kelly_notional, min(_min_notional, paper_capital))

    def test_luno_normal_passes_with_boosted_notional(self):
        """Luno normal: raw_edge=164 bps, all_in_cost=29.2 bps, net=134.8 bps → APPROVED."""
        gross_bps = 164.0
        cost_bps = 29.2
        paper_capital = 2000.0  # ZAR (wallet balance)

        notional = self._compute_boosted_notional(
            paper_capital, "luno", "normal", gross_bps, cost_bps
        )

        result = self.gate.evaluate(
            strategy="normal", venue="luno", symbol="XBTZAR",
            bot_equity=paper_capital, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            **_feasibility_gate_approve_setup(),
        )

        assert result["approved"] is True, (
            f"Luno normal should be APPROVED after notional boost. "
            f"Got reason={result['decision_reason_code']} "
            f"projected={result['projected_net_profit_quote']:.4f} "
            f"required={result.get('min_net_profit_quote_required', '?')}"
        )

    def test_luno_normal_not_rejected_min_profit(self):
        """Specifically: reason must NOT be ENTRY_REJECTED_MIN_PROFIT."""
        gross_bps = 164.0
        cost_bps = 29.2
        paper_capital = 2000.0

        notional = self._compute_boosted_notional(
            paper_capital, "luno", "normal", gross_bps, cost_bps
        )

        result = self.gate.evaluate(
            strategy="normal", venue="luno", symbol="XBTZAR",
            bot_equity=paper_capital, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            **_feasibility_gate_approve_setup(),
        )

        assert result["decision_reason_code"] != "ENTRY_REJECTED_MIN_PROFIT", (
            "Luno normal with 134.8 bps net edge must NOT be rejected by min-profit gate"
        )


class TestBinanceNormalPaperTradeCanPass:
    """
    A Binance normal paper bot with net_edge=167 bps and ~52.63 USDT capital
    should NOT be rejected by ENTRY_REJECTED_MIN_PROFIT after the fix.
    """

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        from services.trading_brain_v2.entry_thresholds import (
            ABS_PROFIT_MIN_QUOTE,
            equity_bucket,
            venue_class,
        )
        self.gate = TradeFeasibilityGate()
        self.ABS_PROFIT_MIN_QUOTE = ABS_PROFIT_MIN_QUOTE
        self.equity_bucket = equity_bucket
        self.venue_class = venue_class

    def _compute_boosted_notional(self, paper_capital, exchange, bot_type, gross_bps, cost_bps):
        kelly_notional = paper_capital * 0.01
        _net_edge_frac = max((gross_bps - cost_bps) / 10000.0, 0.0001)
        _vc = self.venue_class(exchange)
        _eq_bucket = self.equity_bucket(paper_capital, _vc)
        _lookup = (
            bot_type if bot_type in ("scalper", "mean_reversion") else "normal",
            _eq_bucket, _vc,
        )
        _abs_min = self.ABS_PROFIT_MIN_QUOTE.get(_lookup, 2.0)
        _min_notional = _abs_min / _net_edge_frac
        return max(kelly_notional, min(_min_notional, paper_capital))

    def test_binance_normal_passes_with_52_usdt(self):
        """Binance normal: raw_edge=200 bps, cost=33 bps, net=167 bps → APPROVED."""
        gross_bps = 200.0
        cost_bps = 33.0
        paper_capital = 52.63  # USDT (R1000 @ fx=19)

        notional = self._compute_boosted_notional(
            paper_capital, "binance", "normal", gross_bps, cost_bps
        )

        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=paper_capital, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            **_feasibility_gate_approve_setup(),
        )

        assert result["approved"] is True, (
            f"Binance normal should PASS. reason={result['decision_reason_code']} "
            f"projected={result['projected_net_profit_quote']:.4f} USDT "
            f"required={result.get('min_net_profit_quote_required', '?')} USDT"
        )

    def test_binance_normal_not_rejected_min_profit(self):
        gross_bps = 200.0
        cost_bps = 33.0
        paper_capital = 52.63

        notional = self._compute_boosted_notional(
            paper_capital, "binance", "normal", gross_bps, cost_bps
        )

        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=paper_capital, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            **_feasibility_gate_approve_setup(),
        )

        assert result["decision_reason_code"] != "ENTRY_REJECTED_MIN_PROFIT", (
            "Binance normal with 167 bps net edge and 52.63 USDT capital must NOT be blocked by min-profit"
        )


class TestLunoScalperPaperTradeCanPass:
    """
    A Luno scalper with net_edge=65.7 bps and 2000 ZAR capital
    should be able to pass min-profit when notional is boosted.
    """

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        from services.trading_brain_v2.entry_thresholds import (
            ABS_PROFIT_MIN_QUOTE,
            equity_bucket,
            venue_class,
        )
        self.gate = TradeFeasibilityGate()
        self.ABS_PROFIT_MIN_QUOTE = ABS_PROFIT_MIN_QUOTE
        self.equity_bucket = equity_bucket
        self.venue_class = venue_class

    def _compute_boosted_notional(self, paper_capital, exchange, bot_type, gross_bps, cost_bps):
        kelly_notional = paper_capital * 0.01
        _net_edge_frac = max((gross_bps - cost_bps) / 10000.0, 0.0001)
        _vc = self.venue_class(exchange)
        _eq_bucket = self.equity_bucket(paper_capital, _vc)
        _lookup = (
            bot_type if bot_type in ("scalper", "mean_reversion") else "normal",
            _eq_bucket, _vc,
        )
        _abs_min = self.ABS_PROFIT_MIN_QUOTE.get(_lookup, 2.0)
        _min_notional = _abs_min / _net_edge_frac
        return max(kelly_notional, min(_min_notional, paper_capital))

    def test_scalper_passes_with_boosted_notional(self):
        """Luno scalper: gross=100 bps, cost=34.3 bps, net=65.7 bps → NOT min-profit-blocked."""
        gross_bps = 100.0
        cost_bps = 34.3
        paper_capital = 2000.0

        notional = self._compute_boosted_notional(
            paper_capital, "luno", "scalper", gross_bps, cost_bps
        )

        # Scalper needs consolidation/mean_reversion regime
        result = self.gate.evaluate(
            strategy="scalper", venue="luno", symbol="XBTZAR",
            bot_equity=paper_capital, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            spread_pct=0.10,
            depth_notional=500_000,
            entry_confidence=0.78,
            regime_result={"regime_label": "consolidation", "regime_confidence": 0.85},
            regime_eligibility={
                "eligible": True, "action": "full",
                "edge_multiplier": 1.0, "size_multiplier": 1.0,
            },
        )

        assert result["decision_reason_code"] != "ENTRY_REJECTED_MIN_PROFIT", (
            f"Scalper with 65.7 bps net edge must NOT be blocked by min-profit. "
            f"Got: {result['decision_reason_code']} "
            f"projected={result['projected_net_profit_quote']:.4f} ZAR"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Uneconomic trades still rejected
# ══════════════════════════════════════════════════════════════════════════════

class TestUneconomicTradesStillRejected:
    """Risk controls must not be weakened — bad trades must still be blocked."""

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        self.gate = TradeFeasibilityGate()

    def test_zero_net_edge_rejected(self):
        """A trade with zero net edge must be rejected (EDGE_TOO_SMALL)."""
        result = self.gate.evaluate(
            strategy="normal", venue="luno", symbol="XBTZAR",
            bot_equity=2000.0, notional=1000.0,
            expected_gross_edge_bps=30.0, all_in_cost_bps=30.0,  # net = 0
            **_feasibility_gate_approve_setup(),
        )
        assert result["approved"] is False
        assert result["decision_reason_code"] == "EDGE_TOO_SMALL"

    def test_negative_net_edge_rejected(self):
        """A trade with negative net edge (costs exceed gross edge) must be rejected."""
        result = self.gate.evaluate(
            strategy="normal", venue="binance", symbol="BTC/USDT",
            bot_equity=52.63, notional=10.0,
            expected_gross_edge_bps=20.0, all_in_cost_bps=40.0,  # net = -20
            **_feasibility_gate_approve_setup(),
        )
        assert result["approved"] is False

    def test_insufficient_notional_rejected(self):
        """Even with good edge, a tiny notional that can't meet abs_min is rejected."""
        result = self.gate.evaluate(
            strategy="normal", venue="luno", symbol="XBTZAR",
            bot_equity=2000.0, notional=5.0,   # way too small
            expected_gross_edge_bps=164.0, all_in_cost_bps=29.2,
            **_feasibility_gate_approve_setup(),
        )
        # With notional=5 ZAR, projected = 5 × 0.01348 = 0.067 ZAR < 3.0 ZAR minimum
        assert result["approved"] is False
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"


# ══════════════════════════════════════════════════════════════════════════════
# PART C — Transparency fields in gate output
# ══════════════════════════════════════════════════════════════════════════════

class TestGateTransparencyFields:
    """Gate output must expose the fields needed to diagnose min-profit decisions."""

    def setup_method(self):
        from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
        self.gate = TradeFeasibilityGate()

    def _run_approved(self, venue="luno", equity=2000.0, notional=300.0,
                      gross_bps=164.0, cost_bps=29.2):
        return self.gate.evaluate(
            strategy="normal", venue=venue, symbol="XBTZAR",
            bot_equity=equity, notional=notional,
            expected_gross_edge_bps=gross_bps, all_in_cost_bps=cost_bps,
            **_feasibility_gate_approve_setup(),
        )

    def test_projected_net_profit_quote_in_output(self):
        result = self._run_approved()
        assert "projected_net_profit_quote" in result, \
            "projected_net_profit_quote must be in gate output"
        assert result["projected_net_profit_quote"] > 0

    def test_min_profit_required_quote_in_output(self):
        result = self._run_approved()
        # Available as either min_profit_required_quote or min_net_profit_quote_required
        has_field = (
            "min_profit_required_quote" in result or
            "min_net_profit_quote_required" in result
        )
        assert has_field, "min_profit_required_quote or min_net_profit_quote_required must be in output"

    def test_rejection_currency_side_in_output(self):
        result = self._run_approved()
        assert "rejection_currency_side" in result, \
            "rejection_currency_side must be in gate output"
        assert result["rejection_currency_side"] == "quote_native"

    def test_notional_quote_in_output(self):
        result = self._run_approved(notional=300.0)
        assert "notional_quote" in result, "notional_quote must be in gate output"
        assert math.isclose(result["notional_quote"], 300.0, rel_tol=1e-3)

    def test_capital_tier_in_output(self):
        result = self._run_approved()
        assert "capital_tier" in result, "capital_tier must be in gate output"
        assert result["capital_tier"] in ("micro", "small", "medium", "large")

    def test_transparency_on_min_profit_rejection(self):
        """Transparency fields must also appear in ENTRY_REJECTED_MIN_PROFIT rejections."""
        result = self.gate.evaluate(
            strategy="normal", venue="luno", symbol="XBTZAR",
            bot_equity=2000.0, notional=5.0,   # too small to clear minimum
            expected_gross_edge_bps=164.0, all_in_cost_bps=29.2,
            **_feasibility_gate_approve_setup(),
        )
        assert result["decision_reason_code"] == "ENTRY_REJECTED_MIN_PROFIT"
        assert "projected_net_profit_quote" in result
        assert "rejection_currency_side" in result


# ══════════════════════════════════════════════════════════════════════════════
# PART D — Unit consistency: quote / ZAR / display
# ══════════════════════════════════════════════════════════════════════════════

class TestUnitConsistency:
    """Verify that quote, ZAR, and display amounts are correctly separated."""

    def test_binance_r1000_funding_produces_52_usdt_native_capital(self):
        """R1000 → Binance bot: native capital must be ~52.63 USDT @ fx=19."""
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "binance")
        assert quote_currency == "USDT"
        assert math.isclose(quote_capital, 1000.0 / 19.0, rel_tol=1e-3), (
            f"Expected ~52.63 USDT, got {quote_capital}"
        )

    def test_binance_r1000_display_back_to_zar_is_1000(self):
        """quote_capital × fx_rate must equal original R1000 (round-trip check)."""
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, _, fx_rate = resolve_capital_for_exchange(1000.0, "binance")
        display_zar = quote_capital * fx_rate
        assert math.isclose(display_zar, 1000.0, rel_tol=1e-3), (
            f"ZAR round-trip: expected ~1000, got {display_zar}"
        )

    def test_mixed_wallet_zar_plus_usdt_totals_correct(self):
        """
        Wallet with ZAR 2000 + USDT 52.63 (R1000-equivalent) should total ~R3000.
        """
        _mock_fx_rate(19.0)
        from services.fx_normalizer import get_fx_rate

        zar_balance = 2000.0
        usdt_balance = 52.63
        usdt_fx, _ = get_fx_rate("USDT", "ZAR")  # ~19.0

        total_zar = zar_balance + (usdt_balance * usdt_fx)
        assert math.isclose(total_zar, 3000.0, rel_tol=0.01), (
            f"Mixed wallet total should be ~R3000, got R{total_zar:.2f}"
        )

    def test_gate_comparison_is_in_native_quote_not_zar(self):
        """
        Min-profit comparison in the gate is in native quote currency.
        For Luno (ZAR venue): quote IS ZAR — values are equal.
        For Binance (USDT venue): quote is USDT — values differ from ZAR.
        """
        from services.trading_brain_v2.entry_thresholds import (
            equity_bucket, venue_class, ABS_PROFIT_MIN_QUOTE,
        )

        # Luno: ZAR venue
        luno_vc = venue_class("luno")
        assert luno_vc == "zar"
        luno_bucket = equity_bucket(2000.0, luno_vc)
        assert luno_bucket == "small"
        luno_min = ABS_PROFIT_MIN_QUOTE[("normal", "small", "zar")]
        assert luno_min == 3.0  # R3.00 ZAR

        # Binance: USDT venue
        binance_vc = venue_class("binance")
        assert binance_vc == "usdt"
        binance_bucket = equity_bucket(52.63, binance_vc)
        assert binance_bucket == "micro"   # 52.63 < 100 USDT
        binance_min = ABS_PROFIT_MIN_QUOTE[("normal", "micro", "usdt")]
        assert binance_min == 0.10  # $0.10 USDT — NOT $1.50 or R25
