"""
Tests: Multi-Currency Aggregation Truth

Validates that ALL financial aggregates in the system are in ZAR and that
mixed-currency fleets (e.g. Luno ZAR + Binance USDT) are correctly normalised
before any summing occurs.

Test cases (from problem statement):
1. ZAR-only fleet — totals remain correct in ZAR
2. USDT-only fleet — native value stays USDT; display value converts to ZAR
3. Mixed fleet — 2 × R1000 ZAR bots + 1 × R1000-equivalent USDT bot → ~R3000 total
4. Profit aggregation — mixed-currency profits are normalised before summaries
5. API contract — relevant services expose both native and display truth

Run with:
  ENVIRONMENT=testing PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
  python3 -m pytest tests/test_multi_currency_aggregation.py -v
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ── Mock heavy infrastructure before importing backend services ───────────────
# The database module depends on motor/pymongo which are not installed in the
# test environment. We stub them out at sys.modules level so all service imports
# succeed without touching MongoDB.
for _mod in ("motor", "motor.motor_asyncio", "pymongo", "pymongo.errors"):
    sys.modules.setdefault(_mod, MagicMock())

_mock_db_module = MagicMock()
_mock_db_module.bots_collection = None
_mock_db_module.trades_collection = None
sys.modules.setdefault("database", _mock_db_module)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USDT_ZAR_RATE", "19.0")  # deterministic rate for tests


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_trade(bot_id, exchange, pnl_quote, quote_currency,
                pnl_zar=None, fee_quote=0.0, fee_zar=None):
    """Build a minimal closed trade record."""
    trade = {
        "bot_id": bot_id,
        "exchange": exchange,
        "quote_currency": quote_currency,
        "status": "closed",
        "net_pnl": pnl_quote,
        "profit_loss": pnl_quote,
        "gross_pnl": pnl_quote,
        "fee_amount": fee_quote,
        "timestamp": "2026-01-01T12:00:00+00:00",
    }
    if pnl_zar is not None:
        trade["realized_pnl_zar"] = pnl_zar
    if fee_zar is not None:
        trade["fee_display_zar"] = fee_zar
    return trade


def _make_bot(bot_id, exchange, initial_capital, quote_currency,
              canonical_base_zar=None):
    """Build a minimal bot record."""
    bot = {
        "id": bot_id,
        "exchange": exchange,
        "quote_currency": quote_currency,
        "initial_capital": initial_capital,
        "current_capital": initial_capital,
        "status": "active",
    }
    if canonical_base_zar is not None:
        bot["canonical_base_capital_zar"] = canonical_base_zar
    return bot


# ─── 1. enrich_trade_pnl_fields — the reconciliation layer ────────────────────

class TestEnrichTradePnlFields:
    """The reconciliation layer must correctly set realized_pnl_zar."""

    def test_luno_trade_zar_rate_is_identity(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {"exchange": "luno", "net_pnl": 100.0, "pair": "BTC/ZAR"}
        enrich_trade_pnl_fields(trade)
        assert trade["realized_pnl_zar"] == 100.0, "Luno ZAR trade must stay at 1:1"
        assert trade["quote_currency"] == "ZAR"
        assert trade["fx_rate_used"] == 1.0

    def test_binance_usdt_trade_converts_to_zar(self):
        from services.reconciliation import enrich_trade_pnl_fields
        # At 19 ZAR/USDT: 5.26 USDT → 99.94 ZAR
        trade = {"exchange": "binance", "net_pnl": 5.26, "pair": "BTC/USDT"}
        enrich_trade_pnl_fields(trade)
        assert trade["quote_currency"] == "USDT"
        assert trade["fx_rate_used"] == 19.0
        assert abs(trade["realized_pnl_zar"] - 99.94) < 0.01

    def test_negative_pnl_converted_correctly(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {"exchange": "binance", "net_pnl": -2.0, "pair": "BTC/USDT"}
        enrich_trade_pnl_fields(trade)
        assert abs(trade["realized_pnl_zar"] - (-38.0)) < 0.01

    def test_fee_converted_to_zar(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {"exchange": "binance", "net_pnl": 0.0,
                 "fee_amount": 1.0, "pair": "BTC/USDT"}
        enrich_trade_pnl_fields(trade)
        assert abs(trade["fee_display_zar"] - 19.0) < 0.01

    def test_zar_trade_fee_unchanged(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {"exchange": "luno", "net_pnl": 0.0,
                 "fee_amount": 5.0, "pair": "BTC/ZAR"}
        enrich_trade_pnl_fields(trade)
        assert trade["fee_display_zar"] == 5.0


# ─── 2. compute_equity_zar — reconciliation capital helper ────────────────────

class TestComputeEquityZar:
    """compute_equity_zar must convert all bots to ZAR before summing."""

    def test_zar_only_fleet(self):
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "quote_currency": "ZAR", "current_capital": 1000.0},
            {"exchange": "luno", "quote_currency": "ZAR", "current_capital": 1500.0},
        ]
        total, breakdown = compute_equity_zar(bots)
        assert total == 2500.0
        # fx_rate_used is the USDT→ZAR rate (which is fetched regardless of fleet);
        # what matters is that ZAR bots are correctly treated with rate=1.0 each.
        assert breakdown["by_exchange"]["luno"] == 2500.0

    def test_usdt_only_fleet_converts_to_zar(self):
        from services.reconciliation import compute_equity_zar
        # At 19 ZAR/USDT: 52.63 USDT → ~1000 ZAR
        bots = [
            {"exchange": "binance", "quote_currency": "USDT",
             "current_capital": 52.63},
        ]
        total, breakdown = compute_equity_zar(bots)
        assert abs(total - 52.63 * 19.0) < 1.0
        assert breakdown["fx_rate_used"] == 19.0

    def test_mixed_fleet_sums_in_zar(self):
        """2 × R1000 Luno + 1 × 52.63 USDT (= R1000) → ~R3000."""
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "current_capital": 1000.0},
            {"exchange": "luno", "quote_currency": "ZAR",
             "current_capital": 1000.0},
            {
                "exchange": "binance",
                "quote_currency": "USDT",
                "current_capital": 1000.0 / 19.0,   # ≈ 52.63 USDT
                "canonical_base_capital_zar": None,  # force FX conversion path
            },
        ]
        total, _ = compute_equity_zar(bots)
        assert abs(total - 3000.0) < 5.0, f"Expected ~R3000, got R{total}"

    def test_canonical_base_capital_zar_preferred(self):
        """canonical_base_capital_zar must be used when set."""
        from services.reconciliation import compute_equity_zar
        bots = [
            {
                "exchange": "binance",
                "quote_currency": "USDT",
                "current_capital": 52.63,
                "canonical_base_capital_zar": 1000.0,
            },
        ]
        total, _ = compute_equity_zar(bots)
        assert total == 1000.0, "canonical_base_capital_zar must take priority"

    def test_mixed_fleet_never_raw_sums(self):
        """R1000 + 52.63 USDT must NOT equal R1052.63."""
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "current_capital": 1000.0},
            {"exchange": "binance", "quote_currency": "USDT",
             "current_capital": 52.63},
        ]
        total, _ = compute_equity_zar(bots)
        assert total != 1052.63, "Mixed currencies must NOT be raw-summed"
        assert total > 1500.0, "USDT must be converted to ZAR before summing"


# ─── 3. overview_service._compute_capital_metrics ─────────────────────────────

class TestOverviewCapitalMetrics:
    """_compute_capital_metrics must return ZAR totals (no motor dependency)."""

    def _service(self):
        from services.overview_service import OverviewService
        return OverviewService()

    def test_zar_only_capital(self):
        svc = self._service()
        bots = [
            _make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0),
            _make_bot("b2", "luno", 500.0, "ZAR", canonical_base_zar=500.0),
        ]
        result = svc._compute_capital_metrics(bots)
        assert result["required_capital_total"] == 1500.0

    def test_usdt_capital_converted_to_zar(self):
        svc = self._service()
        bots = [
            _make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        result = svc._compute_capital_metrics(bots)
        assert result["required_capital_total"] == 1000.0

    def test_mixed_fleet_required_capital_is_zar(self):
        svc = self._service()
        bots = [
            _make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0),
            _make_bot("b2", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        result = svc._compute_capital_metrics(bots)
        assert result["required_capital_total"] == 2000.0, (
            f"Mixed fleet R1000+R1000 must total R2000, "
            f"got R{result['required_capital_total']}"
        )

    def test_capital_fallback_uses_fx_rate(self):
        """When canonical_base_capital_zar is absent, fall back to initial × fx_rate."""
        svc = self._service()
        bots = [
            _make_bot("b1", "binance", 52.63, "USDT"),  # no canonical_base_zar
        ]
        result = svc._compute_capital_metrics(bots)
        assert abs(result["required_capital_total"] - 52.63 * 19.0) < 2.0


# ─── 4. accounting.get_unified_metrics ────────────────────────────────────────

class TestAccountingUnifiedMetrics:
    """get_unified_metrics must return ZAR profit totals."""

    def _run_unified(self, trades):
        from services.accounting import AccountingService
        import services.accounting as acc_mod

        mock_db = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find = MagicMock(return_value=cursor)

        async def run():
            svc = AccountingService()
            with patch.object(acc_mod, "db", mock_db):
                return await svc.get_unified_metrics("user1", include_unrealised=False)

        return _run(run())

    def test_zar_only_trades_correct_sum(self):
        trades = [
            _make_trade("b1", "luno", 100.0, "ZAR", pnl_zar=100.0),
            _make_trade("b1", "luno", 50.0, "ZAR", pnl_zar=50.0),
        ]
        result = self._run_unified(trades)
        assert result["net_realised_pnl_zar"] == 150.0
        assert result["executed_trades_count"] == 2

    def test_usdt_trades_converted_to_zar(self):
        """5.0 USDT × 19 = R95.0."""
        trades = [
            _make_trade("b1", "binance", 5.0, "USDT", pnl_zar=5.0 * 19.0),
        ]
        result = self._run_unified(trades)
        assert abs(result["net_realised_pnl_zar"] - 95.0) < 0.01

    def test_mixed_trades_sum_in_zar(self):
        """R100 (Luno) + 5 USDT (Binance) → R100 + R95 = R195."""
        trades = [
            _make_trade("b1", "luno", 100.0, "ZAR", pnl_zar=100.0),
            _make_trade("b2", "binance", 5.0, "USDT", pnl_zar=95.0),
        ]
        result = self._run_unified(trades)
        assert abs(result["net_realised_pnl_zar"] - 195.0) < 0.01, (
            f"Mixed profit must be R195, got R{result['net_realised_pnl_zar']}"
        )

    def test_mixed_sum_never_raw_adds_currencies(self):
        """R100 + 5 USDT must NOT equal R105."""
        trades = [
            _make_trade("b1", "luno", 100.0, "ZAR", pnl_zar=100.0),
            _make_trade("b2", "binance", 5.0, "USDT", pnl_zar=95.0),
        ]
        result = self._run_unified(trades)
        assert result["net_realised_pnl_zar"] != 105.0, (
            "Must NOT raw-sum R100 + 5 USDT = R105"
        )

    def test_legacy_trade_without_realized_pnl_zar_uses_fx(self):
        """Older trades without realized_pnl_zar must be converted via fx_rate."""
        # No pnl_zar → fallback path: 10 USDT × 19 = R190
        trades = [
            _make_trade("b1", "binance", 10.0, "USDT"),  # no realized_pnl_zar
        ]
        result = self._run_unified(trades)
        assert abs(result["net_realised_pnl_zar"] - 190.0) < 0.01


# ─── 5. accounting.get_profit_breakdown ───────────────────────────────────────

class TestAccountingProfitBreakdown:
    """get_profit_breakdown must return ZAR values per exchange and per bot."""

    def _run_breakdown(self, trades):
        from services.accounting import AccountingService
        import services.accounting as acc_mod

        mock_db = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find = MagicMock(return_value=cursor)

        async def run():
            svc = AccountingService()
            with patch.object(acc_mod, "db", mock_db):
                return await svc.get_profit_breakdown("user1")

        return _run(run())

    def test_by_exchange_luno_in_zar(self):
        trades = [
            _make_trade("b1", "luno", 100.0, "ZAR", pnl_zar=100.0),
            _make_trade("b2", "binance", 5.0, "USDT", pnl_zar=95.0),
        ]
        result = self._run_breakdown(trades)
        by_exch = result["by_exchange"]
        assert by_exch["luno"]["net_pnl"] == 100.0
        assert abs(by_exch["binance"]["net_pnl"] - 95.0) < 0.01

    def test_by_exchange_usdt_not_raw(self):
        """binance entry must show ZAR value, not USDT raw."""
        trades = [
            _make_trade("b1", "binance", 5.0, "USDT", pnl_zar=95.0)
        ]
        result = self._run_breakdown(trades)
        assert result["by_exchange"]["binance"]["net_pnl"] != 5.0, (
            "USDT raw value must not appear as ZAR in breakdown"
        )


# ─── 6. canonical_metrics build_canonical_capital_summary ─────────────────────

class TestBuildCanonicalCapitalSummary:
    """build_canonical_capital_summary must expose quote_currency and display_currency."""

    def test_luno_zar_fields(self):
        from services.canonical_metrics import build_canonical_capital_summary
        result = build_canonical_capital_summary(
            capital_initial=1000.0,
            capital_allocated=1000.0,
            capital_available=800.0,
            open_position_value=200.0,
            profit_realized=50.0,
            quote_currency="ZAR",
            display_currency="ZAR",
        )
        assert result["quote_currency"] == "ZAR"
        assert result["display_currency"] == "ZAR"
        assert result["initial_capital"] == 1000.0

    def test_binance_usdt_quote_currency_exposed(self):
        from services.canonical_metrics import build_canonical_capital_summary
        result = build_canonical_capital_summary(
            capital_initial=1000.0,   # already converted to ZAR
            capital_allocated=1000.0,
            capital_available=800.0,
            open_position_value=200.0,
            profit_realized=50.0,
            quote_currency="USDT",
            display_currency="ZAR",
        )
        assert result["quote_currency"] == "USDT"
        assert result["display_currency"] == "ZAR"
        # All monetary values are ZAR display
        assert result["initial_capital"] == 1000.0


# ─── 7. canonical_metrics.get_canonical_metrics_snapshot ─────────────────────

class TestCanonicalMetricsSnapshot:
    """get_canonical_metrics_snapshot summary must be in ZAR."""

    def _run_snapshot(self, bots, trade_stats=None):
        from services.canonical_metrics import get_canonical_metrics_snapshot
        import services.canonical_metrics as cm_mod

        mock_db = MagicMock()
        mock_db.bots_collection = None   # skip DB bot fetch (bots passed directly)

        if trade_stats is not None:
            trade_cursor = MagicMock()
            trade_cursor.to_list = AsyncMock(return_value=trade_stats)
            mock_db.trades_collection = MagicMock()
            mock_db.trades_collection.aggregate = MagicMock(
                return_value=trade_cursor
            )
        else:
            mock_db.trades_collection = None

        async def run():
            with patch.object(cm_mod, "db", mock_db):
                return await get_canonical_metrics_snapshot("user1", bots=bots)

        return _run(run())

    def test_zar_only_bots_correct_capital_sum(self):
        bots = [
            _make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0),
            _make_bot("b2", "luno", 500.0, "ZAR", canonical_base_zar=500.0),
        ]
        result = self._run_snapshot(bots)
        assert result["summary"]["capital_initial"] == 1500.0

    def test_usdt_bot_capital_converted_to_zar(self):
        """52.63 USDT with canonical_base_zar=1000 must display as R1000."""
        bots = [
            _make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        result = self._run_snapshot(bots)
        assert result["summary"]["capital_initial"] == 1000.0
        # Per-bot must also expose quote_currency and display_currency
        bot_data = result["by_bot_id"]["b1"]
        assert bot_data["quote_currency"] == "USDT"
        assert bot_data["display_currency"] == "ZAR"

    def test_mixed_fleet_capital_sums_in_zar(self):
        """R1000 Luno + R1000-equivalent Binance → R2000 total."""
        bots = [
            _make_bot("b1", "luno", 1000.0, "ZAR", canonical_base_zar=1000.0),
            _make_bot("b2", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        result = self._run_snapshot(bots)
        assert result["summary"]["capital_initial"] == 2000.0, (
            f"Mixed fleet R1000+R1000 must total R2000, "
            f"got R{result['summary']['capital_initial']}"
        )

    def test_per_bot_native_capital_exposed(self):
        """Per-bot entry must expose capital_initial_quote (native value)."""
        bots = [
            _make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        result = self._run_snapshot(bots)
        bot_data = result["by_bot_id"]["b1"]
        assert bot_data["capital_initial_quote"] == 52.63, (
            "Native USDT capital must be exposed in capital_initial_quote"
        )
        # ZAR display must be R1000 (not R52.63)
        assert bot_data["capital_initial"] == 1000.0, (
            "capital_initial must be the ZAR display value (R1000)"
        )

    def test_profit_with_trade_stats_converted(self):
        """When trade stats are provided, profit_realized is converted to ZAR."""
        bots = [
            _make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0),
        ]
        # trade_count == trades_with_zar_field → use profit_realized_zar_sum
        trade_stats = [{
            "_id": "b1",
            "trade_count": 3,
            "winning_trades": 2,
            "losing_trades": 1,
            "profit_realized_raw": 15.0,   # 15 USDT raw
            "profit_realized_zar_sum": 285.0,  # 15 × 19 = 285 ZAR (pre-converted)
            "trades_with_zar_field": 3,    # all trades have realized_pnl_zar
        }]
        result = self._run_snapshot(bots, trade_stats=trade_stats)
        # Should use the pre-converted ZAR sum (285)
        assert result["by_bot_id"]["b1"]["profit_realized"] == 285.0


# ─── 8. FX normalizer stays canonical (regression guard) ─────────────────────

class TestFxNormalizerRegression:
    """Regression guard: no second FX path; fx_normalizer is still canonical."""

    def test_to_display_zar_zar_identity(self):
        from services.fx_normalizer import to_display_zar
        val, rate, source = to_display_zar(1000.0, "ZAR")
        assert val == 1000.0
        assert rate == 1.0

    def test_to_display_zar_usdt_conversion(self):
        from services.fx_normalizer import to_display_zar
        val, rate, source = to_display_zar(52.63, "USDT")
        assert rate == 19.0
        assert abs(val - 52.63 * 19.0) < 0.01

    def test_normalize_money_field_structure(self):
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(52.63, "USDT")
        assert result["raw_value"] == 52.63
        assert result["raw_currency"] == "USDT"
        assert result["display_currency"] == "ZAR"
        assert abs(result["display_value"] - 52.63 * 19.0) < 0.01
        assert result["fx_rate_used"] == 19.0

    def test_no_mixed_sum_without_conversion(self):
        """Fundamental contract: R1000 + 52.63 USDT ≠ R1052.63."""
        from services.fx_normalizer import to_display_zar

        zar_val, _, _ = to_display_zar(1000.0, "ZAR")
        usdt_val, _, _ = to_display_zar(52.63, "USDT")
        total = zar_val + usdt_val

        raw_incorrect = 1000.0 + 52.63  # R1052.63 — this is the BUG we fix
        assert total != raw_incorrect, "Mixed raw sum must never be used"
        assert abs(total - 2000.0) < 5.0, (
            f"Correct ZAR total should be ~R2000, got R{total}"
        )


# ─── 9. Display currency contract ─────────────────────────────────────────────

class TestDisplayCurrencyContract:
    """Services must expose display_currency='ZAR' on aggregate summaries."""

    def test_accounting_trade_list_summary_has_display_currency(self):
        from services.accounting import AccountingService
        import services.accounting as acc_mod

        trades = [_make_trade("b1", "luno", 100.0, "ZAR", pnl_zar=100.0)]

        mock_db = MagicMock()
        # get_trade_list_with_metrics calls .find().sort().limit().to_list()
        # which are chained sync calls; mock the whole chain
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find = MagicMock(return_value=chain)

        async def run():
            svc = AccountingService()
            with patch.object(acc_mod, "db", mock_db):
                result = await svc.get_trade_list_with_metrics("user1")
                return result["summary"].get("display_currency")

        dc = _run(run())
        assert dc == "ZAR", "Trade list summary must expose display_currency=ZAR"

    def test_canonical_metrics_bot_entry_has_display_currency(self):
        from services.canonical_metrics import get_canonical_metrics_snapshot
        import services.canonical_metrics as cm_mod

        bots = [_make_bot("b1", "binance", 52.63, "USDT", canonical_base_zar=1000.0)]

        mock_db = MagicMock()
        mock_db.bots_collection = None
        mock_db.trades_collection = None

        async def run():
            with patch.object(cm_mod, "db", mock_db):
                return await get_canonical_metrics_snapshot("user1", bots=bots)

        result = _run(run())
        bot_data = result["by_bot_id"]["b1"]
        assert bot_data.get("display_currency") == "ZAR"
        assert bot_data.get("quote_currency") == "USDT"
