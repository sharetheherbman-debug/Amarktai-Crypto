"""
System Limits API - Trade Budget Status and Management
Provides visibility into per-exchange and per-bot trade budgets
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Dict, List
import logging

from auth import get_current_user
from engines.trade_budget_manager import trade_budget_manager
from exchange_limits import EXCHANGE_LIMITS, MAX_BOTS_GLOBAL, BOT_ALLOCATION
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Limits"])


@router.get("/limits")
async def get_trade_limits(user_id: str = Depends(get_current_user)):
    """Get current trade budgets and remaining capacity per exchange and per bot
    
    Returns comprehensive budget information:
    - Exchange limits configuration (max bots, trades per bot/day, fees)
    - Per-exchange daily budgets and utilization
    - Per-bot allocated budgets and remaining trades
    - System-wide statistics
    """
    try:
        # Return static exchange limits configuration
        exchange_configs = {}
        for exchange, limits in EXCHANGE_LIMITS.items():
            exchange_configs[exchange] = {
                "max_bots": limits.get("max_bots"),
                "trades_per_bot_day": limits.get("trades_per_bot_day"),
                "total_trades_day": limits.get("total_trades_day"),
                "fee_maker": limits.get("fee_maker"),
                "fee_taker": limits.get("fee_taker"),
            }
        
        # Get all exchanges budget report
        exchange_reports = await trade_budget_manager.get_all_exchanges_budget_report()
        
        # Get user's active bots (excluding deleted)
        user_bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$nin": ["deleted", "marked_for_deletion"]}},
            {"_id": 0}
        ).to_list(1000)
        
        # Get per-bot budget details
        bot_budgets = []
        for bot in user_bots:
            bot_id = bot['id']
            exchange = bot.get('exchange', 'binance')
            
            daily_budget = await trade_budget_manager.calculate_bot_daily_budget(bot_id, exchange)
            remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
            can_trade, reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
            
            bot_budgets.append({
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "exchange": exchange,
                "daily_budget": daily_budget,
                "remaining_today": remaining,
                "can_trade": can_trade,
                "status_reason": reason
            })
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "global_limits": {
                "max_bots_total": MAX_BOTS_GLOBAL,
                "bot_allocation": BOT_ALLOCATION
            },
            "exchange_limits": exchange_configs,
            "exchanges": exchange_reports,
            "user_bots": bot_budgets,
            "summary": {
                "total_exchanges": len(exchange_reports),
                "total_active_bots": len(user_bots),
                "exchanges_near_limit": len([e for e in exchange_reports if e.get('utilization_percent', 0) > 80]),
                "bots_can_trade": len([b for b in bot_budgets if b['can_trade']])
            }
        }
        
    except Exception as e:
        logger.error(f"Get limits error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/limits/exchange/{exchange}")
async def get_exchange_limits(exchange: str, user_id: str = Depends(get_current_user)):
    """Get detailed trade budget information for a specific exchange
    
    Args:
        exchange: Exchange name (luno, binance, kucoin, ovex, valr)
    """
    try:
        report = await trade_budget_manager.get_exchange_budget_report(exchange)
        
        # Get user's bots on this exchange
        user_bots = await db.bots_collection.find(
            {"user_id": user_id, "exchange": exchange, "status": "active"},
            {"_id": 0}
        ).to_list(100)
        
        bot_details = []
        for bot in user_bots:
            bot_id = bot['id']
            daily_budget = await trade_budget_manager.calculate_bot_daily_budget(bot_id, exchange)
            remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
            
            bot_details.append({
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "daily_budget": daily_budget,
                "remaining_today": remaining,
                "utilization_pct": round((daily_budget - remaining) / daily_budget * 100, 2) if daily_budget > 0 else 0
            })
        
        return {
            "exchange": exchange,
            "exchange_budget": report,
            "user_bots": bot_details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get exchange limits error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/limits/bot/{bot_id}")
async def get_bot_limits(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed trade budget information for a specific bot"""
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        exchange = bot.get('exchange', 'binance')
        
        daily_budget = await trade_budget_manager.calculate_bot_daily_budget(bot_id, exchange)
        remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
        can_trade, reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
        
        # Get today's trade count
        import database as db
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await db.trades_collection.count_documents({
            "bot_id": bot_id,
            "timestamp": {"$gte": today_start.isoformat()}
        })
        
        return {
            "bot_id": bot_id,
            "bot_name": bot.get('name'),
            "exchange": exchange,
            "limits": {
                "daily_budget": daily_budget,
                "remaining_today": remaining,
                "trades_executed_today": trades_today,
                "utilization_pct": round((daily_budget - remaining) / daily_budget * 100, 2) if daily_budget > 0 else 0
            },
            "status": {
                "can_trade": can_trade,
                "reason": reason
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get bot limits error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
