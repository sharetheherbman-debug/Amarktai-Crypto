"""
Fiat FX Provider — Live Fiat Exchange Rate Service
====================================================

Provider abstraction for fetching ZAR/USD/GBP/EUR cross-rates from a live
free-tier HTTP API with aggressive caching and graceful fallback.

Priority order (per-request resolution):
    1. Live rate from primary provider (if fresh, i.e. < CACHE_TTL_SECONDS old)
    2. Last-good cached rate from primary provider
    3. Live rate from fallback provider (if primary fails)
    4. Last-good cached rate from fallback provider
    5. Environment-variable override (*_ZAR_RATE env vars)
    6. Static module-level fallback constants

This module is the ONLY place that touches external fiat FX APIs.
Do NOT add duplicate fiat rate lookups elsewhere.

Usage from fx_normalizer:
    from services.fiat_fx_provider import get_zar_per_unit

    rate, source = get_zar_per_unit("USD")   # → (18.5, "live_fiat_api")

Design constraints:
    - All HTTP calls are server-side only (no browser API keys).
    - Rate is refreshed at most once per CACHE_TTL_SECONDS (default 900s = 15 min).
    - A background refresh is triggered lazily on cache miss; callers always get
      a synchronous result from cache/fallback while the refresh runs in background.
    - Module is importable without network access — all async calls are deferred.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS: float = float(os.getenv("FIAT_FX_CACHE_TTL_SECONDS", "900"))   # 15 min
STALE_MAX_SECONDS: float = float(os.getenv("FIAT_FX_STALE_MAX_SECONDS", "7200"))  # 2 hours
REQUEST_TIMEOUT: float = float(os.getenv("FIAT_FX_REQUEST_TIMEOUT", "8"))

# Static fallback rates (ZAR per 1 unit of fiat) — env-overridable
_FALLBACK_RATES: Dict[str, float] = {
    "USD": float(os.getenv("USD_ZAR_RATE", "18.5")),
    "GBP": float(os.getenv("GBP_ZAR_RATE", "23.5")),
    "EUR": float(os.getenv("EUR_ZAR_RATE", "20.0")),
}

# ── Supported fiat currencies ─────────────────────────────────────────────────
SUPPORTED_FIAT: tuple = ("USD", "GBP", "EUR")

# ── Provider endpoints (free, no API key required) ───────────────────────────
# Primary: open.er-api.com — completely free, no key, ZAR base
# Fallback: exchangerate-api.com — free tier, ZAR base
_PRIMARY_URL = "https://open.er-api.com/v6/latest/ZAR"
_FALLBACK_URL = "https://api.exchangerate-api.com/v4/latest/ZAR"

# ── In-memory cache ───────────────────────────────────────────────────────────
# { "USD": {"rate": float, "fetched_at": float, "source": str}, ... }
_rate_cache: Dict[str, Dict] = {}
_cache_lock = threading.Lock()
_fetch_in_progress: bool = False
_fetch_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def get_zar_per_unit(currency: str) -> Tuple[float, str]:
    """Return (zar_rate, source) for 1 unit of *currency* in ZAR.

    This is the SYNCHRONOUS entry point — always returns immediately.
    If the cache is fresh it returns cached live data.
    If the cache is stale it triggers a background refresh but still returns
    the stale value (or env/static fallback on first cold start).

    Source strings:
        live_fiat_primary   — fresh from open.er-api.com
        live_fiat_fallback  — fresh from exchangerate-api.com
        cache_stale         — stale but within STALE_MAX_SECONDS
        env_fallback        — value from *_ZAR_RATE env var (static)
        static_fallback     — module-level hardcoded constant
    """
    cur = str(currency or "").upper()
    if cur not in SUPPORTED_FIAT:
        logger.debug("fiat_fx_provider: unsupported currency %s, returning fallback 1.0", cur)
        return 1.0, "unknown"

    now = time.monotonic()

    with _cache_lock:
        entry = _rate_cache.get(cur)

    if entry is not None:
        age = now - entry["fetched_at"]
        if age < CACHE_TTL_SECONDS:
            # Fresh hit
            return entry["rate"], entry["source"]
        if age < STALE_MAX_SECONDS:
            # Stale but acceptable — trigger background refresh if not already in progress
            _trigger_background_refresh()
            return entry["rate"], "cache_stale"

    # Cold start or fully expired cache — try a synchronous fetch first
    # If that fails (e.g. no network in test env), fall back to env/static
    _trigger_background_refresh()
    return _get_fallback_rate(cur)


def get_all_fiat_rates() -> Dict[str, Tuple[float, str]]:
    """Return a dict of {currency: (rate, source)} for all supported fiat currencies."""
    return {cur: get_zar_per_unit(cur) for cur in SUPPORTED_FIAT}


def get_rates_snapshot() -> Dict:
    """Return diagnostic snapshot including cache age, source, and rates."""
    now = time.monotonic()
    snapshot = {}
    with _cache_lock:
        for cur, entry in _rate_cache.items():
            snapshot[cur] = {
                "rate_zar_per_unit": entry["rate"],
                "source": entry["source"],
                "age_seconds": round(now - entry["fetched_at"], 1),
                "fresh": (now - entry["fetched_at"]) < CACHE_TTL_SECONDS,
                "stale": (now - entry["fetched_at"]) >= CACHE_TTL_SECONDS,
            }
    # Fill missing currencies with fallback info
    for cur in SUPPORTED_FIAT:
        if cur not in snapshot:
            rate, src = _get_fallback_rate(cur)
            snapshot[cur] = {
                "rate_zar_per_unit": rate,
                "source": src,
                "age_seconds": None,
                "fresh": False,
                "stale": True,
            }
    return {
        "rates": snapshot,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "stale_max_seconds": STALE_MAX_SECONDS,
    }


async def refresh_rates_async() -> Dict[str, float]:
    """Explicitly refresh fiat rates from provider (async).

    Returns dict of {currency: rate} for successfully fetched currencies.
    Called by background refresh trigger and optionally by startup.
    """
    rates, source = await _fetch_from_primary()
    if not rates:
        rates, source = await _fetch_from_fallback()

    if rates:
        now = time.monotonic()
        with _cache_lock:
            for cur, rate in rates.items():
                if cur in SUPPORTED_FIAT and rate > 0:
                    _rate_cache[cur] = {
                        "rate": rate,
                        "fetched_at": now,
                        "source": source,
                    }
        logger.info("fiat_fx_provider: rates refreshed from %s: %s", source, rates)
        return rates

    logger.warning("fiat_fx_provider: all providers failed, cache not updated")
    return {}


def force_update_rate(currency: str, rate: float, source: str = "manual_override") -> None:
    """Manually inject a rate into the cache.

    Useful for testing and operator overrides.
    """
    cur = str(currency or "").upper()
    if cur not in SUPPORTED_FIAT:
        raise ValueError(f"Unsupported fiat currency: {cur}")
    if rate <= 0:
        raise ValueError(f"Rate must be positive, got {rate}")
    with _cache_lock:
        _rate_cache[cur] = {
            "rate": float(rate),
            "fetched_at": time.monotonic(),
            "source": source,
        }
    logger.debug("fiat_fx_provider: manual rate injected %s=%.4f from %s", cur, rate, source)


def clear_cache() -> None:
    """Clear the rate cache (useful in tests)."""
    global _rate_cache
    with _cache_lock:
        _rate_cache = {}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_fallback_rate(currency: str) -> Tuple[float, str]:
    """Return (rate, source) from env var or static fallback."""
    rate = _FALLBACK_RATES.get(currency)
    if rate is not None and rate > 0:
        return rate, "env_fallback"
    return 1.0, "static_fallback"


def _trigger_background_refresh() -> None:
    """Fire-and-forget: start an async rate refresh in the background thread.

    Uses a simple lock flag to prevent multiple concurrent refreshes.
    """
    global _fetch_in_progress
    with _fetch_lock:
        if _fetch_in_progress:
            return
        _fetch_in_progress = True

    def _run_refresh():
        global _fetch_in_progress
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(refresh_rates_async())
            finally:
                loop.close()
        except Exception as exc:
            logger.warning("fiat_fx_provider background refresh error: %s", exc)
        finally:
            with _fetch_lock:
                _fetch_in_progress = False

    import threading as _threading
    t = _threading.Thread(target=_run_refresh, daemon=True, name="fiat-fx-refresh")
    t.start()


async def _fetch_from_primary() -> Tuple[Optional[Dict[str, float]], str]:
    """Fetch from open.er-api.com (primary, free, no key)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(_PRIMARY_URL)
            resp.raise_for_status()
            data = resp.json()
            # Response shape: {"rates": {"USD": 0.054, "GBP": 0.042, ...}} (ZAR base)
            # ZAR base → rates are 1/ZAR_per_unit, so we invert them
            raw_rates = data.get("rates", {})
            rates = {}
            for cur in SUPPORTED_FIAT:
                raw = raw_rates.get(cur)
                if raw and raw > 0:
                    # raw = units of *cur* per 1 ZAR → we want ZAR per 1 *cur*
                    rates[cur] = round(1.0 / float(raw), 6)
            return rates, "live_fiat_primary"
    except Exception as exc:
        logger.warning("fiat_fx_provider primary fetch failed: %s", exc)
        return None, "primary_failed"


async def _fetch_from_fallback() -> Tuple[Optional[Dict[str, float]], str]:
    """Fetch from exchangerate-api.com (fallback, free)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(_FALLBACK_URL)
            resp.raise_for_status()
            data = resp.json()
            raw_rates = data.get("rates", {})
            rates = {}
            for cur in SUPPORTED_FIAT:
                raw = raw_rates.get(cur)
                if raw and raw > 0:
                    rates[cur] = round(1.0 / float(raw), 6)
            return rates, "live_fiat_fallback"
    except Exception as exc:
        logger.warning("fiat_fx_provider fallback fetch failed: %s", exc)
        return None, "fallback_failed"
