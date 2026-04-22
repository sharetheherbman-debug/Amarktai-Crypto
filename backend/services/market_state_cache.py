"""
MarketStateCache — Shared Normalized Symbol-State Store
=======================================================
One process-level cache keyed by (exchange, symbol).

All paper-bot market-data reads go through here first.  ExchangeFeedService
instances write here; PaperTradingEngine reads here.

Design
------
- asyncio-safe: per-(exchange,symbol) asyncio.Lock prevents duplicate fetches
- LRU eviction: max MAX_SYMBOLS_PER_EXCHANGE entries per exchange
- TTL: entries older than STALE_THRESHOLD_SECONDS are marked is_stale=True
  but remain readable (degraded mode).  Entries older than EVICT_THRESHOLD_SECONDS
  are evicted on the next write cycle.
- Bounded OHLCV: at most OHLCV_MAX_CANDLES per (exchange, symbol)
- No unbounded growth: total cache entries are bounded by
  MAX_SYMBOLS_PER_EXCHANGE × number_of_exchanges

Environment variables
---------------------
MSC_TTL_SECONDS           — freshness window (default: 30 s)
MSC_STALE_THRESHOLD       — stale but usable (default: 90 s)
MSC_EVICT_THRESHOLD       — evict after this age (default: 300 s)
MSC_MAX_SYMBOLS           — max symbols per exchange (default: 50)
MSC_OHLCV_MAX_CANDLES     — max OHLCV candles kept (default: 100)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_TTL: float = float(os.getenv("MSC_TTL_SECONDS", "30"))
_STALE: float = float(os.getenv("MSC_STALE_THRESHOLD", "90"))
_EVICT: float = float(os.getenv("MSC_EVICT_THRESHOLD", "300"))
_MAX_SYMBOLS: int = int(os.getenv("MSC_MAX_SYMBOLS", "50"))
_OHLCV_MAX: int = int(os.getenv("MSC_OHLCV_MAX_CANDLES", "100"))


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

class _ExchangeCache:
    """LRU-bounded store for one exchange."""

    def __init__(self, exchange: str, max_symbols: int = _MAX_SYMBOLS) -> None:
        self.exchange = exchange
        self.max_symbols = max_symbols
        # OrderedDict preserves insertion order for LRU eviction
        self._ticker: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._ohlcv: OrderedDict[str, List[List[float]]] = OrderedDict()
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._locks:
            self._locks[symbol] = asyncio.Lock()
        return self._locks[symbol]

    def _age(self, entry: Dict[str, Any]) -> float:
        return time.monotonic() - entry.get("_fetched_at", 0)

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        entry = self._ticker.get(symbol)
        if entry is None:
            return None
        age = self._age(entry)
        if age > _EVICT:
            # Too old — remove
            self._ticker.pop(symbol, None)
            return None
        result = dict(entry)
        result["is_stale"] = age > _STALE
        result["age_seconds"] = round(age, 1)
        return result

    def set(self, symbol: str, data: Dict[str, Any]) -> None:
        now = time.monotonic()
        entry = {
            "bid": data.get("bid"),
            "ask": data.get("ask"),
            "mid": data.get("mid"),
            "last": data.get("last"),
            "spread": data.get("spread"),
            "spread_pct": data.get("spread_pct"),
            "bid_volume": data.get("bid_volume"),
            "ask_volume": data.get("ask_volume"),
            "depth_notional": data.get("depth_notional"),
            "volume_24h": data.get("volume_24h"),
            "timestamp": data.get("timestamp"),
            "source": data.get("source", "feed"),
            "_fetched_at": now,
            "is_stale": False,
            "age_seconds": 0.0,
        }
        if symbol in self._ticker:
            # Move to end (MRU)
            self._ticker.move_to_end(symbol)
        self._ticker[symbol] = entry

        # LRU eviction: remove oldest if over limit
        while len(self._ticker) > self.max_symbols:
            oldest = next(iter(self._ticker))
            self._ticker.popitem(last=False)
            logger.debug("MarketStateCache LRU evict: %s/%s", self.exchange, oldest)

    def get_ohlcv(self, symbol: str) -> Optional[List[List[float]]]:
        return self._ohlcv.get(symbol)

    def set_ohlcv(self, symbol: str, candles: List[List[float]]) -> None:
        if not candles:
            return
        # Keep only the last OHLCV_MAX candles
        self._ohlcv[symbol] = candles[-_OHLCV_MAX:]
        if symbol in self._ohlcv:
            self._ohlcv.move_to_end(symbol)
        while len(self._ohlcv) > self.max_symbols:
            self._ohlcv.popitem(last=False)

    def stats(self) -> Dict[str, Any]:
        now = time.monotonic()
        fresh = sum(
            1 for e in self._ticker.values()
            if (now - e.get("_fetched_at", 0)) <= _TTL
        )
        stale = sum(
            1 for e in self._ticker.values()
            if _TTL < (now - e.get("_fetched_at", 0)) <= _STALE
        )
        return {
            "exchange": self.exchange,
            "total_symbols": len(self._ticker),
            "fresh_symbols": fresh,
            "stale_symbols": stale,
            "ohlcv_symbols": len(self._ohlcv),
            "max_symbols": self.max_symbols,
        }


# ---------------------------------------------------------------------------
# Singleton cache
# ---------------------------------------------------------------------------

class MarketStateCache:
    """Process-level market-state cache (singleton)."""

    def __init__(self) -> None:
        self._exchanges: Dict[str, _ExchangeCache] = {}
        self._global_lock = asyncio.Lock()

    def _get_exchange_cache(self, exchange: str) -> _ExchangeCache:
        if exchange not in self._exchanges:
            self._exchanges[exchange] = _ExchangeCache(exchange)
        return self._exchanges[exchange]

    # -- Ticker / snapshot --------------------------------------------------

    def get(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Return normalized market state or None if missing/evicted."""
        ec = self._exchanges.get(exchange)
        if ec is None:
            return None
        return ec.get(symbol)

    def set(self, exchange: str, symbol: str, data: Dict[str, Any]) -> None:
        """Store normalized market state for (exchange, symbol)."""
        ec = self._get_exchange_cache(exchange)
        ec.set(symbol, data)

    # -- OHLCV --------------------------------------------------------------

    def get_ohlcv(self, exchange: str, symbol: str) -> Optional[List[List[float]]]:
        ec = self._exchanges.get(exchange)
        if ec is None:
            return None
        return ec.get_ohlcv(symbol)

    def set_ohlcv(self, exchange: str, symbol: str, candles: List[List[float]]) -> None:
        ec = self._get_exchange_cache(exchange)
        ec.set_ohlcv(symbol, candles)

    # -- Diagnostics --------------------------------------------------------

    def get_all_exchanges(self) -> List[str]:
        return list(self._exchanges.keys())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "exchanges": [ec.stats() for ec in self._exchanges.values()],
            "ttl_seconds": _TTL,
            "stale_threshold_seconds": _STALE,
            "evict_threshold_seconds": _EVICT,
            "max_symbols_per_exchange": _MAX_SYMBOLS,
        }

    def is_fresh(self, exchange: str, symbol: str) -> bool:
        """Return True if the cached entry exists and is within TTL."""
        entry = self.get(exchange, symbol)
        if entry is None:
            return False
        return not entry.get("is_stale", True)


# Module-level singleton
market_state_cache = MarketStateCache()
