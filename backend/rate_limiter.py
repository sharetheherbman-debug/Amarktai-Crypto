"""Rate limiter for exchange API calls"""
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging
from exchange_limits import get_exchange_limits

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.orders_today = defaultdict(int)  # {exchange: count}
        self.orders_this_minute = defaultdict(lambda: {"count": 0, "reset_time": datetime.now(timezone.utc)})
        self.orders_per_10_seconds = defaultdict(lambda: {"count": 0, "reset_time": datetime.now(timezone.utc)})  # Burst protection
        self.bot_orders_today = defaultdict(int)  # {bot_id: count}
        self.last_reset = datetime.now(timezone.utc).date()
    
    def _reset_if_needed(self):
        """Reset daily counters at midnight"""
        today = datetime.now(timezone.utc).date()
        if today > self.last_reset:
            self.orders_today.clear()
            self.bot_orders_today.clear()
            self.last_reset = today
            logger.info("Rate limiter: Daily counters reset")
    
    def _reset_minute_if_needed(self, exchange: str):
        """Reset per-minute counter after 60 seconds"""
        now = datetime.now(timezone.utc)
        minute_data = self.orders_this_minute[exchange]
        if (now - minute_data["reset_time"]).total_seconds() >= 60:
            minute_data["count"] = 0
            minute_data["reset_time"] = now
    
    def _reset_10_seconds_if_needed(self, exchange: str):
        """Reset per-10-seconds counter (BURST PROTECTION)"""
        now = datetime.now(timezone.utc)
        burst_data = self.orders_per_10_seconds[exchange]
        if (now - burst_data["reset_time"]).total_seconds() >= 10:
            burst_data["count"] = 0
            burst_data["reset_time"] = now
    
    def can_trade(self, bot_id: str, exchange: str) -> tuple[bool, str]:
        """Check if bot can trade on exchange (with BURST PROTECTION)"""
        self._reset_if_needed()
        self._reset_minute_if_needed(exchange)
        self._reset_10_seconds_if_needed(exchange)
        
        limits = get_exchange_limits(exchange)
        
        # Check BURST PROTECTION (10 orders per 10 seconds)
        if self.orders_per_10_seconds[exchange]["count"] >= limits.get("max_orders_per_10_seconds", 10):
            return False, f"Burst limit reached for {exchange.upper()} (max 10 orders per 10 seconds)"
        
        # Check daily exchange limit
        if self.orders_today[exchange] >= limits["max_orders_per_day"]:
            return False, f"Daily limit reached for {exchange.upper()} ({limits['max_orders_per_day']} orders)"
        
        # Check per-minute limit
        if self.orders_this_minute[exchange]["count"] >= limits["max_orders_per_minute"]:
            return False, f"Per-minute limit reached for {exchange.upper()}"
        
        # Check per-bot daily limit
        if self.bot_orders_today[bot_id] >= limits["max_orders_per_bot_per_day"]:
            return False, f"Bot daily limit reached ({limits['max_orders_per_bot_per_day']} orders)"
        
        return True, "OK"
    
    def record_trade(self, bot_id: str, exchange: str):
        """Record a trade for rate limiting"""
        self.orders_today[exchange] += 1
        self.orders_this_minute[exchange]["count"] += 1
        self.orders_per_10_seconds[exchange]["count"] += 1  # Burst tracking
        self.bot_orders_today[bot_id] += 1
        logger.debug(f"Rate limiter: {exchange} orders today: {self.orders_today[exchange]}, burst: {self.orders_per_10_seconds[exchange]['count']}/10")
    
    def purge_bots(self, bot_ids: list) -> None:
        """Remove per-bot counters for a list of deleted/reset bot IDs.

        Called by the reset orchestrator so that dangling rate-limit counts
        from soft-deleted bots don't affect new bots created after a reset.
        """
        for bid in bot_ids:
            self.bot_orders_today.pop(bid, None)

    def get_stats(self, exchange: str = None) -> dict:
        """Get current rate limit statistics"""
        if exchange:
            limits = get_exchange_limits(exchange)
            return {
                "exchange": exchange,
                "orders_today": self.orders_today[exchange],
                "max_daily": limits["max_orders_per_day"],
                "orders_this_minute": self.orders_this_minute[exchange]["count"],
                "max_per_minute": limits["max_orders_per_minute"],
            }
        
        return {
            "orders_by_exchange": dict(self.orders_today),
            "total_orders_today": sum(self.orders_today.values()),
        }

# Global instance
rate_limiter = RateLimiter()
