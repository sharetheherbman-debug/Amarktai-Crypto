"""
Trades API - Canonical trade history and metrics
Frontend calls GET /api/trades/recent?limit=50
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import Optional, List
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trades", tags=["Trades"])


@router.get("/ping")
async def trades_ping() -> dict:
    """Return a simple heartbeat response for trades checks."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/recent")
async def get_recent_trades(
    limit: int = Query(50, ge=1, le=500),
    user_id: str = Depends(get_current_user)
):
    """
    Get recent trades with date+time metrics
    Frontend calls this endpoint to display trade history
    
    Args:
        limit: Maximum number of trades to return (1-500)
        user_id: Current authenticated user
        
    Returns:
        List of trades with full timestamps and metrics
    """
    try:
        # Fetch recent trades sorted by timestamp descending
        trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Ensure all trades have proper date+time fields
        for trade in trades:
            # Ensure timestamp exists
            if 'timestamp' not in trade or not trade['timestamp']:
                trade['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Parse timestamp to ensure it's ISO format
            try:
                if isinstance(trade['timestamp'], str):
                    dt = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                elif isinstance(trade['timestamp'], datetime):
                    dt = trade['timestamp']
                else:
                    dt = datetime.now(timezone.utc)
                
                # Ensure timezone-aware
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                # Set formatted fields
                trade['timestamp'] = dt.isoformat()
                trade['date'] = dt.strftime('%Y-%m-%d')
                trade['time'] = dt.strftime('%H:%M:%S')
                
            except Exception as parse_error:
                logger.warning(f"Trade timestamp parse error: {parse_error}")
                now = datetime.now(timezone.utc)
                trade['timestamp'] = now.isoformat()
                trade['date'] = now.strftime('%Y-%m-%d')
                trade['time'] = now.strftime('%H:%M:%S')
        
        return {
            "trades": trades,
            "count": len(trades),
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get recent trades error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_trade_stats(
    user_id: str = Depends(get_current_user)
):
    """
    Get trade statistics summary
    
    Returns:
        Summary statistics for all user trades
    """
    try:
        # Get all trades
        trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(10000)
        
        if not trades:
            return {
                "total_trades": 0,
                "total_volume": 0,
                "total_pnl": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Calculate statistics
        total_trades = len(trades)
        total_volume = sum(abs(t.get('amount', 0) * t.get('price', 0)) for t in trades)
        total_pnl = sum(t.get('profit_loss', 0) for t in trades)
        winning_trades = len([t for t in trades if t.get('profit_loss', 0) > 0])
        losing_trades = len([t for t in trades if t.get('profit_loss', 0) < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "total_volume": round(total_volume, 2),
            "total_pnl": round(total_pnl, 2),
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get trade stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live")
async def get_live_trades(
    limit: int = Query(100, ge=1, le=500),
    user_id: str = Depends(get_current_user)
):
    """Live trade feed with enriched payload (D)
    
    Returns recent trades with full details for live feed display:
    - Bot info (id, name, exchange)
    - Symbol/pair, side, quantity
    - Entry/exit prices
    - Gross profit/loss, fees, net profit/loss
    - Strategy tag or signal reason
    - Timestamps
    
    Args:
        limit: Maximum number of trades to return (1-500)
        user_id: Current authenticated user
        
    Returns:
        Enriched trade feed for live updates
    """
    try:
        # Fetch recent trades sorted by timestamp descending
        trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Get bot names for enrichment
        bot_ids = list(set(t.get('bot_id') for t in trades if t.get('bot_id')))
        bots = await db.bots_collection.find(
            {"id": {"$in": bot_ids}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(1000)
        bot_names = {bot['id']: bot.get('name') for bot in bots}
        
        # Enrich each trade
        enriched_trades = []
        for trade in trades:
            # Parse timestamp
            try:
                if isinstance(trade.get('timestamp'), str):
                    dt = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                elif isinstance(trade.get('timestamp'), datetime):
                    dt = trade['timestamp']
                else:
                    dt = datetime.now(timezone.utc)
                
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                timestamp = dt.isoformat()
            except:
                timestamp = datetime.now(timezone.utc).isoformat()
            
            # Build enriched trade object
            enriched_trade = {
                # Bot info
                "bot_id": trade.get('bot_id'),
                "bot_name": bot_names.get(trade.get('bot_id'), 'Unknown'),
                "exchange": trade.get('exchange', 'unknown'),
                
                # Trade details
                "symbol": trade.get('symbol') or trade.get('pair', 'UNKNOWN'),
                "side": trade.get('side', 'buy'),
                "quantity": trade.get('amount', 0),
                
                # Prices
                "entry_price": trade.get('entry_price') or trade.get('price', 0),
                "exit_price": trade.get('exit_price') or trade.get('price', 0),
                
                # P&L breakdown
                "gross_profit_loss": trade.get('gross_pnl', trade.get('profit_loss', 0)),
                "fee_total": trade.get('fee_amount', 0),
                "net_profit_loss": trade.get('net_pnl', trade.get('profit_loss', 0)),
                
                # Strategy/signal
                "strategy_tag": trade.get('strategy_tag') or trade.get('trend', 'unknown'),
                "signal_reason": trade.get('signal_reason') or trade.get('ai_regime', 'unknown'),
                
                # Metadata
                "timestamp": timestamp,
                "trading_mode": trade.get('trading_mode', 'paper'),
                "status": trade.get('status', 'closed'),
                
                # Additional context
                "data_source": trade.get('data_source', 'unknown'),
                "quality_score": trade.get('quality_score', 0),
                "ai_confidence": trade.get('ai_confidence', 0)
            }
            
            enriched_trades.append(enriched_trade)
        
        return {
            "trades": enriched_trades,
            "count": len(enriched_trades),
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get live trades error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
