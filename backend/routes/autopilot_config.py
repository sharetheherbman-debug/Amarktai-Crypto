"""
Autopilot Configuration Routes
User-configurable autopilot settings per exchange.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


class AutopilotConfigRequest(BaseModel):
    """Request model for autopilot configuration"""
    exchange: str
    profit_threshold_zar: Optional[float] = 1000.0
    bot_cap: Optional[int] = 10
    reinvest_min_zar: Optional[float] = 500.0


@router.get("/api/autopilot/user-settings")
async def get_user_autopilot_settings(user_id: str = Depends(get_current_user)):
    """
    Get user's autopilot configuration settings for all exchanges.
    
    Returns:
        User's custom autopilot settings per exchange
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Get user settings
        settings_doc = await db.db.autopilot_user_settings.find_one({"user_id": user_id})
        
        if not settings_doc:
            return {
                "success": True,
                "settings": {},
                "message": "No custom settings found, using defaults"
            }
        
        # Remove MongoDB _id
        settings = settings_doc.get("settings", {})
        
        return {
            "success": True,
            "settings": settings,
            "last_updated": settings_doc.get("updated_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get autopilot settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/autopilot/configure")
async def configure_autopilot(
    config: AutopilotConfigRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Configure autopilot settings for a specific exchange.
    
    Args:
        config: Autopilot configuration including exchange, thresholds, caps
        
    Returns:
        Confirmation of configuration update
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Validate exchange
        valid_exchanges = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']
        if config.exchange not in valid_exchanges:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange. Must be one of: {', '.join(valid_exchanges)}"
            )
        
        # Validate values
        if config.profit_threshold_zar < 100:
            raise HTTPException(
                status_code=400,
                detail="Profit threshold must be at least R100"
            )
        
        if config.bot_cap < 1 or config.bot_cap > 50:
            raise HTTPException(
                status_code=400,
                detail="Bot cap must be between 1 and 50"
            )
        
        if config.reinvest_min_zar < 50:
            raise HTTPException(
                status_code=400,
                detail="Reinvest minimum must be at least R50"
            )
        
        # Update or create settings
        exchange_settings = {
            "profit_threshold_zar": config.profit_threshold_zar,
            "bot_cap": config.bot_cap,
            "reinvest_min_zar": config.reinvest_min_zar
        }
        
        await db.db.autopilot_user_settings.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"settings.{config.exchange}": exchange_settings,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        
        logger.info(f"Updated autopilot settings for user {user_id[:8]} on {config.exchange}")
        
        return {
            "success": True,
            "message": f"Autopilot configured for {config.exchange}",
            "settings": exchange_settings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Configure autopilot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/autopilot/settings/{exchange}")
async def reset_autopilot_settings(
    exchange: str,
    user_id: str = Depends(get_current_user)
):
    """
    Reset autopilot settings for an exchange to defaults.
    
    Args:
        exchange: Exchange to reset settings for
        
    Returns:
        Confirmation of reset
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Remove exchange-specific settings
        await db.db.autopilot_user_settings.update_one(
            {"user_id": user_id},
            {
                "$unset": {f"settings.{exchange}": ""},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        
        logger.info(f"Reset autopilot settings for user {user_id[:8]} on {exchange}")
        
        return {
            "success": True,
            "message": f"Settings reset to defaults for {exchange}"
        }
        
    except Exception as e:
        logger.error(f"Reset autopilot settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
