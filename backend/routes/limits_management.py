"""
System Limits and Circuit Breaker Management Endpoints

Provides:
- Current limits configuration
- Limits usage inspection
- Bot quarantine management
- Manual circuit breaker reset
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import os

from auth import get_current_user, is_admin
import database as db

router = APIRouter(prefix="/api/limits", tags=["Limits"])
logger = logging.getLogger(__name__)


@router.get("/config")
async def get_limits_config(user_id: str = Depends(get_current_user)):
    """
    Get current limits configuration
    
    Returns all configured limits from environment and defaults
    """
    try:
        config = {
            "trade_limits": {
                "max_trades_per_bot_daily": int(os.getenv("MAX_TRADES_PER_BOT_DAILY", "400")),
                "max_trades_per_user_daily": int(os.getenv("MAX_TRADES_PER_USER_DAILY", "3000")),
                "burst_limit_orders": int(os.getenv("BURST_LIMIT_ORDERS_PER_EXCHANGE", "10")),
                "burst_limit_window_seconds": int(os.getenv("BURST_LIMIT_WINDOW_SECONDS", "10"))
            },
            "circuit_breaker": {
                "max_drawdown_percent": float(os.getenv("MAX_DRAWDOWN_PERCENT", "0.20")),
                "max_daily_loss_percent": float(os.getenv("MAX_DAILY_LOSS_PERCENT", "0.10")),
                "max_consecutive_losses": int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5")),
                "max_errors_per_hour": int(os.getenv("MAX_ERRORS_PER_HOUR", "10"))
            },
            "fee_coverage": {
                "min_edge_bps": float(os.getenv("MIN_EDGE_BPS", "10.0")),
                "safety_margin_bps": float(os.getenv("SAFETY_MARGIN_BPS", "5.0")),
                "slippage_buffer_bps": float(os.getenv("SLIPPAGE_BUFFER_BPS", "10.0"))
            },
            "exchange_fees": {
                "binance": {"maker": 7.5, "taker": 10.0},
                "luno": {"maker": 20.0, "taker": 25.0},
                "kucoin": {"maker": 10.0, "taker": 10.0},
                "bybit": {"maker": 10.0, "taker": 10.0},
                "bitget": {"maker": 10.0, "taker": 10.0},
            }
        }
        
        return {
            "success": True,
            "config": config,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get limits config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage")
async def get_limits_usage(
    user_id: str = Depends(get_current_user),
    bot_id: Optional[str] = Query(None, description="Filter by specific bot")
):
    """
    Get current limits usage
    
    Shows how close user/bots are to hitting limits
    """
    try:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get today's fills from ledger
        import database as db
        from services.ledger_service import get_ledger_service
        
        db = await get_database()
        ledger = get_ledger_service(db)
        
        # User-level usage
        user_fills_today = await fills_ledger.count_documents({
            "user_id": user_id,
            "timestamp": {"$gte": today_start}
        })
        
        max_user_trades = int(os.getenv("MAX_TRADES_PER_USER_DAILY", "500"))
        user_usage_pct = (user_fills_today / max_user_trades * 100) if max_user_trades > 0 else 0
        
        # Bot-level usage
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}},
            {"_id": 0}
        ).to_list(1000)
        
        bot_usage = []
        max_bot_trades = int(os.getenv("MAX_TRADES_PER_BOT_DAILY", "50"))
        
        for bot in bots:
            if bot_id and bot["id"] != bot_id:
                continue
            
            bot_fills_today = await fills_ledger.count_documents({
                "user_id": user_id,
                "bot_id": bot["id"],
                "timestamp": {"$gte": today_start}
            })
            
            bot_usage_pct = (bot_fills_today / max_bot_trades * 100) if max_bot_trades > 0 else 0
            
            # Get drawdown from ledger
            try:
                current_dd, max_dd = await ledger.compute_drawdown(user_id, bot_id=bot["id"])
            except:
                current_dd, max_dd = 0, 0
            
            bot_usage.append({
                "bot_id": bot["id"],
                "bot_name": bot.get("name"),
                "status": bot.get("status"),
                "trades_today": bot_fills_today,
                "trades_limit": max_bot_trades,
                "usage_pct": round(bot_usage_pct, 1),
                "drawdown_current": round(current_dd * 100, 2),
                "drawdown_max": round(max_dd * 100, 2),
                "drawdown_limit": float(os.getenv("MAX_DRAWDOWN_PERCENT", "0.20")) * 100
            })
        
        return {
            "success": True,
            "user_usage": {
                "trades_today": user_fills_today,
                "trades_limit": max_user_trades,
                "usage_pct": round(user_usage_pct, 1),
                "status": "ok" if user_usage_pct < 80 else "warning" if user_usage_pct < 95 else "critical"
            },
            "bot_usage": bot_usage,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get limits usage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quarantined")
async def get_quarantined_bots(user_id: str = Depends(get_current_user)):
    """
    Get list of quarantined bots
    
    Quarantined bots require manual reset
    """
    try:
        quarantined = await db.bots_collection.find(
            {"user_id": user_id, "status": "quarantined"},
            {"_id": 0}
        ).to_list(1000)
        
        return {
            "success": True,
            "quarantined_bots": quarantined,
            "count": len(quarantined),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get quarantined bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quarantine/reset/{bot_id}")
async def reset_quarantined_bot(
    bot_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Reset a quarantined bot (admin action)
    
    Changes status from quarantined -> paused
    Bot can then be manually resumed by user
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        if bot.get("status") != "quarantined":
            return {
                "success": False,
                "message": f"Bot is not quarantined (current status: {bot.get('status')})"
            }
        
        # Reset to paused (not active - requires explicit resume)
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "paused",
                    "reset_from_quarantine": True,
                    "reset_at": datetime.now(timezone.utc).isoformat(),
                    "reset_by": user_id
                },
                "$unset": {
                    "quarantine_reason": "",
                    "quarantined_at": "",
                    "requires_manual_reset": ""
                }
            }
        )
        
        # Create alert
        await db.alerts_collection.insert_one({
            "user_id": user_id,
            "bot_id": bot_id,
            "type": "quarantine_reset",
            "severity": "medium",
            "message": f"✅ Bot '{bot.get('name')}' reset from quarantine to paused. You can resume it manually.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dismissed": False
        })
        
        logger.info(f"Bot {bot_id} reset from quarantine by user {user_id}")
        
        return {
            "success": True,
            "message": f"Bot '{bot.get('name')}' reset from quarantine. Status is now 'paused'. Resume manually when ready.",
            "bot_id": bot_id,
            "new_status": "paused"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset quarantined bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/circuit-breaker/check")
async def check_circuit_breaker(
    user_id: str = Depends(get_current_user),
    bot_id: Optional[str] = Query(None, description="Check specific bot")
):
    """
    Manually check circuit breaker conditions
    
    Useful for testing or diagnosing issues
    """
    try:
        from engines.circuit_breaker import circuit_breaker
        import database as db
        from services.ledger_service import get_ledger_service
        
        db = await get_database()
        ledger = get_ledger_service(db)
        
        results = {
            "user_id": user_id,
            "checks": []
        }
        
        if bot_id:
            # Check specific bot
            checks = [
                ("Drawdown", await circuit_breaker.check_bot_drawdown_ledger(user_id, bot_id, ledger)),
                ("Daily Loss", await circuit_breaker.check_daily_loss_ledger(user_id, bot_id, ledger)),
                ("Consecutive Losses", await circuit_breaker.check_consecutive_losses_ledger(user_id, bot_id, ledger)),
                ("Error Rate", await circuit_breaker.check_error_rate(user_id, bot_id))
            ]
            
            for check_name, (breached, reason) in checks:
                results["checks"].append({
                    "check": check_name,
                    "bot_id": bot_id,
                    "breached": breached,
                    "reason": reason
                })
        else:
            # Check global
            global_breach, global_reason = await circuit_breaker.check_global_drawdown(user_id)
            results["checks"].append({
                "check": "Global Drawdown",
                "breached": global_breach,
                "reason": global_reason
            })
        
        results["timestamp"] = datetime.now(timezone.utc).isoformat()
        results["any_breached"] = any(c["breached"] for c in results["checks"])
        
        return results
    
    except Exception as e:
        logger.error(f"Check circuit breaker error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_limits_health(user_id: str = Depends(get_current_user)):
    """
    Get overall health status of limits system
    
    Returns summary of usage and breaches
    """
    try:
        # Get usage
        usage_response = await get_limits_usage(user_id)
        
        # Count quarantined bots
        quarantined_count = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "quarantined"
        })
        
        # Count recent breaches
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent_breaches = await db.alerts_collection.count_documents({
            "user_id": user_id,
            "type": "circuit_breaker",
            "timestamp": {"$gte": one_hour_ago}
        })
        
        # Determine health status
        user_usage_pct = usage_response["user_usage"]["usage_pct"]
        
        if quarantined_count > 0 or recent_breaches > 0:
            health_status = "critical"
        elif user_usage_pct > 80:
            health_status = "warning"
        else:
            health_status = "healthy"
        
        return {
            "success": True,
            "health_status": health_status,
            "summary": {
                "user_usage_pct": user_usage_pct,
                "quarantined_bots": quarantined_count,
                "recent_breaches": recent_breaches
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get limits health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
