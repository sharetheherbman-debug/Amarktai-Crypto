"""
System Status Endpoint
Reports feature flags, scheduler status, and trading activity
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import logging
import os

from auth import get_current_user
from utils.env_utils import env_bool
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Status"])


@router.get("/status")
async def get_system_status(user_id: str = Depends(get_current_user)):
    """
    Get system status including:
    - Feature flags (trading, schedulers, autopilot)
    - Trading mode flags (paper/live)
    - Scheduler running status
    - Last trade time
    - Last tick time
    - Database health
    """
    try:
        # Get feature flags using consistent parsing
        feature_flags = {
            "enable_trading": env_bool('ENABLE_TRADING', False),
            "enable_schedulers": env_bool('ENABLE_SCHEDULERS', False),
            "enable_autopilot": env_bool('ENABLE_AUTOPILOT', False),
            "enable_ccxt": env_bool('ENABLE_CCXT', True)
        }
        
        # Get trading mode flags (paper/live) - these are separate from feature flags
        trading_mode_flags = {
            "paper_trading": env_bool('PAPER_TRADING', False),
            "live_trading": env_bool('LIVE_TRADING', False)
        }
        
        # Check scheduler status - Safe handling like system_health.py
        scheduler_status = {}
        try:
            from trading_scheduler import trading_scheduler
            
            # Safe check for is_running (could be callable, boolean, or missing)
            if hasattr(trading_scheduler, 'is_running'):
                is_running = trading_scheduler.is_running
                # Handle if it's a callable
                if callable(is_running):
                    running_status = "running" if is_running() else "stopped"
                else:
                    # It's a boolean attribute
                    running_status = "running" if is_running else "stopped"
            else:
                running_status = "unknown"
                
            scheduler_status["trading_scheduler"] = {
                "running": running_status,
                "enabled": feature_flags["enable_trading"]
            }
        except Exception as e:
            logger.warning(f"Could not check trading_scheduler status: {e}")
            scheduler_status["trading_scheduler"] = {
                "running": "unknown",
                "enabled": feature_flags["enable_trading"]
            }
        
        # Get last trade time for user
        last_trade = None
        last_trade_time = None
        try:
            last_trade = await db.trades_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "timestamp": 1, "symbol": 1, "side": 1, "profit_loss": 1},
                sort=[("timestamp", -1)]
            )
            if last_trade:
                last_trade_time = last_trade.get("timestamp")
        except Exception as e:
            logger.error(f"Error fetching last trade: {e}")
        
        # Get system health
        db_health = await db.health_check()
        
        # Get active bots count
        active_bots_count = 0
        try:
            active_bots_count = await db.bots_collection.count_documents({
                "user_id": user_id,
                "status": "active"
            })
        except Exception as e:
            logger.error(f"Error counting active bots: {e}")
        
        # Get system modes (user-specific settings)
        system_modes = {}
        try:
            modes = await db.system_modes_collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            if modes:
                system_modes = {
                    "paper_trading": modes.get("paperTrading", False),
                    "live_trading": modes.get("liveTrading", False),
                    "autonomous": modes.get("autonomous", False)
                }
        except Exception as e:
            logger.error(f"Error fetching system modes: {e}")
        
        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feature_flags": feature_flags,
            "trading_mode_flags": trading_mode_flags,
            "scheduler_status": scheduler_status,
            "database": {
                "connected": db_health.get("status") == "connected",
                "database_name": db_health.get("database")
            },
            "trading_activity": {
                "active_bots": active_bots_count,
                "last_trade": last_trade,
                "last_trade_time": last_trade_time
            },
            "system_modes": system_modes
        }
        
    except Exception as e:
        logger.error(f"System status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/since-last-login")
async def get_since_last_login(user_id: str = Depends(get_current_user)):
    """
    Get activity since last login:
    - Updates last_login timestamp
    - Returns system modes, active bots, recent trades, alerts
    - Returns notes describing activity
    """
    try:
        now = datetime.now(timezone.utc)
        
        # Get user's last login and update it
        user = await db.users_collection.find_one({"_id": user_id}, {"last_login": 1})
        last_login = user.get("last_login") if user else None
        
        # Update last_login to now
        await db.users_collection.update_one(
            {"_id": user_id},
            {"$set": {"last_login": now}},
            upsert=False
        )
        
        # Get system modes
        modes = await db.system_modes_collection.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
        system_modes = {
            "paperTrading": modes.get("paperTrading", False) if modes else False,
            "liveTrading": modes.get("liveTrading", False) if modes else False,
            "autopilot": modes.get("autopilot", False) if modes else False
        }
        
        # Get active bots count
        active_bots = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "active"
        })
        
        # Get recent trades (last 24h)
        cutoff_24h = now - timedelta(hours=24)
        recent_trades_count = 0
        last_trade_time = None
        
        if last_login:
            # Count trades since last login
            recent_trades_count = await db.trades_collection.count_documents({
                "user_id": user_id,
                "timestamp": {"$gte": cutoff_24h}
            })
        
        # Get last trade time
        last_trade = await db.trades_collection.find_one(
            {"user_id": user_id},
            {"timestamp": 1},
            sort=[("timestamp", -1)]
        )
        if last_trade:
            last_trade_time = last_trade.get("timestamp")
        
        # Get alerts count (if alerts collection exists)
        alerts_count = 0
        try:
            if last_login:
                alerts_count = await db.alerts_collection.count_documents({
                    "user_id": user_id,
                    "timestamp": {"$gte": last_login}
                })
        except Exception:
            pass  # alerts collection may not exist
        
        # Build activity notes
        notes = []
        if not last_login:
            notes.append("First login - welcome!")
        else:
            time_away = (now - last_login).total_seconds()
            if time_away < 3600:
                notes.append(f"Welcome back! You were away for {int(time_away / 60)} minutes")
            elif time_away < 86400:
                notes.append(f"Welcome back! You were away for {int(time_away / 3600)} hours")
            else:
                notes.append(f"Welcome back! You were away for {int(time_away / 86400)} days")
            
            if recent_trades_count > 0:
                notes.append(f"{recent_trades_count} trade(s) executed in the last 24 hours")
            
            if active_bots > 0:
                notes.append(f"{active_bots} bot(s) currently active")
            else:
                notes.append("No active bots")
            
            if alerts_count > 0:
                notes.append(f"{alerts_count} new alert(s)")
        
        return {
            "success": True,
            "last_login": last_login.isoformat() if last_login else None,
            "now": now.isoformat(),
            "paperTrading": system_modes["paperTrading"],
            "liveTrading": system_modes["liveTrading"],
            "autopilot": system_modes["autopilot"],
            "active_bots": active_bots,
            "recent_trades_count": recent_trades_count,
            "last_trade_time": last_trade_time.isoformat() if last_trade_time else None,
            "alerts_count": alerts_count,
            "notes": notes
        }
        
    except Exception as e:
        logger.error(f"Since last login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint (no auth required)
    Returns 200 if system is operational
    """
    try:
        # Check database connection
        db_health = await db.health_check()
        
        if db_health.get("status") != "connected":
            raise HTTPException(status_code=503, detail="Database not connected")
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "connected"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
