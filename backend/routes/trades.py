"""
Trades API - Canonical trade history and metrics
Uses unified accounting service for consistency
Frontend calls GET /api/trades/recent?limit=50
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import Optional, List
import logging

from auth import get_current_user
from services.accounting import accounting_service
import database as db
from utils.trade_utils import normalize_trade_timestamps, parse_trade_timestamp, build_trade_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trades", tags=["Trades"])


@router.get("/ping")
async def trades_ping() -> dict:
    """Return a simple heartbeat response for trades checks."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def get_trade_metrics(
    user_id: str = Depends(get_current_user)
):
    """
    Get trade metrics using unified accounting service
    
    This endpoint provides consistent metrics for Live Trades page.
    Uses the same accounting service as Overview and Profits pages.
    
    Returns:
        Trade metrics with net PnL, fees, and trade counts
    """
    try:
        # Get unified metrics from accounting service
        metrics = await accounting_service.get_unified_metrics(
            user_id=user_id,
            trading_mode=None,  # All modes
            include_unrealised=True
        )
        
        return {
            "success": True,
            "metrics": metrics,
            "currency": "ZAR",
            "data_source": "accounting_service",
            "timestamp": metrics["last_calculated_at"]
        }
        
    except Exception as e:
        logger.error(f"Get trade metrics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$addFields": {"_sort_ts": {"$ifNull": ["$timestamp", "$created_at"]}}},
            {"$sort": {"_sort_ts": -1}},
            {"$limit": limit},
            {"$project": {"_id": 0, "_sort_ts": 0}},
        ]
        trades = await db.trades_collection.aggregate(pipeline).to_list(limit)

        bot_ids = list({t.get("bot_id") for t in trades if t.get("bot_id")})
        bot_names = {}
        if bot_ids:
            bots = await db.bots_collection.find(
                {"id": {"$in": bot_ids}},
                {"_id": 0, "id": 1, "name": 1, "exchange": 1, "pair": 1, "trading_mode": 1}
            ).to_list(1000)
            bot_names = {b.get("id"): b for b in bots}
        
        normalized_trades = []
        # Ensure all trades have proper date+time fields
        for trade in trades:
            bot_meta = bot_names.get(trade.get("bot_id"), {})
            normalized = build_trade_record(trade, user_id=user_id, bot=bot_meta)
            normalize_trade_timestamps(normalized)
            dt = parse_trade_timestamp(normalized)
            normalized["date"] = dt.strftime("%Y-%m-%d")
            normalized["time"] = dt.strftime("%H:%M:%S")
            normalized_trades.append(normalized)

        return {
            "success": True,
            "trades": normalized_trades,
            "total": len(normalized_trades),
            "count": len(normalized_trades),
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
        total_pnl = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in trades)
        winning_trades = len([t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0])
        losing_trades = len([t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) < 0])
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
    """Live trade feed with enriched payload and consistent metrics
    
    Uses unified accounting service for consistent PnL calculations.
    Returns recent trades with full details for live feed display:
    - Bot info (id, name, exchange)
    - Symbol/pair, side, quantity
    - Entry/exit prices
    - Gross profit/loss, fees, net profit/loss (from accounting service)
    - Strategy tag or signal reason
    - Timestamps
    
    Args:
        limit: Maximum number of trades to return (1-500)
        user_id: Current authenticated user
        
    Returns:
        Enriched trade feed for live updates with consistent metrics
    """
    try:
        # Get trades with consistent metrics from accounting service
        result = await accounting_service.get_trade_list_with_metrics(
            user_id=user_id,
            trading_mode=None,  # All modes
            limit=limit,
            status="closed"
        )
        
        trades = result["trades"]
        
        # Get bot names for enrichment
        bot_ids = list(set(t.get('bot_id') for t in trades if t.get('bot_id')))
        if bot_ids:
            bots = await db.bots_collection.find(
                {"id": {"$in": bot_ids}},
                {"_id": 0, "id": 1, "name": 1}
            ).to_list(1000)
            bot_names = {bot['id']: bot.get('name') for bot in bots}
        else:
            bot_names = {}
        
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
                
                # P&L breakdown (from accounting service - consistent!)
                "gross_profit_loss": trade.get('gross_pnl', 0),
                "fee_total": trade.get('fee_amount', 0),
                "net_profit_loss": trade.get('net_pnl', 0),
                
                # Display labels
                "net_pnl_display": trade.get('net_pnl_display', f"R{trade.get('net_pnl', 0):.2f}"),
                "gross_pnl_display": trade.get('gross_pnl_display', f"R{trade.get('gross_pnl', 0):.2f}"),
                "fee_display": trade.get('fee_display', f"R{trade.get('fee_amount', 0):.2f}"),
                
                # Strategy/signal
                "strategy_tag": trade.get('strategy_tag') or trade.get('trend', 'unknown'),
                "signal_reason": trade.get('signal_reason') or trade.get('ai_regime', 'unknown'),
                
                # Metadata
                "timestamp": timestamp,
                "trading_mode": trade.get('trading_mode', 'paper'),
                "status": trade.get('status', 'closed'),
                
                # Additional context
                "data_source": "accounting_service",
                "quality_score": trade.get('quality_score', 0),
                "ai_confidence": trade.get('ai_confidence', 0)
            }
            
            enriched_trades.append(enriched_trade)
        
        return {
            "trades": enriched_trades,
            "count": len(enriched_trades),
            "summary": result.get("summary", {}),
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_source": "accounting_service"
        }
        
    except Exception as e:
        logger.error(f"Get live trades error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activity")
async def get_trading_activity(user_id: str = Depends(get_current_user)):
    """
    Trading activity summary – lightweight probe for paper trading proof.

    Returns:
        active_bots: number of bots with status='active'
        queued_trades: trades with status='pending'
        last_trade_at: ISO timestamp of most recent trade (any status)
        last_fill_at:  ISO timestamp of most recent filled/closed trade
        last_tick_at:  ISO timestamp read from bot_runtime_state if available
    """
    try:
        active_bots = await db.bots_collection.count_documents(
            {"user_id": user_id, "status": "active", "deleted_at": {"$exists": False}}
        )
        queued_trades = await db.trades_collection.count_documents(
            {"user_id": user_id, "status": "pending"}
        )

        last_trade_doc = await db.trades_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "timestamp": 1},
            sort=[("timestamp", -1)],
        )
        last_trade_at = (last_trade_doc or {}).get("timestamp")

        last_fill_doc = await db.trades_collection.find_one(
            {"user_id": user_id, "status": {"$in": ["filled", "closed", "completed"]}},
            {"_id": 0, "timestamp": 1},
            sort=[("timestamp", -1)],
        )
        last_fill_at = (last_fill_doc or {}).get("timestamp")

        # Best-effort: read last_tick_at from bot_runtime_state
        last_tick_at = None
        try:
            tick_doc = await db.bot_runtime_state_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "updated_at": 1},
                sort=[("updated_at", -1)],
            )
            last_tick_at = (tick_doc or {}).get("updated_at")
        except Exception:
            pass

        return {
            "success": True,
            "active_bots": active_bots,
            "queued_trades": queued_trades,
            "last_trade_at": last_trade_at,
            "last_fill_at": last_fill_at,
            "last_tick_at": last_tick_at,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Trading activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
