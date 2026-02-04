"""
Trade Limiter - Enforces per-exchange trade limits and cooldowns
Enhanced with per-bot and per-exchange daily trade tracking
"""
import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from config import (
    EXCHANGE_TRADE_LIMITS, 
    MAX_TRADES_PER_USER_PER_DAY, 
    MAX_TRADES_PER_BOT_PER_DAY,
    EXCHANGE_DAILY_TRADE_LIMITS
)
from logger_config import logger
import random


class TradeLimiter:
    def __init__(self):
        self.exchange_limits = EXCHANGE_TRADE_LIMITS
        self.max_user_daily_trades = MAX_TRADES_PER_USER_PER_DAY
        self.max_bot_daily_trades = MAX_TRADES_PER_BOT_PER_DAY
        self.exchange_daily_limits = EXCHANGE_DAILY_TRADE_LIMITS
        self.warning_threshold = 0.80  # Send warning at 80% of limit
    
    async def can_trade(self, bot_id: str) -> tuple[bool, str]:
        """Check if bot is allowed to trade now - Enhanced with per-bot and per-exchange limits"""
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            if not bot:
                return False, "Bot not found"
            
            if bot.get('status') != 'active':
                return False, "Bot is not active"
            
            # Get exchange-specific limits
            exchange = bot.get('exchange', 'binance').lower()
            limits = self.exchange_limits.get(exchange, self.exchange_limits['binance'])
            user_id = bot.get('user_id')
            
            # 1. Check per-bot daily limit (1000 trades/day per bot)
            bot_daily_count = bot.get('daily_trade_count', 0)
            if bot_daily_count >= self.max_bot_daily_trades:
                await self._send_limit_alert(bot_id, user_id, 'bot', bot_daily_count, self.max_bot_daily_trades)
                return False, f"Bot daily limit reached ({bot_daily_count}/{self.max_bot_daily_trades})"
            
            # Check if approaching limit (80% threshold)
            if bot_daily_count >= self.max_bot_daily_trades * self.warning_threshold:
                await self._send_warning_alert(bot_id, user_id, 'bot', bot_daily_count, self.max_bot_daily_trades)
            
            # 2. Check per-exchange daily limit
            exchange_daily_count = await self._get_exchange_daily_trades(exchange, user_id)
            exchange_limit = self.exchange_daily_limits.get(exchange, 50000)
            if exchange_daily_count >= exchange_limit:
                await self._send_limit_alert(bot_id, user_id, 'exchange', exchange_daily_count, exchange_limit, exchange)
                return False, f"Exchange daily limit reached ({exchange_daily_count}/{exchange_limit} for {exchange})"
            
            # Check if approaching exchange limit (80% threshold)
            if exchange_daily_count >= exchange_limit * self.warning_threshold:
                await self._send_warning_alert(bot_id, user_id, 'exchange', exchange_daily_count, exchange_limit, exchange)
            
            # 3. Check legacy per-bot-per-exchange limit (from EXCHANGE_TRADE_LIMITS)
            max_daily = limits['max_trades_per_bot_per_day']
            min_cooldown = limits['min_cooldown_minutes']
            if bot_daily_count >= max_daily:
                return False, f"Bot exchange limit reached ({bot_daily_count}/{max_daily} for {exchange})"
            
            # 4. Check cooldown
            last_trade = bot.get('last_trade_time')
            if last_trade:
                # Normalize last_trade to timezone-aware datetime
                if isinstance(last_trade, str):
                    last_trade = datetime.fromisoformat(last_trade.replace('Z', '+00:00'))
                
                # Ensure timezone-aware
                if last_trade.tzinfo is None:
                    last_trade = last_trade.replace(tzinfo=timezone.utc)
                
                # Random cooldown with jitter (min_cooldown + 0-5 minutes)
                cooldown = random.randint(min_cooldown, min_cooldown + 5)
                next_allowed = last_trade + timedelta(minutes=cooldown)
                
                # Compare with timezone-aware now
                now = datetime.now(timezone.utc)
                if now < next_allowed:
                    wait_minutes = int((next_allowed - now).total_seconds() / 60)
                    return False, f"Cooldown active ({wait_minutes} min remaining)"
            
            return True, "OK"
        
        except Exception as e:
            logger.error(f"Can trade check error: {e}")
            return False, f"Error: {str(e)}"
    
    async def record_trade(self, bot_id: str) -> bool:
        """Record that a trade was executed"""
        try:
            result = await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {"last_trade_time": datetime.now(timezone.utc).isoformat()},
                    "$inc": {
                        "daily_trade_count": 1,
                        "trades_count": 1
                    }
                }
            )
            
            return result.modified_count > 0
        
        except Exception as e:
            logger.error(f"Record trade error: {e}")
            return False
    
    async def get_bot_trade_status(self, bot_id: str) -> dict:
        """Get current trade status for a bot"""
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            if not bot:
                return {"error": "Bot not found"}
            
            exchange = bot.get('exchange', 'binance').lower()
            limits = self.exchange_limits.get(exchange, self.exchange_limits['binance'])
            max_daily = limits['max_trades_per_bot_per_day']
            
            daily_count = bot.get('daily_trade_count', 0)
            remaining = max_daily - daily_count
            
            can_trade, reason = await self.can_trade(bot_id)
            
            return {
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "exchange": exchange,
                "daily_trades": daily_count,
                "daily_limit": max_daily,
                "remaining_today": max(0, remaining),
                "can_trade_now": can_trade,
                "reason": reason
            }
        
        except Exception as e:
            logger.error(f"Get trade status error: {e}")
            return {"error": str(e)}
    
    async def _get_exchange_daily_trades(self, exchange: str, user_id: str) -> int:
        """Get total trades across all bots for an exchange today"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Count trades from all bots on this exchange for this user today
            pipeline = [
                {
                    "$match": {
                        "user_id": user_id,
                        "exchange": exchange,
                        "status": {"$in": ["active", "paused"]}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_trades": {"$sum": "$daily_trade_count"}
                    }
                }
            ]
            
            result = await db.bots_collection.aggregate(pipeline).to_list(1)
            return result[0]['total_trades'] if result else 0
        
        except Exception as e:
            logger.error(f"Get exchange daily trades error: {e}")
            return 0
    
    async def _send_warning_alert(self, bot_id: str, user_id: str, limit_type: str, current: int, limit: int, exchange: str = None):
        """Send warning when approaching trade limit (80% threshold)"""
        try:
            percentage = int((current / limit) * 100)
            
            if limit_type == 'bot':
                message = f"⚠️ Bot {bot_id} has reached {percentage}% of daily trade limit ({current}/{limit})"
            else:
                message = f"⚠️ Exchange {exchange} has reached {percentage}% of daily trade limit ({current}/{limit})"
            
            # Log warning
            logger.warning(f"Trade limit warning: {message}")
            
            # Send SSE event if realtime is available
            try:
                from realtime_events import emit_event
                await emit_event(user_id, "trade_limit_warning", {
                    "bot_id": bot_id,
                    "limit_type": limit_type,
                    "exchange": exchange,
                    "current_trades": current,
                    "limit": limit,
                    "percentage": percentage,
                    "message": message
                })
            except ImportError:
                pass  # Realtime events not available
        
        except Exception as e:
            logger.error(f"Send warning alert error: {e}")
    
    async def _send_limit_alert(self, bot_id: str, user_id: str, limit_type: str, current: int, limit: int, exchange: str = None):
        """Send alert when trade limit is reached (100%)"""
        try:
            if limit_type == 'bot':
                message = f"🛑 Bot {bot_id} has reached daily trade limit ({current}/{limit}) - PAUSED"
            else:
                message = f"🛑 Exchange {exchange} has reached daily trade limit ({current}/{limit}) - ALL BOTS PAUSED"
            
            # Log alert
            logger.error(f"Trade limit reached: {message}")
            
            # Pause bot
            await db.bots_collection.update_one(
                {"id": bot_id},
                {"$set": {"status": "paused", "pause_reason": "Daily trade limit reached"}}
            )
            
            # Send SSE event if realtime is available
            try:
                from realtime_events import emit_event
                await emit_event(user_id, "trade_limit_reached", {
                    "bot_id": bot_id,
                    "limit_type": limit_type,
                    "exchange": exchange,
                    "current_trades": current,
                    "limit": limit,
                    "message": message,
                    "action": "bot_paused"
                })
            except ImportError:
                pass  # Realtime events not available
        
        except Exception as e:
            logger.error(f"Send limit alert error: {e}")


trade_limiter = TradeLimiter()
