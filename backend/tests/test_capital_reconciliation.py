"""
Capital Reconciliation Tests
==============================

Focused tests for the capital-truth fix (post PR #62):

1. Luno ZAR bot capital — no FX conversion, quote == ZAR
2. Binance USDT bot capital from ZAR input — ZAR / FX rate, not raw ZAR
3. Radar equity computation uses canonical ZAR base, not raw currency sum
4. Trade P&L quote vs display conversion — net_profit_zar is ZAR, not quote copy
5. Wallet available/allocated/balances consistency under mixed ZAR+USDT state
6. enrich_trade_pnl_fields never copies USDT P&L into realized_pnl_zar
"""

import pytest
from pathlib import Path

backend_path = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(backend_path))


# ---------------------------------------------------------------------------
# 1. resolve_capital_for_exchange — Luno ZAR bot
# ---------------------------------------------------------------------------

def test_luno_zar_capital_no_conversion():
    """Luno bots trade in ZAR natively; capital must not be converted."""
    from services.fx_normalizer import resolve_capital_for_exchange
    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "luno")
    assert quote_currency == "ZAR", "Luno quote currency must be ZAR"
    assert quote_capital == pytest.approx(1000.0), "Luno capital must equal ZAR input"
    assert fx_rate == pytest.approx(1.0), "Luno FX rate must be 1.0 (no conversion)"


# ---------------------------------------------------------------------------
# 2. resolve_capital_for_exchange — Binance USDT bot from ZAR input
# ---------------------------------------------------------------------------

def test_binance_usdt_capital_from_zar():
    """Binance bot with R1000 ZAR input at FX 19 must yield ≈52.63 USDT, not 500 USDT."""
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    # Pin rate to 19 for deterministic test
    update_fx_rate(19.0, "test")
    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "binance")
    assert quote_currency == "USDT", "Binance quote currency must be USDT"
    assert quote_capital == pytest.approx(1000.0 / 19.0, rel=1e-3), (
        f"Binance capital should be ≈52.63 USDT at FX 19, got {quote_capital}"
    )
    assert fx_rate == pytest.approx(19.0, rel=1e-3)


def test_binance_usdt_capital_not_inflated():
    """Binance capital at FX 19 must never be silently inflated to 500 USDT from R1000."""
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    update_fx_rate(19.0, "test")
    quote_capital, _, _ = resolve_capital_for_exchange(1000.0, "binance")
    # 500 USDT would mean the ZAR base was not divided by the FX rate (old bug)
    assert quote_capital < 100.0, (
        f"Capital must not be inflated: expected ~52.63 USDT, got {quote_capital}"
    )


# ---------------------------------------------------------------------------
# 3. compute_equity_zar — radar equity must not raw-sum USDT+ZAR
# ---------------------------------------------------------------------------

def test_radar_equity_uses_canonical_zar_base():
    """compute_equity_zar must convert USDT bot capital to ZAR, not raw-sum."""
    from services.reconciliation import compute_equity_zar
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    bots = [
        # Luno ZAR bot: 1000 ZAR
        {
            "exchange": "luno",
            "canonical_base_capital_zar": 1000.0,
            "current_capital": 1000.0,
            "quote_currency": "ZAR",
        },
        # Binance USDT bot: 52.63 USDT created from R1000 at FX 19
        {
            "exchange": "binance",
            "canonical_base_capital_zar": 1000.0,
            "current_capital": 52.631579,
            "quote_currency": "USDT",
        },
    ]
    total_zar, breakdown = compute_equity_zar(bots)
    # Should be 1000 + 1000 = R2000 (using canonical_base_capital_zar for both)
    assert total_zar == pytest.approx(2000.0, rel=1e-2), (
        f"Expected ~R2000 equity, got {total_zar}"
    )


def test_radar_equity_without_canonical_base_converts_usdt():
    """When canonical_base_capital_zar is absent, USDT is converted via FX rate."""
    from services.reconciliation import compute_equity_zar
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    bots = [
        # Binance bot without stored canonical_base (legacy bot scenario)
        {
            "exchange": "binance",
            "current_capital": 52.631579,
            "quote_currency": "USDT",
        },
    ]
    total_zar, _ = compute_equity_zar(bots)
    # 52.631579 USDT × 19 ≈ R1000
    assert total_zar == pytest.approx(52.631579 * 19.0, rel=1e-2), (
        f"Expected ~R1000 from USDT conversion, got {total_zar}"
    )


# ---------------------------------------------------------------------------
# 4. enrich_trade_pnl_fields — USDT P&L must not equal net_profit_zar raw
# ---------------------------------------------------------------------------

def test_usdt_trade_pnl_zar_is_converted():
    """For a USDT trade, realized_pnl_zar must be USDT × FX rate, not raw USDT copy."""
    from services.reconciliation import enrich_trade_pnl_fields
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    trade = {
        "exchange": "binance",
        "pair": "BTC/USDT",
        "net_profit": -0.23,  # USDT loss
    }
    enriched = enrich_trade_pnl_fields(trade)
    assert enriched["quote_currency"] == "USDT"
    assert enriched["realized_pnl_quote"] == pytest.approx(-0.23, rel=1e-4)
    # ZAR display: -0.23 × 19 ≈ -4.37, NOT -0.23
    assert abs(enriched["realized_pnl_zar"]) > 1.0, (
        f"realized_pnl_zar must be ZAR-converted; got {enriched['realized_pnl_zar']}"
    )
    assert enriched["realized_pnl_zar"] == pytest.approx(-0.23 * 19.0, rel=1e-2)


def test_zar_trade_pnl_unchanged():
    """For a ZAR trade (Luno), realized_pnl_zar must equal the raw P&L (no conversion)."""
    from services.reconciliation import enrich_trade_pnl_fields

    trade = {
        "exchange": "luno",
        "pair": "BTC/ZAR",
        "net_profit": -5.0,  # ZAR loss
    }
    enriched = enrich_trade_pnl_fields(trade)
    assert enriched["quote_currency"] == "ZAR"
    assert enriched["realized_pnl_quote"] == pytest.approx(-5.0)
    assert enriched["realized_pnl_zar"] == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# 5. reconcile_wallet_balances — mixed ZAR+USDT wallet
# ---------------------------------------------------------------------------

def test_wallet_total_display_zar_converts_usdt():
    """total_display_zar must use FX conversion, not raw-sum ZAR+USDT."""
    from services.reconciliation import reconcile_wallet_balances
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    available = {"ZAR": 1000.0, "USDT": 104.51}
    allocated = {"ZAR": 1000.0}
    result = reconcile_wallet_balances(available, allocated)

    assert result["canonical_currency"] == "ZAR"
    # ZAR portion: 1000 available + 1000 allocated = 2000 ZAR
    # USDT portion: 104.51 × 19 ≈ 1985.69 ZAR
    # Total ≈ 3985.69 ZAR — NOT 2104.51 (raw sum)
    expected = 2000.0 + 104.51 * 19.0
    assert result["total_display_zar"] == pytest.approx(expected, rel=1e-2), (
        f"total_display_zar expected ~{expected:.2f}, got {result['total_display_zar']}"
    )
    # total_display_zar must NOT equal the raw ZAR+USDT sum (1000+1000+104.51)
    raw_sum = 1000.0 + 1000.0 + 104.51
    assert abs(result["total_display_zar"] - raw_sum) > 100.0, (
        "total_display_zar should not be a raw currency sum"
    )


def test_wallet_available_allocated_balances_consistency():
    """available + allocated must equal balances for each currency."""
    from services.reconciliation import reconcile_wallet_balances

    available = {"ZAR": 500.0, "USDT": 50.0}
    allocated = {"ZAR": 200.0, "USDT": 30.0}
    result = reconcile_wallet_balances(available, allocated)

    assert result["balances"]["ZAR"] == pytest.approx(700.0)
    assert result["balances"]["USDT"] == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# 6. fx_normalizer.to_display_zar — sanity check for net_profit_zar patch
# ---------------------------------------------------------------------------

def test_to_display_zar_usdt():
    """to_display_zar must convert USDT to ZAR using canonical FX rate."""
    from services.fx_normalizer import to_display_zar, update_fx_rate
    update_fx_rate(19.0, "test")
    display, rate, source = to_display_zar(-0.23, "USDT")
    assert display == pytest.approx(-0.23 * 19.0, rel=1e-3)
    assert rate == pytest.approx(19.0)


def test_to_display_zar_zar_identity():
    """to_display_zar for a ZAR amount must return the same value (rate=1.0)."""
    from services.fx_normalizer import to_display_zar
    display, rate, _ = to_display_zar(100.0, "ZAR")
    assert display == pytest.approx(100.0)
    assert rate == pytest.approx(1.0)
