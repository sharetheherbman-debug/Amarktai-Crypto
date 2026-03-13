"""
FX Normalizer — Canonical Display Currency Service
===================================================

Single source of truth for currency resolution and ZAR normalization.

Rules:
- Luno bots trade in ZAR natively (no conversion needed).
- Binance/KuCoin/Bybit/Bitget/Gate/Kraken bots trade in USDT.
- All user-facing monetary amounts are displayed in ZAR.
- This module owns the USDT→ZAR conversion path.

FX rate resolution order:
  1. Runtime cached rate (set by market intelligence engine when live USDT/ZAR price is available)
  2. Environment variable USDT_ZAR_RATE (operator override)
  3. Module-level static fallback (USDT_ZAR_FALLBACK) — conservative safe default

Do NOT add a second FX conversion path anywhere else in the codebase.
"""

from __future__ import annotations

import os
import logging
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Static fallback rate ──────────────────────────────────────────────────────
# Updated periodically — set USDT_ZAR_RATE env var to override at deployment.
USDT_ZAR_FALLBACK: float = float(os.getenv("USDT_ZAR_RATE", "19.0"))

# ── Supported quote currencies ────────────────────────────────────────────────
_ZAR_QUOTE_CURRENCIES = {"ZAR"}
_USDT_QUOTE_CURRENCIES = {"USDT", "BUSD", "USDC", "TUSD", "USD"}

# ── Canonical exchange → quote currency map (single authoritative definition) ─
# All 7 supported venues. Update here only — no duplicate mappings elsewhere.
EXCHANGE_QUOTE_MAP: dict[str, str] = {
    "luno": "ZAR",     # ZAR-native South African venue
    "binance": "USDT",
    "kucoin": "USDT",
    "bybit": "USDT",
    "kraken": "USDT",
    "bitget": "USDT",
    "gate": "USDT",
}

# ── Runtime rate cache (set by market intelligence or live price feeds) ───────
_lock = threading.Lock()
_cached_rate: Optional[float] = None
_cached_rate_source: str = "fallback"


# ── Public API ────────────────────────────────────────────────────────────────

def get_quote_currency(exchange: str, symbol: Optional[str] = None) -> str:
    """Return canonical quote currency for a given exchange + symbol combination.

    Priority:
    1) Symbol-based inference ('/ZAR' in symbol → ZAR)
    2) Authoritative EXCHANGE_QUOTE_MAP lookup
    3) USDT default fallback
    """
    if symbol:
        sym = str(symbol).upper()
        if sym.endswith("/ZAR"):
            return "ZAR"
        for usdt_like in _USDT_QUOTE_CURRENCIES:
            if sym.endswith(f"/{usdt_like}"):
                return usdt_like
    exch = str(exchange or "").lower()
    return EXCHANGE_QUOTE_MAP.get(exch, "USDT")


def get_fx_rate(from_currency: str, to_currency: str = "ZAR") -> Tuple[float, str]:
    """Return (rate, source) to convert *from_currency* into *to_currency*.

    Currently supports: any→ZAR.
    If from_currency is already ZAR the rate is always 1.0.
    """
    src = str(from_currency or "").upper()
    dst = str(to_currency or "ZAR").upper()

    if src == dst or src == "ZAR":
        return 1.0, "identity"

    # USDT-family → ZAR
    if src in _USDT_QUOTE_CURRENCIES:
        rate = _get_cached_rate()
        source = _cached_rate_source
        return rate, source

    # Unknown currency — return 1.0 so caller doesn't crash, but log a warning
    logger.warning("FX rate unknown for %s→%s; using 1.0 identity", src, dst)
    return 1.0, "unknown"


def to_display_zar(
    amount: Optional[float],
    quote_currency: str,
    fx_rate: Optional[float] = None,
) -> Tuple[Optional[float], float, str]:
    """Convert *amount* in *quote_currency* to ZAR display value.

    Returns (display_value_zar, fx_rate_used, fx_source).

    - If amount is None, returns (None, rate, source).
    - If quote_currency is ZAR, rate = 1.0.
    - Otherwise uses canonical FX rate.
    """
    if amount is None:
        rate, source = get_fx_rate(quote_currency, "ZAR")
        return None, rate, source

    if fx_rate is not None and fx_rate > 0:
        rate, source = fx_rate, "caller_provided"
    else:
        rate, source = get_fx_rate(quote_currency, "ZAR")

    display = round(float(amount) * rate, 2)
    return display, rate, source


def normalize_money_field(
    raw_value: Optional[float],
    quote_currency: str,
    fx_rate: Optional[float] = None,
) -> dict:
    """Return canonical money field dict for serialization.

    Shape (matches problem statement preferred structure):
    {
        "raw_value": float | None,
        "raw_currency": str,
        "display_value": float | None,
        "display_currency": "ZAR",
        "fx_rate_used": float,
        "fx_source": str,
    }
    """
    display_value, fx_rate_used, fx_source = to_display_zar(raw_value, quote_currency, fx_rate)
    return {
        "raw_value": raw_value,
        "raw_currency": str(quote_currency or "USDT").upper(),
        "display_value": display_value,
        "display_currency": "ZAR",
        "fx_rate_used": fx_rate_used,
        "fx_source": fx_source,
    }


# ── Cache management (called by market intelligence when a fresh rate is known) ──

def update_fx_rate(rate: float, source: str = "market") -> None:
    """Update the module-level cached FX rate (USDT→ZAR).

    Call this from the market intelligence engine whenever a fresh rate is
    fetched. Thread-safe.
    """
    global _cached_rate, _cached_rate_source
    if rate and rate > 0:
        with _lock:
            _cached_rate = float(rate)
            _cached_rate_source = str(source)
            logger.debug("FX rate updated: 1 USDT = %.4f ZAR (source=%s)", rate, source)


def get_current_usdt_zar_rate() -> Tuple[float, str]:
    """Public accessor for the current USDT→ZAR rate and its source."""
    return _get_cached_rate(), _cached_rate_source


def resolve_capital_for_exchange(
    capital_zar: float,
    exchange: str,
) -> Tuple[float, str, float]:
    """Convert a ZAR economic base into the correct quote currency for an exchange.

    This is the canonical capital-truth function for bot creation:
    - ALL bots start from an economic base expressed in ZAR.
    - Luno bots trade natively in ZAR → quote_capital == capital_zar.
    - USDT exchanges (Binance, KuCoin, etc.) → quote_capital = capital_zar / fx_rate.

    Returns (quote_capital, quote_currency, fx_rate_used).

    Example:
        resolve_capital_for_exchange(1000.0, "binance")
        # → (52.63, "USDT", 19.0) at a 19 ZAR/USDT rate
        # → display back to ZAR: 52.63 × 19 = 1000 ZAR  ✓ (not inflated to R19000)
    """
    if (exchange or "").lower() == "luno":
        return round(float(capital_zar), 2), "ZAR", 1.0
    # USDT exchange — convert ZAR base to USDT
    fx_rate, _ = get_fx_rate("USDT", "ZAR")  # ZAR per 1 USDT
    if fx_rate <= 0:
        fx_rate = USDT_ZAR_FALLBACK
    quote_capital = round(float(capital_zar) / fx_rate, 6)
    return quote_capital, "USDT", round(fx_rate, 4)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_cached_rate() -> float:
    with _lock:
        if _cached_rate is not None and _cached_rate > 0:
            return _cached_rate
    return USDT_ZAR_FALLBACK
