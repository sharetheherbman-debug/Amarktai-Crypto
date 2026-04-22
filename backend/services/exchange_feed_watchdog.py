"""
ExchangeFeedWatchdog — Infrastructure-Level Feed Health Monitor
===============================================================
Monitors ExchangeFeedService instances and the MarketStateCache for stale data.
Marks exchanges as degraded when their feed becomes too old.

This is DISTINCT from strategy discipline (adaptive stand-down, regime
stand-down).  This is RUNTIME self-healing: feed reconnection, exchange-scoped
isolation, degraded-mode reporting.

Design
------
- Runs as a background asyncio task, checking every CHECK_INTERVAL_SECONDS.
- Per-exchange degraded flag: one sick exchange does NOT affect others.
- Clears degraded state only when feed is genuinely healthy again.
- Exposes get_health_snapshot() for the /api/system/feed-health endpoint.

Environment variables
---------------------
WATCHDOG_CHECK_INTERVAL   — how often to check (default: 15 s)
WATCHDOG_STALE_THRESHOLD  — seconds before marking degraded (default: 90 s)
WATCHDOG_RECOVER_THRESHOLD — seconds fresh before clearing degraded (default: 30 s)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CHECK_INTERVAL: float = float(os.getenv("WATCHDOG_CHECK_INTERVAL", "15"))
_STALE_THRESHOLD: float = float(os.getenv("WATCHDOG_STALE_THRESHOLD", "90"))
_RECOVER_THRESHOLD: float = float(os.getenv("WATCHDOG_RECOVER_THRESHOLD", "30"))


class ExchangeFeedWatchdog:
    """Monitors all ExchangeFeedService instances for feed health."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        # exchange → float (monotonic timestamp of last confirmed fresh state)
        self._last_healthy_at: Dict[str, float] = {}
        # exchange → bool (degraded state)
        self._degraded: Dict[str, bool] = {}

    # -- Lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="feed_watchdog")
        logger.info("ExchangeFeedWatchdog started (interval=%.0fs)", _CHECK_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ExchangeFeedWatchdog stopped")

    # -- Main loop ----------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._check_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ExchangeFeedWatchdog check error: %s", exc)
            await asyncio.sleep(_CHECK_INTERVAL)

    async def _check_all(self) -> None:
        try:
            from services.exchange_feed_service import _feed_services
            from services.market_state_cache import market_state_cache
        except ImportError:
            return

        now = time.monotonic()

        for exchange, svc in list(_feed_services.items()):
            # Determine freshness from the service's last_success_at
            age: Optional[float] = None
            if svc.last_success_at is not None:
                age = now - svc.last_success_at

            # Also check cache staleness as a second signal
            cache_fresh = any(
                not (market_state_cache.get(exchange, sym) or {}).get("is_stale", True)
                for sym in svc.symbols[:3]  # sample first 3 symbols
            ) if svc.symbols else False

            # Mark degraded when:
            #  - service reports degraded internally, OR
            #  - last success was too long ago
            is_feed_stale = (age is None or age > _STALE_THRESHOLD) and not cache_fresh

            was_degraded = self._degraded.get(exchange, False)

            if is_feed_stale or svc.is_degraded:
                if not was_degraded:
                    logger.warning(
                        "ExchangeFeedWatchdog: %s feed DEGRADED (age=%.0fs, svc_degraded=%s)",
                        exchange, age or -1, svc.is_degraded,
                    )
                self._degraded[exchange] = True
                self._last_healthy_at.pop(exchange, None)
            else:
                # Feed is healthy — track consecutive healthy duration
                if exchange not in self._last_healthy_at:
                    self._last_healthy_at[exchange] = now

                healthy_for = now - self._last_healthy_at[exchange]
                if was_degraded and healthy_for >= _RECOVER_THRESHOLD:
                    logger.info(
                        "ExchangeFeedWatchdog: %s recovered (healthy for %.0fs)",
                        exchange, healthy_for,
                    )
                    self._degraded[exchange] = False

    # -- Public API ---------------------------------------------------------

    def is_degraded(self, exchange: str) -> bool:
        """Return True if the feed for *exchange* is degraded."""
        return self._degraded.get(exchange, False)

    def get_health_snapshot(self) -> Dict[str, Any]:
        """Return per-exchange health summary for the API endpoint."""
        try:
            from services.exchange_feed_service import _feed_services
        except ImportError:
            return {}

        snapshot: Dict[str, Any] = {}
        for exchange, svc in _feed_services.items():
            h = svc.health()
            h["watchdog_degraded"] = self._degraded.get(exchange, False)
            snapshot[exchange] = h

        return snapshot


# Module-level singleton
exchange_feed_watchdog = ExchangeFeedWatchdog()
