"""
Fetch.ai Integration Routes
Provides endpoints for Fetch.ai API key management and market signals.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging

from auth import get_current_user
from fetchai_integration import fetchai

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fetchai", tags=["Fetch.ai"])


async def get_fetchai_key(user_id: str) -> Optional[str]:
    """Get Fetch.ai API key for user"""
    try:
        from routes.api_key_management import get_decrypted_key
        
        key_data = await get_decrypted_key(user_id, "fetchai")
        if key_data and key_data.get("api_key"):
            return key_data.get("api_key", "").strip()
        return None
    except Exception as e:
        logger.warning(f"Failed to get Fetch.ai key: {e}")
        return None


@router.get("/test-connection")
async def test_connection(user_id: str = Depends(get_current_user)):
    """
    Test Fetch.ai API connection with user's key.
    
    Returns:
        Status of connection test
    """
    try:
        api_key = await get_fetchai_key(user_id)
        
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "error",
                    "message": "No Fetch.ai API key configured",
                    "source": "missing"
                }
            )
        
        # Test the connection
        is_connected = await fetchai.test_connection(api_key)
        
        if is_connected:
            return {
                "status": "success",
                "message": "Successfully connected to Fetch.ai",
                "source": "user"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to connect to Fetch.ai - invalid API key or service unavailable",
                "source": "user"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/{pair}")
async def get_signals(
    pair: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get AI-powered market signals for a trading pair.
    
    Args:
        pair: Trading pair (e.g., "BTC/USD", "ETH/USD")
        
    Returns:
        Market signals with confidence, indicators, and sentiment
    """
    try:
        api_key = await get_fetchai_key(user_id)
        
        # Set API key if available
        if api_key:
            fetchai.set_credentials(api_key)
        
        # Fetch market signals
        signals = await fetchai.fetch_market_signals(pair)
        
        return {
            "success": True,
            "pair": pair,
            "signals": signals,
            "configured": api_key is not None
        }
        
    except Exception as e:
        logger.error(f"Get signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendation/{pair}")
async def get_recommendation(
    pair: str,
    risk_level: str = "moderate",
    user_id: str = Depends(get_current_user)
):
    """
    Get AI-powered trading recommendation for a pair.
    
    Args:
        pair: Trading pair (e.g., "BTC/USD", "ETH/USD")
        risk_level: Risk level ("safe", "moderate", "aggressive")
        
    Returns:
        Trading recommendation with entry, stop-loss, and take-profit levels
    """
    try:
        api_key = await get_fetchai_key(user_id)
        
        # Set API key if available
        if api_key:
            fetchai.set_credentials(api_key)
        
        # Get trading recommendation
        recommendation = await fetchai.get_trading_recommendation(pair, risk_level)
        
        return {
            "success": True,
            "pair": pair,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "configured": api_key is not None
        }
        
    except Exception as e:
        logger.error(f"Get recommendation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(user_id: str = Depends(get_current_user)):
    """
    Get Fetch.ai integration status.
    
    Returns:
        Integration status and configuration state
    """
    try:
        api_key = await get_fetchai_key(user_id)
        
        is_configured = api_key is not None
        is_active = False
        
        if is_configured:
            # Test if connection is active
            is_active = await fetchai.test_connection(api_key)
        
        return {
            "success": True,
            "configured": is_configured,
            "active": is_active,
            "message": "Fetch.ai is active" if is_active else (
                "Fetch.ai is configured but not responding" if is_configured else
                "Fetch.ai is not configured"
            )
        }
        
    except Exception as e:
        logger.error(f"Get status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
