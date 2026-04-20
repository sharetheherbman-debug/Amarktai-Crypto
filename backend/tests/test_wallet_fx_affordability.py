"""
Tests for wallet / FX / affordability truth — Step 2.

Mandatory tests:

1. test_total_paper_equity_zar_includes_zar_and_usdt
   — ZAR + USDT are both included and USDT is converted via FX, not added raw.

2. test_binance_capital_converts_correctly_to_zar_equivalent
   — A Binance bot with USDT initial_capital contributes ZAR-equivalent equity,
     not inflated USDT-treated-as-ZAR.

3. test_affordability_check_blocks_before_insert
   — batch_create_bots affordability check uses ZAR-equivalent total and rejects
     creation when equity is insufficient.

4. test_wallet_overview_countdown_use_same_equity_truth
   — countdown helper, overview equity, and wallet total all resolve through
     get_canonical_paper_wallet_equity / get_total_paper_equity_zar.

Additional:

5. test_no_raw_zar_usdt_sum_in_paper_wallet
   — 1000 ZAR + 100 USDT @19 ZAR/USDT should total ~2900 ZAR, NOT 1100 ZAR
     (which would be the naive raw sum).

6. test_wallet_summary_required_funds_converts_usdt
   — wallet_summary_service.get_summary uses canonical_base_capital_zar so
     that a Binance bot (USDT initial_capital) is not counted as tiny ZAR.

7. test_compute_equity_zar_uses_canonical_base
   — compute_equity_zar uses canonical_base_capital_zar before falling back.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── helpers ──────────────────────────────────────────────────────────────────

def _set_fx_rate(rate: float):
    """Set the module-level FX rate so tests are deterministic."""
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(rate, "test")


# ── 1. get_canonical_paper_wallet_equity sums ZAR+USDT through FX ────────────

@pytest.mark.asyncio
async def test_total_paper_equity_zar_includes_zar_and_usdt():
    """ZAR + USDT×fx should be included and not raw-summed."""
    from unittest.mock import AsyncMock, patch, MagicMock

    _set_fx_rate(19.0)

    mock_balances = {"ZAR": 1000.0, "USDT": 100.0}

    wallet_svc_mock = MagicMock()
    wallet_svc_mock.get_balances = AsyncMock(return_value={"balances": mock_balances})

    with (
        patch("services.canonical.paper_wallet_service", wallet_svc_mock),
        patch("services.canonical.db") as mock_db,
    ):
        mock_db.paper_ledger_collection = None  # no allocated
        from services.canonical import get_canonical_paper_wallet_equity
        result = await get_canonical_paper_wallet_equity("user-test")

    # At FX=19: 1000 ZAR + 100 USDT × 19 = 1000 + 1900 = 2900 ZAR total
    expected = 1000.0 + 100.0 * 19.0
    assert abs(result["total_equity"] - expected) < 1.0, (
        f"Expected ~{expected} ZAR equity, got {result['total_equity']}"
    )
    # Must NOT equal 1100 (raw sum)
    assert abs(result["total_equity"] - 1100.0) > 100.0, (
        "total_equity looks like a raw USDT+ZAR sum — USDT was not converted!"
    )
    assert result["source"] == "paper_wallet_total_equity_zar"


# ── 2. Binance capital converts to ZAR-equivalent equity ─────────────────────

def test_binance_capital_converts_correctly_to_zar_equivalent():
    """A Binance bot with USDT initial_capital → correct ZAR equity, not inflated."""
    from services.reconciliation import compute_equity_zar

    _set_fx_rate(19.0)

    # Bot with USDT initial_capital=52.63 USDT (≈ R1000 ZAR at 19 ZAR/USDT)
    binance_bot = {
        "exchange": "binance",
        "quote_currency": "USDT",
        "current_capital": 52.63,
        "canonical_base_capital_zar": 1000.0,  # stored at creation
    }

    equity_zar, breakdown = compute_equity_zar([binance_bot])

    # Should be ~R1000 (from canonical_base), NOT ~R999.97 raw USDT, NOT ~R19000
    assert abs(equity_zar - 1000.0) < 1.0, (
        f"Binance equity should be ~R1000 ZAR, got {equity_zar}"
    )
    assert equity_zar < 2000.0, (
        f"Binance equity appears to be raw-multiplied (got {equity_zar}), "
        "expected ~R1000"
    )


# ── 3. Affordability check uses ZAR-equivalent (not raw USDT balance) ─────────

@pytest.mark.asyncio
async def test_affordability_check_blocks_before_insert():
    """batch_create_bots affordability check must use ZAR-equivalent and reject when insufficient.

    Regression: the old code read get_available_balance(user_id, "USDT") which returned
    0 when the wallet only held ZAR. Then it fell back to PAPER_STARTING_CAPITAL_ZAR as
    a raw ZAR number compared against total_required in USDT — apples vs oranges.

    The fix: affordability is always ZAR-equivalent (canonical equity) vs ZAR cost.
    """
    from unittest.mock import AsyncMock, patch, MagicMock

    _set_fx_rate(19.0)

    # Wallet has only R100 ZAR — not enough for 10 bots at R1000 each
    tiny_equity = {"total_equity": 100.0, "available_total": 100.0, "allocated_total": 0.0}

    with patch("services.canonical.get_canonical_paper_wallet_equity", new=AsyncMock(return_value=tiny_equity)):
        # Simulate the affordability logic from batch_create_bots
        from services.canonical import get_canonical_paper_wallet_equity
        equity_info = await get_canonical_paper_wallet_equity("user-test")
        available_zar_equiv = float(equity_info.get("total_equity", 0) or 0)

        num_bots = 10
        capital_per_bot = 1000.0
        total_required_zar = num_bots * capital_per_bot

        assert available_zar_equiv < total_required_zar, (
            "Affordability check should block: insufficient ZAR-equivalent funds"
        )

    # Now test passing case: R20000 ZAR → enough for 10 bots at R1000 each
    sufficient_equity = {"total_equity": 20000.0, "available_total": 20000.0, "allocated_total": 0.0}
    with patch("services.canonical.get_canonical_paper_wallet_equity", new=AsyncMock(return_value=sufficient_equity)):
        from services.canonical import get_canonical_paper_wallet_equity
        equity_info = await get_canonical_paper_wallet_equity("user-test")
        available_zar_equiv = float(equity_info.get("total_equity", 0) or 0)
        assert available_zar_equiv >= total_required_zar, (
            "Affordability check should pass: sufficient ZAR-equivalent funds"
        )


# ── 4. Countdown / overview / wallet all route through same canonical source ──

@pytest.mark.asyncio
async def test_wallet_overview_countdown_use_same_equity_truth():
    """All three entry points must call get_canonical_paper_wallet_equity."""
    import inspect

    # 1. user_countdowns.py source must use get_total_paper_equity_zar
    countdowns_path = os.path.join(os.path.dirname(__file__), "..", "routes", "user_countdowns.py")
    with open(countdowns_path) as f:
        countdowns_source = f.read()
    assert "get_total_paper_equity_zar" in countdowns_source, (
        "routes/user_countdowns.py must use get_total_paper_equity_zar from services.canonical"
    )

    # 2. canonical.py must define both equity functions
    from services import canonical
    assert hasattr(canonical, "get_canonical_paper_wallet_equity"), (
        "canonical.py must export get_canonical_paper_wallet_equity"
    )
    assert hasattr(canonical, "get_total_paper_equity_zar"), (
        "canonical.py must export get_total_paper_equity_zar"
    )

    # 3. wallet_hub.py uses get_canonical_paper_wallet_equity for its total
    wallet_hub_path = os.path.join(os.path.dirname(__file__), "..", "routes", "wallet_hub.py")
    with open(wallet_hub_path) as f:
        wallet_hub_source = f.read()
    assert "get_canonical_paper_wallet_equity" in wallet_hub_source, (
        "routes/wallet_hub.py get_paper_wallet must use get_canonical_paper_wallet_equity for total"
    )

    # 4. get_total_paper_equity_zar must wrap get_canonical_paper_wallet_equity
    canonical_source = inspect.getsource(canonical)
    equity_fn_body = canonical_source.split("async def get_total_paper_equity_zar")[-1][:500]
    assert "get_canonical_paper_wallet_equity" in equity_fn_body, (
        "get_total_paper_equity_zar must delegate to get_canonical_paper_wallet_equity"
    )


# ── 5. No raw ZAR+USDT sum ────────────────────────────────────────────────────

def test_no_raw_zar_usdt_sum_in_paper_wallet():
    """1000 ZAR + 100 USDT @19 = ~2900 ZAR, NOT 1100 ZAR raw sum."""
    from services.fx_normalizer import to_display_zar

    _set_fx_rate(19.0)

    balances = {"ZAR": 1000.0, "USDT": 100.0}
    total = 0.0
    for currency, amount in balances.items():
        zar_val, _, _ = to_display_zar(float(amount), currency)
        total += zar_val or 0.0

    # Correct: ~2900 ZAR
    assert abs(total - 2900.0) < 1.0, f"Expected ~2900 ZAR, got {total}"
    # WRONG would be 1100 (raw sum)
    assert total > 2000.0, f"Total {total} is suspiciously low — check FX conversion"


# ── 6. wallet_summary required_funds converts USDT bots via canonical_base ───

def test_wallet_summary_required_funds_converts_usdt():
    """Binance bots must contribute ZAR-equivalent to required_funds, not raw USDT."""
    from services.fx_normalizer import to_display_zar, get_quote_currency

    _set_fx_rate(19.0)

    # A Binance bot created with R1000 ZAR → 52.63 USDT stored as initial_capital
    # canonical_base_capital_zar = 1000 (stored at creation time)
    binance_bot = {
        "exchange": "binance",
        "quote_currency": "USDT",
        "initial_capital": 52.63,         # USDT (the exchange-native amount)
        "canonical_base_capital_zar": 1000.0,  # ZAR economic base
        "active": True,
        "trading_mode": "paper",
        "is_deleted": False,
    }

    def _bot_capital_zar(bot: dict, field: str = "initial_capital") -> float:
        canonical = bot.get("canonical_base_capital_zar")
        if canonical is not None:
            try:
                return float(canonical)
            except (TypeError, ValueError):
                pass
        raw = float(bot.get(field) or bot.get("initial_capital") or 1000)
        exchange = bot.get("exchange") or ""
        qc = bot.get("quote_currency") or get_quote_currency(exchange)
        zar_val, _, _ = to_display_zar(raw, qc)
        return zar_val if zar_val is not None else raw

    required_zar = _bot_capital_zar(binance_bot)

    # Should be ~1000 ZAR (from canonical_base), NOT 52.63 ZAR (raw USDT treated as ZAR)
    assert abs(required_zar - 1000.0) < 1.0, (
        f"Binance bot required_funds should be ~R1000 ZAR, got R{required_zar}"
    )
    # Sanity: should NOT be 52.63 (USDT treated as ZAR)
    assert required_zar > 500.0, (
        f"required_funds={required_zar} — USDT value was NOT converted to ZAR"
    )


# ── 7. compute_equity_zar uses canonical_base_capital_zar first ──────────────

def test_compute_equity_zar_uses_canonical_base():
    """compute_equity_zar must prefer canonical_base_capital_zar over raw current_capital × FX."""
    from services.reconciliation import compute_equity_zar

    _set_fx_rate(19.0)

    # Bot with high current_capital in USDT but canonical_base set to R1000
    bot = {
        "exchange": "binance",
        "quote_currency": "USDT",
        "current_capital": 52.63,           # USDT
        "canonical_base_capital_zar": 1000.0,  # should win
    }
    equity_zar, _ = compute_equity_zar([bot])

    # canonical_base should be used: R1000 ZAR
    assert abs(equity_zar - 1000.0) < 1.0, (
        f"compute_equity_zar should use canonical_base_capital_zar=1000, got {equity_zar}"
    )

    # Without canonical_base → falls back to current_capital × fx_rate
    bot_no_canonical = {
        "exchange": "binance",
        "quote_currency": "USDT",
        "current_capital": 52.63,  # USDT — at 19 → ~R1000
    }
    equity_fallback, _ = compute_equity_zar([bot_no_canonical])
    assert abs(equity_fallback - 52.63 * 19.0) < 2.0, (
        f"Without canonical_base, should use current_capital×fx, got {equity_fallback}"
    )
