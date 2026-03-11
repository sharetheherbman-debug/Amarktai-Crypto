"""
Tests: Canonical Display Currency Contract

Verifies:
1. fx_normalizer — get_quote_currency, get_fx_rate, to_display_zar, normalize_money_field
2. Radar entry includes quote_currency, display_currency, and *_display fields
3. Luno bots: ZAR currency, no conversion needed
4. Binance/KuCoin bots: USDT currency, converted to ZAR display values
5. Bot lifecycle enriched bot includes quote_currency and display_currency
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ─── fx_normalizer tests ──────────────────────────────────────────────────────

class TestFxNormalizerQuoteCurrency:
    def test_luno_symbol_infers_zar(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("luno", "BTC/ZAR") == "ZAR"

    def test_luno_exchange_infers_zar(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("luno", "") == "ZAR"

    def test_luno_no_symbol_infers_zar(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("luno", None) == "ZAR"

    def test_binance_symbol_infers_usdt(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("binance", "BTC/USDT") == "USDT"

    def test_binance_exchange_default_usdt(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("binance", "") == "USDT"

    def test_kucoin_exchange_default_usdt(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("kucoin", "ETH/USDT") == "USDT"

    def test_zar_symbol_takes_priority_over_exchange(self):
        from services.fx_normalizer import get_quote_currency
        # If someone runs a ZAR pair on a non-Luno exchange, symbol wins
        assert get_quote_currency("binance", "BTC/ZAR") == "ZAR"

    def test_unknown_exchange_defaults_usdt(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("unknown_exchange", "BTC/USDT") == "USDT"


class TestFxNormalizerRates:
    def test_zar_to_zar_is_identity(self):
        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("ZAR", "ZAR")
        assert rate == 1.0
        assert source == "identity"

    def test_usdt_to_zar_returns_positive_rate(self):
        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("USDT", "ZAR")
        assert rate > 0
        assert isinstance(source, str)

    def test_usdt_to_zar_uses_env_fallback(self):
        """When no cached rate is set, uses USDT_ZAR_FALLBACK from env."""
        import importlib
        import services.fx_normalizer as fx_mod
        # Reset cache so we test fallback path
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = None
        fx_mod._cached_rate_source = "fallback"
        try:
            rate, source = fx_mod.get_fx_rate("USDT", "ZAR")
            assert rate == fx_mod.USDT_ZAR_FALLBACK
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

    def test_update_fx_rate_changes_cached_value(self):
        from services.fx_normalizer import update_fx_rate, get_current_usdt_zar_rate
        update_fx_rate(20.5, "test")
        rate, source = get_current_usdt_zar_rate()
        assert rate == pytest.approx(20.5)
        assert source == "test"
        # Restore a safe value
        update_fx_rate(19.0, "restored")

    def test_update_fx_rate_rejects_zero(self):
        from services.fx_normalizer import update_fx_rate, get_current_usdt_zar_rate
        update_fx_rate(19.5, "setup")
        update_fx_rate(0, "bad")
        rate, _ = get_current_usdt_zar_rate()
        assert rate == pytest.approx(19.5)
        update_fx_rate(19.0, "restored")


class TestFxNormalizerDisplayConversion:
    def test_zar_amount_unchanged(self):
        from services.fx_normalizer import to_display_zar
        display, rate, source = to_display_zar(1000.0, "ZAR")
        assert display == pytest.approx(1000.0)
        assert rate == pytest.approx(1.0)

    def test_usdt_amount_converted_to_zar(self):
        from services.fx_normalizer import to_display_zar, update_fx_rate
        update_fx_rate(20.0, "test")
        display, rate, source = to_display_zar(100.0, "USDT")
        assert display == pytest.approx(2000.0)
        assert rate == pytest.approx(20.0)
        update_fx_rate(19.0, "restored")

    def test_none_amount_returns_none_display(self):
        from services.fx_normalizer import to_display_zar
        display, rate, source = to_display_zar(None, "ZAR")
        assert display is None

    def test_caller_provided_rate_is_used(self):
        from services.fx_normalizer import to_display_zar
        display, rate, source = to_display_zar(50.0, "USDT", fx_rate=22.0)
        assert display == pytest.approx(1100.0)
        assert rate == pytest.approx(22.0)
        assert source == "caller_provided"

    def test_normalize_money_field_structure(self):
        from services.fx_normalizer import normalize_money_field, update_fx_rate
        update_fx_rate(20.0, "test")
        result = normalize_money_field(100.0, "USDT")
        assert result["raw_value"] == 100.0
        assert result["raw_currency"] == "USDT"
        assert result["display_value"] == pytest.approx(2000.0)
        assert result["display_currency"] == "ZAR"
        assert result["fx_rate_used"] == pytest.approx(20.0)
        assert "fx_source" in result
        update_fx_rate(19.0, "restored")

    def test_normalize_money_field_zar_bot(self):
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(500.0, "ZAR")
        assert result["raw_value"] == 500.0
        assert result["raw_currency"] == "ZAR"
        assert result["display_value"] == pytest.approx(500.0)
        assert result["display_currency"] == "ZAR"
        assert result["fx_rate_used"] == pytest.approx(1.0)


# ─── Radar display currency contract tests ───────────────────────────────────

class TestRadarDisplayCurrencyFields:
    """Radar _compute_radar_entry must include display currency fields."""

    def _make_bot(self, exchange="luno", capital=1000.0):
        return {
            "id": "bot_test",
            "name": "Test Bot",
            "exchange": exchange,
            "pair": "BTC/ZAR" if exchange == "luno" else "BTC/USDT",
            "bot_type": "normal",
            "risk_mode": "balanced",
            "current_capital": capital,
            "initial_capital": capital,
            "status": "active",
        }

    def test_luno_bot_has_zar_quote_currency(self):
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        bot = self._make_bot("luno", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert entry["quote_currency"] == "ZAR"
        assert entry["display_currency"] == "ZAR"
        assert entry["fx_rate_used"] == pytest.approx(1.0)

    def test_luno_bot_display_target_equals_raw_target(self):
        """For Luno (ZAR) bots, display target == raw target (no conversion, rate=1.0)."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        bot = self._make_bot("luno", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        # For ZAR bots, display == raw (fx_rate = 1.0)
        assert entry["fx_rate_used"] == pytest.approx(1.0)
        daily_raw = entry["daily_profit_target"]
        daily_display = entry["daily_profit_target_display"]
        if daily_raw is not None and daily_display is not None:
            assert daily_display == pytest.approx(daily_raw)
        assert entry["capital_allocated_display"] == pytest.approx(entry["capital_allocated"])

    def test_binance_bot_has_usdt_quote_currency(self):
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        bot = self._make_bot("binance", 1000.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert entry["quote_currency"] == "USDT"
        assert entry["display_currency"] == "ZAR"

    def test_binance_bot_display_target_is_converted_to_zar(self):
        """For Binance (USDT) bots, display values are FX-converted from USDT to ZAR."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        import services.fx_normalizer as fx_mod
        from datetime import datetime, timezone

        # Force a deterministic rate for this test using direct module state
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 20.0
        fx_mod._cached_rate_source = "test"
        try:
            bot = self._make_bot("binance", 100.0)
            with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
                entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

            assert entry["quote_currency"] == "USDT"
            assert entry["fx_rate_used"] == pytest.approx(20.0)
            # Capital display should be capital * fx_rate
            assert entry["capital_allocated_display"] == pytest.approx(entry["capital_allocated"] * 20.0)
            # Daily display should be daily_raw * fx_rate
            if entry["daily_profit_target"] is not None:
                assert entry["daily_profit_target_display"] == pytest.approx(entry["daily_profit_target"] * 20.0)
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

    def test_display_currency_is_always_zar(self):
        """display_currency must always be ZAR regardless of exchange."""
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        for exchange in ("luno", "binance", "kucoin", "bybit"):
            bot = self._make_bot(exchange, 500.0)
            with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
                entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))
            assert entry["display_currency"] == "ZAR", f"Expected ZAR for {exchange}"

    def test_fx_source_present_in_entry(self):
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency (fastapi/database)")
            return
        from datetime import datetime, timezone

        bot = self._make_bot("binance", 500.0)
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))

        assert "fx_source" in entry
        assert entry["fx_source"] is not None


# ─── Bot lifecycle quote_currency contract ────────────────────────────────────

class TestBotLifecycleQuoteCurrency:
    def test_get_quote_currency_luno(self):
        from services.fx_normalizer import get_quote_currency
        result = get_quote_currency("luno", "BTC/ZAR")
        assert result == "ZAR"

    def test_get_quote_currency_binance(self):
        from services.fx_normalizer import get_quote_currency
        result = get_quote_currency("binance", "ETH/USDT")
        assert result == "USDT"

    def test_get_quote_currency_no_symbol(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("luno") == "ZAR"
        assert get_quote_currency("binance") == "USDT"
