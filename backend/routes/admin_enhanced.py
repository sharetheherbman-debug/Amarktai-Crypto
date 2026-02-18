"""
Enhanced Admin Endpoints - User selection and bot filtering

Adds user dropdown support and per-bot profit/loss indicators.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
import logging
from datetime import datetime, timezone, timedelta
import psutil
import shutil

from auth import require_admin
import database as db
from config.platforms import SUPPORTED_PLATFORMS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Enhanced Admin"])


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


@router.get("/system-stats")
async def get_system_stats(admin_id: str = Depends(require_admin)):
    """
    Get comprehensive system statistics including VPS resources.
    Returns CPU, RAM, disk usage, and system health.
    Requires admin role.
    """
    try:
        # Get user statistics
        
        total_users = await db.users_collection.count_documents({})
        blocked_users = await db.users_collection.count_documents({
            "$or": [{"blocked": True}, {"status": "blocked"}]
        })
        active_users = max(total_users - blocked_users, 0)
        
        bot_filter = {
            "status": {"$ne": "deleted"},
            "deleted": {"$ne": True},
            "deleted_at": {"$exists": False}
        }
        total_bots = await db.bots_collection.count_documents(bot_filter)
        active_bots = await db.bots_collection.count_documents({**bot_filter, "status": "active"})
        paused_bots = await db.bots_collection.count_documents({**bot_filter, "status": "paused"})
        quarantined_bots = await db.bots_collection.count_documents({**bot_filter, "status": "quarantined"})
        live_bots = await db.bots_collection.count_documents({
            **bot_filter,
            "$or": [{"trading_mode": "live"}, {"mode": "live"}]
        })
        paper_bots = max(total_bots - live_bots, 0)
        
        total_trades = await db.trades_collection.count_documents({})
        live_trades = await db.trades_collection.count_documents({
            "$or": [{"trading_mode": "live"}, {"is_paper": False}]
        })
        paper_trades = max(total_trades - live_trades, 0)
        
        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        trades_24h = await db.trades_collection.count_documents({
            "$or": [
                {"timestamp": {"$gte": last_24h.isoformat()}},
                {"created_at": {"$gte": last_24h.isoformat()}}
            ]
        })
        
        exchange_breakdown = {
            exchange: {"bots": 0, "trades": 0, "profit": 0.0}
            for exchange in SUPPORTED_PLATFORMS
        }
        for exchange in SUPPORTED_PLATFORMS:
            exchange_breakdown[exchange]["bots"] = await db.bots_collection.count_documents({
                **bot_filter,
                "exchange": exchange
            })
        
        trade_pipeline = [
            {"$match": {"exchange": {"$in": list(SUPPORTED_PLATFORMS)}}},
            {"$project": {
                "exchange": 1,
                "profit": {
                    "$ifNull": ["$net_pnl", {"$ifNull": ["$profit_loss", 0]}]
                }
            }},
            {"$group": {
                "_id": "$exchange",
                "trades": {"$sum": 1},
                "profit": {"$sum": "$profit"}
            }}
        ]
        trade_groups = await db.trades_collection.aggregate(trade_pipeline).to_list(len(SUPPORTED_PLATFORMS))
        total_profit = 0.0
        for doc in trade_groups:
            exchange = doc.get("_id")
            if exchange in exchange_breakdown:
                exchange_breakdown[exchange]["trades"] = doc.get("trades", 0)
                exchange_breakdown[exchange]["profit"] = round(doc.get("profit", 0.0), 2)
                total_profit += doc.get("profit", 0.0)
        
        total_profit = round(total_profit, 2)
        
        modes_cursor = db.system_modes_collection.find({}, {"_id": 0, "paperTrading": 1, "liveTrading": 1, "autopilot": 1})
        modes = await modes_cursor.to_list(1000)
        system_modes = {
            "paper_trading": sum(1 for mode in modes if mode.get("paperTrading")),
            "live_trading": sum(1 for mode in modes if mode.get("liveTrading")),
            "autopilot": sum(1 for mode in modes if mode.get("autopilot"))
        }
        
        try:
            from trading_scheduler import trading_scheduler
            is_running_attr = getattr(trading_scheduler, "is_running", None)
            if callable(is_running_attr):
                scheduler_running = is_running_attr()
            elif isinstance(is_running_attr, bool):
                scheduler_running = is_running_attr
            else:
                scheduler_running = False
        except Exception as e:
            logger.warning(f"Scheduler status error: {e}")
            scheduler_running = False
        
        # VPS Resource metrics
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_total_gb = memory.total / (1024**3)
        memory_used_gb = memory.used / (1024**3)
        memory_free_gb = memory.available / (1024**3)
        memory_percent = memory.percent
        
        # Disk usage
        disk = shutil.disk_usage("/")
        disk_total_gb = disk.total / (1024**3)
        disk_used_gb = disk.used / (1024**3)
        disk_free_gb = disk.free / (1024**3)
        disk_percent = round((disk.used / disk.total) * 100, 2)
        
        # Load average (if available)
        try:
            load_avg = psutil.getloadavg()
            load_info = {
                "1min": round(load_avg[0], 2),
                "5min": round(load_avg[1], 2),
                "15min": round(load_avg[2], 2)
            }
        except (AttributeError, OSError):
            load_info = None
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "blocked": blocked_users
            },
            "bots": {
                "total": total_bots,
                "active": active_bots,
                "live": live_bots,
                "paper": paper_bots,
                "paused": paused_bots,
                "quarantined": quarantined_bots
            },
            "trades": {
                "total": total_trades,
                "live": live_trades,
                "paper": paper_trades,
                "last_24h": trades_24h
            },
            "profit": {
                "total": total_profit
            },
            "exchange_breakdown": exchange_breakdown,
            "system_modes": system_modes,
            "scheduler_status": {
                "running": bool(scheduler_running)
            },
            "vps_resources": {
                "cpu": {
                    "usage_percent": round(cpu_percent, 2),
                    "count": cpu_count,
                    "load_average": load_info
                },
                "memory": {
                    "total_gb": round(memory_total_gb, 2),
                    "used_gb": round(memory_used_gb, 2),
                    "free_gb": round(memory_free_gb, 2),
                    "usage_percent": round(memory_percent, 2)
                },
                "disk": {
                    "total_gb": round(disk_total_gb, 2),
                    "used_gb": round(disk_used_gb, 2),
                    "free_gb": round(disk_free_gb, 2),
                    "usage_percent": disk_percent
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
