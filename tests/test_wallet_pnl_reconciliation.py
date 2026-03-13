"""
Tests: Wallet / P&L Reconciliation — Canonical Currency Truth

Validates:
1. reconcile_wallet_balances — Luno ZAR only, Binance USDT only, mixed ZAR+USDT
2. compute_equity_zar — single-currency and mixed-bot equity
3. enrich_trade_pnl_fields — Luno ZAR trade, Binance USDT trade, fee conversion
4. trade pnl conversion correctness (no USDT-as-ZAR bug)
5. exposure check under mixed-currency wallet state
6. build_trade_record includes canonical fields

All tests are pure-unit (no DB, no network) so they run in the CI environment
that lacks fastapi/pymongo/ccxt.
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── helpers ──────────────────────────────────────────────────────────────────

def _set_fx_rate(rate: float):
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(rate, source="test")


# ── 1. reconcile_wallet_balances ─────────────────────────────────────────────

class TestReconcileWalletBalances:

    def test_luno_zar_only_wallet(self):
        _set_fx_rate(19.0)
        from services.reconciliation import reconcile_wallet_balances
        result = reconcile_wallet_balances(
            available_by_currency={"ZAR": 1000.0},
            allocated_by_currency={"ZAR": 1000.0},
        )
        assert result["balances"]["ZAR"] == 2000.0
        # ZAR total must equal sum of ZAR (no cross-currency inflation)
        assert result["total_display_zar"] == 2000.0
        assert result["canonical_currency"] == "ZAR"
        assert "USDT" not in result["balances"]

    def test_binance_usdt_only_wallet(self):
        _set_fx_rate(19.0)
        from services.reconciliation import reconcile_wallet_balances
        result = reconcile_wallet_balances(
            available_by_currency={"USDT": 50.0},
            allocated_by_currency={"USDT": 104.85},
        )
        assert result["balances"]["USDT"] == pytest.approx(154.85, rel=1e-4)
        # 154.85 USDT × 19 ZAR/USDT = 2942.15 ZAR — NOT 154.85
        expected_zar = round(154.85 * 19.0, 2)
        assert result["total_display_zar"] == pytest.approx(expected_zar, rel=1e-3)
        assert "ZAR" not in result["balances"]

    def test_mixed_zar_and_usdt_wallet_no_raw_sum(self):
        """The old bug: available.ZAR=1000 + allocated.USDT=104.85 → total=2104.85 (WRONG).
        The correct total must convert USDT→ZAR first."""
        _set_fx_rate(19.0)
        from services.reconciliation import reconcile_wallet_balances
        result = reconcile_wallet_balances(
            available_by_currency={"ZAR": 1000.0},
            allocated_by_currency={"ZAR": 1000.0, "USDT": 104.85},
        )
        assert result["balances"]["ZAR"] == 2000.0
        assert result["balances"]["USDT"] == pytest.approx(104.85, rel=1e-4)
        # Correct total: 2000 ZAR + (104.85 × 19) USDT-as-ZAR = 2000 + 1992.15 = 3992.15
        expected_zar = 2000.0 + round(104.85 * 19.0, 2)
        assert result["total_display_zar"] == pytest.approx(expected_zar, rel=1e-3)
        # Must NOT equal the raw buggy sum of 2104.85
        assert result["total_display_zar"] != pytest.approx(2104.85, rel=1e-3)

    def test_fx_metadata_present(self):
        _set_fx_rate(18.5)
        from services.reconciliation import reconcile_wallet_balances
        result = reconcile_wallet_balances(
            available_by_currency={"USDT": 100.0},
            allocated_by_currency={},
        )
        meta = result["fx_metadata"]
        assert "usdt_zar_rate" in meta
        assert "usdt_zar_source" in meta
        assert "rates_by_currency" in meta
        assert meta["usdt_zar_rate"] == pytest.approx(18.5, rel=1e-4)

    def test_empty_wallet(self):
        from services.reconciliation import reconcile_wallet_balances
        result = reconcile_wallet_balances({}, {})
        assert result["total_display_zar"] == 0.0
        assert result["balances"] == {}


# ── 2. compute_equity_zar ────────────────────────────────────────────────────

class TestComputeEquityZar:

    def test_luno_zar_bot_uses_current_capital_directly(self):
        _set_fx_rate(19.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 2000.0, "quote_currency": "ZAR"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        assert equity == 2000.0
        assert breakdown["by_exchange"]["luno"] == 2000.0

    def test_binance_usdt_bot_converts_to_zar(self):
        _set_fx_rate(19.0)
        from services.reconciliation import compute_equity_zar
        # 100 USDT × 19 = 1900 ZAR
        bots = [
            {"exchange": "binance", "current_capital": 100.0, "quote_currency": "USDT"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        assert equity == pytest.approx(1900.0, rel=1e-3)
        assert breakdown["by_exchange"]["binance"] == pytest.approx(1900.0, rel=1e-3)

    def test_canonical_base_capital_zar_takes_priority(self):
        """canonical_base_capital_zar stored at creation is preferred over current fx conversion."""
        _set_fx_rate(19.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {
                "exchange": "binance",
                "current_capital": 100.0,
                "quote_currency": "USDT",
                "canonical_base_capital_zar": 2000.0,  # e.g. rate was 20 at creation
            },
        ]
        equity, breakdown = compute_equity_zar(bots)
        # Must use canonical_base_capital_zar, not 100 × 19 = 1900
        assert equity == pytest.approx(2000.0, rel=1e-3)

    def test_mixed_luno_and_binance_bots(self):
        _set_fx_rate(20.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 3000.0, "quote_currency": "ZAR"},
            {"exchange": "binance", "current_capital": 50.0, "quote_currency": "USDT"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        # 3000 ZAR + (50 × 20) ZAR = 3000 + 1000 = 4000
        assert equity == pytest.approx(4000.0, rel=1e-3)
        assert breakdown["by_exchange"]["luno"] == pytest.approx(3000.0, rel=1e-3)
        assert breakdown["by_exchange"]["binance"] == pytest.approx(1000.0, rel=1e-3)

    def test_no_r19000_inflation(self):
        """A 1000-ZAR Binance bot must NOT produce R19000 equity."""
        _set_fx_rate(19.0)
        from services.reconciliation import compute_equity_zar
        # Bot stored with canonical_base_capital_zar=1000, initial_capital=52.63 USDT
        bots = [
            {
                "exchange": "binance",
                "current_capital": 52.63,
                "quote_currency": "USDT",
                "canonical_base_capital_zar": 1000.0,
            },
        ]
        equity, _ = compute_equity_zar(bots)
        assert equity == pytest.approx(1000.0, rel=1e-3)
        assert equity < 1100.0, f"Equity inflated: {equity}"

    def test_empty_bots_list(self):
        from services.reconciliation import compute_equity_zar
        equity, breakdown = compute_equity_zar([])
        assert equity == 0.0


# ── 3. enrich_trade_pnl_fields ───────────────────────────────────────────────

class TestEnrichTradePnlFields:

    def test_luno_zar_trade_no_conversion(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "net_pnl": 50.0,
            "fee_amount": 2.0,
            "fee_currency": "ZAR",
        }
        result = enrich_trade_pnl_fields(trade)
        assert result["quote_currency"] == "ZAR"
        assert result["realized_pnl_quote"] == pytest.approx(50.0)
        # ZAR→ZAR: display == quote
        assert result["realized_pnl_display"] == pytest.approx(50.0)
        assert result["realized_pnl_zar"] == pytest.approx(50.0)
        assert result["fee_display_zar"] == pytest.approx(2.0)
        assert result["fx_rate_used"] == pytest.approx(1.0)

    def test_binance_usdt_trade_converts_to_zar(self):
        _set_fx_rate(19.0)
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {
            "exchange": "binance",
            "pair": "BTC/USDT",
            "net_pnl": -0.1,          # -0.1 USDT (NOT -0.1 ZAR)
            "fee_amount": 0.05,
            "fee_currency": "USDT",
        }
        result = enrich_trade_pnl_fields(trade)
        assert result["quote_currency"] == "USDT"
        assert result["realized_pnl_quote"] == pytest.approx(-0.1, rel=1e-4)
        # Must convert: -0.1 × 19 = -1.9 ZAR
        assert result["realized_pnl_display"] == pytest.approx(-1.9, rel=1e-3)
        assert result["realized_pnl_zar"] == pytest.approx(-1.9, rel=1e-3)
        # Must NOT equal -0.1 (the live bug: net_profit_zar = net_profit without conversion)
        assert result["realized_pnl_zar"] != pytest.approx(-0.1, abs=1e-3)

    def test_fee_converted_to_zar(self):
        _set_fx_rate(20.0)
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {
            "exchange": "kucoin",
            "pair": "ETH/USDT",
            "net_pnl": 5.0,
            "fee_amount": 0.1,
            "fee_currency": "USDT",
        }
        result = enrich_trade_pnl_fields(trade)
        # 0.1 USDT × 20 = 2.0 ZAR
        assert result["fee_display_zar"] == pytest.approx(2.0, rel=1e-3)

    def test_fx_source_present(self):
        from services.reconciliation import enrich_trade_pnl_fields
        trade = {"exchange": "luno", "pair": "BTC/ZAR", "net_pnl": 10.0}
        result = enrich_trade_pnl_fields(trade)
        assert isinstance(result["fx_source"], str)
        assert result["fx_source"] != ""


# ── 4. build_trade_record canonical fields ───────────────────────────────────

class TestBuildTradeRecordCanonicalFields:

    def test_luno_trade_includes_canonical_fields(self):
        _set_fx_rate(19.0)
        from utils.trade_utils import build_trade_record
        trade = {
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "net_pnl": 100.0,
            "fee_amount": 5.0,
            "fee_currency": "ZAR",
        }
        result = build_trade_record(trade)
        assert "quote_currency" in result
        assert "realized_pnl_quote" in result
        assert "realized_pnl_display" in result
        assert "realized_pnl_zar" in result
        assert result["quote_currency"] == "ZAR"
        assert result["realized_pnl_zar"] == pytest.approx(100.0)

    def test_binance_trade_includes_canonical_fields(self):
        _set_fx_rate(19.0)
        from utils.trade_utils import build_trade_record
        trade = {
            "exchange": "binance",
            "pair": "BTC/USDT",
            "net_pnl": -0.1,
        }
        result = build_trade_record(trade)
        assert result["quote_currency"] == "USDT"
        # realized_pnl_zar must be the ZAR-converted value, not raw USDT
        assert result["realized_pnl_zar"] == pytest.approx(-0.1 * 19.0, rel=1e-3)

    def test_net_pnl_quote_contains_raw_quote_value(self):
        """net_pnl_quote must be the quote-currency raw value, not net_profit_zar."""
        _set_fx_rate(19.0)
        from utils.trade_utils import build_trade_record
        # A Binance trade where the DB has a stale net_profit_zar field set to -0.1
        # (the pre-fix bug: USDT value stored as ZAR without conversion).
        trade = {
            "exchange": "binance",
            "pair": "BTC/USDT",
            "net_pnl": -0.1,
            "net_profit_zar": -0.1,  # stale/broken field from old code
        }
        result = build_trade_record(trade)
        # net_pnl_quote should be -0.1 (USDT raw), NOT the stale net_profit_zar
        assert result["net_pnl_quote"] == pytest.approx(-0.1, rel=1e-4)
        # realized_pnl_zar should be -1.9 (properly converted)
        assert result["realized_pnl_zar"] == pytest.approx(-1.9, rel=1e-3)


# ── 5. Exposure check under mixed-currency wallet state ──────────────────────

class TestExposureCheckMixedCurrency:

    def test_luno_only_exposure_single_exchange(self):
        """Single exchange: no 60% rule applies."""
        _set_fx_rate(19.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 5000.0, "quote_currency": "ZAR"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        # Single exchange → len(exchanges_used)==1 → no exposure check triggered
        # Just verify equity is correct
        assert equity == pytest.approx(5000.0)

    def test_mixed_exchange_equity_is_canon(self):
        """With Luno + Binance bots, equity must be canonical ZAR (not raw sum)."""
        _set_fx_rate(20.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 2000.0, "quote_currency": "ZAR"},
            {"exchange": "binance", "current_capital": 100.0, "quote_currency": "USDT"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        # 2000 + (100×20) = 4000
        assert equity == pytest.approx(4000.0, rel=1e-3)
        # Exchange-level exposure for binance: 2000 / 4000 = 50% (under 60% limit)
        binance_equity = breakdown["by_exchange"]["binance"]
        exposure_pct = binance_equity / equity
        assert exposure_pct < 0.60, "Binance should be under 60% limit"

    def test_usdt_bot_no_false_overexposure(self):
        """Before fix: a Binance bot with 100 USDT would be seen as R100 vs R2000 Luno = 5%
        but after raw-sum the values are just 2100 total meaning 100/2100=4.7%.
        With canonical equity: 100×20=2000 ZAR, total=4000, exposure=50%.
        This must NOT trigger the 60% limit."""
        _set_fx_rate(20.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 2000.0, "quote_currency": "ZAR"},
            {"exchange": "binance", "current_capital": 100.0, "quote_currency": "USDT"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        binance_equity = breakdown["by_exchange"]["binance"]
        # 2000/4000 = exactly 50% → under 60% limit, no block
        assert binance_equity / equity <= 0.60

    def test_high_usdt_exposure_would_trigger_limit(self):
        """If Binance has 80% of canonical equity, it exceeds 60% limit."""
        _set_fx_rate(20.0)
        from services.reconciliation import compute_equity_zar
        bots = [
            {"exchange": "luno", "current_capital": 500.0, "quote_currency": "ZAR"},
            {"exchange": "binance", "current_capital": 200.0, "quote_currency": "USDT"},
        ]
        equity, breakdown = compute_equity_zar(bots)
        # 500 + (200×20=4000) = 4500, binance = 4000/4500 ≈ 88.9%
        binance_equity = breakdown["by_exchange"]["binance"]
        exposure_pct = binance_equity / equity
        assert exposure_pct > 0.60, "Binance should exceed 60% limit"
