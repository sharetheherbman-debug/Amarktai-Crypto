"""
Market API - Live market prices for supported pairs
Provides real-time prices for BTC/ZAR, ETH/ZAR, XRP/ZAR from Luno

Uses a shared TTL cache (services.luno_ticker_cache) to prevent request
storms and HTTP 429 errors when multiple subsystems poll the same ticker.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional, Dict
import logging

from auth import get_current_user
import database as db
from services import luno_ticker_cache as _ticker_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/prices")
async def get_market_prices(user_id: str = Depends(get_current_user)):
    """Get live market prices for BTC/ZAR, ETH/ZAR, XRP/ZAR

    Uses Luno API via shared TTL cache (authenticated if keys available).

    Returns:
        Dict with prices for each pair including:
        - price: Current price
        - change_24h: 24h change percentage (fallback to most recent snapshot)
        - change_pct: Alias for change_24h
        - timestamp: When price was fetched
        - source: "luno_authenticated", "luno_public", "cache", or "unavailable"
    """
    try:
        # Try to get user's Luno API keys for authenticated requests
        api_key_doc = await db.api_keys_collection.find_one(
            {"user_id": user_id, "provider": "luno"},
            {"_id": 0}
        )
        ak = api_key_doc.get("api_key") if api_key_doc else None
        secret = api_key_doc.get("api_secret") if api_key_doc else None

        prices = {}
        pairs = ["XBTZAR", "ETHZAR", "XRPZAR"]
        display_pairs = ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR"]

        for luno_pair, display_pair in zip(pairs, display_pairs):
            try:
                price_data = await _build_price_entry(luno_pair, display_pair, ak, secret)
                prices[display_pair] = price_data
            except Exception as e:
                logger.warning(f"Failed to fetch {display_pair} price: {e}")
                prices[display_pair] = {
                    "price": 0.0,
                    "change_24h": 0.0,
                    "change_pct": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "unavailable",
                }

        return {
            "prices": prices,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cache_stats": _ticker_cache.cache_stats(),
        }

    except Exception as e:
        logger.error(f"Get market prices error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _build_price_entry(
    pair: str,
    display_pair: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> Dict:
    """Fetch ticker via cache and build the canonical price entry dict."""
    ticker = await _ticker_cache.get_ticker(pair, api_key=api_key, api_secret=api_secret)
    if ticker is None:
        raise RuntimeError(f"No ticker data for {pair}")

    last_trade = ticker.get("last_trade", 0.0)
    from services.price_snapshot_service import record_snapshot
    change_pct, _window = await record_snapshot(display_pair, last_trade)

    return {
        "price": round(last_trade, 2),
        "change_24h": round(change_pct, 2),
        "change_pct": round(change_pct, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": ticker.get("source", "unknown"),
        "volume_24h": float(ticker.get("rolling_24_hour_volume", 0)),
        "bid": float(ticker.get("bid", 0)),
        "ask": float(ticker.get("ask", 0)),
    }
