"""
Trade Staggerer - 24/7 Staggered Trade Execution
- Spreads trades across the day to avoid rate limits
- Manages concurrent execution across exchanges
- Prevents API overload with intelligent queuing
"""

import asyncio
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone, timedelta
from collections import deque
import logging

import database as db

logger = logging.getLogger(__name__)

class TradeStaggerer:
    def __init__(self):
        # Queue management
        self.trade_queue = deque()
        self.active_trades = {}  # {bot_id: timestamp}
        
        # Rate limiting per exchange
        self.exchange_limits = {
            'luno': {'max_concurrent': 2, 'min_delay': 10},      # 2 concurrent, 10s between
            'binance': {'max_concurrent': 5, 'min_delay': 2},    # 5 concurrent, 2s between
            'kucoin': {'max_concurrent': 3, 'min_delay': 3},     # 3 concurrent, 3s between
            'bybit': {'max_concurrent': 4, 'min_delay': 3},      # 4 concurrent, 3s between
            'bitget': {'max_concurrent': 4, 'min_delay': 3}      # 4 concurrent, 3s between
        }
        
        self.last_trade_per_exchange = {}
        self.concurrent_trades_per_exchange = {}
        
        # Initialize counters
        for exchange in self.exchange_limits.keys():
            self.last_trade_per_exchange[exchange] = None
            self.concurrent_trades_per_exchange[exchange] = 0
    
    async def can_execute_now(self, bot_id: str, exchange: str) -> tuple[bool, str]:
        """Check if a bot can execute a trade now"""
        try:
            # Check if bot already has an active trade
            if bot_id in self.active_trades:
                elapsed = (datetime.now(timezone.utc) - self.active_trades[bot_id]).seconds
                if elapsed < 60:  # Wait at least 1 minute between bot trades
                    return False, f"Bot cooldown active ({60 - elapsed}s remaining)"
            
            # Check exchange rate limits
            limits = self.exchange_limits.get(exchange.lower(), self.exchange_limits['binance'])
            
            # Check concurrent limit
            concurrent = self.concurrent_trades_per_exchange.get(exchange, 0)
            if concurrent >= limits['max_concurrent']:
                return False, f"Exchange concurrent limit reached ({concurrent}/{limits['max_concurrent']})"
            
            # Check minimum delay between trades on this exchange
            last_trade = self.last_trade_per_exchange.get(exchange)
            if last_trade:
                elapsed = (datetime.now(timezone.utc) - last_trade).seconds
                if elapsed < limits['min_delay']:
                    return False, f"Exchange rate limit ({limits['min_delay'] - elapsed}s remaining)"
            
            return True, "OK"
            
        except Exception as e:
            logger.error(f"Can execute check error: {e}")
            return False, str(e)
    
    async def register_trade_start(self, bot_id: str, exchange: str):
        """Register that a trade has started"""
        try:
            now = datetime.now(timezone.utc)
            self.active_trades[bot_id] = now
            self.last_trade_per_exchange[exchange] = now
            
            current = self.concurrent_trades_per_exchange.get(exchange, 0)
            self.concurrent_trades_per_exchange[exchange] = current + 1
            
            logger.debug(f"📊 Trade started: {bot_id[:8]} on {exchange} (concurrent: {current + 1})")
            
        except Exception as e:
            logger.error(f"Register trade start error: {e}")
    
    async def register_trade_complete(self, bot_id: str, exchange: str):
        """Register that a trade has completed"""
        try:
            if bot_id in self.active_trades:
                del self.active_trades[bot_id]
            
            current = self.concurrent_trades_per_exchange.get(exchange, 0)
            self.concurrent_trades_per_exchange[exchange] = max(0, current - 1)
            
            logger.debug(f"✅ Trade completed: {bot_id[:8]} on {exchange} (concurrent: {current - 1})")
            
        except Exception as e:
            logger.error(f"Register trade complete error: {e}")
    
    async def add_to_queue(self, bot_id: str, exchange: str, priority: int = 0):
        """Add a trade request to the queue"""
        try:
            trade_request = {
                "bot_id": bot_id,
                "exchange": exchange,
                "priority": priority,
                "queued_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Higher priority goes first
            if priority > 0:
                self.trade_queue.appendleft(trade_request)
            else:
                self.trade_queue.append(trade_request)
            
            logger.info(f"📥 Queued trade: {bot_id[:8]} on {exchange} (queue size: {len(self.trade_queue)})")
            
        except Exception as e:
            logger.error(f"Add to queue error: {e}")
    
    async def get_next_trade(self) -> Dict | None:
        """Get next trade from queue that can execute now"""
        try:
            if not self.trade_queue:
                return None
            
            # Try each item in queue until we find one that can execute
            for _ in range(len(self.trade_queue)):
                trade_request = self.trade_queue.popleft()
                
                bot_id = trade_request['bot_id']
                exchange = trade_request['exchange']
                
                can_execute, reason = await self.can_execute_now(bot_id, exchange)
                
                if can_execute:
                    return trade_request
                else:
                    # Put back in queue if still relevant
                    queued_time = datetime.fromisoformat(trade_request['queued_at'].replace('Z', '+00:00'))
                    age_minutes = (datetime.now(timezone.utc) - queued_time).seconds / 60
                    
                    if age_minutes < 30:  # Only re-queue if less than 30 minutes old
                        self.trade_queue.append(trade_request)
                    else:
                        logger.warning(f"⏰ Dropped stale trade request: {bot_id[:8]} (age: {age_minutes:.1f}m)")
            
            return None
            
        except Exception as e:
            logger.error(f"Get next trade error: {e}")
            return None
    
    async def calculate_daily_schedule(self, user_id: str) -> Dict:
        """Calculate staggered schedule for all active bots"""
        try:
            # Get all active bots
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": "active"},
                {"_id": 0, "id": 1, "name": 1, "exchange": 1}
            ).to_list(1000)
            
            if not bots:
                return {"schedules": [], "message": "No active bots"}
            
            # Calculate time slots for 24 hours
            # Spread bots evenly across the day
            total_bots = len(bots)
            minutes_per_day = 1440  # 24 * 60
            slot_duration = minutes_per_day / total_bots
            
            schedules = []
            current_time = datetime.now(timezone.utc)
            
            for i, bot in enumerate(bots):
                # Calculate next trade time for this bot
                offset_minutes = int(i * slot_duration)
                next_trade_time = current_time + timedelta(minutes=offset_minutes)
                
                schedules.append({
                    "bot_id": bot['id'],
                    "bot_name": bot['name'],
                    "exchange": bot['exchange'],
                    "next_trade_time": next_trade_time.isoformat(),
                    "slot_number": i + 1,
                    "time_offset_minutes": offset_minutes
                })
            
            return {
                "total_bots": total_bots,
                "slot_duration_minutes": slot_duration,
                "schedules": schedules,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Calculate schedule error: {e}")
            return {"error": str(e)}
    
    async def get_queue_status(self) -> Dict:
        """Get current queue and execution status"""
        try:
            return {
                "queue_size": len(self.trade_queue),
                "active_trades": len(self.active_trades),
                "concurrent_by_exchange": dict(self.concurrent_trades_per_exchange),
                "queue_items": [
                    {
                        "bot_id": item['bot_id'][:8],
                        "exchange": item['exchange'],
                        "queued_at": item['queued_at']
                    }
                    for item in list(self.trade_queue)[:10]  # Show first 10
                ]
            }
            
        except Exception as e:
            logger.error(f"Get queue status error: {e}")
            return {"error": str(e)}
    
    async def clear_stale_trades(self):
        """Clean up stale active trades (e.g., if trade crashed)"""
        try:
            now = datetime.now(timezone.utc)
            stale_bots = []
            
            for bot_id, timestamp in list(self.active_trades.items()):
                age_minutes = (now - timestamp).seconds / 60
                
                if age_minutes > 10:  # Consider stale after 10 minutes
                    stale_bots.append(bot_id)
            
            for bot_id in stale_bots:
                del self.active_trades[bot_id]
                logger.warning(f"🧹 Cleaned up stale trade: {bot_id[:8]}")
            
            if stale_bots:
                # Reset concurrent counters
                for exchange in self.concurrent_trades_per_exchange.keys():
                    self.concurrent_trades_per_exchange[exchange] = 0
                    
        except Exception as e:
            logger.error(f"Clear stale trades error: {e}")

    async def purge_orphaned_queue(self, valid_bot_ids: Optional[Set[str]] = None) -> Dict:
        """Remove queue items for deleted/non-existent bots and stale queued items."""
        try:
            if valid_bot_ids is None:
                docs = await db.bots_collection.find(
                    {
                        "status": {"$ne": "deleted"},
                        "deleted_at": {"$exists": False},
                    },
                    {"_id": 0, "id": 1},
                ).to_list(5000)
                valid_bot_ids = {d.get("id") for d in docs if d.get("id")}

            now = datetime.now(timezone.utc)
            kept = deque()
            removed_missing = 0
            removed_stale = 0

            for item in list(self.trade_queue):
                bot_id = item.get("bot_id")
                if bot_id not in valid_bot_ids:
                    removed_missing += 1
                    continue
                queued_at = self._parse_queued_at(item.get("queued_at"), now)
                age_minutes = (now - queued_at).total_seconds() / 60
                if age_minutes >= 30:
                    removed_stale += 1
                    continue
                kept.append(item)

            self.trade_queue = kept

            # Active-trade entries for invalid bots should be removed too.
            stale_active = [bid for bid in list(self.active_trades.keys()) if bid not in valid_bot_ids]
            for bid in stale_active:
                self.active_trades.pop(bid, None)

            if removed_missing or removed_stale or stale_active:
                logger.info(
                    "🧹 Queue cleanup: removed_missing=%d removed_stale=%d stale_active=%d queue_size=%d",
                    removed_missing, removed_stale, len(stale_active), len(self.trade_queue),
                )

            return {
                "removed_missing": removed_missing,
                "removed_stale": removed_stale,
                "stale_active_removed": len(stale_active),
                "queue_size": len(self.trade_queue),
            }
        except Exception as e:
            logger.error(f"Purge orphaned queue error: {e}")
            return {"error": str(e), "queue_size": len(self.trade_queue)}

    async def clear_bot(self, bot_id: str) -> None:
        """Remove all queued/active runtime state for a bot."""
        self.active_trades.pop(bot_id, None)
        self.trade_queue = deque([item for item in self.trade_queue if item.get("bot_id") != bot_id])

    async def clear_user(self, user_id: str) -> None:
        """Remove queued/active runtime state for all bots belonging to user."""
        try:
            docs = await db.bots_collection.find({"user_id": user_id}, {"_id": 0, "id": 1}).to_list(5000)
            for doc in docs:
                bot_id = doc.get("id")
                if bot_id:
                    await self.clear_bot(bot_id)
        except Exception as e:
            logger.warning(f"clear_user queue cleanup failed: {e}")

    @staticmethod
    def _parse_queued_at(value, fallback: datetime) -> datetime:
        """Best-effort queued_at parser for queue cleanup."""
        if isinstance(value, datetime):
            return value
        try:
            raw = str(value or "").strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            parsed = datetime.fromisoformat(raw)
            return parsed
        except Exception:
            return fallback

# Global instance
trade_staggerer = TradeStaggerer()
