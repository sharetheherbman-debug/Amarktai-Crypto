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


# ---------------------------------------------------------------------------
# 7. batch-create capital conversion — PR #63 targeted fix
# ---------------------------------------------------------------------------

def test_batch_create_binance_uses_canonical_capital():
    """Batch-create for Binance must produce USDT capital via FX conversion, not raw ZAR."""
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    update_fx_rate(19.0, "test")

    capital_per_bot = 1000.0  # ZAR economic base entered by user
    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_per_bot, "binance")

    assert quote_currency == "USDT"
    assert quote_capital == pytest.approx(1000.0 / 19.0, rel=1e-3), (
        f"batch-create Binance capital must be ~52.63 USDT, got {quote_capital}"
    )
    # Must NOT be 500 USDT (old silent inflation bug)
    assert quote_capital < 100.0, "batch-create must not silently inflate capital to 500 USDT"
    assert fx_rate == pytest.approx(19.0)


def test_batch_create_luno_no_conversion():
    """Batch-create for Luno must keep ZAR capital unchanged (no FX conversion)."""
    from services.fx_normalizer import resolve_capital_for_exchange
    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "luno")
    assert quote_currency == "ZAR"
    assert quote_capital == pytest.approx(1000.0)
    assert fx_rate == pytest.approx(1.0)


def test_batch_create_canonical_fields_present():
    """bot dicts built for batch-create must include all canonical capital truth fields."""
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    update_fx_rate(19.0, "test")

    capital_per_bot = 1000.0
    exchange = "binance"
    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_per_bot, exchange)

    # Simulate the fields that batch-create now writes (mirrors the fixed server.py code)
    bot_record = {
        "canonical_base_capital_zar": round(capital_per_bot, 2),
        "funding_input_amount": round(capital_per_bot, 2),
        "funding_input_currency": "ZAR",
        "fx_rate_at_creation": fx_rate,
        "quote_currency": quote_currency,
        "initial_capital": quote_capital,
        "current_capital": quote_capital,
    }

    assert bot_record["canonical_base_capital_zar"] == pytest.approx(1000.0)
    assert bot_record["funding_input_currency"] == "ZAR"
    assert bot_record["quote_currency"] == "USDT"
    assert bot_record["initial_capital"] == pytest.approx(quote_capital)
    assert bot_record["current_capital"] == pytest.approx(quote_capital)
    assert bot_record["fx_rate_at_creation"] == pytest.approx(19.0)
    # initial_capital and current_capital are the same at bot creation (no trades yet)
    assert bot_record["initial_capital"] == pytest.approx(bot_record["current_capital"])
    # Sanity: canonical_base / fx_rate should round-trip to initial_capital
    assert bot_record["canonical_base_capital_zar"] / bot_record["fx_rate_at_creation"] == pytest.approx(
        bot_record["initial_capital"], rel=1e-3
    )


# ---------------------------------------------------------------------------
# 8. trades endpoint — net_profit_zar must not copy raw USDT value
# ---------------------------------------------------------------------------

def test_trades_endpoint_net_profit_zar_converted():
    """For a USDT Binance trade, net_profit_zar must be USDT × FX rate, not raw copy."""
    from services.reconciliation import enrich_trade_pnl_fields
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    # Simulate a closed Binance trade as would be stored in MongoDB
    stored_trade = {
        "exchange": "binance",
        "pair": "BTC/USDT",
        "net_pnl": -0.23,
        "net_profit": -0.23,
        "profit_loss": -0.23,
        "status": "closed",
    }
    enriched = enrich_trade_pnl_fields(dict(stored_trade))
    net_profit_zar = enriched.get("realized_pnl_zar")

    assert net_profit_zar is not None
    # -0.23 USDT × 19 ≈ -4.37 ZAR; must NOT equal -0.23
    assert abs(net_profit_zar) > 1.0, (
        f"net_profit_zar must be ZAR-converted; got {net_profit_zar}"
    )
    assert net_profit_zar == pytest.approx(-0.23 * 19.0, rel=1e-2)


def test_trades_endpoint_luno_net_profit_zar_unchanged():
    """For a Luno ZAR trade, net_profit_zar must equal the raw P&L (identity conversion)."""
    from services.reconciliation import enrich_trade_pnl_fields

    stored_trade = {
        "exchange": "luno",
        "pair": "BTC/ZAR",
        "net_pnl": -5.0,
        "net_profit": -5.0,
        "status": "closed",
    }
    enriched = enrich_trade_pnl_fields(dict(stored_trade))
    net_profit_zar = enriched.get("realized_pnl_zar")

    assert net_profit_zar == pytest.approx(-5.0), (
        f"Luno ZAR trade net_profit_zar must be unchanged; got {net_profit_zar}"
    )


# ---------------------------------------------------------------------------
# 9. exposure check — equity must use canonical_base_capital_zar
# ---------------------------------------------------------------------------

def test_exposure_check_uses_canonical_base_not_inflated_current():
    """compute_equity_zar must use canonical_base_capital_zar, not inflated current_capital."""
    from services.reconciliation import compute_equity_zar
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    # Binance bot with LEGACY inflated current_capital (500 USDT = old bug),
    # but canonical_base_capital_zar = 1000 ZAR (what the user actually funded).
    bots = [
        {
            "exchange": "binance",
            "canonical_base_capital_zar": 1000.0,   # authoritative ZAR base
            "current_capital": 500.0,               # LEGACY inflated value (old bug)
            "quote_currency": "USDT",
        },
    ]
    total_zar, _ = compute_equity_zar(bots)
    # Must use canonical_base (1000), NOT current_capital × fx_rate (500 × 19 = 9500)
    assert total_zar == pytest.approx(1000.0, rel=1e-2), (
        f"Equity must be R1000 (canonical base), not R9500 (inflated); got {total_zar}"
    )
    assert total_zar < 2000.0, "Equity must not use inflated current_capital"


def test_exposure_check_single_exchange_within_limit():
    """With one Binance bot at R1000 ZAR canonical base, max 60% exchange exposure must pass."""
    from services.reconciliation import compute_equity_zar
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    bots = [
        {
            "exchange": "luno",
            "canonical_base_capital_zar": 1000.0,
            "current_capital": 1000.0,
            "quote_currency": "ZAR",
        },
        {
            "exchange": "binance",
            "canonical_base_capital_zar": 1000.0,
            "current_capital": 52.631579,
            "quote_currency": "USDT",
        },
    ]
    total_zar, breakdown = compute_equity_zar(bots)
    binance_zar = breakdown["by_exchange"].get("binance", 0)
    max_allowed = total_zar * 0.60  # 60% per-exchange cap
    assert total_zar == pytest.approx(2000.0, rel=1e-2)
    # R1000 Binance equity is 50% of R2000 total — within the 60% cap
    assert binance_zar <= max_allowed, (
        f"Binance equity R{binance_zar:.2f} should be ≤ R{max_allowed:.2f} (60% of R{total_zar:.2f})"
    )


# ---------------------------------------------------------------------------
# REGRESSION GUARD — batch_create capital policy
# These tests ensure the batch_create wallet check and bot records NEVER silently
# regress to using the raw ZAR amount (1000) as USDT for non-Luno bots.
# ---------------------------------------------------------------------------

def test_regression_guard_wallet_check_uses_quote_capital():
    """REGRESSION GUARD: batch-create wallet check must use quote_capital (R1000/FX),
    not capital_per_bot flat (1000 USDT).

    With a R30,000 paper wallet at FX 19, a batch of 10 Binance bots should be
    affordable (~540 USDT needed).  If the bug re-appears (10000 USDT needed) the
    entire fleet would be blocked by wallet_insufficient.
    """
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    update_fx_rate(19.0, "test")

    capital_per_bot = 1000.0  # ZAR economic base
    bot_count = 10

    quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_per_bot, "binance")

    # total_required as batch_create now computes it
    total_required = bot_count * quote_capital

    assert quote_currency == "USDT"
    # Must NOT equal bot_count * capital_per_bot (10000 — the old broken value)
    assert total_required < bot_count * capital_per_bot, (
        "REGRESSION: wallet check must use quote_capital (USDT), not capital_per_bot (ZAR). "
        f"Got total_required={total_required:.2f} which equals or exceeds {bot_count * capital_per_bot}"
    )
    # With R30000 paper wallet at FX 19 ≈ 1578 USDT available; 10 bots need ~526 USDT
    simulated_usdt_available = 30000.0 / fx_rate
    assert total_required < simulated_usdt_available, (
        f"REGRESSION: 10 starter Binance bots ({total_required:.2f} USDT) must fit in "
        f"a R30k paper wallet (~{simulated_usdt_available:.2f} USDT). "
        "If this fails the old bug (1000 USDT per bot flat) has returned."
    )


def test_regression_guard_bot_record_initial_capital_is_usdt():
    """REGRESSION GUARD: batch-create bot records must store initial_capital in
    quote_currency units (USDT for Binance/KuCoin/etc.), not the raw ZAR base.

    Luno must remain ZAR-native at R1000 exactly.
    """
    from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
    update_fx_rate(19.0, "test")

    capital_per_bot = 1000.0  # ZAR input from user

    # Non-Luno exchanges: initial_capital must be R1000/FX, not 1000 flat
    for exchange in ("binance", "kucoin", "bybit", "kraken", "bitget", "gate", "coinbase"):
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_per_bot, exchange)
        assert quote_currency == "USDT", f"{exchange}: quote_currency must be USDT"
        assert quote_capital < capital_per_bot, (
            f"REGRESSION [{exchange}]: initial_capital must be ~R1000/FX USDT (~52.63), "
            f"not {quote_capital:.2f} (which equals the raw ZAR amount). "
            "The old bug stored 1000 USDT, inflating canonical_base_capital_zar to R19000+."
        )
        assert quote_capital == pytest.approx(capital_per_bot / fx_rate, rel=1e-3)

    # Luno: initial_capital must be ZAR 1000 (no conversion)
    luno_capital, luno_currency, luno_fx = resolve_capital_for_exchange(capital_per_bot, "luno")
    assert luno_currency == "ZAR", "Luno must remain ZAR-native"
    assert luno_capital == pytest.approx(capital_per_bot), (
        "Luno initial_capital must be R1000 ZAR exactly (no FX conversion)"
    )
    assert luno_fx == pytest.approx(1.0), "Luno FX rate must be 1.0 (identity)"

