"""
Prices API - Canonical live price endpoint for frontend
Provides real-time prices for dashboard overview
Delegates to market_api for actual data fetching
"""

from fastapi import APIRouter, Depends
from typing import List
import logging

from auth import get_current_user
from routes.market_api import get_market_prices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prices", tags=["Prices"])


@router.get("/live")
async def get_live_prices(user_id: str = Depends(get_current_user)):
    """Get live market prices - frontend-friendly format
    
    Returns array of price objects for each trading pair:
    - pair: Trading pair symbol (e.g., "BTC/ZAR")
    - price: Current price  
    - change_24h: 24h percentage change
    - last_update: ISO timestamp
    
    This is an alias/wrapper for /api/market/prices that returns
    data in the format expected by frontend components.
    """
    try:
        # Delegate to market API
        market_data = await get_market_prices(user_id)
        
        # Transform to frontend-expected array format
        prices = market_data.get("prices", {})
        result = []
        
        for pair, data in prices.items():
            result.append({
                "pair": pair,
                "price": data.get("price", 0.0),
                "change_24h": data.get("change_pct", 0.0),
                "last_update": data.get("timestamp"),
                "source": data.get("source", "unknown")
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Get live prices error: {e}")
        # Return empty array on error (graceful degradation)
        return []
