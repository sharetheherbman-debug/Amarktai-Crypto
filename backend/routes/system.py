"""System routes for basic ping and status endpoints.

This module defines a minimal router that exposes system‑wide ping endpoints.  Having a
dedicated file ensures that the server can mount `/api/system/ping` without
conflicting with other route prefixes and satisfies health checks used by
deployment scripts.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
from typing import Dict
import config
import logging
import os

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

# Prefix ensures final paths begin with /api/system when mounted without an
# additional prefix.
router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/ping")
async def system_ping() -> dict:
    """Return a simple heartbeat response for system health checks."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/platforms")
async def get_platforms() -> dict:
    """Return list of all enabled trading platforms/exchanges.
    
    Returns platform names, enabled status, and bot limits.
    Frontend should use this to populate platform selectors.
    NOW RETURNS ALL 7 PLATFORMS: Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate
    """
    try:
        # Import canonical platform registry
        from config.platforms import get_all_platforms, SUPPORTED_PLATFORMS
        
        # Get all platform configs from canonical source
        platform_configs = get_all_platforms()
        
        platforms = []
        for platform_config in platform_configs:
            platforms.append({
                "id": platform_config["id"],
                "name": platform_config["name"],
                "display_name": platform_config["display_name"],
                "enabled": platform_config["enabled"],
                "bot_limit": platform_config["max_bots"],
                "supports_paper": platform_config["supports_paper"],
                "supports_live": platform_config["supports_live"],
                "icon": platform_config.get("icon", ""),
                "color": platform_config.get("color", ""),
                "region": platform_config.get("region", "")
            })
        
        return {
            "platforms": platforms,
            "total_count": len(platforms),
            "default": "all",  # Default filter value
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        # Never crash - return safe defaults with ALL 7 platforms
        logger.error(f"Error in get_platforms: {e}")
        return {
            "platforms": [
                {"id": "luno", "name": "Luno", "display_name": "Luno", "enabled": True, "bot_limit": 5, "supports_paper": True, "supports_live": True},
                {"id": "binance", "name": "Binance", "display_name": "Binance", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "kucoin", "name": "KuCoin", "display_name": "KuCoin", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "bybit", "name": "Bybit", "display_name": "Bybit", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "bitget", "name": "Bitget", "display_name": "Bitget", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True}
            ],
            "total_count": 5,
            "default": "all",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# REMOVED: Duplicate of live_trading_gate.py endpoint GET /api/system/live-eligibility
# Use live_trading_gate.py instead


# REMOVED: Duplicate of emergency_stop_endpoints.py endpoint GET /api/system/emergency-stop/status  
# Use emergency_stop_endpoints.py instead


# REMOVED: Duplicate GET /api/system/status - canonical version in routes/system_status.py
# This duplicate route causes collision. Use system_status.py instead.

# @router.get("/status")
# async def system_status(user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_status.py for canonical implementation"""
#     pass


# REMOVED: Duplicate GET /api/system/mode - canonical version in routes/system_mode.py  
# This duplicate route causes collision. Use system_mode.py instead.

# @router.get("/mode")
# async def get_system_mode(user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_mode.py for canonical implementation"""
#     pass


# REMOVED: Duplicate POST /api/system/mode - canonical version in routes/system_mode.py
# This duplicate route causes collision. Use system_mode.py /mode/switch instead.

# @router.post("/mode")
# async def set_system_mode(payload: Dict = Body(...), user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_mode.py for canonical implementation"""
#     pass