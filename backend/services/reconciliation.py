"""
Canonical Reconciliation Layer
================================

Single source of truth for cross-currency wallet, equity, and P&L calculations.

All wallet/radar/trades/risk endpoints MUST use these helpers instead of
raw-summing multi-currency values (e.g., ZAR + USDT into one unlabeled total).

Rules enforced here:
- Luno bots and ZAR wallets are native ZAR — rate = 1.0, no conversion needed.
- Binance/KuCoin/Bybit/Kraken/Bitget/Gate wallets and bots are USDT-first.
- A combined ZAR display total is ALWAYS derived through one shared FX path
  (fx_normalizer.to_display_zar) and never by raw-summing different currencies.
- P&L fields distinguish quote (native) vs. display (ZAR equivalent).

Do NOT add a second reconciliation path anywhere else in the codebase.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging

from services.fx_normalizer import (
    get_fx_rate,
    get_quote_currency,
    to_display_zar,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wallet reconciliation
# ---------------------------------------------------------------------------

def reconcile_wallet_balances(
    available_by_currency: Dict[str, float],
    allocated_by_currency: Dict[str, float],
) -> Dict[str, Any]:
    """Merge available + allocated balances with proper cross-currency conversion.

    Parameters
    ----------
    available_by_currency:
        Per-currency unallocated wallet balances, e.g. ``{"ZAR": 1000, "USDT": 50}``.
    allocated_by_currency:
        Per-currency capital locked in active bot ledgers,
        e.g. ``{"ZAR": 500, "USDT": 104.85}``.

    Returns
    -------
    dict with keys:
    - ``available``        — per-currency available balances (cleaned floats)
    - ``allocated``        — per-currency allocated balances (cleaned floats)
    - ``balances``         — per-currency total (available + allocated)
    - ``total_display_zar``— sum of all currencies converted to ZAR display equivalent
    - ``canonical_currency``— always ``"ZAR"``
    - ``fx_metadata``      — rates used for each currency → ZAR conversion

    The old ``total`` field (which raw-summed different currencies) is gone
    from this return value.  Callers should emit ``total_display_zar`` and
    keep ``total = total_display_zar`` for backward compatibility.
    """
    fx_rate, fx_source = get_fx_rate("USDT", "ZAR")

    # Compute per-currency totals
    all_currencies: set = set(available_by_currency) | set(allocated_by_currency)
    balances_by_currency: Dict[str, float] = {}
    for currency in all_currencies:
        avail = float(available_by_currency.get(currency) or 0)
        alloc = float(allocated_by_currency.get(currency) or 0)
        balances_by_currency[currency] = round(avail + alloc, 2)

    # Convert all to ZAR display total through the canonical FX path
    total_display_zar = 0.0
    fx_used: Dict[str, float] = {}
    for currency, amount in balances_by_currency.items():
        display_value, rate_used, _ = to_display_zar(amount, currency)
        if display_value is not None:
            total_display_zar += display_value
        fx_used[currency] = rate_used

    return {
        "available": {k: round(float(v or 0), 2) for k, v in available_by_currency.items()},
        "allocated": {k: round(float(v or 0), 2) for k, v in allocated_by_currency.items()},
        "balances": balances_by_currency,
        "total_display_zar": round(total_display_zar, 2),
        "canonical_currency": "ZAR",
        "fx_metadata": {
            "usdt_zar_rate": round(fx_rate, 4),
            "usdt_zar_source": fx_source,
            "rates_by_currency": {k: round(v, 4) for k, v in fx_used.items()},
        },
    }


# ---------------------------------------------------------------------------
# Equity reconciliation (used by risk engine and exposure checks)
# ---------------------------------------------------------------------------

def compute_equity_zar(
    user_bots: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """Compute total equity in ZAR across all bots, converting USDT bots properly.

    Capital resolution priority per bot:
    1. ``canonical_base_capital_zar`` — stored at creation, most accurate.
    2. If ``quote_currency == "ZAR"``: use ``current_capital`` directly.
    3. If ``quote_currency == "USDT"`` (or other): ``current_capital × fx_rate``.

    Parameters
    ----------
    user_bots:
        List of bot documents (dicts) as returned from the bots collection.

    Returns
    -------
    Tuple of (total_equity_zar, breakdown) where breakdown contains:
    - ``by_exchange``  — ZAR equity sum keyed by exchange name
    - ``fx_rate_used`` — USDT→ZAR rate used for conversion
    - ``fx_source``    — source of that rate
    """
    fx_rate, fx_source = get_fx_rate("USDT", "ZAR")
    total_zar = 0.0
    by_exchange: Dict[str, float] = {}

    for bot in user_bots:
        exchange = (bot.get("exchange") or "").lower()
        current_capital = float(bot.get("current_capital") or 0)

        # 1. Prefer canonical_base_capital_zar (most reliable — stored at bot creation)
        canonical_base = bot.get("canonical_base_capital_zar")
        if canonical_base is not None:
            try:
                zar_value = float(canonical_base)
            except (TypeError, ValueError):
                zar_value = None
        else:
            zar_value = None

        if zar_value is None:
            # 2/3. Infer from quote_currency (or exchange default)
            quote_currency = bot.get("quote_currency") or get_quote_currency(exchange)
            if (quote_currency or "").upper() == "ZAR":
                zar_value = current_capital
            else:
                # USDT (or USDT-family) — convert at current FX rate
                zar_value = current_capital * fx_rate

        total_zar += zar_value
        by_exchange[exchange] = by_exchange.get(exchange, 0.0) + zar_value

    return round(total_zar, 2), {
        "by_exchange": {k: round(v, 2) for k, v in by_exchange.items()},
        "fx_rate_used": round(fx_rate, 4),
        "fx_source": fx_source,
    }


# ---------------------------------------------------------------------------
# Trade P&L enrichment
# ---------------------------------------------------------------------------

def enrich_trade_pnl_fields(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich a trade record with canonical P&L display fields.

    Adds/updates the following fields:
    - ``quote_currency``     — native quote currency for the trade (ZAR or USDT)
    - ``realized_pnl_quote`` — P&L in quote currency (raw, as executed on exchange)
    - ``realized_pnl_display``— P&L converted to ZAR for UI display
    - ``realized_pnl_zar``   — P&L in ZAR (only when truly in ZAR or properly converted)
    - ``fee_display_zar``    — fee amount in ZAR display equivalent
    - ``fx_rate_used``       — USDT→ZAR rate used for any conversion
    - ``fx_source``          — source of that rate

    Preserves existing fields (``net_pnl``, ``gross_pnl``, ``net_pnl_quote``, etc.).
    The existing ``net_pnl_quote`` alias is left intact for backward compatibility.

    Parameters
    ----------
    trade:
        Trade record dict (modified in-place and returned).
    """
    exchange = trade.get("exchange") or "unknown"
    pair = trade.get("pair") or trade.get("symbol") or ""

    # Canonical quote currency for this trade
    quote_currency = trade.get("quote_currency") or get_quote_currency(exchange, pair)

    # Realized P&L in quote currency — prefer explicit field, fall back to net_pnl
    realized_pnl_quote = float(
        trade.get("realized_pnl_quote")
        or trade.get("net_pnl")
        or trade.get("net_profit")
        or trade.get("profit_loss")
        or 0
    )

    # Convert to ZAR display through the canonical FX path
    display_value, fx_rate_used, fx_source = to_display_zar(realized_pnl_quote, quote_currency)

    # Fee enrichment
    fee_amount = float(
        trade.get("fee_amount")
        or trade.get("fees_total")
        or trade.get("fees")
        or 0
    )
    fee_currency = trade.get("fee_currency") or quote_currency
    fee_display_zar, _, _ = to_display_zar(fee_amount, fee_currency)

    # Write canonical fields (never overwrite with None)
    trade["quote_currency"] = quote_currency
    trade["realized_pnl_quote"] = round(realized_pnl_quote, 6)
    # realized_pnl_display and realized_pnl_zar are intentionally both set to the
    # ZAR display equivalent.  The problem statement requires both field names for
    # backward compatibility with consumers that read either name.  Both are always
    # the properly-converted ZAR value (not raw quote units for USDT trades).
    trade["realized_pnl_display"] = display_value   # always ZAR for display
    trade["realized_pnl_zar"] = display_value        # canonical ZAR (native or converted)
    trade["fee_display_zar"] = fee_display_zar
    trade["fx_rate_used"] = round(fx_rate_used, 4)
    trade["fx_source"] = fx_source

    # net_pnl_quote: overwrite any previously set value to ensure it is the
    # quote-currency raw P&L.  build_trade_record may pre-set this from a stale
    # net_profit_zar alias; this assignment is the authoritative correction.
    trade["net_pnl_quote"] = round(realized_pnl_quote, 6)

    return trade
