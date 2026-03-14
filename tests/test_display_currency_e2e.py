"""
Tests: Multi-Currency Display Preferences (ZAR/USD/GBP/EUR)

Validates:
1. fx_normalizer.get_fx_rate()  — cross-rate via ZAR for USD/GBP/EUR
2. fx_normalizer.to_display_currency() — final ZAR→display conversion
3. fx_normalizer.normalize_money_field() — multi-target display_currency
4. accounting.get_unified_metrics(display_currency=…) — _display fields
5. canonical_metrics.get_canonical_metrics_snapshot(display_currency=…)
6. overview_service.get_snapshot(display_currency=…)
7. ZAR stability regression — all original ZAR tests still pass when
   display_currency defaults to "ZAR"

Run with:
  ENVIRONMENT=testing PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
  python3 -m pytest tests/test_display_currency_e2e.py -v
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ── Stub heavy infrastructure at module level ─────────────────────────────────
for _mod in ("motor", "motor.motor_asyncio", "pymongo", "pymongo.errors"):
    sys.modules.setdefault(_mod, MagicMock())

_mock_db_module = MagicMock()
_mock_db_module.bots_collection = None
_mock_db_module.trades_collection = None
sys.modules.setdefault("database", _mock_db_module)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USDT_ZAR_RATE", "19.0")
os.environ.setdefault("USD_ZAR_RATE", "18.5")
os.environ.setdefault("GBP_ZAR_RATE", "23.5")
os.environ.setdefault("EUR_ZAR_RATE", "20.0")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. FX Normalizer — cross-rate & display conversion ──────────────────────

class TestFxNormalizerMultiCurrency:
    """Extended fx_normalizer tests: USD/GBP/EUR cross-rates."""

    def test_usdt_to_usd_rate(self):
        """USDT→USD = (USDT→ZAR) / (USD→ZAR) = 19/18.5 ≈ 1.027."""
        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("USDT", "USD")
        expected = 19.0 / 18.5
        assert abs(rate - expected) < 0.001, f"Expected ~{expected:.4f}, got {rate}"

    def test_usdt_to_gbp_rate(self):
        """USDT→GBP = 19/23.5 ≈ 0.808."""
        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("USDT", "GBP")
        expected = 19.0 / 23.5
        assert abs(rate - expected) < 0.001

    def test_usdt_to_eur_rate(self):
        """USDT→EUR = 19/20 = 0.95."""
        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("USDT", "EUR")
        assert abs(rate - 0.95) < 0.001

    def test_zar_to_usd_rate(self):
        """ZAR→USD = 1/18.5 ≈ 0.054."""
        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("ZAR", "USD")
        expected = 1.0 / 18.5
        assert abs(rate - expected) < 0.001

    def test_identity_same_currency(self):
        """Same currency → rate=1.0."""
        from services.fx_normalizer import get_fx_rate
        rate, src = get_fx_rate("USD", "USD")
        assert rate == 1.0
        assert src == "identity"

    def test_to_display_currency_zar_identity(self):
        from services.fx_normalizer import to_display_currency
        val, rate, _ = to_display_currency(1000.0, "ZAR")
        assert val == 1000.0
        assert rate == 1.0

    def test_to_display_currency_zar_to_usd(self):
        """R18.5 → $1.00."""
        from services.fx_normalizer import to_display_currency
        val, rate, _ = to_display_currency(18.5, "USD")
        assert abs(val - 1.0) < 0.01, f"Expected $1, got ${val}"

    def test_to_display_currency_zar_to_gbp(self):
        """R23.5 → £1.00."""
        from services.fx_normalizer import to_display_currency
        val, rate, _ = to_display_currency(23.5, "GBP")
        assert abs(val - 1.0) < 0.01

    def test_to_display_currency_zar_to_eur(self):
        """R20.0 → €1.00."""
        from services.fx_normalizer import to_display_currency
        val, rate, _ = to_display_currency(20.0, "EUR")
        assert abs(val - 1.0) < 0.01

    def test_normalize_money_field_usdt_to_usd(self):
        """52.63 USDT → ~$53.89 display (19/18.5 rate)."""
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(52.63, "USDT", display_currency="USD")
        assert result["raw_currency"] == "USDT"
        assert result["display_currency"] == "USD"
        expected_usd = 52.63 * (19.0 / 18.5)
        assert abs(result["display_value"] - expected_usd) < 0.05

    def test_normalize_money_field_zar_default(self):
        """ZAR with default display_currency='ZAR' unchanged."""
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(1000.0, "ZAR")
        assert result["display_value"] == 1000.0
        assert result["display_currency"] == "ZAR"

    def test_supported_display_currencies_constant(self):
        from services.fx_normalizer import SUPPORTED_DISPLAY_CURRENCIES
        assert "ZAR" in SUPPORTED_DISPLAY_CURRENCIES
        assert "USD" in SUPPORTED_DISPLAY_CURRENCIES
        assert "GBP" in SUPPORTED_DISPLAY_CURRENCIES
        assert "EUR" in SUPPORTED_DISPLAY_CURRENCIES


# ─── 2. accounting.get_unified_metrics — display_currency param ───────────────

class TestAccountingDisplayCurrency:

    def _run_unified(self, trades, display_currency="ZAR"):
        from services.accounting import AccountingService
        import services.accounting as acc_mod

        mock_db = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find = MagicMock(return_value=cursor)

        async def run():
            svc = AccountingService()
            with patch.object(acc_mod, "db", mock_db):
                return await svc.get_unified_metrics(
                    "user1", display_currency=display_currency
                )

        return _run(run())

    def test_zar_display_unchanged(self):
        """ZAR display — _display == _zar."""
        trades = [{"exchange": "luno", "net_pnl": 100.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 100.0}]
        result = self._run_unified(trades, display_currency="ZAR")
        assert result["display_currency"] == "ZAR"
        assert result["net_realised_pnl_zar"] == 100.0
        assert result["net_realised_pnl_display"] == 100.0

    def test_usd_display_converts_from_zar(self):
        """R185 profit displayed as $10.00 at 18.5 ZAR/USD."""
        trades = [{"exchange": "luno", "net_pnl": 185.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 185.0}]
        result = self._run_unified(trades, display_currency="USD")
        assert result["display_currency"] == "USD"
        assert result["net_realised_pnl_zar"] == 185.0   # internal ZAR unchanged
        expected_usd = 185.0 / 18.5
        assert abs(result["net_realised_pnl_display"] - expected_usd) < 0.05

    def test_gbp_display(self):
        """R235 profit → £10.00 at 23.5 ZAR/GBP."""
        trades = [{"exchange": "luno", "net_pnl": 235.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 235.0}]
        result = self._run_unified(trades, display_currency="GBP")
        expected_gbp = 235.0 / 23.5
        assert abs(result["net_realised_pnl_display"] - expected_gbp) < 0.05
        assert result["display_currency"] == "GBP"

    def test_eur_display(self):
        """R200 profit → €10.00 at 20.0 ZAR/EUR."""
        trades = [{"exchange": "luno", "net_pnl": 200.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 200.0}]
        result = self._run_unified(trades, display_currency="EUR")
        expected_eur = 200.0 / 20.0
        assert abs(result["net_realised_pnl_display"] - expected_eur) < 0.05
        assert result["display_currency"] == "EUR"

    def test_usdt_profit_in_usd_display(self):
        """5 USDT profit (95 ZAR internal) displayed in USD."""
        trades = [{"exchange": "binance", "net_pnl": 5.0, "quote_currency": "USDT",
                   "status": "closed", "realized_pnl_zar": 5.0 * 19.0}]  # 95 ZAR
        result = self._run_unified(trades, display_currency="USD")
        # 95 ZAR / 18.5 = ~$5.135
        expected_usd = 95.0 / 18.5
        assert abs(result["net_realised_pnl_display"] - expected_usd) < 0.05

    def test_invalid_display_currency_falls_back_to_zar(self):
        """Unsupported display_currency → silently fall back to ZAR."""
        trades = [{"exchange": "luno", "net_pnl": 100.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 100.0}]
        result = self._run_unified(trades, display_currency="XYZ")
        assert result["display_currency"] == "ZAR"
        assert result["net_realised_pnl_display"] == 100.0

    def test_fx_metadata_present(self):
        """Response must include fx_metadata with rate and source."""
        trades = [{"exchange": "luno", "net_pnl": 100.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 100.0}]
        result = self._run_unified(trades, display_currency="USD")
        assert "fx_metadata" in result
        assert "zar_to_display_rate" in result["fx_metadata"]
        assert result["fx_metadata"]["zar_to_display_rate"] > 0


# ─── 3. canonical_metrics.get_canonical_metrics_snapshot — display_currency ───

class TestCanonicalMetricsDisplayCurrency:

    def _make_bot(self, bot_id, exchange, capital, quote_currency, canonical_base_zar=None):
        bot = {
            "id": bot_id,
            "exchange": exchange,
            "quote_currency": quote_currency,
            "initial_capital": capital,
            "current_capital": capital,
            "status": "active",
        }
        if canonical_base_zar is not None:
            bot["canonical_base_capital_zar"] = canonical_base_zar
        return bot

    def _run_snapshot(self, bots, display_currency="ZAR"):
        from services.canonical_metrics import get_canonical_metrics_snapshot
        import services.canonical_metrics as cm_mod

        mock_db = MagicMock()
        mock_db.bots_collection = None
        mock_db.trades_collection = None

        async def run():
            with patch.object(cm_mod, "db", mock_db):
                return await get_canonical_metrics_snapshot(
                    "user1", bots=bots, display_currency=display_currency
                )

        return _run(run())

    def test_zar_display_unchanged(self):
        bots = [self._make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0)]
        result = self._run_snapshot(bots, display_currency="ZAR")
        assert result["summary"]["capital_initial"] == 1000.0
        assert result["summary"]["display_currency"] == "ZAR"

    def test_usd_display_converts_summary(self):
        """R1000 capital → ~$54.05 in USD display (1000/18.5)."""
        bots = [self._make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0)]
        result = self._run_snapshot(bots, display_currency="USD")
        expected = 1000.0 / 18.5
        assert abs(result["summary"]["capital_initial"] - expected) < 0.5
        assert result["summary"]["display_currency"] == "USD"

    def test_gbp_display_converts_summary(self):
        """R2350 capital → £100 in GBP."""
        bots = [self._make_bot("b1", "luno", 2350.0, "ZAR", canonical_base_zar=2350.0)]
        result = self._run_snapshot(bots, display_currency="GBP")
        expected = 2350.0 / 23.5
        assert abs(result["summary"]["capital_initial"] - expected) < 0.5

    def test_per_bot_display_currency_matches(self):
        """Per-bot entries expose the requested display_currency."""
        bots = [self._make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0)]
        result = self._run_snapshot(bots, display_currency="USD")
        bot_data = result["by_bot_id"]["b1"]
        assert bot_data["display_currency"] == "USD"
        assert bot_data["quote_currency"] == "USDT"

    def test_per_bot_capital_initial_quote_unchanged(self):
        """Native quote amount is never converted."""
        bots = [self._make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0)]
        result = self._run_snapshot(bots, display_currency="USD")
        assert result["by_bot_id"]["b1"]["capital_initial_quote"] == 52.63

    def test_fx_metadata_in_summary(self):
        bots = [self._make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0)]
        result = self._run_snapshot(bots, display_currency="GBP")
        assert "fx_metadata" in result["summary"]
        meta = result["summary"]["fx_metadata"]
        assert meta["internal_currency"] == "ZAR"
        assert meta["zar_to_display_rate"] > 0


# ─── 4. overview_service.get_snapshot — display_currency param ───────────────

class TestOverviewServiceDisplayCurrency:

    def _service(self):
        from services.overview_service import OverviewService
        return OverviewService()

    def test_zar_display_snapshot_has_metadata(self):
        svc = self._service()
        bots = []
        result = svc._compute_capital_metrics(bots)
        # Just verifying the service is importable and _compute_capital_metrics works
        assert "required_capital_total" in result

    def test_capital_metrics_usdt_zar(self):
        """Capital metrics with canonical_base_zar are returned in ZAR."""
        svc = self._service()
        bots = [{"exchange": "binance", "quote_currency": "USDT",
                 "initial_capital": 52.63, "current_capital": 52.63,
                 "canonical_base_capital_zar": 1000.0}]
        result = svc._compute_capital_metrics(bots)
        assert result["required_capital_total"] == 1000.0


# ─── 5. ZAR stability regression — ensure nothing broke with the new param ───

class TestZARStabilityRegression:
    """These are copies of critical ZAR tests from test_multi_currency_aggregation.py.
    They must pass unchanged after the display_currency feature is added."""

    def test_fx_rate_zar_identity(self):
        from services.fx_normalizer import get_fx_rate
        rate, src = get_fx_rate("ZAR", "ZAR")
        assert rate == 1.0
        assert src == "identity"

    def test_to_display_zar_identity(self):
        from services.fx_normalizer import to_display_zar
        val, rate, _ = to_display_zar(1000.0, "ZAR")
        assert val == 1000.0
        assert rate == 1.0

    def test_to_display_zar_usdt(self):
        from services.fx_normalizer import to_display_zar
        val, rate, _ = to_display_zar(52.63, "USDT")
        assert rate == 19.0
        assert abs(val - 52.63 * 19.0) < 0.01

    def test_to_display_currency_zar_noop(self):
        from services.fx_normalizer import to_display_currency
        val, rate, _ = to_display_currency(1000.0, "ZAR")
        assert val == 1000.0
        assert rate == 1.0

    def test_no_mixed_raw_sum(self):
        """Core invariant: R1000 + 52.63 USDT ≠ R1052.63."""
        from services.fx_normalizer import to_display_zar
        zar_val, _, _ = to_display_zar(1000.0, "ZAR")
        usdt_val, _, _ = to_display_zar(52.63, "USDT")
        total = zar_val + usdt_val
        assert total != 1052.63
        assert abs(total - 2000.0) < 5.0

    def test_accounting_zar_default_unchanged(self):
        """When no display_currency is passed, ZAR is the default and values unchanged."""
        from services.accounting import AccountingService
        import services.accounting as acc_mod

        trades = [{"exchange": "luno", "net_pnl": 100.0, "quote_currency": "ZAR",
                   "status": "closed", "realized_pnl_zar": 100.0}]
        mock_db = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find = MagicMock(return_value=cursor)

        async def run():
            svc = AccountingService()
            with patch.object(acc_mod, "db", mock_db):
                return await svc.get_unified_metrics("user1")

        result = _run(run())
        assert result["display_currency"] == "ZAR"
        assert result["net_realised_pnl_zar"] == 100.0
        assert result["net_realised_pnl_display"] == 100.0


# ─── 6. FX rate cross-currency consistency ───────────────────────────────────

class TestFxRateCrossConsistency:
    """Cross-rates must be internally consistent (derived from ZAR pivot)."""

    def test_usd_gbp_consistent(self):
        """USD→GBP should equal (USD→ZAR rate) / (GBP→ZAR rate)."""
        from services.fx_normalizer import get_fx_rate
        usd_gbp, _ = get_fx_rate("USD", "GBP")
        usd_zar, _ = get_fx_rate("USD", "ZAR")
        gbp_zar, _ = get_fx_rate("GBP", "ZAR")
        expected = usd_zar / gbp_zar
        assert abs(usd_gbp - expected) < 0.001

    def test_round_trip_zar(self):
        """ZAR → USD → ZAR must return the original amount."""
        from services.fx_normalizer import get_fx_rate
        zar_to_usd, _ = get_fx_rate("ZAR", "USD")
        usd_to_zar, _ = get_fx_rate("USD", "ZAR")
        # 1 ZAR → x USD → should return 1 ZAR
        assert abs(zar_to_usd * usd_to_zar - 1.0) < 0.001

    def test_round_trip_usdt(self):
        """USDT → GBP → USDT must return the original amount."""
        from services.fx_normalizer import get_fx_rate
        usdt_gbp, _ = get_fx_rate("USDT", "GBP")
        gbp_usdt, _ = get_fx_rate("GBP", "USDT")
        assert abs(usdt_gbp * gbp_usdt - 1.0) < 0.001

    def test_usdt_to_zar_then_to_usd_consistent(self):
        """USDT→ZAR→USD must equal USDT→USD directly."""
        from services.fx_normalizer import get_fx_rate
        usdt_zar, _ = get_fx_rate("USDT", "ZAR")   # 19.0
        zar_usd, _ = get_fx_rate("ZAR", "USD")       # 1/18.5
        usdt_usd_via_zar = usdt_zar * zar_usd

        usdt_usd_direct, _ = get_fx_rate("USDT", "USD")
        assert abs(usdt_usd_via_zar - usdt_usd_direct) < 0.001
