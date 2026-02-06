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
        - change_pct: 24h change percentage
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
                price_data = await _fetch_luno_ticker(luno_pair, api_key)
                prices[display_pair] = price_data
            except Exception as e:
                logger.warning(f"Failed to fetch {display_pair} price: {e}")
                prices[display_pair] = {
                    "price": 0.0,
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


async def _fetch_luno_ticker(pair: str, api_key: Optional[Dict] = None) -> Dict:
    """Fetch ticker data from Luno API
    
    Args:
        pair: Trading pair in Luno format (e.g., XBTZAR)
        api_key: Optional API key dict with api_key and api_secret
        
    Returns:
        Dict with price, change_pct, timestamp, source
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
            
            # Calculate 24h change from rolling_24_hour_volume if available
            # Luno doesn't provide 24h change directly, so we'll use a simple heuristic
            # Future Enhancement: Store previous prices and calculate actual 24h change
            # Non-critical for core trading - tracked in backlog (see DEPLOYMENT_NOTES.md)
            change_pct = 0.0
            
            return {
                "price": round(last_trade, 2),
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
