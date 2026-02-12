"""
Platform Endpoints - Platform-specific bot performance and drilldown
Provides per-exchange analytics and bot listings
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import logging

from auth import get_current_user
import database as db
from services.profit_service import profit_service
import platforms  # Import authoritative platform registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platforms", tags=["Platforms"])

# Use authoritative platform registry
EXCHANGES = platforms.SUPPORTED_PLATFORMS


@router.get("")
async def get_platforms():
    """Get list of all supported platforms (public endpoint)
    
    Returns the authoritative list of 7 supported platforms with their configurations.
    This endpoint does not require authentication and serves as the single source of truth
    for platform information consumed by the frontend and other clients.
    
    Returns:
        {
            "success": true,
            "platforms": [...],  # List of platform configs
            "total": 7
        }
    """
    try:
        all_platforms = platforms.get_all_platforms()
        
        return {
            "success": True,
            "platforms": all_platforms,
            "total": len(all_platforms),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get platforms error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_platforms_summary(
    mode: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """Get summary of all platforms with performance metrics
    
    Returns per-platform:
    - bots_count_total
    - bots_active
    - profit_today
    - profit_total
    - trades_today
    - win_rate
    
    Args:
        mode: Filter by trading mode ('paper' or 'live', None = current system mode)
        user_id: Current user ID
        
    Returns:
        Summary data for each platform
    """
    try:
        # Get system mode if not specified
        if not mode:
            from routes.system_mode import get_system_mode
            system_mode = await get_system_mode()
            if system_mode.get("paperTrading"):
                mode = "paper"
            elif system_mode.get("liveTrading"):
                mode = "live"
            else:
                mode = "paper"  # Default to paper
        
        # Calculate today's start
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Get all user's bots
        bots_query = {"user_id": user_id}
        if mode:
            bots_query["trading_mode"] = mode
        
        bots_cursor = db.bots_collection.find(bots_query, {"_id": 0})
        all_bots = await bots_cursor.to_list(1000)
        
        # Build summary for each exchange
        platform_summaries = []
        
        for exchange in EXCHANGES:
            # Filter bots for this exchange
            exchange_bots = [b for b in all_bots if b.get("exchange") == exchange]
            
            bots_count_total = len(exchange_bots)
            bots_active = sum(1 for b in exchange_bots if b.get("status") == "active")
            
            # Calculate profit for this exchange's bots
            bot_ids = [b["id"] for b in exchange_bots if "id" in b]
            
            # Get today's trades for these bots
            today_trades_query = {
                "bot_id": {"$in": bot_ids},
                "status": "closed",
                "timestamp": {"$gte": today_start.isoformat()}
            }
            
            today_trades_cursor = db.trades_collection.find(
                today_trades_query,
                {"_id": 0, "net_pnl": 1, "profit_loss": 1}
            )
            today_trades = await today_trades_cursor.to_list(1000)
            
            profit_today = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in today_trades)
            trades_today = len(today_trades)
            
            # Get all-time trades for these bots
            all_trades_query = {
                "bot_id": {"$in": bot_ids},
                "status": "closed"
            }
            
            all_trades_cursor = db.trades_collection.find(
                all_trades_query,
                {"_id": 0, "net_pnl": 1, "profit_loss": 1}
            )
            all_trades = await all_trades_cursor.to_list(10000)
            
            profit_total = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in all_trades)
            
            # Calculate win rate
            winning_trades = sum(1 for t in all_trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
            win_rate = (winning_trades / len(all_trades) * 100) if all_trades else 0
            
            platform_summaries.append({
                "platform": exchange,
                "display_name": exchange.upper(),
                "bots_count_total": bots_count_total,
                "bots_active": bots_active,
                "profit_today": round(profit_today, 2),
                "profit_total": round(profit_total, 2),
                "trades_today": trades_today,
                "win_rate": round(win_rate, 2)
            })
        
        return {
            "success": True,
            "mode": mode,
            "platforms": platform_summaries,
            "total_platforms": len(EXCHANGES),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get platforms summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{platform}/bots")
async def get_platform_bots(
    platform: str,
    mode: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """Get all bots on a specific platform with performance metrics
    
    Args:
        platform: Platform/exchange name (luno, binance, kucoin, bybit, bitget)
        mode: Filter by trading mode ('paper' or 'live')
        user_id: Current user ID
        
    Returns:
        List of bots with performance data and action controls
    """
    try:
        # Validate platform
        if platform.lower() not in EXCHANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid platform. Must be one of: {', '.join(EXCHANGES)}"
            )
        
        # Get system mode if not specified
        if not mode:
            from routes.system_mode import get_system_mode
            system_mode = await get_system_mode()
            if system_mode.get("paperTrading"):
                mode = "paper"
            elif system_mode.get("liveTrading"):
                mode = "live"
            else:
                mode = "paper"
        
        # Get bots for this platform
        bots_query = {
            "user_id": user_id,
            "exchange": platform.lower()
        }
        
        if mode:
            bots_query["trading_mode"] = mode
        
        bots_cursor = db.bots_collection.find(bots_query, {"_id": 0})
        bots = await bots_cursor.to_list(1000)
        
        # Enrich each bot with performance data
        enriched_bots = []
        
        for bot in bots:
            bot_id = bot.get("id")
            
            if not bot_id:
                continue
            
            # Get bot's trades
            trades_query = {
                "bot_id": bot_id,
                "status": "closed"
            }
            
            trades_cursor = db.trades_collection.find(
                trades_query,
                {"_id": 0, "net_pnl": 1, "profit_loss": 1, "timestamp": 1}
            )
            trades = await trades_cursor.to_list(1000)
            
            # Calculate performance
            total_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)
            total_trades = len(trades)
            winning_trades = sum(1 for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate today's profit
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            
            today_trades = [
                t for t in trades
                if t.get("timestamp") and t["timestamp"] >= today_start.isoformat()
            ]
            
            profit_today = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in today_trades)
            
            # Build enriched bot data
            enriched_bot = {
                "id": bot_id,
                "name": bot.get("name"),
                "pair": bot.get("pair"),
                "status": bot.get("status"),
                "trading_mode": bot.get("trading_mode"),
                "current_capital": bot.get("current_capital", 0),
                "total_profit": round(total_profit, 2),
                "profit_today": round(profit_today, 2),
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "created_at": bot.get("created_at"),
                "last_trade_time": bot.get("last_trade_time"),
                # Action controls
                "can_start": bot.get("status") in ["stopped", "paused"],
                "can_pause": bot.get("status") == "active",
                "can_resume": bot.get("status") == "paused",
                "can_stop": bot.get("status") in ["active", "paused"],
                "can_delete": True  # With safety checks in delete endpoint
            }
            
            enriched_bots.append(enriched_bot)
        
        # Sort by profit_total descending
        enriched_bots.sort(key=lambda b: b["total_profit"], reverse=True)
        
        return {
            "success": True,
            "platform": platform.lower(),
            "display_name": platform.upper(),
            "mode": mode,
            "bots": enriched_bots,
            "total_bots": len(enriched_bots),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get platform bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_platform_status(user_id: str = Depends(get_current_user)) -> dict:
    """
    GET /api/platforms/status (auth required)
    
    Returns per-platform status for the current user:
    - enabled_for_user: whether user wants to trade on this platform
    - ready_for_paper: can do paper trading (always true for all platforms)
    - ready_for_live: has valid API keys for live trading
    - missing_keys: true if API keys not configured or invalid
    - last_error: string with last known error or null
    
    This is the canonical source for frontend to determine which platforms
    a user can trade on in paper vs live mode.
    """
    try:
        from config.platforms import SUPPORTED_PLATFORMS, get_platform_config
        
        platform_statuses = {}
        
        for platform_id in SUPPORTED_PLATFORMS:
            platform_config = get_platform_config(platform_id)
            
            if not platform_config:
                continue
            
            # Check if user has API keys configured
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": platform_id
            }, {"_id": 0, "test_status": 1, "last_test": 1, "error_message": 1})
            
            has_keys = bool(api_key_doc)
            keys_valid = api_key_doc.get("test_status") == "test_ok" if has_keys else False
            last_error = api_key_doc.get("error_message") if has_keys else None
            
            # Get user's enabled platforms preference (if stored in user settings)
            user = await db.users_collection.find_one(
                {"id": user_id},
                {"_id": 0, "enabled_platforms": 1}
            )
            enabled_platforms = user.get("enabled_platforms", SUPPORTED_PLATFORMS) if user else SUPPORTED_PLATFORMS
            enabled_for_user = platform_id in enabled_platforms
            
            platform_statuses[platform_id] = {
                "platform": platform_id,
                "display_name": platform_config['display_name'],
                "enabled_for_user": enabled_for_user,
                "ready_for_paper": platform_config.get("supports_paper", True),
                "ready_for_live": keys_valid and platform_config.get("supports_live", True),
                "missing_keys": not keys_valid,
                "has_keys": has_keys,
                "last_error": last_error,
                "last_check": api_key_doc.get("last_test") if has_keys else None
            }
        
        return {
            "success": True,
            "platforms": platform_statuses,
            "total_platforms": len(SUPPORTED_PLATFORMS),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get platform status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get platform status: {str(e)}")


@router.get("/health")
async def platform_health(user_id: str = Depends(get_current_user)) -> dict:
    """
    Get health status for all 5 platforms
    
    Checks:
    - Whether user has configured API keys
    - Whether keys are valid (if configured)
    - Platform operational status
    
    Returns status for: Luno, Binance, KuCoin, Bybit, Bitget
    """
    try:
        from config.platforms import SUPPORTED_PLATFORMS, get_platform_config
        
        platforms_status = {}
        
        for platform_id in SUPPORTED_PLATFORMS:
            platform_config = get_platform_config(platform_id)
            
            if not platform_config:
                platforms_status[platform_id] = {
                    "status": "unsupported",
                    "has_keys": False,
                    "keys_valid": None,
                    "last_check": None,
                    "api_latency_ms": None,
                    "message": "Platform not found in configuration"
                }
                continue
            
            # Check if user has configured API keys for this platform
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": platform_id
            }, {"_id": 0, "api_key": 1, "api_secret": 1, "passphrase": 1, "last_test": 1, "test_status": 1})
            
            if not api_key_doc:
                platforms_status[platform_id] = {
                    "status": "not_configured",
                    "has_keys": False,
                    "keys_valid": None,
                    "last_check": None,
                    "api_latency_ms": None,
                    "supports_paper": platform_config.get("supports_paper", True),
                    "supports_live": platform_config.get("supports_live", True),
                    "message": f"No API keys configured for {platform_config['display_name']}"
                }
                continue
            
            # User has keys - check their validity
            last_test_status = api_key_doc.get("test_status")
            last_test_time = api_key_doc.get("last_test")
            
            if last_test_status == "test_ok":
                status = "operational"
                keys_valid = True
                message = f"{platform_config['display_name']} is operational"
            elif last_test_status == "test_failed":
                status = "keys_invalid"
                keys_valid = False
                message = f"API keys invalid for {platform_config['display_name']}"
            else:
                status = "saved_untested"
                keys_valid = None
                message = f"API keys saved but not tested for {platform_config['display_name']}"
            
            platforms_status[platform_id] = {
                "status": status,
                "has_keys": True,
                "keys_valid": keys_valid,
                "last_check": last_test_time,
                "api_latency_ms": None,
                "supports_paper": platform_config.get("supports_paper", True),
                "supports_live": platform_config.get("supports_live", True),
                "message": message
            }
        
        return {
            "success": True,
            "platforms": platforms_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Platform health check error: {e}")
        # Return safe defaults for all 5 platforms
        from config.platforms import SUPPORTED_PLATFORMS
        safe_defaults = {}
        for platform_id in SUPPORTED_PLATFORMS:
            safe_defaults[platform_id] = {
                "status": "unknown",
                "has_keys": False,
                "keys_valid": None,
                "last_check": None,
                "api_latency_ms": None,
                "message": "Health check failed"
            }
        
        return {
            "success": False,
            "platforms": safe_defaults,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/readiness")
async def platform_readiness(user_id: str = Depends(get_current_user)) -> dict:
    """
    Get platform readiness report for user
    
    Returns which platforms are ready for:
    - Paper trading
    - Live trading
    
    Includes recommendations for missing configurations
    """
    try:
        from config.platforms import SUPPORTED_PLATFORMS, get_platform_config
        
        readiness_report = {
            "paper_ready": [],
            "live_ready": [],
            "needs_configuration": [],
            "summary": {},
            "recommendations": []
        }
        
        for platform_id in SUPPORTED_PLATFORMS:
            platform_config = get_platform_config(platform_id)
            
            if not platform_config:
                continue
            
            # Check API keys
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": platform_id
            }, {"_id": 0, "test_status": 1})
            
            has_valid_keys = api_key_doc and api_key_doc.get("test_status") == "test_ok"
            
            platform_name = platform_config['display_name']
            
            # Check paper trading readiness
            if platform_config.get("supports_paper", True):
                readiness_report["paper_ready"].append({
                    "platform": platform_id,
                    "name": platform_name,
                    "has_keys": bool(api_key_doc),
                    "keys_validated": has_valid_keys
                })
            
            # Check live trading readiness
            if platform_config.get("supports_live", True):
                if has_valid_keys:
                    readiness_report["live_ready"].append({
                        "platform": platform_id,
                        "name": platform_name,
                        "ready": True
                    })
                else:
                    readiness_report["needs_configuration"].append({
                        "platform": platform_id,
                        "name": platform_name,
                        "reason": "Missing or invalid API keys",
                        "action": f"Configure API keys for {platform_name}"
                    })
        
        # Generate summary
        readiness_report["summary"] = {
            "paper_trading_ready": len(readiness_report["paper_ready"]),
            "live_trading_ready": len(readiness_report["live_ready"]),
            "needs_configuration": len(readiness_report["needs_configuration"]),
            "total_platforms": len(SUPPORTED_PLATFORMS)
        }
        
        # Generate recommendations
        if readiness_report["needs_configuration"]:
            readiness_report["recommendations"].append(
                "Configure API keys for remaining platforms to enable live trading"
            )
        if len(readiness_report["live_ready"]) == len(SUPPORTED_PLATFORMS):
            readiness_report["recommendations"].append(
                "All platforms configured! You're ready for live trading."
            )
        
        return {
            "success": True,
            "readiness": readiness_report,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Platform readiness check error: {e}")
        raise HTTPException(status_code=500, detail=f"Readiness check failed: {str(e)}")
