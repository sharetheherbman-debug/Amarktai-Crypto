"""
Trade Budget Manager - Per-Exchange and Per-Bot Budget Enforcement

This module manages trading budgets fairly across exchanges and bots:
- Per exchange: enforces request/order limits + optional daily trade budgets
- Per bot: allocates daily trade budgets fairly based on active bot count
  - If 1 bot per exchange → gets the full daily budget
  - If N bots → each gets floor(budget/N) to enforce fair limits

Exchange limits are sourced from official documentation:
- Binance: https://binance-docs.github.io/apidocs/spot/en/#limits
  - Weight limits: 1200 per minute, 200,000 orders per 24 hours
  - Order rate limits: 100 orders per 10 seconds per account
- KuCoin: https://docs.kucoin.com/#request-rate-limit
  - Public endpoints: 100 requests per 10 seconds
  - Private endpoints: 200 requests per 10 seconds per user
  - Order placement: 45 orders per 3 seconds
- Luno: https://www.luno.com/en/developers/api
  - Rate limit: 300 requests per minute per IP
  - No explicit order count limit documented (conservative: 100 orders/min)
- Bybit: Similar rate limits to Binance
- Kraken: Conservative rate limits apply
- Bitget: Similar rate limits to KuCoin
- Gate.io: Similar rate limits to KuCoin
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import database as db
from exchange_limits import EXCHANGE_LIMITS, get_exchange_limits
import logging

logger = logging.getLogger(__name__)


class TradeBudgetManager:
    """Manages daily trade budgets per exchange and allocates fairly among bots"""
    
    def __init__(self):
        self.exchange_limits = EXCHANGE_LIMITS
        self.budget_cache = {}  # Cache for per-bot daily budgets
        self.last_budget_reset = {}  # Track when budgets were last reset
        
    async def get_exchange_daily_budget(self, exchange: str) -> int:
        """Get the daily trade budget for an exchange
        
        Args:
            exchange: Exchange name (e.g., 'binance', 'kucoin', 'luno')
            
        Returns:
            Maximum number of trades allowed per day for this exchange
        """
        limits = get_exchange_limits(exchange)
        # Use new 'total_trades_day' key, fallback to old key for compatibility
        return limits.get('total_trades_day', limits.get('max_orders_per_day', 500))
    
    async def get_active_bots_for_exchange(self, exchange: str, user_id: Optional[str] = None) -> List[Dict]:
        """Get all active bots trading on a specific exchange
        
        Args:
            exchange: Exchange name
            user_id: Optional user ID to filter bots (None = all users)
            
        Returns:
            List of active bot documents
        """
        query = {
            "exchange": exchange,
            "status": "active"
        }
        if user_id:
            query["user_id"] = user_id
            
        bots = await db.bots_collection.find(query, {"_id": 0}).to_list(1000)
        return bots
    
    async def calculate_bot_daily_budget(self, bot_id: str, exchange: str) -> int:
        """Calculate daily trade budget for a specific bot
        
        Uses exchange-specific per-bot limits (trades_per_bot_day).
        If multiple bots exceed exchange max, scales down proportionally.
        
        Args:
            bot_id: Bot ID
            exchange: Exchange name
            
        Returns:
            Number of trades allowed for this bot today
        """
        limits = get_exchange_limits(exchange)
        
        # Get per-bot limit from new configuration
        per_bot_limit = limits.get('trades_per_bot_day', 50)
        
        # Get all active bots on this exchange
        active_bots = await self.get_active_bots_for_exchange(exchange)
        bot_count = len(active_bots)
        
        if bot_count == 0:
            return 0
        
        # Check if we need to scale down (e.g., if max_bots exceeded)
        max_bots = limits.get('max_bots', 10)
        total_budget = limits.get('total_trades_day', per_bot_limit * max_bots)
        
        # If within limit, use per-bot limit
        if bot_count <= max_bots:
            per_bot_budget = per_bot_limit
        else:
            # Scale down proportionally if too many bots
            per_bot_budget = total_budget // bot_count
            per_bot_budget = max(10, per_bot_budget)  # Minimum 10 trades/day
        
        logger.debug(f"Bot {bot_id[:8]} on {exchange}: {per_bot_budget} trades/day "
                    f"(limit: {per_bot_limit}, bots: {bot_count}/{max_bots})")
        
        return per_bot_budget
    
    async def get_bot_remaining_budget(self, bot_id: str, exchange: str) -> int:
        """Get remaining trades available for bot today
        
        Args:
            bot_id: Bot ID
            exchange: Exchange name
            
        Returns:
            Number of trades remaining for today
        """
        # Get bot's daily budget
        daily_budget = await self.calculate_bot_daily_budget(bot_id, exchange)
        
        # Count trades executed today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await db.trades_collection.count_documents({
            "bot_id": bot_id,
            "timestamp": {"$gte": today_start.isoformat()}
        })
        
        remaining = max(0, daily_budget - trades_today)
        return remaining
    
    async def can_execute_trade(self, bot_id: str, exchange: str) -> Tuple[bool, str]:
        """Check if a bot can execute a trade within budget limits
        
        Args:
            bot_id: Bot ID
            exchange: Exchange name
            
        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        try:
            # Check bot exists and is active
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return False, "Bot not found"
            
            if bot.get('status') != 'active':
                return False, f"Bot is {bot.get('status', 'inactive')}"
            
            # Check remaining budget
            remaining = await self.get_bot_remaining_budget(bot_id, exchange)
            
            if remaining <= 0:
                return False, f"Daily budget exhausted (0 trades remaining)"
            
            # Check exchange-level limits (burst protection)
            can_burst, burst_reason = await self._check_burst_limits(exchange)
            if not can_burst:
                return False, f"Exchange burst limit: {burst_reason}"
            
            return True, f"OK ({remaining} trades remaining today)"
        
        except Exception as e:
            logger.error(f"Budget check error for bot {bot_id}: {e}")
            return False, f"Error: {str(e)}"
    
    async def _check_burst_limits(self, exchange: str) -> Tuple[bool, str]:
        """Check if exchange burst limits allow trading
        
        Burst protection prevents overwhelming exchanges with requests.
        Limit: max 10 orders per 10 seconds per exchange (conservative)
        
        Args:
            exchange: Exchange name
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Count trades in last 10 seconds for this exchange
        ten_seconds_ago = datetime.now(timezone.utc) - timedelta(seconds=10)
        
        recent_trades = await db.trades_collection.count_documents({
            "exchange": exchange,
            "timestamp": {"$gte": ten_seconds_ago.isoformat()}
        })
        
        limits = get_exchange_limits(exchange)
        max_burst = limits.get('max_orders_per_10_seconds', 10)
        
        if recent_trades >= max_burst:
            return False, f"Burst limit reached ({recent_trades}/{max_burst} in 10s)"
        
        return True, "OK"
    
    async def record_trade_execution(self, bot_id: str, exchange: str) -> bool:
        """Record that a trade was executed (for tracking purposes)
        
        Note: Actual trade recording happens in trading_scheduler.
        This method is for budget tracking metadata if needed.
        
        Args:
            bot_id: Bot ID
            exchange: Exchange name
            
        Returns:
            Success status
        """
        try:
            # Update bot's daily trade count
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$inc": {"daily_trade_count": 1},
                    "$set": {"last_trade_time": datetime.now(timezone.utc).isoformat()}
                }
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record trade execution: {e}")
            return False
    
    async def reset_daily_budgets(self):
        """Reset daily trade counts for all bots (called at midnight UTC)"""
        try:
            result = await db.bots_collection.update_many(
                {},
                {"$set": {"daily_trade_count": 0}}
            )
            logger.info(f"✅ Reset daily budgets for {result.modified_count} bots")
        except Exception as e:
            logger.error(f"Failed to reset daily budgets: {e}")
    
    async def get_exchange_budget_report(self, exchange: str) -> Dict:
        """Get comprehensive budget report for an exchange
        
        Args:
            exchange: Exchange name
            
        Returns:
            Dictionary with budget statistics
        """
        try:
            total_budget = await self.get_exchange_daily_budget(exchange)
            active_bots = await self.get_active_bots_for_exchange(exchange)
            bot_count = len(active_bots)
            
            per_bot_budget = total_budget // bot_count if bot_count > 0 else 0
            
            # Count trades today
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            trades_today = await db.trades_collection.count_documents({
                "exchange": exchange,
                "timestamp": {"$gte": today_start.isoformat()}
            })
            
            remaining = max(0, total_budget - trades_today)
            utilization = (trades_today / total_budget * 100) if total_budget > 0 else 0
            
            return {
                "exchange": exchange,
                "total_daily_budget": total_budget,
                "active_bots": bot_count,
                "per_bot_budget": per_bot_budget,
                "trades_today": trades_today,
                "remaining_today": remaining,
                "utilization_percent": round(utilization, 2),
                "status": "healthy" if utilization < 80 else "near_limit" if utilization < 95 else "critical"
            }
        except Exception as e:
            logger.error(f"Failed to generate budget report for {exchange}: {e}")
            return {
                "exchange": exchange,
                "error": str(e)
            }
    
    async def get_all_exchanges_budget_report(self) -> List[Dict]:
        """Get budget reports for all configured exchanges
        
        Returns:
            List of budget reports, one per exchange
        """
        reports = []
        for exchange in self.exchange_limits.keys():
            report = await self.get_exchange_budget_report(exchange)
            reports.append(report)
        return reports


# Global instance
trade_budget_manager = TradeBudgetManager()
