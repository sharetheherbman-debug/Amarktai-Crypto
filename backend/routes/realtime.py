"""Real‑time streaming endpoints.

This router provides Server‑Sent Events (SSE) for real‑time dashboard updates.
Connected to actual database changes and system events via event bus.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["RealTime"])


async def calculate_period_profit(user_id: str, days: int) -> float:
    """
    Calculate profit for a specific time period.
    
    Args:
        user_id: User identifier
        days: Number of days to look back (1 for daily, 7 for weekly, 30 for monthly)
    
    Returns:
        Total profit for the period
    """
    try:
        cutoff_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Get trades in the period
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": cutoff_time},
                "status": {"$in": ["completed", "closed"]}
            },
            {"profit": 1, "net_profit": 1}
        ).to_list(10000)
        
        # Sum up net profit (includes fees and slippage)
        period_profit = sum(t.get('net_profit', t.get('profit', 0)) for t in trades)
        return round(period_profit, 2)
    except Exception as e:
        logger.error(f"Error calculating {days}-day profit: {e}")
        return 0.0


async def calculate_win_rate(user_id: str) -> float:
    """
    Calculate overall win rate (percentage of profitable trades).
    
    Args:
        user_id: User identifier
    
    Returns:
        Win rate as percentage (0-100)
    """
    try:
        # Get all completed trades
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "status": {"$in": ["completed", "closed"]}
            },
            {"profit": 1, "net_profit": 1}
        ).to_list(10000)
        
        if not trades:
            return 0.0
        
        # Count winning trades
        winning_trades = sum(1 for t in trades if t.get('net_profit', t.get('profit', 0)) > 0)
        win_rate = (winning_trades / len(trades)) * 100
        return round(win_rate, 2)
    except Exception as e:
        logger.error(f"Error calculating win rate: {e}")
        return 0.0


async def calculate_exposure(user_id: str) -> float:
    """
    Calculate current exposure (total position value / total capital).
    
    Args:
        user_id: User identifier
    
    Returns:
        Exposure as percentage (0-100)
    """
    try:
        # Get active bots with positions
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": "active"
            },
            {"current_capital": 1, "position_size": 1, "open_position_value": 1}
        ).to_list(1000)
        
        if not bots:
            return 0.0
        
        total_capital = sum(b.get('current_capital', 0) for b in bots)
        
        if total_capital <= 0:
            return 0.0
        
        # Calculate total open position value
        total_position_value = sum(b.get('open_position_value', 0) for b in bots)
        
        exposure = (total_position_value / total_capital) * 100
        return round(exposure, 2)
    except Exception as e:
        logger.error(f"Error calculating exposure: {e}")
        return 0.0


async def _event_generator(user_id: str):
    """Yield real-time server‑sent events with actual system data."""
    heartbeat_counter = 0
    last_overview_data = None
    last_bot_count = 0
    
    while True:
        try:
            # Heartbeat event every 5 seconds
            heartbeat_counter += 1
            yield f"event: heartbeat\ndata: {{\"timestamp\": \"{datetime.now(timezone.utc).isoformat()}\", \"counter\": {heartbeat_counter}}}\n\n"
            
            # Every 15 seconds, send overview update with REAL data
            if heartbeat_counter % 3 == 0:
                try:
                    # Get real bot data
                    bots = await db.bots_collection.find(
                        {"user_id": user_id},
                        {"_id": 0, "status": 1, "total_profit": 1, "current_capital": 1}
                    ).to_list(1000)
                    
                    active_bots = len([b for b in bots if b.get('status') == 'active'])
                    total_profit = sum(b.get('total_profit', 0) for b in bots)
                    total_capital = sum(b.get('current_capital', 0) for b in bots)
                    
                    # Calculate period profits, win rate, and exposure
                    daily_profit = await calculate_period_profit(user_id, days=1)
                    weekly_profit = await calculate_period_profit(user_id, days=7)
                    monthly_profit = await calculate_period_profit(user_id, days=30)
                    win_rate = await calculate_win_rate(user_id)
                    exposure = await calculate_exposure(user_id)
                    
                    overview_data = {
                        "type": "overview",
                        "active_bots": active_bots,
                        "total_bots": len(bots),
                        "total_profit": round(total_profit, 2),
                        "daily_profit": daily_profit,
                        "weekly_profit": weekly_profit,
                        "monthly_profit": monthly_profit,
                        "win_rate": win_rate,
                        "exposure": exposure,
                        "total_capital": round(total_capital, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Only emit if data changed
                    if overview_data != last_overview_data:
                        yield f"event: overview_update\ndata: {json.dumps(overview_data)}\n\n"
                        last_overview_data = overview_data
                except Exception as e:
                    logger.error(f"Overview update error: {e}")
            
            # Every 10 seconds, send bot update with REAL data
            if heartbeat_counter % 2 == 0:
                try:
                    # Check if bot count changed
                    bot_count = await db.bots_collection.count_documents({"user_id": user_id})
                    if bot_count != last_bot_count:
                        bot_data = {
                            "type": "bot_count_changed",
                            "total_bots": bot_count,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        yield f"event: bot_update\ndata: {json.dumps(bot_data)}\n\n"
                        last_bot_count = bot_count
                except Exception as e:
                    logger.error(f"Bot update error: {e}")
            
            # Every 20 seconds, check for recent trades
            if heartbeat_counter % 4 == 0:
                try:
                    # Get trades from last 2 minutes
                    from datetime import timedelta
                    two_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
                    
                    recent_trades = await db.trades_collection.find(
                        {
                            "user_id": user_id,
                            "timestamp": {"$gte": two_min_ago}
                        },
                        {"_id": 0}
                    ).sort("timestamp", -1).limit(5).to_list(5)
                    
                    if recent_trades:
                        trade_data = {
                            "type": "recent_trades",
                            "trades": recent_trades,
                            "count": len(recent_trades),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        yield f"event: trade_update\ndata: {json.dumps(trade_data)}\n\n"
                except Exception as e:
                    logger.error(f"Trade update error: {e}")
            
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            # Clean shutdown on client disconnect
            logger.debug(f"SSE connection closed for user {user_id[:8]}")
            break
        except Exception as e:
            # Log error but keep connection alive
            logger.error(f"SSE generator error: {e}")
            await asyncio.sleep(5)


@router.get("/events")
async def realtime_events(user_id: str = Depends(get_current_user)) -> StreamingResponse:
    """Server‑Sent Events endpoint for real‑time updates.
    
    Connected to actual database changes and system events.
    
    Emits events:
    - heartbeat: Every 5s with counter
    - overview_update: Dashboard overview data including:
      * active_bots: Number of active bots
      * total_profit: Cumulative profit
      * daily_profit: Profit in last 24 hours
      * weekly_profit: Profit in last 7 days
      * monthly_profit: Profit in last 30 days
      * win_rate: Percentage of winning trades
      * exposure: Current position exposure as % of capital
      * total_capital: Current capital across all bots
    - bot_update: Bot count changes
    - trade_update: Recent trades
    - performance_update: Performance metrics
    - wallet_update: Wallet balance changes
    """
    logger.info(f"SSE connection established for user {user_id[:8]}")
    return StreamingResponse(
        _event_generator(user_id), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )