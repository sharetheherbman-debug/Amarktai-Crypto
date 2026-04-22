"""
Feed Health API — Exchange Feed Health Status
=============================================
GET /api/system/feed-health

Returns per-exchange feed health from ExchangeFeedWatchdog + MarketStateCache.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from auth import get_current_user
from services.exchange_feed_watchdog import exchange_feed_watchdog
from services.market_state_cache import market_state_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/system/feed-health")
async def get_feed_health(user_id: str = Depends(get_current_user)):
    """Return per-exchange feed health snapshot.

    Response shape::

        {
            "luno": {
                "status": "fresh" | "stale" | "degraded" | "initializing",
                "age_seconds": 8.2,
                "consecutive_errors": 0,
                "last_error": null,
                "is_running": true,
                "watchdog_degraded": false,
                "symbols_tracked": 4,
                "cache_stats": { ... }
            },
            ...
        }
    """
    try:
        snapshot = exchange_feed_watchdog.get_health_snapshot()
        # Enrich with cache stats per exchange
        cache_stats = market_state_cache.get_stats()
        cache_by_exchange = {s["exchange"]: s for s in cache_stats.get("exchanges", [])}

        for exchange, data in snapshot.items():
            data["cache_stats"] = cache_by_exchange.get(exchange, {})

        return {
            "feeds": snapshot,
            "cache_config": {
                "ttl_seconds": cache_stats.get("ttl_seconds"),
                "stale_threshold_seconds": cache_stats.get("stale_threshold_seconds"),
                "max_symbols_per_exchange": cache_stats.get("max_symbols_per_exchange"),
            },
        }
    except Exception as exc:
        logger.error("get_feed_health error: %s", exc, exc_info=True)
        return {"feeds": {}, "error": str(exc)}
