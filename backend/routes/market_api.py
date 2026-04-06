"""
Market API - Live market prices for supported pairs
Provides real-time prices for BTC/ZAR, ETH/ZAR, XRP/ZAR from Luno
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import logging
import httpx

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/prices")
async def get_market_prices(user_id: str = Depends(get_current_user)):
    """Get live market prices for BTC/ZAR, ETH/ZAR, XRP/ZAR
    
    Uses Luno API (authenticated if keys available, public otherwise)
    
    Returns:
        Dict with prices for each pair including:
        - price: Current price
        - change_24h: 24h change percentage (fallback to most recent snapshot)
        - change_pct: Alias for change_24h
        - timestamp: When price was fetched
        - source: "luno_authenticated", "luno_public", or "unavailable"
    """
    try:
        # Try to get user's Luno API keys
        api_key = await db.api_keys_collection.find_one(
            {"user_id": user_id, "provider": "luno"},
            {"_id": 0}
        )
        
        prices = {}
        pairs = ["XBTZAR", "ETHZAR", "XRPZAR"]  # Luno pair format
        display_pairs = ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR"]
        
        for luno_pair, display_pair in zip(pairs, display_pairs):
            try:
                price_data = await _fetch_luno_ticker(luno_pair, display_pair, api_key)
                prices[display_pair] = price_data
            except Exception as e:
                logger.warning(f"Failed to fetch {display_pair} price: {e}")
                prices[display_pair] = {
                    "price": 0.0,
                    "change_24h": 0.0,
                    "change_pct": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "unavailable"
                }
        
        return {
            "prices": prices,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get market prices error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_luno_ticker(pair: str, display_pair: str, api_key: Optional[Dict] = None) -> Dict:
    """Fetch ticker data from Luno API
    
    Args:
        pair: Trading pair in Luno format (e.g., XBTZAR)
        api_key: Optional API key dict with api_key and api_secret
        
    Returns:
        Dict with price, change_24h, change_pct, timestamp, source
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Use public ticker endpoint
            url = f"https://api.luno.com/api/1/ticker?pair={pair}"
            
            # Add authentication if keys available
            auth = None
            source = "luno_public"
            if api_key and api_key.get("api_key") and api_key.get("api_secret"):
                auth = httpx.BasicAuth(api_key["api_key"], api_key["api_secret"])
                source = "luno_authenticated"
            
            response = await client.get(url, auth=auth)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse response
            last_trade = float(data.get("last_trade", 0))
            
            from services.price_snapshot_service import record_snapshot

            change_pct, _window = await record_snapshot(display_pair, last_trade)
            
            return {
                "price": round(last_trade, 2),
                "change_24h": round(change_pct, 2),
                "change_pct": round(change_pct, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "volume_24h": float(data.get("rolling_24_hour_volume", 0)),
                "bid": float(data.get("bid", 0)),
                "ask": float(data.get("ask", 0))
            }
            
    except httpx.HTTPError as e:
        logger.error(f"Luno API error for {pair}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching Luno ticker for {pair}: {e}")
        raise


# Cache for /api/market/brief
import time as _time
_brief_cache: dict = {}
_brief_cache_at: float = 0.0
_BRIEF_TTL = 90  # seconds


@router.get("/brief")
async def get_market_brief(user_id: str = Depends(get_current_user)):
    """
    GET /api/market/brief

    CoinStats-based market intelligence summary, cached for 90 seconds.

    Returns:
      - mood: positive | negative | neutral
      - brief: Latest headline or market summary
      - top_risk: Risk category detected in headlines (or "none")
      - confidence: Confidence description
      - source: "CoinStats"
      - last_updated: ISO timestamp of last CoinStats fetch
    """
    global _brief_cache, _brief_cache_at

    age = _time.monotonic() - _brief_cache_at
    if not _brief_cache or age > _BRIEF_TTL:
        try:
            from services.market_intelligence_service import get_latest_intelligence
            data = await get_latest_intelligence()
            _brief_cache = {
                "mood": data.get("mood", "neutral"),
                "brief": data.get("what_happened", "No data yet"),
                "top_risk": data.get("top_risk", "none"),
                "confidence": data.get("confidence", "Unknown"),
                "what_amarktai_is_doing": data.get("what_amarktai_is_doing", ""),
                "source": data.get("source", "CoinStats"),
                "last_updated": data.get("updated_at"),
                "fetch_status": data.get("fetch_status", "ok"),
                "block_reason": data.get("block_reason"),
            }
            _brief_cache_at = _time.monotonic()
        except Exception as e:
            logger.error(f"Market brief fetch error: {e}")
            if not _brief_cache:
                _brief_cache = {
                    "mood": "neutral", "brief": "Market intelligence unavailable",
                    "top_risk": "none", "confidence": "Unknown",
                    "what_amarktai_is_doing": "",
                    "source": "CoinStats", "last_updated": None,
                }

    return _brief_cache


@router.get("/intelligence")
async def get_market_intelligence(user_id: str = Depends(get_current_user)):
    """
    GET /api/market/intelligence

    Cached market intelligence brief derived from the CoinStats news pipeline.
    Returns the most recently computed brief including mood, top headlines, and
    an actionable block_reason when data is unavailable.

    Returns:
      - success: bool
      - source: "CoinStats"
      - mood: positive | negative | neutral
      - why_it_matters: plain-English impact description
      - what_amarktai_is_doing: platform response description
      - last_updated: ISO timestamp of last successful update (or null)
      - articles_count: number of articles in the last brief
      - top_headlines: list of up to 5 top article titles
      - block_reason: reason data is missing (or null when data is ok)
      - fetch_status: ok | no_articles | key_missing | rate_limited | invalid_key | error | pending
    """
    try:
        from services.market_intelligence_service import get_latest_intelligence
        data = await get_latest_intelligence(user_id=user_id)

        top_headlines = []
        for art in (data.get("top_articles") or [])[:5]:
            title = art.get("title") if isinstance(art, dict) else str(art)
            if title:
                top_headlines.append(title)

        return {
            "success": True,
            "source": data.get("source", "CoinStats"),
            "mood": data.get("mood", "neutral"),
            "why_it_matters": data.get("why_it_matters", ""),
            "what_amarktai_is_doing": data.get("what_amarktai_is_doing", ""),
            "last_updated": data.get("updated_at"),
            "articles_count": data.get("headlines_count", 0),
            "top_headlines": top_headlines,
            "block_reason": data.get("block_reason"),
            "fetch_status": data.get("fetch_status", "pending"),
        }
    except Exception as e:
        logger.error(f"Market intelligence endpoint error: {e}")
        return {
            "success": False,
            "source": "CoinStats",
            "mood": "neutral",
            "why_it_matters": "",
            "what_amarktai_is_doing": "",
            "last_updated": None,
            "articles_count": 0,
            "top_headlines": [],
            "block_reason": f"Internal error: {str(e)[:200]}",
            "fetch_status": "error",
        }
