"""
Canonical Repair Truth Tests

Validates the fixes for:
1. trades_today counter convergence — now counts open+closed executed today
2. Exchange-aware target policy — Luno/ZAR bots use higher minimum percentages
3. Capital/equity display semantics — radar entry includes funding_currency +
   funding_amount to disambiguate user input from FX-converted display values
4. Absolute profit minimums — Luno small accounts now have achievable thresholds

Run with:
  ENVIRONMENT=testing PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
      python -m pytest tests/test_canonical_repair_truth.py -v
"""

import sys
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── helpers ────────────────────────────────────────────────────────────────

def _mock_cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _mock_collection(docs):
    col = MagicMock()
    col.find.return_value = _mock_cursor(docs)
    return col


# ══════════════════════════════════════════════════════════════════════════════
# 1. TRADES_TODAY COUNTER CONVERGENCE
# ══════════════════════════════════════════════════════════════════════════════


class TestTradesTodayCounterConvergence:
    """
    trades_today must count all executed trades for today regardless of
    whether they are still open (position held) or already closed.

    Without this fix:
      - Scheduler total_trades_executed = 1  (paper trade placed)
      - trades_today = 0                      (only "closed" counted)
    After the fix both agree.

    These tests use AST / source inspection because `motor` is not installed
    in the CI test environment (it is only available on the VPS).
    """

    CANONICAL_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'backend', 'services', 'canonical.py'
    )

    def _read_canonical(self):
        with open(self.CANONICAL_PATH, encoding="utf-8") as fh:
            return fh.read()

    def test_today_filter_includes_open_status(self):
        """The today query must include 'open' in its status filter."""
        src = self._read_canonical()
        # The canonical today count should use $in with "open"
        assert '"open"' in src or "'open'" in src, (
            "get_canonical_trade_counts must include 'open' in the trades_today status filter "
            "so paper trades opened today are counted even before closing"
        )

    def test_today_filter_uses_in_operator(self):
        """trades_today must use $in so multiple statuses can be matched."""
        src = self._read_canonical()
        assert '"$in"' in src or "'$in'" in src, (
            "get_canonical_trade_counts must use $in operator for trades_today status filter"
        )

    def test_today_filter_includes_closed_status(self):
        """The today query must still include 'closed' status."""
        src = self._read_canonical()
        assert '"closed"' in src or "'closed'" in src, (
            "get_canonical_trade_counts must still include 'closed' in today filter"
        )

    def test_today_and_total_are_separate_queries(self):
        """total (closed only) and today (open+closed) must use separate count queries."""
        src = self._read_canonical()
        # The source should have at least two count_documents calls
        occurrences = src.count("count_documents")
        assert occurrences >= 2, (
            "get_canonical_trade_counts must have separate count_documents calls "
            "for 'total' (closed only) and 'today' (open+closed)"
        )

    def test_canonical_py_parses_correctly(self):
        """services/canonical.py must parse without syntax errors."""
        import ast
        src = self._read_canonical()
        try:
            ast.parse(src)
        except SyntaxError as exc:
            raise AssertionError(f"Syntax error in canonical.py: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. EXCHANGE-AWARE TARGET POLICY
# ══════════════════════════════════════════════════════════════════════════════


class TestExchangeAwareTargetPolicy:
    """
    Luno/ZAR bots must use higher minimum percentages than USDT exchange bots
    because Luno's round-trip costs (~1.5%) require targets well above cost floor.

    Before fix: Luno scalper/safe 1000 ZAR → 8 ZAR/day (0.8%) — trivially small
    After fix:  Luno scalper/safe 1000 ZAR → ≥20 ZAR/day (2.0%) — above cost floor
    """

    def test_luno_normal_safe_target_above_cost_floor(self):
        from services.target_policy import derive_targets, _LUNO_MIN_DAILY_PCT
        bot = {"exchange": "luno", "bot_type": "normal", "risk_mode": "safe", "current_capital": 1000}
        t = derive_targets(bot)
        # derive_targets returns daily_target_pct as a percentage (e.g. 2.0 for 2.0%)
        # _LUNO_MIN_DAILY_PCT is a decimal (e.g. 0.020 for 2.0%)
        # Convert min floor to percentage for comparison
        min_pct = _LUNO_MIN_DAILY_PCT * 100  # 0.020 → 2.0
        assert t["daily_target_pct"] >= min_pct, (
            f"Luno normal/safe daily target pct {t['daily_target_pct']}% "
            f"must be >= {min_pct}% (the Luno minimum cost floor)"
        )

    def test_luno_scalper_safe_no_longer_returns_8_zar(self):
        """The old 8 ZAR problem (scalper/safe 0.8% × 1000 ZAR) must be fixed."""
        from services.target_policy import derive_targets
        bot = {"exchange": "luno", "bot_type": "scalper", "risk_mode": "safe", "current_capital": 1000}
        t = derive_targets(bot)
        daily = t["daily_profit_target"]
        assert daily is not None
        assert daily > 10.0, (
            f"Luno scalper/safe 1000 ZAR daily target was {daily} ZAR — "
            "must be > 10 ZAR to be above the exchange cost floor"
        )

    def test_luno_has_higher_target_than_binance_for_same_profile(self):
        """Luno bots must have higher daily_pct than USDT bots for the same profile."""
        from services.target_policy import derive_targets
        luno_bot = {"exchange": "luno", "bot_type": "normal", "risk_mode": "safe", "current_capital": 1000}
        binance_bot = {"exchange": "binance", "bot_type": "normal", "risk_mode": "safe", "current_capital": 1000}
        t_luno = derive_targets(luno_bot)
        t_binance = derive_targets(binance_bot)
        assert t_luno["daily_target_pct"] >= t_binance["daily_target_pct"], (
            "Luno targets must be >= USDT targets due to higher exchange costs"
        )

    def test_binance_normal_balanced_target_reasonable(self):
        """Binance normal/balanced 1000 USDT should yield a reasonable daily target."""
        from services.target_policy import derive_targets
        bot = {"exchange": "binance", "bot_type": "normal", "risk_mode": "balanced", "current_capital": 1000}
        t = derive_targets(bot)
        assert t["daily_profit_target"] is not None
        # Should be at least 1% (10 USDT) — non-trivial for 1000 USDT capital
        assert t["daily_profit_target"] >= 10.0, (
            f"Binance normal/balanced 1000 USDT daily target {t['daily_profit_target']} too small"
        )

    def test_configured_targets_override_exchange_defaults(self):
        """Bot-configured pcts must still override exchange-derived defaults."""
        from services.target_policy import derive_targets
        bot = {
            "exchange": "luno",
            "bot_type": "normal",
            "risk_mode": "safe",
            "current_capital": 1000,
            "daily_profit_target_pct": 0.05,  # 5% configured
            "trade_profit_target_pct": 0.02,
        }
        t = derive_targets(bot)
        assert t["target_source"] == "configured"
        assert t["daily_profit_target"] == pytest.approx(50.0)  # 5% × 1000

    def test_all_luno_profiles_above_minimum_floor(self):
        """Every Luno profile combination must return daily target >= 2.0% of capital."""
        from services.target_policy import derive_targets, _LUNO_MIN_DAILY_PCT
        min_floor_pct = _LUNO_MIN_DAILY_PCT * 100  # convert to %
        for bot_type in ("normal", "scalper"):
            for risk_mode in ("safe", "balanced", "aggressive"):
                bot = {
                    "exchange": "luno",
                    "bot_type": bot_type,
                    "risk_mode": risk_mode,
                    "current_capital": 1000,
                }
                t = derive_targets(bot)
                assert t["daily_target_pct"] >= min_floor_pct, (
                    f"Luno {bot_type}/{risk_mode} daily_target_pct={t['daily_target_pct']} "
                    f"must be >= {min_floor_pct}%"
                )

    def test_target_policy_includes_exchange_field(self):
        """derive_targets result must include 'exchange' field for audit."""
        from services.target_policy import derive_targets
        bot = {"exchange": "luno", "bot_type": "normal", "risk_mode": "balanced", "current_capital": 500}
        t = derive_targets(bot)
        assert "exchange" in t
        assert t["exchange"] == "luno"

    def test_zero_capital_returns_none_targets(self):
        """Bots with no capital must return None targets, not 0 ZAR."""
        from services.target_policy import derive_targets
        bot = {"exchange": "luno", "bot_type": "normal", "current_capital": 0}
        t = derive_targets(bot)
        assert t["daily_profit_target"] is None
        assert t["trade_profit_target"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. CAPITAL / EQUITY DISPLAY SEMANTICS
# ══════════════════════════════════════════════════════════════════════════════


class TestCapitalDisplaySemantics:
    """
    Radar entry must include explicit `funding_currency` and `funding_amount`
    fields so UI can distinguish "user entered 1000 USDT" from "19000 ZAR display".

    Before fix: Only capital_allocated (1000) and capital_allocated_display (19000)
                No way for UI to know that 1000 is USDT and 19000 is the ZAR display.
    After fix:  funding_currency = "USDT", funding_amount = 1000.0 also present.
    """

    def _make_bot(self, exchange, capital):
        return {
            "id": "bot-test",
            "name": "Test Bot",
            "exchange": exchange,
            "pair": "BTC/ZAR" if exchange == "luno" else "BTC/USDT",
            "bot_type": "normal",
            "risk_mode": "balanced",
            "current_capital": capital,
            "initial_capital": capital,
            "status": "active",
        }

    def test_radar_entry_has_funding_currency_field(self):
        """_compute_radar_entry must include 'funding_currency' in returned dict."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        from datetime import datetime, timezone

        bot = self._make_bot("luno", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert "funding_currency" in entry, "Radar entry must have 'funding_currency' field"

    def test_radar_entry_has_funding_amount_field(self):
        """_compute_radar_entry must include 'funding_amount' in returned dict."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        from datetime import datetime, timezone

        bot = self._make_bot("binance", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert "funding_amount" in entry, "Radar entry must have 'funding_amount' field"

    def test_binance_bot_funding_currency_is_usdt(self):
        """Binance bots have funding_currency = 'USDT'."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        from datetime import datetime, timezone

        bot = self._make_bot("binance", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert entry["funding_currency"] == "USDT"
        assert entry["funding_amount"] == pytest.approx(1000.0)

    def test_luno_bot_funding_currency_is_zar(self):
        """Luno bots have funding_currency = 'ZAR'."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        from datetime import datetime, timezone

        bot = self._make_bot("luno", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert entry["funding_currency"] == "ZAR"
        assert entry["funding_amount"] == pytest.approx(1000.0)

    def test_binance_display_capital_differs_from_funding_amount(self):
        """For Binance bots, capital_allocated_display (ZAR) != funding_amount (USDT)."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        import services.fx_normalizer as fx_mod
        from datetime import datetime, timezone

        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 20.0
        fx_mod._cached_rate_source = "test"
        try:
            bot = self._make_bot("binance", 1000.0)
            with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
                entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

            # funding_amount is raw USDT, capital_allocated_display is ZAR
            assert entry["funding_amount"] == pytest.approx(1000.0)
            assert entry["capital_allocated_display"] == pytest.approx(20000.0)
            assert entry["funding_currency"] == "USDT"
            assert entry["display_currency"] == "ZAR"
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

    def test_luno_display_capital_equals_funding_amount(self):
        """For Luno (ZAR) bots, capital_allocated_display == funding_amount (no FX conversion)."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        from datetime import datetime, timezone

        bot = self._make_bot("luno", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert entry["funding_amount"] == pytest.approx(entry["capital_allocated_display"])

    def test_radar_source_has_funding_currency_key(self):
        """The radar.py source must include the 'funding_currency' key."""
        import ast
        radar_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'radar.py'
        )
        with open(radar_path, encoding="utf-8") as fh:
            src = fh.read()
        assert '"funding_currency"' in src or "'funding_currency'" in src, (
            "routes/radar.py must expose 'funding_currency' in _compute_radar_entry"
        )

    def test_radar_source_has_funding_amount_key(self):
        """The radar.py source must include the 'funding_amount' key."""
        radar_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'radar.py'
        )
        with open(radar_path, encoding="utf-8") as fh:
            src = fh.read()
        assert '"funding_amount"' in src or "'funding_amount'" in src, (
            "routes/radar.py must expose 'funding_amount' in _compute_radar_entry"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. ABSOLUTE PROFIT MINIMUMS — LUNO SMALL ACCOUNTS
# ══════════════════════════════════════════════════════════════════════════════


class TestLunoSmallAccountProfitMinimums:
    """
    Before fix: ABS_PROFIT_MIN_QUOTE[("normal", "small", "zar")] = 5.0 ZAR
    This was unreachable with 1000 ZAR capital at 3% notional proxy = 30 ZAR,
    even at 200 bps net edge: 30 × 0.02 = 0.60 ZAR << 5 ZAR.
    After fix: 1.50 ZAR minimum — achievable with 300 ZAR notional at 50 bps.
    """

    def test_trade_worth_filter_small_zar_floor_is_achievable(self):
        """Small ZAR absolute minimum must be achievable at reasonable notional."""
        from services.trade_worth_filter import _ABS_MIN_QUOTE
        floor = _ABS_MIN_QUOTE.get(("normal", "small", "zar"), 999)
        # With 100 ZAR notional at 50 bps net edge: projected = 100 × 0.005 = 0.5 ZAR
        # With 300 ZAR notional at 50 bps net edge: projected = 300 × 0.005 = 1.5 ZAR
        # Floor must be achievable with 300 ZAR notional at 50 bps
        min_notional = 300.0
        min_edge_bps = 50.0
        achievable = min_notional * (min_edge_bps / 10_000.0)
        assert floor <= achievable, (
            f"trade_worth_filter small ZAR floor {floor} is not achievable "
            f"with {min_notional} ZAR notional at {min_edge_bps} bps edge (projected={achievable})"
        )

    def test_feasibility_gate_small_zar_floor_is_achievable(self):
        """TradeFeasibilityGate small ZAR minimum must also be achievable."""
        from services.trading_brain_v2.trade_feasibility_gate import ABS_PROFIT_MIN_QUOTE
        floor = ABS_PROFIT_MIN_QUOTE.get(("normal", "small", "zar"), 999)
        min_notional = 300.0
        min_edge_bps = 50.0
        achievable = min_notional * (min_edge_bps / 10_000.0)
        assert floor <= achievable, (
            f"TradeFeasibilityGate small ZAR floor {floor} is not achievable "
            f"with {min_notional} ZAR notional at {min_edge_bps} bps (projected={achievable})"
        )

    def test_both_filters_have_consistent_small_zar_floors(self):
        """trade_worth_filter and TradeFeasibilityGate must have consistent ZAR floors."""
        from services.trade_worth_filter import _ABS_MIN_QUOTE as wf_floors
        from services.trading_brain_v2.trade_feasibility_gate import ABS_PROFIT_MIN_QUOTE as fg_floors
        wf = wf_floors.get(("normal", "small", "zar"), 0)
        fg = fg_floors.get(("normal", "small", "zar"), 0)
        # Both values should be positive and within 3× of each other
        assert wf > 0, f"trade_worth_filter small ZAR floor must be positive, got {wf}"
        assert fg > 0, f"TradeFeasibilityGate small ZAR floor must be positive, got {fg}"
        # Check ratio: the larger must not exceed 3× the smaller
        larger = max(wf, fg)
        smaller = min(wf, fg)
        assert larger <= smaller * 3.0, (
            f"trade_worth_filter ({wf}) and TradeFeasibilityGate ({fg}) "
            "small ZAR floors are inconsistent (differ by more than 3×)"
        )

    def test_trade_worth_filter_luno_small_normal_passes(self):
        """A small-capital Luno normal bot at realistic edge must pass worth filter."""
        from services.trade_worth_filter import evaluate_minimum_worthwhile_trade
        result = evaluate_minimum_worthwhile_trade(
            bot_type="normal",
            exchange="luno",
            bot_equity=1000.0,
            notional=300.0,          # 30% of equity (higher than typical but for test)
            expected_gross_edge_bps=80.0,   # 80 bps gross edge
            all_in_cost_bps=20.0,           # 20 bps cost
            # No hold duration — skip the reward-rate check (hold time is unknown at entry)
        )
        # At 300 ZAR × 60 bps = 1.8 ZAR projected — must be >= 1.5 ZAR floor
        assert result["approved"], (
            f"Small Luno normal bot with 300 ZAR notional and 60 bps net edge "
            f"must pass worth filter; got: {result['reason_code']} — {result['reason_text']}"
        )

    def test_scalper_small_zar_floor_is_low(self):
        """Scalper small ZAR floor must be even lower (many small trades/day)."""
        from services.trade_worth_filter import _ABS_MIN_QUOTE
        scalper_floor = _ABS_MIN_QUOTE.get(("scalper", "small", "zar"), 999)
        normal_floor = _ABS_MIN_QUOTE.get(("normal", "small", "zar"), 999)
        assert scalper_floor <= normal_floor, (
            "Scalper absolute minimum must be <= normal minimum "
            "(scalpers use smaller per-trade targets, making many trades)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. SYNTAX INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════


class TestSyntaxIntegrity:
    """All canonical service files must parse without syntax errors."""

    def _check_syntax(self, relpath):
        import ast
        base = os.path.join(os.path.dirname(__file__), '..', 'backend')
        path = os.path.join(base, relpath)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            ast.parse(src)
        except SyntaxError as exc:
            raise AssertionError(f"Syntax error in {relpath}: {exc}")

    def test_canonical_py(self):
        self._check_syntax("services/canonical.py")

    def test_target_policy_py(self):
        self._check_syntax("services/target_policy.py")

    def test_trade_worth_filter_py(self):
        self._check_syntax("services/trade_worth_filter.py")

    def test_feasibility_gate_py(self):
        self._check_syntax("services/trading_brain_v2/trade_feasibility_gate.py")

    def test_radar_py(self):
        self._check_syntax("routes/radar.py")
