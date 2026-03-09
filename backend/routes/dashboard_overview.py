"""
Dashboard Overview Endpoint - Consolidated Stats

Provides a single endpoint for all dashboard overview metrics:
- Total profit, daily/weekly/monthly profit
- Bot counts (active/paused/training)
- System mode flags
- Bodyguard status
- Last trade info
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
import logging
from typing import Dict, Optional

from auth import get_current_user
import database as db
from routes.system_mode import get_system_mode

logger = logging.getLogger(__name__)
router = APIRouter()

OVERVIEW_SNAPSHOT_KEYS = [
    "systemMode",
    "activeBots",
    "openPositions",
    "totalProfit",
    "winRate",
    "todaysTrades",
    "riskLevel",
    "lastRebalance",
    "nextReinvest",
]


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@router.get("/api/dashboard/overview")
async def get_dashboard_overview(user_id: str = Depends(get_current_user)):
    """
    Get consolidated dashboard overview stats
    
    Returns:
        - total_profit: Overall profit across all bots
        - daily_profit: Profit today
        - weekly_profit: Profit this week
        - monthly_profit: Profit this month
        - active_bots: Count of active bots
        - paused_bots: Count of paused bots
        - training_bots: Count of bots in training
        - total_bots: Total bot count
        - last_trade_time: Timestamp of most recent trade
        - system_mode: paper_trading/live_trading/autonomous flags
        - bodyguard_status: Daily loss lock status
        - total_trades: Total number of trades
        - win_rate: Percentage of winning trades
    """
    try:
        # Get all user's bots (exclude deleted)
        bots = await db.bots_collection.find({
            "user_id": user_id,
            "status": {"$ne": "deleted"},
            "deleted_at": {"$exists": False}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate bot counts
        active_bots = sum(1 for b in bots if b.get("status") == "active")
        paused_bots = sum(1 for b in bots if b.get("status") == "paused")
        training_bots = sum(1 for b in bots if b.get("status") in ["training", "quarantined"])
        total_bots = len(bots)
        
        # Calculate total profit from bots
        total_profit = sum(b.get("total_profit", 0) for b in bots)
        
        # Get user info for profile-derived fields
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # System modes (canonical source: system_modes collection)
        canonical_mode = await get_system_mode(user_id)
        system_mode = {
            "paper_trading": bool(canonical_mode.get("paperTrading", False)),
            "live_trading": bool(canonical_mode.get("liveTrading", False)),
            "autopilot": bool(canonical_mode.get("autopilot", False)),
            # Backward-compatible alias used by some older frontend cards
            "autonomous": bool(canonical_mode.get("autopilot", False)),
        }
        
        # Bodyguard/risk lock status
        bodyguard_status = {
            "locked": user.get("daily_loss_lock_active", False),
            "reason": user.get("daily_loss_locked_reason"),
            "locked_at": user.get("daily_loss_locked_at"),
            "loss_pct": user.get("daily_loss_pct")
        }
        
        # Calculate time-based profits from trades
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        # Get trades for time calculations
        bot_ids = [b["id"] for b in bots]
        
        if bot_ids:
            # Today's profit
            daily_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": today_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            daily_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in daily_trades)
            
            # Weekly profit
            weekly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": week_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            weekly_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in weekly_trades)
            
            # Monthly profit
            monthly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": month_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            monthly_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in monthly_trades)
            
            # Total trades and win rate
            all_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            
            total_trades = len(all_trades)
            winning_trades = sum(1 for t in all_trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Last trade time
            last_trade = await db.trades_collection.find_one(
                {"bot_id": {"$in": bot_ids}},
                {"_id": 0, "timestamp": 1},
                sort=[("timestamp", -1)]
            )
            last_trade_time = last_trade.get("timestamp") if last_trade else None
        else:
            # No bots
            daily_profit = 0
            weekly_profit = 0
            monthly_profit = 0
            total_trades = 0
            win_rate = 0
            last_trade_time = None
        
        return {
            "success": True,
            "total_profit": round(total_profit, 2),
            "daily_profit": round(daily_profit, 2),
            "weekly_profit": round(weekly_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "active_bots": active_bots,
            "paused_bots": paused_bots,
            "training_bots": training_bots,
            "total_bots": total_bots,
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "last_trade_time": last_trade_time,
            "system_mode": system_mode,
            "bodyguard_status": bodyguard_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/overview/snapshot")
async def get_overview_snapshot(user_id: str = Depends(get_current_user)):
    """
    Enhanced overview snapshot - SINGLE SOURCE OF TRUTH for all dashboard metrics

    Returns comprehensive snapshot including:
    - Profit metrics (total, today, gross, net)
    - Fee metrics (total fees, today fees)
    - Trade metrics (count, win rate)
    - Bot metrics (active, paused, training, quarantine) — derived from canonical service
    - Capital metrics (equity, required capital by platform)
    - Market prices (BTC/ZAR, ETH/ZAR, XRP/ZAR with source and % change)
    - Daily loss lock state
    - Trading mode flags

    ALL dashboard tiles must use this endpoint. No duplicated calculations.
    """
    try:
        from services.overview_service import overview_service
        from services.canonical import get_canonical_bot_counts

        # Get complete snapshot from centralized service
        snapshot = await overview_service.get_snapshot(user_id)
        user_doc = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "risk_profile": 1}
        )
        risk_level = (user_doc or {}).get("risk_profile") or "balanced"

        mode_flags = snapshot.get("trading_mode_flags") or {}
        if mode_flags.get("live_trading"):
            system_mode = "live"
        elif mode_flags.get("autopilot"):
            system_mode = "autopilot"
        else:
            system_mode = "paper"

        open_positions = 0
        if db.positions_collection is not None:
            try:
                open_positions = await db.positions_collection.count_documents({
                    "user_id": user_id,
                    "status": {"$ne": "closed"}
                })
            except Exception:
                open_positions = await db.positions_collection.count_documents({"user_id": user_id})

        # Canonical bot counts — guaranteed consistent with /api/bots/status
        counts = await get_canonical_bot_counts(user_id)

        normalized_snapshot = {
            "systemMode": system_mode,
            "activeBots": counts["active"],
            "runnableBots": counts["runnable"],
            "totalBots": counts["total"],
            "openPositions": _safe_int(open_positions),
            "totalProfit": round(_safe_float(snapshot.get("total_profit", 0)), 2),
            "winRate": round(_safe_float(snapshot.get("win_rate", 0)), 2),
            "todaysTrades": _safe_int(snapshot.get("trades_today", 0)),
            "riskLevel": risk_level.replace("_", " ").title(),
            "lastRebalance": snapshot.get("last_rebalance") or "Not available",
            "nextReinvest": snapshot.get("next_reinvest") or "Not available",
        }

        return {
            **normalized_snapshot
        }

    except Exception as e:
        logger.error(f"Overview snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
