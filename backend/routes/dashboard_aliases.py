"""
Dashboard Alias Routes
Provides alternative URLs for dashboard sections to prevent 404s
All routes forward to canonical handlers
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
import logging

from auth import get_current_user
from models import User

logger = logging.getLogger(__name__)

# Create alias router
router = APIRouter(prefix="/api", tags=["Dashboard Aliases"])


# ============================================================================
# Whale Flow Aliases
# Canonical: /api/advanced/whale/*
# Aliases: /api/whale-flow/*
# ============================================================================

@router.get("/whale-flow/summary")
async def whale_flow_summary_alias(current_user: User = Depends(get_current_user)):
    """Alias for /api/advanced/whale/summary"""
    try:
        from routes.advanced_trading_endpoints import get_whale_summary
        return await get_whale_summary(current_user)
    except Exception as e:
        logger.error(f"Whale flow summary alias error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whale-flow/{coin}")
async def whale_flow_coin_alias(
    coin: str,
    current_user: User = Depends(get_current_user)
):
    """Alias for /api/advanced/whale/{coin}"""
    try:
        from routes.advanced_trading_endpoints import get_whale_signal
        return await get_whale_signal(coin, current_user)
    except Exception as e:
        logger.error(f"Whale flow coin alias error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Decision Trace REST Endpoint
# WebSocket: /ws/decisions
# REST Fallback: /api/decision-trace/latest
# ============================================================================

@router.get("/decision-trace/latest")
async def get_decision_trace_latest(
    limit: int = 50,
    user_id: str = Depends(get_current_user)
):
    """
    Get latest decision events via REST (fallback for WebSocket)
    Returns recent autonomous decision logs
    """
    try:
        import database as db
        
        # Fetch recent decision events from database
        decisions_cursor = db.db["decision_logs"].find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(limit)
        
        decisions = await decisions_cursor.to_list(limit)
        
        # Format for frontend
        formatted_decisions = []
        for decision in decisions:
            formatted_decisions.append({
                "id": str(decision.get("_id", "")),
                "timestamp": decision.get("timestamp", ""),
                "bot_id": decision.get("bot_id", ""),
                "decision_type": decision.get("decision_type", ""),
                "action": decision.get("action", ""),
                "reason": decision.get("reason", ""),
                "confidence": decision.get("confidence", 0.0),
                "metadata": decision.get("metadata", {})
            })
        
        return {
            "success": True,
            "decisions": formatted_decisions,
            "total": len(formatted_decisions),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Decision trace error: {e}")
        # Return empty list instead of error to prevent UI breakage
        return {
            "success": True,
            "decisions": [],
            "total": 0,
            "limit": limit,
            "note": "No decision logs available or collection not initialized"
        }


# ============================================================================
# Metrics Summary Endpoint
# Canonical Prometheus: /api/metrics (text format)
# JSON Summary: /api/metrics/summary
# ============================================================================

@router.get("/metrics/summary")
async def get_metrics_summary(user_id: str = Depends(get_current_user)):
    """
    Get structured metrics summary for dashboard
    Returns JSON instead of Prometheus text format
    """
    try:
        import database as db
        from datetime import datetime, timezone, timedelta
        from services.canonical_metrics import get_canonical_metrics_snapshot
        from services.canonical import get_canonical_bot_counts
        
        bots_cursor = db.bots_collection.find({
            "user_id": user_id,
            "status": {"$nin": ["deleted", "marked_for_deletion"]},
            "deleted": {"$ne": True},
            "is_deleted": {"$ne": True},
            "deleted_at": {"$exists": False},
        })
        bots = await bots_cursor.to_list(1000)
        canonical = await get_canonical_metrics_snapshot(user_id, bots=bots)
        summary = canonical.get("summary", {})
        bot_counts = await get_canonical_bot_counts(user_id)
        
        total_bots = bot_counts.get("total", 0)
        active_bots = bot_counts.get("active", 0)
        paused_bots = bot_counts.get("paused", 0)
        
        # Get recent trades count (last 24h)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_trades = await db.trades_collection.count_documents({
            "user_id": user_id,
            "timestamp": {"$gte": yesterday.isoformat()}
        })
        winning_trades = summary.get("winning_trades", 0)
        losing_trades = summary.get("losing_trades", 0)
        total_profit = summary.get("profit_realized", 0)
        win_rate = summary.get("win_rate_pct", 0)
        
        return {
            "success": True,
            "metrics": {
                "bots": {
                    "total": total_bots,
                    "active": active_bots,
                    "paused": paused_bots,
                },
                "trades": {
                    "total": summary.get("trade_count", 0),
                    "recent_24h": recent_trades,
                    "winning": winning_trades,
                    "losing": losing_trades
                },
                "performance": {
                    "total_profit": round(total_profit, 2),
                    "win_rate": round(win_rate, 2)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Metrics summary error: {e}")
        # Return safe empty metrics instead of error
        return {
            "success": True,
            "metrics": {
                "bots": {"total": 0, "active": 0, "paused": 0},
                "trades": {"total": 0, "recent_24h": 0, "winning": 0, "losing": 0},
                "performance": {"total_profit": 0, "win_rate": 0},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
