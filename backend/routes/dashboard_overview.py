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
from services.fx_normalizer import get_fx_rate as _gfr, get_quote_currency as _gqc

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


def _sum_pnl_zar(trades) -> float:
    """Sum trade P&L normalised to ZAR — uses realized_pnl_zar when available,
    otherwise converts via the trade's quote currency FX rate."""
    total = 0.0
    for t in trades:
        pnl_zar = t.get("realized_pnl_zar")
        if pnl_zar is not None:
            total += float(pnl_zar)
        else:
            raw_pnl = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
            qc = t.get("quote_currency") or _gqc(t.get("exchange", ""), "")
            rate, _ = _gfr(qc, "ZAR")
            total += raw_pnl * rate
    return total


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
        
        # Calculate total profit from bots — normalised to ZAR
        total_profit = 0.0
        for b in bots:
            raw_profit = float(b.get("total_profit", 0) or 0)
            qc = b.get("quote_currency") or _gqc(b.get("exchange", ""), "")
            rate, _ = _gfr(qc, "ZAR")
            total_profit += raw_profit * rate
        
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
            # Today's profit — normalised to ZAR using realized_pnl_zar or FX conversion
            daily_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": today_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1, "realized_pnl_zar": 1,
                "quote_currency": 1, "exchange": 1}).to_list(10000)
            daily_profit = _sum_pnl_zar(daily_trades)
            
            # Weekly profit — normalised to ZAR
            weekly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": week_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1, "realized_pnl_zar": 1,
                "quote_currency": 1, "exchange": 1}).to_list(10000)
            weekly_profit = _sum_pnl_zar(weekly_trades)
            
            # Monthly profit — normalised to ZAR
            monthly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": month_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1, "realized_pnl_zar": 1,
                "quote_currency": 1, "exchange": 1}).to_list(10000)
            monthly_profit = _sum_pnl_zar(monthly_trades)
            
            # Total trades and win rate
            all_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1, "realized_pnl_zar": 1,
                "quote_currency": 1, "exchange": 1}).to_list(10000)
            
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
async def get_overview_snapshot(
    user_id: str = Depends(get_current_user),
    display_currency: Optional[str] = None,
):
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

    ALL monetary values are in the user's *display_currency* preference
    (default: ZAR).  The preference is read from the user document; the
    optional ``?display_currency=`` query parameter overrides it for that
    request only.

    ALL dashboard tiles must use this endpoint. No duplicated calculations.
    """
    try:
        from services.overview_service import overview_service
        from services.canonical import get_canonical_bot_activity, get_canonical_open_position_count

        # Resolve display_currency: query param > user profile > ZAR
        if display_currency is None:
            user_doc_prefs = await db.users_collection.find_one(
                {"id": user_id},
                {"_id": 0, "display_currency": 1, "risk_profile": 1}
            )
            display_currency = (user_doc_prefs or {}).get("display_currency", "ZAR")
            risk_level = (user_doc_prefs or {}).get("risk_profile") or "balanced"
        else:
            user_doc_prefs = await db.users_collection.find_one(
                {"id": user_id},
                {"_id": 0, "risk_profile": 1}
            )
            risk_level = (user_doc_prefs or {}).get("risk_profile") or "balanced"

        dc = str(display_currency or "ZAR").upper()

        # Get complete snapshot from centralized service (converted to dc)
        snapshot = await overview_service.get_snapshot(user_id, display_currency=dc)

        mode_flags = snapshot.get("trading_mode_flags") or {}
        if mode_flags.get("live_trading"):
            system_mode = "live"
        elif mode_flags.get("paper_trading"):
            system_mode = "paper"
        else:
            system_mode = "testing"
        automation_mode = "autopilot" if mode_flags.get("autopilot") else "manual"

        open_positions = await get_canonical_open_position_count(user_id)

        # Canonical bot activity semantics — guaranteed consistent with /api/bots/status
        activity = await get_canonical_bot_activity(user_id)

        normalized_snapshot = {
            "systemMode": system_mode,
            "automationMode": automation_mode,
            "activeBots": activity["active_bot_records"],
            "runnableBots": activity["runnable_active_bots"],
            "totalBots": activity["total_bot_records"],
            "pausedBots": activity["paused_bots"],
            "blockedBots": activity["blocked_bots"],
            "openPositions": _safe_int(open_positions),
            "totalProfit": round(_safe_float(snapshot.get("total_profit", 0)), 2),
            "winRate": round(_safe_float(snapshot.get("win_rate", 0)), 2),
            "todaysTrades": _safe_int(snapshot.get("trades_today", 0)),
            "riskLevel": risk_level.replace("_", " ").title(),
            "lastRebalance": snapshot.get("last_rebalance") or "Not available",
            "nextReinvest": snapshot.get("next_reinvest") or "Not available",
            # Display currency metadata — frontend uses this to format symbols
            "display_currency": dc,
            "fx_metadata": snapshot.get("fx_metadata", {}),
        }

        return {**normalized_snapshot, "activity": activity}

    except Exception as e:
        logger.error(f"Overview snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
