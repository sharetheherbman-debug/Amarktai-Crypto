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
from services.fx_normalizer import get_quote_currency

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
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    user_id: str = Depends(get_current_user)
):
    """
    Get recent trades with date+time metrics
    Frontend calls this endpoint to display trade history
    
    Args:
        limit: Maximum number of trades to return (1-500)
        bot_type: Optional filter by bot type (normal or scalper)
        user_id: Current authenticated user
        
    Returns:
        List of trades with full timestamps and metrics
    """
    try:
        match_query = {"user_id": user_id}
        if bot_type:
            matching_bots = await db.bots_collection.find(
                {"user_id": user_id, "bot_type": bot_type, "deleted": {"$ne": True}},
                {"_id": 0, "id": 1}
            ).to_list(200)
            bot_ids = [b["id"] for b in matching_bots]
            match_query["bot_id"] = {"$in": bot_ids}

        pipeline = [
            {"$match": match_query},
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
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    user_id: str = Depends(get_current_user)
):
    """
    Get trade statistics summary
    
    Args:
        bot_type: Optional filter by bot type (normal or scalper)
    
    Returns:
        Summary statistics for all user trades
    """
    try:
        query = {"user_id": user_id}
        if bot_type:
            matching_bots = await db.bots_collection.find(
                {"user_id": user_id, "bot_type": bot_type, "deleted": {"$ne": True}},
                {"_id": 0, "id": 1}
            ).to_list(200)
            bot_ids = [b["id"] for b in matching_bots]
            query["bot_id"] = {"$in": bot_ids}

        # Get all trades
        trades = await db.trades_collection.find(
            query,
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
            
            # Determine native quote currency for this trade so the frontend
            # can display prices/P&L with the correct symbol ($ for USDT, R for ZAR).
            _trade_exchange = trade.get('exchange', 'unknown')
            _trade_symbol = trade.get('symbol') or trade.get('pair', '')
            _trade_quote_currency = (
                trade.get('quote_currency')
                or trade.get('fee_currency')
                or get_quote_currency(_trade_exchange, _trade_symbol)
            )
            # Choose currency symbol for default _display fields.
            # Mirror the frontend CURRENCY_SYMBOLS mapping so both sides use the same symbols.
            _CURRENCY_SYMBOL_MAP = {"ZAR": "R", "USD": "$", "USDT": "$", "USDC": "$", "BUSD": "$", "TUSD": "$"}
            _cur_sym = _CURRENCY_SYMBOL_MAP.get(_trade_quote_currency.upper(), _trade_quote_currency.upper() + "\u00A0")

            # Build enriched trade object
            enriched_trade = {
                # Bot info
                "bot_id": trade.get('bot_id'),
                "bot_name": bot_names.get(trade.get('bot_id'), 'Unknown'),
                "exchange": _trade_exchange,

                # Trade details
                "symbol": _trade_symbol or 'UNKNOWN',
                "side": trade.get('side', 'buy'),
                # Size field — multiple aliases for frontend compatibility
                "quantity": trade.get('amount', 0),
                "qty": trade.get('qty', trade.get('amount', 0)),
                "size": trade.get('qty', trade.get('amount', 0)),

                # Prices
                "entry_price": trade.get('entry_price') or trade.get('price', 0),
                "exit_price": trade.get('exit_price') or trade.get('price', 0),
                "price": trade.get('entry_price') or trade.get('price', 0),

                # P&L breakdown (from accounting service - consistent!)
                "gross_profit_loss": trade.get('gross_pnl', 0),
                "gross_pnl": trade.get('gross_pnl', 0),
                "fee_total": trade.get('fee_amount', trade.get('fees_total', trade.get('fees', 0))),
                "fees": trade.get('fees_total', trade.get('fee_amount', trade.get('fees', 0))),
                "fee": trade.get('fees_total', trade.get('fee_amount', trade.get('fees', 0))),
                "net_profit_loss": trade.get('net_pnl', 0),
                "net_pnl": trade.get('net_pnl', 0),
                "profit_loss": trade.get('net_pnl', trade.get('profit_loss', 0)),
                # Slippage
                "slippage": trade.get('slippage_cost', trade.get('slippage', 0)),
                "slippage_cost": trade.get('slippage_cost', trade.get('slippage', 0)),

                # Currency — canonical quote currency for this trade.
                # Frontend uses this field (not the exchange name) to pick the
                # correct symbol: "ZAR" → "R", "USDT" → "$"/"USDT".
                "quote_currency": _trade_quote_currency,

                # Display labels use the correct currency symbol
                "net_pnl_display": trade.get('net_pnl_display', f"{_cur_sym}{trade.get('net_pnl', 0):.2f}"),
                "gross_pnl_display": trade.get('gross_pnl_display', f"{_cur_sym}{trade.get('gross_pnl', 0):.2f}"),
                "fee_display": trade.get('fee_display', f"{_cur_sym}{trade.get('fee_amount', trade.get('fees', 0)):.2f}"),

                # Strategy/signal
                "strategy_tag": trade.get('strategy_tag') or trade.get('trend', 'unknown'),
                "signal_reason": trade.get('signal_reason') or trade.get('ai_regime', 'unknown'),

                # Metadata
                "id": trade.get('id') or trade.get('trade_id'),
                "timestamp": timestamp,
                "trading_mode": trade.get('trading_mode', 'paper'),
                "mode": trade.get('trading_mode', 'paper'),
                "status": trade.get('status', 'closed'),
                # Classify as profitable: check if PnL > 0 (treat exactly-zero as not profitable)
                "is_profitable": (
                    (trade.get('net_pnl') if trade.get('net_pnl') is not None else trade.get('profit_loss', 0)) > 0
                ),

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
