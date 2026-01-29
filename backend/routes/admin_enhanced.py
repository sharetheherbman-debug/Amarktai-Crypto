"""
Enhanced Admin Endpoints - User selection and bot filtering

Adds user dropdown support and per-bot profit/loss indicators.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Enhanced Admin"])


async def require_admin(current_user: str = Depends(get_current_user)) -> str:
    """Ensure current user is admin"""
    user = await db.users_collection.find_one({"id": current_user}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    is_admin = user.get('is_admin', False) or user.get('role') == 'admin'
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return current_user


@router.get("/users/list")
async def get_users_list(admin_id: str = Depends(require_admin)):
    """
    Get list of all users for admin dropdown
    
    Returns simplified user list with id, name, email, bot count
    """
    try:
        # Get all users
        users_cursor = db.users_collection.find(
            {},
            {"_id": 0, "id": 1, "first_name": 1, "email": 1}
        )
        users = await users_cursor.to_list(10000)
        
        # Enrich with bot counts
        enriched_users = []
        for user in users:
            user_id = user.get("id")
            
            # Count bots for this user
            bot_count = await db.bots_collection.count_documents({
                "user_id": user_id,
                "status": {"$nin": ["deleted"]}
            })
            
            enriched_users.append({
                "user_id": user_id,
                "name": user.get("first_name", "Unknown"),
                "email": user.get("email", "Unknown"),
                "bot_count": bot_count
            })
        
        # Sort by bot count (most active users first)
        enriched_users.sort(key=lambda u: u["bot_count"], reverse=True)
        
        return {
            "users": enriched_users,
            "total": len(enriched_users)
        }
        
    except Exception as e:
        logger.error(f"Get users list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/bots")
async def get_user_bots_detailed(
    user_id: str,
    admin_id: str = Depends(require_admin)
):
    """
    Get all bots for a specific user with detailed profit/loss indicators
    
    Shows per-bot profit/loss, not just totals.
    """
    try:
        # Verify user exists
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "first_name": 1, "email": 1}
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get all bots for this user (excluding deleted)
        bots_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted"]}
            },
            {"_id": 0}
        )
        bots = await bots_cursor.to_list(1000)
        
        # Enrich each bot with profit/loss indicator
        enriched_bots = []
        for bot in bots:
            bot_id = bot.get("id")
            
            # Calculate net profit/loss
            current_capital = bot.get("current_capital", 0)
            initial_capital = bot.get("initial_capital", 1000)
            net_pnl = current_capital - initial_capital
            pnl_pct = ((net_pnl / initial_capital) * 100) if initial_capital > 0 else 0
            
            # Get today's performance
            from datetime import timedelta
            today_start = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(hour=0, minute=0, second=0)
            
            trades_today_cursor = db.trades_collection.find({
                "bot_id": bot_id,
                "timestamp": {"$gte": today_start.isoformat()}
            })
            trades_today = await trades_today_cursor.to_list(1000)
            
            today_pnl = sum(t.get("net_pnl", 0) for t in trades_today)
            
            enriched_bots.append({
                "bot_id": bot_id,
                "name": bot.get("name"),
                "exchange": bot.get("exchange"),
                "trading_mode": bot.get("trading_mode", "paper"),
                "status": bot.get("status", "unknown"),
                "current_capital": round(current_capital, 2),
                "initial_capital": round(initial_capital, 2),
                "net_pnl": round(net_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "today_pnl": round(today_pnl, 2),
                "profit_indicator": "profit" if net_pnl > 0 else "loss" if net_pnl < 0 else "neutral",
                "trades_count": bot.get("trades_count", 0),
                "last_trade": bot.get("last_trade"),
                "created_at": bot.get("created_at")
            })
        
        # Sort by net profit/loss (best performers first)
        enriched_bots.sort(key=lambda b: b["net_pnl"], reverse=True)
        
        return {
            "user_id": user_id,
            "username": user.get("first_name", "Unknown"),
            "email": user.get("email"),
            "bots": enriched_bots,
            "total_bots": len(enriched_bots),
            "total_net_pnl": round(sum(b["net_pnl"] for b in enriched_bots), 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user bots detailed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/stats")
async def get_admin_dashboard_stats(admin_id: str = Depends(require_admin)):
    """
    Get comprehensive admin dashboard statistics
    
    Returns realtime stats for admin overview.
    """
    try:
        # User stats
        total_users = await db.users_collection.count_documents({})
        
        # Bot stats
        total_bots = await db.bots_collection.count_documents({"status": {"$nin": ["deleted"]}})
        active_bots = await db.bots_collection.count_documents({"status": "active"})
        paused_bots = await db.bots_collection.count_documents({"status": "paused"})
        quarantined_bots = await db.bots_collection.count_documents({"status": "quarantined"})
        
        # Trading stats
        total_trades = await db.trades_collection.count_documents({})
        
        # Calculate system-wide profit/loss
        bots_cursor = db.bots_collection.find(
            {"status": {"$nin": ["deleted"]}},
            {"_id": 0, "current_capital": 1, "initial_capital": 1}
        )
        all_bots = await bots_cursor.to_list(10000)
        
        total_capital = sum(b.get("current_capital", 0) for b in all_bots)
        initial_capital = sum(b.get("initial_capital", 1000) for b in all_bots)
        system_net_pnl = total_capital - initial_capital
        
        # Get recent activity (last 24 hours)
        from datetime import timedelta
        last_24h = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        trades_24h = await db.trades_collection.count_documents({
            "timestamp": {"$gte": last_24h}
        })
        
        return {
            "users": {
                "total": total_users
            },
            "bots": {
                "total": total_bots,
                "active": active_bots,
                "paused": paused_bots,
                "quarantined": quarantined_bots
            },
            "trading": {
                "total_trades": total_trades,
                "trades_24h": trades_24h,
                "total_capital": round(total_capital, 2),
                "initial_capital": round(initial_capital, 2),
                "system_net_pnl": round(system_net_pnl, 2)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get admin dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
