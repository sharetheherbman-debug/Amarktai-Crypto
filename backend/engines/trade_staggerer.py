"""
Trade Staggerer - 24/7 Staggered Trade Execution
- Spreads trades across the day to avoid rate limits
- Manages concurrent execution across exchanges
- Prevents API overload with intelligent queuing
"""

import asyncio
import os
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from collections import deque
import logging

import database as db

logger = logging.getLogger(__name__)

# Minimum seconds a bot must wait between successfully opening new trades.
# This enforces round-robin fairness across the fleet: once a bot opens a
# trade it is benched for this period so other bots get execution slots.
# Only applied when had_entry=True (new trade opened), NOT for close-only or
# skip ticks — those are unaffected so trade management stays responsive.
# Default: 30s — allows faster rotation in a paper fleet.
# For live mode, set BOT_TRADE_COOLDOWN_SECONDS=60 via env.
BOT_TRADE_COOLDOWN_SECONDS = int(os.getenv("BOT_TRADE_COOLDOWN_SECONDS", "30"))

# Maximum seconds a bot's execution slot may remain "in-flight" before the
# concurrent-execution guard considers it stuck.  In practice paper trades
# complete in < 1s but the guard prevents double-submission if the async loop
# ever delivers two ticks for the same bot at once.
BOT_EXECUTION_TIMEOUT_SECONDS = int(os.getenv("BOT_EXECUTION_TIMEOUT_SECONDS", "60"))

class TradeStaggerer:
    def __init__(self):
        # Queue management
        self.trade_queue = deque()
        self.active_trades = {}  # {bot_id: timestamp} — currently-executing trades

        # Per-bot post-trade cooldown: tracks when each bot last COMPLETED a new
        # trade entry.  Used by can_execute_now to prevent a single bot from
        # consuming all execution slots while others are waiting.
        self._last_completed: Dict[str, datetime] = {}
        
        # Rate limiting per exchange.
        # For LIVE trading these values are real API rate limits.
        # For PAPER trading the concurrency limits govern how many paper-engine
        # coroutines can process simultaneously — paper bots do not hit real APIs
        # so higher concurrency is safe and necessary for fleet-wide participation.
        # Luno: raised from 2→10 for paper so a 10-bot Luno fleet can actually
        # run concurrently rather than serializing through a few slots.
        # Override via env: TRADE_STAGGERER_LUNO_MAX_CONCURRENT, etc.
        _luno_max = int(os.getenv("TRADE_STAGGERER_LUNO_MAX_CONCURRENT", "10"))
        self.exchange_limits = {
            'luno': {'max_concurrent': _luno_max, 'min_delay': 5},
            'binance': {'max_concurrent': 10, 'min_delay': 2},   # 10 concurrent for paper fleet
            'kucoin': {'max_concurrent': 5, 'min_delay': 3},
            'bybit': {'max_concurrent': 5, 'min_delay': 3},
            'bitget': {'max_concurrent': 5, 'min_delay': 3}
        }
        
        self.last_trade_per_exchange = {}
        self.concurrent_trades_per_exchange = {}
        
        # Initialize counters
        for exchange in self.exchange_limits.keys():
            self.last_trade_per_exchange[exchange] = None
            self.concurrent_trades_per_exchange[exchange] = 0
    
    async def can_execute_now(self, bot_id: str, exchange: str, paper_mode: bool = False) -> tuple[bool, str]:
        """Check if a bot can execute a trade now"""
        try:
            # Per-bot post-trade cooldown: prevent the same bot from monopolising
            # execution slots.  This fires AFTER a trade entry completes (not during
            # the trade, which is tracked by active_trades below).
            last_done = self._last_completed.get(bot_id)
            if last_done:
                elapsed = (datetime.now(timezone.utc) - last_done).total_seconds()
                if elapsed < BOT_TRADE_COOLDOWN_SECONDS:
                    remaining = int(BOT_TRADE_COOLDOWN_SECONDS - elapsed)
                    return False, f"Bot post-trade cooldown ({remaining}s remaining)"

            # Check if bot already has an active (in-flight) trade
            if bot_id in self.active_trades:
                elapsed = (datetime.now(timezone.utc) - self.active_trades[bot_id]).total_seconds()
                if elapsed < BOT_EXECUTION_TIMEOUT_SECONDS:
                    return False, f"Bot execution in progress ({int(BOT_EXECUTION_TIMEOUT_SECONDS - elapsed)}s remaining)"
            
            # Check exchange rate limits
            limits = self.exchange_limits.get(exchange.lower(), self.exchange_limits['binance'])
            
            # Check concurrent limit
            concurrent = self.concurrent_trades_per_exchange.get(exchange, 0)
            if concurrent >= limits['max_concurrent']:
                return False, f"Exchange concurrent limit reached ({concurrent}/{limits['max_concurrent']})"
            
            # Check minimum delay between trades on this exchange.
            # Paper bots do not hit real exchange APIs so the inter-trade delay is
            # pure serialisation overhead.  Skip it for paper bots so that multiple
            # paper bots on the same exchange can execute in the same scheduler tick
            # without artificially waiting seconds between each one.
            if not paper_mode:
                last_trade = self.last_trade_per_exchange.get(exchange)
                if last_trade:
                    elapsed = (datetime.now(timezone.utc) - last_trade).total_seconds()
                    if elapsed < limits['min_delay']:
                        return False, f"Exchange rate limit ({int(limits['min_delay'] - elapsed)}s remaining)"
            
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
    
    async def register_trade_complete(self, bot_id: str, exchange: str, had_entry: bool = False):
        """Register that a trade has completed.

        Args:
            bot_id:     The bot that finished its execution slot.
            exchange:   The exchange the bot was trading on.
            had_entry:  True when the bot successfully OPENED a new trade this slot.
                        When True the per-bot cooldown (BOT_TRADE_COOLDOWN_SECONDS) is
                        started so other bots get execution slots before this one
                        re-enters.  False for close-only ticks and skip ticks so that
                        trade management (exit monitoring) remains responsive.
        """
        try:
            if bot_id in self.active_trades:
                del self.active_trades[bot_id]

            if had_entry:
                # Start per-bot cooldown: bench this bot for BOT_TRADE_COOLDOWN_SECONDS
                # so other bots get their turn at the exchange execution slot.
                self._last_completed[bot_id] = datetime.now(timezone.utc)
            
            current = self.concurrent_trades_per_exchange.get(exchange, 0)
            self.concurrent_trades_per_exchange[exchange] = max(0, current - 1)
            
            logger.debug(
                f"✅ Trade completed: {bot_id[:8]} on {exchange} "
                f"(concurrent: {max(0, current - 1)}, had_entry={had_entry})"
            )
            
        except Exception as e:
            logger.error(f"Register trade complete error: {e}")
    
    async def add_to_queue(self, bot_id: str, exchange: str, priority: int = 0, paper_mode: bool = False):
        """Add a trade request to the queue"""
        try:
            if not bot_id or not exchange:
                logger.warning(
                    f"⚠️ Rejecting malformed add_to_queue call: bot_id={bot_id!r}, exchange={exchange!r}"
                )
                return

            trade_request = {
                "bot_id": bot_id,
                "exchange": exchange,
                "priority": priority,
                "paper_mode": paper_mode,
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
                
                bot_id = trade_request.get('bot_id')
                exchange = trade_request.get('exchange')

                if not bot_id or not exchange:
                    logger.warning(
                        f"⚠️ Malformed queue entry – dropping. payload={trade_request!r}"
                    )
                    continue

                # Drop entry immediately if bot is no longer active in DB
                try:
                    bot_doc = await db.bots_collection.find_one(
                        {"id": bot_id, "status": "active"}, {"_id": 0, "id": 1}
                    )
                    if not bot_doc:
                        bot_id_display = str(bot_id)[:8] if bot_id else 'unknown'
                        logger.info(f"🗑️ Discarding queue entry for inactive/deleted bot {bot_id_display}")
                        continue
                except Exception:
                    pass  # If DB check fails, fall through to normal logic
                
                can_execute, reason = await self.can_execute_now(
                    bot_id, exchange, paper_mode=trade_request.get('paper_mode', False)
                )
                
                if can_execute:
                    return trade_request
                else:
                    # Put back in queue if still relevant
                    queued_time = datetime.fromisoformat(trade_request['queued_at'].replace('Z', '+00:00'))
                    age_minutes = (datetime.now(timezone.utc) - queued_time).total_seconds() / 60
                    
                    if age_minutes < 30:  # Only re-queue if less than 30 minutes old
                        self.trade_queue.append(trade_request)
                    else:
                        bot_id_display = str(bot_id)[:8] if bot_id else 'unknown'
                        logger.warning(f"⏰ Dropped stale trade request: {bot_id_display} (age: {age_minutes:.1f}m)")
            
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
                        "bot_id": (item.get('bot_id') or '')[:8],
                        "exchange": item.get('exchange', ''),
                        "queued_at": item.get('queued_at', '')
                    }
                    for item in list(self.trade_queue)[:10]  # Show first 10
                ]
            }
            
        except Exception as e:
            logger.error(f"Get queue status error: {e}")
            return {"error": str(e)}
    
    async def get_queue_state(self) -> Dict:
        """Get detailed queue state for diagnostics (admin-only)
        
        Returns:
            queue_size: Number of trades in queue
            next_eligible: When next trade can execute
            locks: Active trade locks by bot_id
            cooldowns: Last trade time per exchange
            sample_items: Redacted sample of queue items
            exchange_stats: Statistics per exchange
        """
        try:
            # Calculate next eligible time
            next_eligible = None
            now = datetime.now(timezone.utc)
            
            # Check minimum wait times across all exchanges
            for exchange, last_time in self.last_trade_per_exchange.items():
                if last_time:
                    limits = self.exchange_limits.get(exchange, self.exchange_limits['binance'])
                    next_time = last_time + timedelta(seconds=limits['min_delay'])
                    if not next_eligible or next_time < next_eligible:
                        next_eligible = next_time
            
            # Build locks info (active trades)
            locks = {}
            for bot_id, timestamp in self.active_trades.items():
                age_seconds = (now - timestamp).total_seconds()
                locks[bot_id] = {  # Use full bot_id to avoid collisions
                    "started_at": timestamp.isoformat(),
                    "age_seconds": int(age_seconds)
                }
            
            # Build cooldowns info
            cooldowns = {}
            for exchange, last_time in self.last_trade_per_exchange.items():
                if last_time:
                    limits = self.exchange_limits.get(exchange, {})
                    age_seconds = (now - last_time).total_seconds()
                    remaining = max(0, limits.get('min_delay', 0) - int(age_seconds))
                    cooldowns[exchange] = {
                        "last_trade": last_time.isoformat(),
                        "age_seconds": int(age_seconds),
                        "remaining_seconds": remaining,
                        "min_delay": limits.get('min_delay', 0)
                    }
            
            # Sample queue items (redacted)
            sample_items = []
            for item in list(self.trade_queue)[:5]:
                bid = item.get('bot_id') or ''
                sample_items.append({
                    "bot_id": bid[:12] + "..." if len(bid) > 12 else bid,  # Show more characters to reduce collision risk
                    "exchange": item.get('exchange', ''),
                    "priority": item.get('priority', 0),
                    "queued_at": item.get('queued_at', '')
                })
            
            # Exchange stats
            exchange_stats = {}
            for exchange, limits in self.exchange_limits.items():
                concurrent = self.concurrent_trades_per_exchange.get(exchange, 0)
                exchange_stats[exchange] = {
                    "concurrent_trades": concurrent,
                    "max_concurrent": limits['max_concurrent'],
                    "min_delay_seconds": limits['min_delay'],
                    "last_trade": self.last_trade_per_exchange.get(exchange, None).isoformat() if self.last_trade_per_exchange.get(exchange) else None
                }
            
            return {
                "queue_size": len(self.trade_queue),
                "active_trades_count": len(self.active_trades),
                "next_eligible": next_eligible.isoformat() if next_eligible else None,
                "locks": locks,
                "cooldowns": cooldowns,
                "sample_items": sample_items,
                "exchange_stats": exchange_stats,
                # paper_mode flag stored on each queue item bypasses min_delay
                # for paper bots — verified active when True shows in sample_items
                "paper_min_delay_bypass_enabled": True,
                "bot_trade_cooldown_seconds": BOT_TRADE_COOLDOWN_SECONDS,
            }
            
        except Exception as e:
            logger.error(f"Get queue state error: {e}")
            return {"error": str(e)}
    
    async def clear_stale_trades(self):
        """Clean up stale active trades (e.g., if trade crashed)"""
        try:
            now = datetime.now(timezone.utc)
            stale_bots = []
            
            for bot_id, timestamp in list(self.active_trades.items()):
                age_minutes = (now - timestamp).total_seconds() / 60
                
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

# Global instance
trade_staggerer = TradeStaggerer()
