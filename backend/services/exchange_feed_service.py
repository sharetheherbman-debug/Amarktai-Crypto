"""
ExchangeFeedService — Shared Per-Exchange Market-Data Background Service
=======================================================================
One instance per exchange.  Runs as an asyncio background task; writes
normalized market state into MarketStateCache.

This replaces per-bot CCXT polling.  Bots read from MarketStateCache;
only ExchangeFeedService calls the exchange APIs.

Supported exchanges (initial)
-----------------------------
- luno    — public REST polling (ticker + order book top-5)
- binance — public REST polling

Additional exchanges can be added by extending EXCHANGE_CONFIGS.

Environment variables (per exchange)
-------------------------------------
FEED_<EXCHANGE>_INTERVAL_SECONDS   — poll interval (default: 20 for luno, 15 for binance)
FEED_<EXCHANGE>_ENABLED             — set to "false" to disable a feed (default: true)
FEED_OHLCV_ENABLED                  — set to "false" to skip OHLCV fetching (default: true)
FEED_MAX_BACKOFF_SECONDS            — max reconnect backoff (default: 300)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt

from services.market_state_cache import market_state_cache
from services.symbol_universe import DEFAULT_SYMBOL_UNIVERSE, SCALPER_SYMBOL_UNIVERSE

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_FEED_OHLCV = os.getenv("FEED_OHLCV_ENABLED", "true").lower() == "true"
_MAX_BACKOFF: float = float(os.getenv("FEED_MAX_BACKOFF_SECONDS", "300"))
_OHLCV_TIMEFRAME = "5m"
_OHLCV_LIMIT = 50

# Default symbols to track per exchange (drawn from the universe configs)
_DEFAULT_LUNO_SYMBOLS = list(
    dict.fromkeys(
        DEFAULT_SYMBOL_UNIVERSE.get("luno", ["BTC/ZAR"])
        + SCALPER_SYMBOL_UNIVERSE.get("luno", [])
    )
)
_DEFAULT_BINANCE_SYMBOLS = list(
    dict.fromkeys(
        DEFAULT_SYMBOL_UNIVERSE.get("binance", ["BTC/USDT"])[:10]
        + SCALPER_SYMBOL_UNIVERSE.get("binance", [])
    )
)

EXCHANGE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "luno": {
        "poll_interval": float(os.getenv("FEED_LUNO_INTERVAL_SECONDS", "20")),
        "enabled": os.getenv("FEED_LUNO_ENABLED", "true").lower() == "true",
        "symbols": _DEFAULT_LUNO_SYMBOLS,
        "ohlcv_supported": True,
    },
    "binance": {
        "poll_interval": float(os.getenv("FEED_BINANCE_INTERVAL_SECONDS", "15")),
        "enabled": os.getenv("FEED_BINANCE_ENABLED", "true").lower() == "true",
        "symbols": _DEFAULT_BINANCE_SYMBOLS,
        "ohlcv_supported": True,
    },
}

# ── Global registry of running feed services ─────────────────────────────────
_feed_services: Dict[str, "ExchangeFeedService"] = {}


# ---------------------------------------------------------------------------
# CCXT factory helpers
# ---------------------------------------------------------------------------

def _make_luno() -> ccxt.Exchange:
    return ccxt.luno(
        {"enableRateLimit": True, "timeout": 15000, "apiKey": None, "secret": None}
    )


def _make_binance() -> ccxt.Exchange:
    return ccxt.binance(
        {
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
            "apiKey": None,
            "secret": None,
        }
    )


_CCXT_FACTORIES = {
    "luno": _make_luno,
    "binance": _make_binance,
}


# ---------------------------------------------------------------------------
# ExchangeFeedService
# ---------------------------------------------------------------------------

class ExchangeFeedService:
    """Background feed for one exchange.

    Usage::

        svc = ExchangeFeedService("luno")
        await svc.start()
        ...
        await svc.stop()
    """

    def __init__(
        self,
        exchange: str,
        symbols: Optional[List[str]] = None,
        poll_interval: Optional[float] = None,
    ) -> None:
        cfg = EXCHANGE_CONFIGS.get(exchange, {})
        self.exchange = exchange
        self.symbols: List[str] = symbols or cfg.get("symbols", [])
        self.poll_interval: float = poll_interval or cfg.get("poll_interval", 20.0)
        self.ohlcv_supported: bool = cfg.get("ohlcv_supported", True)

        self._task: Optional[asyncio.Task] = None
        self._ccxt: Optional[ccxt.Exchange] = None
        self._running = False

        # Health tracking
        self.last_success_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.consecutive_errors: int = 0
        self._backoff: float = 5.0  # current backoff seconds
        self.is_degraded: bool = False

    # -- Lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name=f"feed_{self.exchange}")
        logger.info("ExchangeFeedService[%s] started (%d symbols)", self.exchange, len(self.symbols))

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ccxt:
            try:
                await self._ccxt.close()
            except Exception:
                pass
        logger.info("ExchangeFeedService[%s] stopped", self.exchange)

    # -- Main loop ----------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main background polling loop.  Never raises; reconnects on error."""
        while self._running:
            try:
                await self._ensure_connection()
                await self._poll_all_symbols()

                self.consecutive_errors = 0
                self._backoff = 5.0
                self.last_success_at = time.monotonic()
                if self.is_degraded:
                    self.is_degraded = False
                    logger.info(
                        "ExchangeFeedService[%s] recovered — feed is fresh", self.exchange
                    )

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.consecutive_errors += 1
                self.last_error = str(exc)
                if self.consecutive_errors >= 3:
                    self.is_degraded = True
                logger.warning(
                    "ExchangeFeedService[%s] error #%d: %s — retrying in %.0fs",
                    self.exchange, self.consecutive_errors, exc, self._backoff,
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _MAX_BACKOFF)
                # Reset CCXT connection so next iteration gets a fresh handle
                await self._close_connection()

    async def _ensure_connection(self) -> None:
        if self._ccxt is not None:
            return
        factory = _CCXT_FACTORIES.get(self.exchange)
        if factory is None:
            raise RuntimeError(f"No CCXT factory for exchange '{self.exchange}'")
        self._ccxt = factory()
        logger.debug("ExchangeFeedService[%s] CCXT connection opened", self.exchange)

    async def _close_connection(self) -> None:
        if self._ccxt:
            try:
                await self._ccxt.close()
            except Exception:
                pass
            self._ccxt = None

    # -- Market-data fetch --------------------------------------------------

    async def _poll_all_symbols(self) -> None:
        """Fetch ticker (and optionally OHLCV) for all tracked symbols."""
        if not self.symbols:
            return

        for symbol in self.symbols:
            if not self._running:
                return
            try:
                await self._fetch_symbol(symbol)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(
                    "ExchangeFeedService[%s] symbol %s fetch failed: %s",
                    self.exchange, symbol, exc,
                )
                # Symbol failure should not abort the rest of the poll cycle.

    async def _fetch_symbol(self, symbol: str) -> None:
        """Fetch ticker + order book for one symbol and write to cache."""
        assert self._ccxt is not None

        timestamp = datetime.now(timezone.utc).isoformat()
        bid = ask = mid = last = None
        bid_volume = ask_volume = depth_notional = volume_24h = None
        source = "ticker"

        # 1) Try order book (best bid/ask accuracy)
        try:
            ob = await asyncio.wait_for(
                self._ccxt.fetch_order_book(symbol, limit=5), timeout=8.0
            )
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and asks:
                bid = float(bids[0][0])
                ask = float(asks[0][0])
                mid = (bid + ask) / 2.0
                bid_volume = sum(level[1] for level in bids[:5])
                ask_volume = sum(level[1] for level in asks[:5])
                depth_notional = sum(p * q for p, q in (bids[:5] + asks[:5]))
                source = "order_book"
        except Exception:
            pass

        # 2) Fall back to ticker if order book failed
        if mid is None:
            ticker = await asyncio.wait_for(
                self._ccxt.fetch_ticker(symbol), timeout=8.0
            )
            bid = bid or ticker.get("bid")
            ask = ask or ticker.get("ask")
            last = ticker.get("last") or ticker.get("close")
            volume_24h = ticker.get("baseVolume")
            if bid and ask:
                mid = (float(bid) + float(ask)) / 2.0
            elif last:
                mid = float(last)
            source = "ticker"

        if mid is None:
            return  # No usable price — skip

        bid = float(bid) if bid is not None else mid
        ask = float(ask) if ask is not None else mid
        last = float(last) if last is not None else mid
        spread = max(ask - bid, 0.0)
        spread_pct = (spread / mid * 100.0) if mid else 0.0

        market_state_cache.set(
            self.exchange,
            symbol,
            {
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "spread": spread,
                "spread_pct": round(spread_pct, 4),
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "depth_notional": depth_notional,
                "volume_24h": volume_24h,
                "timestamp": timestamp,
                "source": source,
            },
        )

        # 3) Optionally fetch OHLCV
        if _FEED_OHLCV and self.ohlcv_supported:
            try:
                ohlcv = await asyncio.wait_for(
                    self._ccxt.fetch_ohlcv(symbol, _OHLCV_TIMEFRAME, limit=_OHLCV_LIMIT),
                    timeout=10.0,
                )
                if ohlcv:
                    market_state_cache.set_ohlcv(self.exchange, symbol, ohlcv)
            except Exception:
                pass  # OHLCV is bonus data; failure is non-fatal

    # -- Status -------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        age: Optional[float] = None
        if self.last_success_at is not None:
            age = round(time.monotonic() - self.last_success_at, 1)

        status = "fresh"
        if self.is_degraded:
            status = "degraded"
        elif age is None:
            status = "initializing"
        elif age > 90:
            status = "stale"

        return {
            "exchange": self.exchange,
            "status": status,
            "age_seconds": age,
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "is_running": self._running and (self._task is not None and not self._task.done()),
            "symbols_tracked": len(self.symbols),
        }


# ---------------------------------------------------------------------------
# Public API — module-level helpers
# ---------------------------------------------------------------------------

def get_feed_service(exchange: str) -> Optional[ExchangeFeedService]:
    return _feed_services.get(exchange)


async def start_feed_services(exchanges: Optional[List[str]] = None) -> None:
    """Start feed services for the given exchanges (default: luno + binance)."""
    targets = exchanges or ["luno", "binance"]
    for exch in targets:
        cfg = EXCHANGE_CONFIGS.get(exch, {})
        if not cfg.get("enabled", True):
            logger.info("ExchangeFeedService[%s] disabled via config", exch)
            continue
        if exch not in _feed_services:
            svc = ExchangeFeedService(exch)
            _feed_services[exch] = svc
        try:
            await _feed_services[exch].start()
        except Exception as exc:
            logger.error(
                "ExchangeFeedService[%s] failed to start (non-fatal): %s", exch, exc
            )


async def stop_feed_services() -> None:
    """Gracefully stop all running feed services."""
    for exch, svc in list(_feed_services.items()):
        try:
            await svc.stop()
        except Exception as exc:
            logger.warning("ExchangeFeedService[%s] stop error: %s", exch, exc)
