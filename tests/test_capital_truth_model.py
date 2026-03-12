"""
Capital Truth Model Tests — Phase 1

Validates the canonical capital semantics required by the problem statement:

  1. Every bot starts with a R1000 ZAR economic base.
  2. Luno bot: quote is ZAR, initial_capital = 1000.
  3. Binance/USDT bot: quote is USDT, initial_capital = 1000 / fx_rate.
  4. canonical_base_capital_zar is always stored at creation for new bots.
  5. total_equity_display never inflates because of currency conversion.
  6. target policy produces meaningful (non-tiny) daily targets for both exchanges.
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_fx_rate(rate: float):
    """Monkey-patch the FX normalizer's cached rate for testing."""
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(rate, source="test")


# ── 1. Bot validator canonical capital fields ─────────────────────────────────

class TestBotValidatorCapitalHelper:
    """resolve_capital_for_exchange must convert ZAR → correct quote currency."""

    def test_luno_returns_zar_unchanged(self):
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "luno")
        assert quote_currency == "ZAR"
        assert quote_capital == 1000.0
        assert fx_rate == 1.0

    def test_binance_converts_zar_to_usdt(self):
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "binance")
        assert quote_currency == "USDT"
        assert math.isclose(quote_capital, 1000.0 / 19.0, rel_tol=1e-4), (
            f"Expected ~52.63 USDT but got {quote_capital}"
        )
        assert math.isclose(fx_rate, 19.0, rel_tol=1e-4)

    def test_kucoin_converts_zar_to_usdt(self):
        _mock_fx_rate(20.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "kucoin")
        assert quote_currency == "USDT"
        assert math.isclose(quote_capital, 50.0, rel_tol=1e-4)

    def test_usdt_bot_display_back_to_zar_equals_base(self):
        """quote_capital × fx_rate must equal the original ZAR base (within rounding)."""
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        capital_zar = 1000.0
        quote_capital, _, fx_rate = resolve_capital_for_exchange(capital_zar, "binance")
        display_zar = quote_capital * fx_rate
        # Must round-trip back to the original R1000 (within floating-point tolerance)
        assert math.isclose(display_zar, capital_zar, rel_tol=1e-4), (
            f"Display ZAR {display_zar} does not match original base {capital_zar}"
        )

    def test_no_r19000_inflation_from_1000_zar_input(self):
        """A R1000 input to a Binance bot must NOT produce ~R19000 equity."""
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange
        quote_capital, _, fx_rate = resolve_capital_for_exchange(1000.0, "binance")
        # The display equity must equal R1000, not R19000
        display_equity = quote_capital * fx_rate
        assert display_equity < 1100.0, (
            f"Binance bot display equity R{display_equity:.2f} is inflated "
            f"(expected ~R1000 after proper ZAR→USDT conversion)"
        )
        assert display_equity > 900.0, (
            f"Binance bot display equity R{display_equity:.2f} is too small"
        )


# ── 2. FX normalizer ──────────────────────────────────────────────────────────

class TestFxNormalizerCapitalConversion:
    """FX normalizer must support canonical capital round-trips."""

    def test_zar_bot_fx_rate_is_1(self):
        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("ZAR", "ZAR")
        assert rate == 1.0

    def test_usdt_to_zar_uses_canonical_rate(self):
        _mock_fx_rate(18.5)
        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("USDT", "ZAR")
        assert math.isclose(rate, 18.5, rel_tol=1e-4)
        assert source != "unknown"

    def test_display_zar_for_luno_capital(self):
        from services.fx_normalizer import to_display_zar
        display, rate, _ = to_display_zar(1000.0, "ZAR")
        assert display == 1000.0
        assert rate == 1.0

    def test_display_zar_for_usdt_capital(self):
        _mock_fx_rate(19.0)
        from services.fx_normalizer import to_display_zar
        # 52.63 USDT → should show ~R1000
        display, rate, _ = to_display_zar(52.631579, "USDT")
        assert display is not None
        assert math.isclose(display, 1000.0, rel_tol=1e-2), (
            f"Expected ~R1000 display for 52.63 USDT but got R{display}"
        )


# ── 3. Target policy: meaningful targets for both exchanges ───────────────────

class TestTargetPolicyCapitalAware:
    """Target policy must produce meaningful (non-trivial) daily targets."""

    def test_luno_normal_balanced_target_not_r5(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "exchange": "luno",
            "current_capital": 1000,  # R1000 ZAR
        }
        result = derive_targets(bot)
        # Daily target must be > R5 (which is the known broken threshold)
        assert result["daily_profit_target"] is not None
        assert result["daily_profit_target"] > 5.0, (
            f"Luno normal/balanced daily target R{result['daily_profit_target']} is too small (R5 bug)"
        )
        # Must also be above Luno cost floor (~1.5% of R1000 = R15)
        assert result["daily_profit_target"] >= 15.0, (
            f"Luno normal/balanced daily target R{result['daily_profit_target']} is below Luno cost floor"
        )

    def test_luno_scalper_balanced_target_not_r5(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "scalper",
            "risk_mode": "balanced",
            "exchange": "luno",
            "current_capital": 1000,  # R1000 ZAR
        }
        result = derive_targets(bot)
        assert result["daily_profit_target"] is not None
        assert result["daily_profit_target"] > 5.0, (
            f"Luno scalper/balanced daily target R{result['daily_profit_target']} is still R5 (bug)"
        )

    def test_binance_normal_balanced_meaningful_target(self):
        _mock_fx_rate(19.0)
        from services.target_policy import derive_targets
        # After capital fix, Binance bot starts with ~52.63 USDT (R1000 / 19)
        quote_capital = round(1000.0 / 19.0, 6)
        bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "exchange": "binance",
            "current_capital": quote_capital,
        }
        result = derive_targets(bot)
        assert result["daily_profit_target"] is not None
        # 2% of ~52.63 USDT = ~1.05 USDT → meaningful (not zero/trivial)
        assert result["daily_profit_target"] > 0.5, (
            f"Binance normal/balanced daily target {result['daily_profit_target']} USDT is too small"
        )

    def test_luno_and_binance_economically_aligned(self):
        """Luno and Binance bots with same ZAR economic base should have similar ZAR-equivalent daily targets."""
        _mock_fx_rate(19.0)
        from services.target_policy import derive_targets
        from services.fx_normalizer import get_fx_rate

        luno_bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "exchange": "luno",
            "current_capital": 1000.0,  # R1000 ZAR
        }
        # Binance bot with the R1000 ZAR economic base converted to USDT
        binance_capital_usdt = round(1000.0 / 19.0, 6)
        binance_bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "exchange": "binance",
            "current_capital": binance_capital_usdt,
        }

        luno_result = derive_targets(luno_bot)
        binance_result = derive_targets(binance_bot)

        luno_target_zar = luno_result["daily_profit_target"]  # already ZAR
        fx_rate, _ = get_fx_rate("USDT", "ZAR")
        binance_target_zar = (binance_result["daily_profit_target"] or 0) * fx_rate

        # Both should be in the same ballpark (within 5×) — not wildly different
        assert luno_target_zar is not None
        assert binance_target_zar > 0
        ratio = max(luno_target_zar, binance_target_zar) / min(luno_target_zar, binance_target_zar)
        assert ratio < 5.0, (
            f"Luno (R{luno_target_zar:.2f}/day) and Binance (R{binance_target_zar:.2f}/day) "
            f"daily targets are misaligned (ratio {ratio:.2f}×)"
        )


# ── 4. V2 target policy alignment ─────────────────────────────────────────────

class TestTargetPolicyV2Alignment:
    """TargetPolicyV2 must no longer produce R5 targets for Luno scalpers."""

    def test_luno_scalper_v2_daily_target_not_r5(self):
        from services.trading_brain_v2.target_policy import TargetPolicyV2
        v2 = TargetPolicyV2()
        result = v2.compute(
            bot_type="scalper",
            venue="luno",
            quote_currency="ZAR",
            bot_equity=1000.0,  # R1000
            notional=100.0,
            all_in_cost_bps=150.0,  # Luno cost floor ~1.5%
            entry_price=0.0,
            side="buy",
        )
        daily_target = result.get("daily_profit_target_quote", 0)
        assert daily_target > 5.0, (
            f"V2 Luno scalper daily target R{daily_target:.2f} is still R5 (bug not fixed)"
        )

    def test_binance_normal_v2_daily_target_meaningful(self):
        _mock_fx_rate(19.0)
        from services.trading_brain_v2.target_policy import TargetPolicyV2
        v2 = TargetPolicyV2()
        binance_equity = round(1000.0 / 19.0, 6)
        result = v2.compute(
            bot_type="normal",
            venue="binance",
            quote_currency="USDT",
            bot_equity=binance_equity,
            notional=binance_equity * 0.2,
            all_in_cost_bps=30.0,
            entry_price=0.0,
            side="buy",
        )
        daily_target_usdt = result.get("daily_profit_target_quote", 0)
        daily_target_zar = daily_target_usdt * 19.0
        # Should produce a meaningful ZAR daily target comparable to R1000 Luno bot
        assert daily_target_zar > 5.0, (
            f"V2 Binance normal daily target R{daily_target_zar:.2f} is too small"
        )

    def test_v2_luno_zar_profile_exceeds_usdt_profile(self):
        """Luno daily % must be higher than USDT daily % because Luno cost floor is higher."""
        from services.trading_brain_v2.target_policy import DAILY_TARGET_PCT
        luno_scalper = DAILY_TARGET_PCT.get(("scalper", "zar"), 0)
        usdt_scalper = DAILY_TARGET_PCT.get(("scalper", "usdt"), 0)
        assert luno_scalper > usdt_scalper, (
            f"Luno scalper daily % ({luno_scalper}%) must exceed USDT ({usdt_scalper}%) "
            f"due to higher Luno cost floor"
        )
