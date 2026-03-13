"""
Luno Ticker Cache — shared TTL cache for public Luno market data.

Prevents request storms to Luno's public API that cause HTTP 429 errors.
All callers (market_api, overview_service, scheduler, diagnostics) should
use get_ticker() instead of making raw HTTP calls to api.luno.com.

Cache behaviour
---------------
- Fresh fetch is performed at most once per pair per TTL window.
- On HTTP 429, the cached value is extended (soft TTL) and 429 is logged.
- On any other network error, cached value is returned if < STALE_FALLBACK_SECONDS old.
- Logs distinguish cache HIT vs network FETCH on every call.

Environment variables
---------------------
LUNO_TICKER_TTL_SECONDS   — default 20 s  (how often we re-fetch)
LUNO_TICKER_STALE_SECONDS — default 120 s (how long to serve stale on error)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_TTL: float = float(os.getenv("LUNO_TICKER_TTL_SECONDS", "20"))
_STALE_FALLBACK: float = float(os.getenv("LUNO_TICKER_STALE_SECONDS", "120"))

# ── In-memory cache ───────────────────────────────────────────────────────────
# { pair: {"data": {...}, "fetched_at": float, "source": str} }
_cache: Dict[str, Dict[str, Any]] = {}
_fetch_locks: Dict[str, asyncio.Lock] = {}


def _get_lock(pair: str) -> asyncio.Lock:
    """One lock per pair prevents parallel duplicate fetches."""
    if pair not in _fetch_locks:
        _fetch_locks[pair] = asyncio.Lock()
    return _fetch_locks[pair]


def _is_fresh(entry: Dict[str, Any]) -> bool:
    return (time.monotonic() - entry["fetched_at"]) < _TTL


def _is_within_stale_window(entry: Dict[str, Any]) -> bool:
    return (time.monotonic() - entry["fetched_at"]) < _STALE_FALLBACK


async def get_ticker(
    pair: str,
    *,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return ticker data for *pair* from cache or a fresh Luno fetch.

    Parameters
    ----------
    pair : str
        Luno pair code, e.g. ``"XBTZAR"``.
    api_key / api_secret : str, optional
        Luno credentials.  If omitted, the public endpoint is used.

    Returns
    -------
    dict or None
        ``{"last_trade": float, "bid": float, "ask": float,
           "rolling_24_hour_volume": float,
           "source": "cache" | "luno_public" | "luno_authenticated",
           "fetched_at": float}``
        ``None`` if no data is available at all.
    """
    existing = _cache.get(pair)

    # ── Fast path: still fresh ─────────────────────────────────────────────
    if existing and _is_fresh(existing):
        logger.debug("Luno ticker cache HIT for %s (age %.1fs)", pair,
                     time.monotonic() - existing["fetched_at"])
        return {**existing["data"], "source": "cache", "fetched_at": existing["fetched_at"]}

    # ── Slow path: need a network fetch (one waiter per pair) ──────────────
    async with _get_lock(pair):
        # Re-check inside the lock in case another waiter just populated it.
        existing = _cache.get(pair)
        if existing and _is_fresh(existing):
            logger.debug("Luno ticker cache HIT (post-lock) for %s", pair)
            return {**existing["data"], "source": "cache", "fetched_at": existing["fetched_at"]}

        try:
            data = await _fetch_from_luno(pair, api_key=api_key, api_secret=api_secret)
            _cache[pair] = {"data": data, "fetched_at": time.monotonic()}
            logger.info("Luno ticker FETCH for %s — price=%s", pair,
                        data.get("last_trade"))
            return {**data, "fetched_at": _cache[pair]["fetched_at"]}

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning(
                    "Luno ticker 429 for %s — serving stale cache (age %.0fs)",
                    pair,
                    time.monotonic() - existing["fetched_at"] if existing else -1,
                )
                if existing and _is_within_stale_window(existing):
                    # Backdate the entry by half a TTL so the next call checks again
                    # sooner (rather than waiting a full TTL), reducing the risk of
                    # serving very stale data while still respecting the 429 backoff.
                    _cache[pair]["fetched_at"] = time.monotonic() - (_TTL / 2)
                    return {**existing["data"], "source": "cache_429_fallback",
                            "fetched_at": _cache[pair]["fetched_at"]}
            else:
                logger.error("Luno ticker HTTP %d for %s: %s",
                             exc.response.status_code, pair, exc)
            if existing and _is_within_stale_window(existing):
                return {**existing["data"], "source": "cache_stale_fallback",
                        "fetched_at": existing["fetched_at"]}
            return None

        except Exception as exc:
            logger.error("Luno ticker fetch error for %s: %s", pair, exc)
            if existing and _is_within_stale_window(existing):
                return {**existing["data"], "source": "cache_stale_fallback",
                        "fetched_at": existing["fetched_at"]}
            return None


async def _fetch_from_luno(
    pair: str,
    *,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Raw HTTP call to Luno ticker endpoint.  Raises on HTTP error."""
    url = f"https://api.luno.com/api/1/ticker?pair={pair}"
    auth = None
    source = "luno_public"
    if api_key and api_secret:
        auth = httpx.BasicAuth(api_key, api_secret)
        source = "luno_authenticated"

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        data = response.json()
        return {
            "last_trade": float(data.get("last_trade", 0)),
            "bid": float(data.get("bid", 0)),
            "ask": float(data.get("ask", 0)),
            "rolling_24_hour_volume": float(data.get("rolling_24_hour_volume", 0)),
            "source": source,
        }


def clear_cache(pair: Optional[str] = None) -> None:
    """Remove cached entry for *pair* (or entire cache if pair is None).

    Useful in tests and manual cache invalidation.
    """
    global _cache
    if pair is None:
        _cache = {}
        logger.debug("Luno ticker cache cleared (all pairs)")
    elif pair in _cache:
        del _cache[pair]
        logger.debug("Luno ticker cache cleared for %s", pair)


def cache_stats() -> Dict[str, Any]:
    """Return diagnostic snapshot of the cache state."""
    now = time.monotonic()
    return {
        pair: {
            "age_seconds": round(now - entry["fetched_at"], 1),
            "fresh": _is_fresh(entry),
            "last_trade": entry["data"].get("last_trade"),
        }
        for pair, entry in _cache.items()
    }
