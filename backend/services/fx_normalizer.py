"""
FX Normalizer — Canonical Display Currency Service
===================================================

Single source of truth for currency resolution and multi-currency normalization.

Rules:
- Luno bots trade in ZAR natively (no conversion needed).
- Binance/KuCoin/Bybit/Bitget/Gate/Kraken bots trade in USDT.
- The canonical *internal* aggregate currency is always ZAR.
- The *display* currency is user-selectable: ZAR, USD, GBP, or EUR.
  All values are first normalised to ZAR (the single internal truth) and then
  optionally re-expressed in the user's preferred display currency.

FX rate resolution order:
  1. Runtime cached rate (set by market intelligence engine when live USDT/ZAR price is available)
  2. Environment variable USDT_ZAR_RATE (operator override)
  3. Module-level static fallback (USDT_ZAR_FALLBACK) — conservative safe default

Supported display currencies (ZAR, USD, GBP, EUR):
  - All cross-rates are via ZAR (quote → ZAR → display).
  - Static fallback rates are env-overridable (USD_ZAR_RATE, GBP_ZAR_RATE, EUR_ZAR_RATE).

Do NOT add a second FX conversion path anywhere else in the codebase.
"""

from __future__ import annotations

import os
import logging
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Static fallback rates ─────────────────────────────────────────────────────
# Updated periodically — set *_RATE env vars to override at deployment.
USDT_ZAR_FALLBACK: float = float(os.getenv("USDT_ZAR_RATE", "19.0"))

# Fiat display-currency cross-rates (ZAR per 1 unit of each fiat)
_USD_ZAR_FALLBACK: float = float(os.getenv("USD_ZAR_RATE", "18.5"))
_GBP_ZAR_FALLBACK: float = float(os.getenv("GBP_ZAR_RATE", "23.5"))
_EUR_ZAR_FALLBACK: float = float(os.getenv("EUR_ZAR_RATE", "20.0"))

# Supported user-selectable display currencies
SUPPORTED_DISPLAY_CURRENCIES: tuple = ("ZAR", "USD", "GBP", "EUR")

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

    Supports any→ZAR and any→USD/GBP/EUR by pivoting through ZAR.
    If from_currency equals to_currency the rate is always 1.0.

    Internal algorithm:
        rate = (from → ZAR) / (to → ZAR)

    This ensures all cross-rates are consistent with the ZAR internal truth.

    Priority in rate resolution:
    1. ZAR (identity, rate=1.0)
    2. Fiat display currencies (USD, GBP, EUR) — use env-overridable static rates
    3. USDT-family stablecoins (USDT, BUSD, USDC, TUSD) — use live/cached rate
    4. Unknown — 1.0 with warning

    Note: "USD" in _USDT_QUOTE_CURRENCIES is for trading pair recognition only
    (e.g. BTC/USD symbols). When used as a display or conversion currency the
    dedicated fiat rate is always preferred over the USDT stablecoin rate.
    """
    src = str(from_currency or "").upper()
    dst = str(to_currency or "ZAR").upper()

    if src == dst:
        return 1.0, "identity"

    def _to_zar_rate(cur: str) -> Tuple[float, str]:
        """Internal helper: return (rate, source) to convert *cur* → ZAR."""
        if cur == "ZAR":
            return 1.0, "identity"
        # Fiat display currencies checked FIRST to avoid "USD" ambiguity.
        # "USD" lives in _USDT_QUOTE_CURRENCIES for trading-pair matching,
        # but as a display currency it must use the dedicated fiat rate.
        _known_fiat = {"USD", "GBP", "EUR"}
        if cur in _known_fiat:
            return _fiat_to_zar_rate(cur)
        # USDT-family stablecoins (USDT, BUSD, USDC, TUSD) → live/cached rate
        _stablecoins = {"USDT", "BUSD", "USDC", "TUSD"}
        if cur in _stablecoins or cur in _USDT_QUOTE_CURRENCIES:
            return _get_cached_rate(), _cached_rate_source
        # Unknown — log and degrade gracefully
        logger.warning("FX rate unknown for %s→ZAR; using 1.0 identity", cur)
        return 1.0, "unknown"

    src_to_zar, src_source = _to_zar_rate(src)
    dst_to_zar, dst_source = _to_zar_rate(dst)

    # ── Cross-rate ────────────────────────────────────────────────────────
    if dst_to_zar <= 0:
        logger.warning("FX: dst_to_zar=0 for %s; using 1.0 identity", dst)
        dst_to_zar = 1.0

    rate = src_to_zar / dst_to_zar
    composite_source = src_source if src_source == dst_source else f"{src_source}/{dst_source}"
    return rate, composite_source


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


def to_display_currency(
    amount_zar: Optional[float],
    display_currency: str = "ZAR",
) -> Tuple[Optional[float], float, str]:
    """Convert an amount already in ZAR to the user's *display_currency*.

    This is the final presentation step — call this AFTER all internal
    aggregation has been normalised to ZAR.

    Returns (display_value, fx_rate_used, fx_source).

    For ZAR→ZAR the rate is 1.0 (identity — no conversion overhead).
    For ZAR→USD/GBP/EUR the rate = 1 / (display_currency→ZAR rate).
    """
    dst = str(display_currency or "ZAR").upper()
    if amount_zar is None:
        rate, source = get_fx_rate("ZAR", dst)
        return None, rate, source

    rate, source = get_fx_rate("ZAR", dst)
    display = round(float(amount_zar) * rate, 2)
    return display, rate, source


def normalize_money_field(
    raw_value: Optional[float],
    quote_currency: str,
    fx_rate: Optional[float] = None,
    display_currency: str = "ZAR",
) -> dict:
    """Return canonical money field dict for serialization.

    Shape (matches problem statement preferred structure):
    {
        "raw_value": float | None,
        "raw_currency": str,
        "display_value": float | None,
        "display_currency": str,       # user's chosen display currency
        "fx_rate_used": float,
        "fx_source": str,
    }

    When display_currency == "ZAR" this behaves identically to the original
    ZAR-only implementation.  For other display currencies (USD/GBP/EUR) the
    value is first converted to ZAR, then re-expressed in display_currency.
    """
    # Step 1: quote → ZAR
    zar_value, zar_rate, zar_source = to_display_zar(raw_value, quote_currency, fx_rate)

    # Step 2: ZAR → display_currency (identity if ZAR)
    dst = str(display_currency or "ZAR").upper()
    if dst == "ZAR":
        display_value = zar_value
        display_rate, display_source = zar_rate, zar_source
    else:
        display_value, display_rate, display_source = to_display_currency(zar_value, dst)

    return {
        "raw_value": raw_value,
        "raw_currency": str(quote_currency or "USDT").upper(),
        "display_value": display_value,
        "display_currency": dst,
        "fx_rate_used": display_rate,
        "fx_source": display_source,
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


def _fiat_to_zar_rate(currency: str) -> Tuple[float, str]:
    """Return (zar_rate, source) for supported fiat currencies.

    Priority order:
      1. Live / cached rate from fiat_fx_provider (live_fiat_primary / live_fiat_fallback / cache_stale)
      2. Environment-variable override (*_ZAR_RATE env vars)  — handled inside fiat_fx_provider
      3. Module-level static fallback constants

    Called by get_fx_rate() when *currency* is a known fiat (USD/GBP/EUR).
    Falls back to 1.0 with a warning for unrecognised currencies.
    """
    _STATIC: dict[str, Tuple[float, str]] = {
        "USD": (_USD_ZAR_FALLBACK, "env_fallback_usd"),
        "GBP": (_GBP_ZAR_FALLBACK, "env_fallback_gbp"),
        "EUR": (_EUR_ZAR_FALLBACK, "env_fallback_eur"),
    }
    if currency not in _STATIC:
        logger.warning("FX rate unknown for %s→ZAR; using 1.0 identity", currency)
        return 1.0, "unknown"

    # Try the fiat provider (may return live/cache/env/static depending on availability)
    try:
        from services.fiat_fx_provider import get_zar_per_unit as _gzpu
        rate, source = _gzpu(currency)
        if rate and rate > 0:
            return rate, source
    except Exception as exc:
        logger.debug("fiat_fx_provider unavailable for %s: %s — using static fallback", currency, exc)

    # Final static fallback
    return _STATIC[currency]
