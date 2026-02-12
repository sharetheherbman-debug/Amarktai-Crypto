"""
Metrics API - Trade cadence and countdown metrics
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("/trade-cadence")
async def get_trade_cadence(user_id: str = Depends(get_current_user)):
    """Get trade cadence and countdown metrics
    
    Only starts countdown after >= 10 trades
    Computes rolling average trade interval from last 30 trades
    
    Returns:
        - next_trade_eta: ISO timestamp of estimated next trade
        - avg_interval_seconds: Average seconds between trades (last 30)
        - avg_interval_display: Human-readable interval (e.g., "2h 30m")
        - trades_total: Total number of closed trades
        - countdown_active: Whether countdown is active (>= 10 trades)
        - last_trade_at: Timestamp of most recent trade
    """
    try:
        # Get all closed trades for user, sorted by timestamp descending
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "status": "closed"
            },
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
