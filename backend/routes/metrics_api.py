"""
Metrics API - Trade cadence, countdown metrics, and system performance metrics
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import time

from auth import get_current_user
import database as db
from services.bot_filters import bot_not_deleted_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])

# Cache for system metrics (avoid hammering DB + CoinStats)
_system_metrics_cache: Optional[dict] = None
_system_metrics_cache_at: float = 0.0
_SYSTEM_METRICS_TTL = 90  # seconds


@router.get("/trade-cadence")
async def get_trade_cadence(
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    user_id: str = Depends(get_current_user),
):
    """Get trade cadence and countdown metrics
    
    Only starts countdown after >= 10 trades
    Computes rolling average trade interval from last 30 trades
    
    Args:
        bot_type: Optional filter by bot type (normal or scalper)
    
    Returns:
        - next_trade_eta: ISO timestamp of estimated next trade
        - avg_interval_seconds: Average seconds between trades (last 30)
        - avg_interval_display: Human-readable interval (e.g., "2h 30m")
        - trades_total: Total number of closed trades
        - countdown_active: Whether countdown is active (>= 10 trades)
        - last_trade_at: Timestamp of most recent trade
    """
    try:
        trade_query = {
            "user_id": user_id,
            "status": "closed"
        }
        if bot_type:
            matching_bots = await db.bots_collection.find(
                bot_not_deleted_filter({"user_id": user_id, "bot_type": bot_type}),
                {"_id": 0, "id": 1}
            ).to_list(200)
            bot_ids = [b["id"] for b in matching_bots]
            trade_query["bot_id"] = {"$in": bot_ids}

        # Get all closed trades for user, sorted by timestamp descending
        trades = await db.trades_collection.find(
            trade_query,
            {
                "_id": 0,
                "timestamp": 1,
                "id": 1
            }
        ).sort("timestamp", -1).to_list(50)  # Get last 50 to ensure we have enough
        
        trades_total = len(trades)
        
        if trades_total < 10:
            # Not enough trades for countdown
            return {
                "countdown_active": False,
                "trades_total": trades_total,
                "trades_needed": 10 - trades_total,
                "next_trade_eta": None,
                "avg_interval_seconds": None,
                "avg_interval_display": "N/A",
                "last_trade_at": trades[0]["timestamp"] if trades else None,
                "message": f"Need {10 - trades_total} more trades to activate countdown"
            }
        
        # Use last 30 trades to calculate average interval
        last_30_trades = trades[:30]
        
        # Parse timestamps and calculate intervals
        timestamps = []
        for trade in last_30_trades:
            try:
                ts = datetime.fromisoformat(trade["timestamp"].replace("Z", "+00:00"))
                timestamps.append(ts)
            except Exception as e:
                logger.warning(f"Failed to parse trade timestamp: {e}")
                continue
        
        if len(timestamps) < 2:
            # Not enough valid timestamps
            return {
                "countdown_active": False,
                "trades_total": trades_total,
                "next_trade_eta": None,
                "avg_interval_seconds": None,
                "avg_interval_display": "N/A",
                "last_trade_at": trades[0]["timestamp"] if trades else None,
                "message": "Insufficient valid timestamps"
            }
        
        # Sort timestamps (should already be sorted, but ensure)
        timestamps.sort(reverse=True)
        
        # Calculate intervals between consecutive trades
        intervals = []
        for i in range(len(timestamps) - 1):
            interval = (timestamps[i] - timestamps[i + 1]).total_seconds()
            if interval > 0:  # Ignore zero or negative intervals
                intervals.append(interval)
        
        if not intervals:
            return {
                "countdown_active": False,
                "trades_total": trades_total,
                "next_trade_eta": None,
                "avg_interval_seconds": None,
                "avg_interval_display": "N/A",
                "last_trade_at": trades[0]["timestamp"] if trades else None,
                "message": "No valid intervals calculated"
            }
        
        # Calculate rolling average
        avg_interval_seconds = sum(intervals) / len(intervals)
        
        # Calculate next trade ETA
        last_trade_time = timestamps[0]
        next_trade_eta = last_trade_time + timedelta(seconds=avg_interval_seconds)
        
        # Format interval for display
        avg_interval_display = _format_interval(avg_interval_seconds)
        
        # Time until next trade
        now = datetime.now(timezone.utc)
        time_until_next = (next_trade_eta - now).total_seconds()
        
        return {
            "countdown_active": True,
            "trades_total": trades_total,
            "next_trade_eta": next_trade_eta.isoformat(),
            "time_until_next_seconds": max(0, time_until_next),
            "time_until_next_display": _format_interval(max(0, time_until_next)),
            "avg_interval_seconds": round(avg_interval_seconds, 0),
            "avg_interval_display": avg_interval_display,
            "last_trade_at": last_trade_time.isoformat(),
            "intervals_calculated": len(intervals),
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get trade cadence error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _format_interval(seconds: float) -> str:
    """Format seconds into human-readable interval"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    else:
        days = int(seconds / 86400)
        hours = int((seconds % 86400) / 3600)
        return f"{days}d {hours}h" if hours > 0 else f"{days}d"


@router.get("/system")
async def get_system_metrics(user_id: str = Depends(get_current_user)):
    """
    GET /api/metrics/system

    Returns real-time trading performance metrics + CoinStats market intelligence.

    Trading section:
      - net_pnl: Total realised profit/loss (ZAR)
      - win_rate: Percentage of winning closed trades
      - trade_count: Total number of closed trades
      - last_trade_at: ISO timestamp of most recent trade
      - max_drawdown_pct: Worst peak-to-trough drawdown across all bots

    Market intelligence section (from CoinStats, cached 90 s):
      - mood: positive | negative | neutral
      - brief: Top headline or summary
      - top_risk: Detected risk category (or "none")
      - source: Always "CoinStats"
      - last_updated: ISO timestamp of last intelligence fetch
    """
    global _system_metrics_cache, _system_metrics_cache_at

    now = datetime.now(timezone.utc)

    # ── Trading metrics (always fresh from DB) ────────────────────────────
    trading = {}
    try:
        closed_trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed"},
            {"_id": 0, "net_pnl": 1, "profit_loss": 1, "timestamp": 1}
        ).sort("timestamp", -1).to_list(1000)

        trade_count = len(closed_trades)
        pnl_values = [
            float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
            for t in closed_trades
        ]
        net_pnl = round(sum(pnl_values), 2)
        wins = sum(1 for v in pnl_values if v >= 0)
        win_rate = round((wins / trade_count * 100), 1) if trade_count > 0 else 0.0

        last_trade_at = None
        if closed_trades:
            last_trade_at = closed_trades[0].get("timestamp")

        # Max drawdown: worst cumulative loss trough
        max_drawdown_pct = 0.0
        if pnl_values:
            peak = 0.0
            trough_pct = 0.0
            running = 0.0
            for v in reversed(pnl_values):  # oldest first
                running += v
                if running > peak:
                    peak = running
                elif peak > 0:
                    dd = (peak - running) / peak * 100
                    if dd > trough_pct:
                        trough_pct = dd
            max_drawdown_pct = round(trough_pct, 2)

        trading = {
            "net_pnl": net_pnl,
            "win_rate": win_rate,
            "trade_count": trade_count,
            "last_trade_at": last_trade_at,
            "max_drawdown_pct": max_drawdown_pct,
        }
    except Exception as e:
        logger.error(f"System metrics: trading fetch error: {e}")
        trading = {
            "net_pnl": None, "win_rate": None,
            "trade_count": None, "last_trade_at": None,
            "max_drawdown_pct": None, "error": str(e)
        }

    # ── Market intelligence (CoinStats, cached) ───────────────────────────
    age = time.monotonic() - _system_metrics_cache_at
    if _system_metrics_cache is None or age > _SYSTEM_METRICS_TTL:
        try:
            from services.market_intelligence_service import get_latest_intelligence
            brief = await get_latest_intelligence()
            _system_metrics_cache = {
                "mood": brief.get("mood", "neutral"),
                "brief": brief.get("what_happened", "No data yet"),
                "top_risk": brief.get("top_risk", "none"),
                "confidence": brief.get("confidence", "Unknown"),
                "source": brief.get("source", "CoinStats"),
                "last_updated": brief.get("updated_at"),
            }
            _system_metrics_cache_at = time.monotonic()
        except Exception as e:
            logger.error(f"System metrics: intelligence fetch error: {e}")
            if _system_metrics_cache is None:
                _system_metrics_cache = {
                    "mood": "neutral", "brief": "Market intelligence unavailable",
                    "top_risk": "none", "confidence": "Unknown",
                    "source": "CoinStats", "last_updated": None,
                }

    return {
        "trading": trading,
        "market_intelligence": _system_metrics_cache,
        "timestamp": now.isoformat(),
    }
