"""
Risk Management System - Stop Loss, Take Profit, Trailing Stop
Critical safety features for live trading

Risk Rule Precedence (highest → lowest):
  1. Emergency Stop   — global kill-switch, overrides everything
  2. Circuit Breaker  — rapid successive losses trigger cooldown
  3. Daily Loss Lock  — cumulative daily loss exceeds threshold
  4. Bodyguard Lock   — per-bot protective pause
  5. Training Gate    — 7-day paper training requirement

Dynamic thresholds are computed as percentages of current equity
(configured via DAILY_LOSS_LIMIT and MAX_DRAW_DOWN env vars).
"""
import asyncio
import os
from datetime import datetime, timezone
import database as db
from logger_config import logger
from typing import Optional, Dict, List


# Default risk parameters (percent values)
# Tuned to realistic scalping defaults and configurable via env.
DEFAULT_STOP_LOSS_PCT = float(os.getenv("DEFAULT_STOP_LOSS_PCT", "0.5"))      # 0.5%
DEFAULT_TAKE_PROFIT_PCT = float(os.getenv("DEFAULT_TAKE_PROFIT_PCT", "0.8"))  # 0.8%
DEFAULT_TRAILING_STOP_PCT = float(os.getenv("DEFAULT_TRAILING_STOP_PCT", "0.4"))  # 0.4%

# Dynamic thresholds from environment (fractions of equity)
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "0.03"))   # 3%
MAX_DRAW_DOWN = float(os.getenv("MAX_DRAW_DOWN", "0.10"))          # 10%

# Risk lock precedence (index 0 = highest priority)
RISK_LOCK_PRECEDENCE = [
    "emergency_stop",
    "circuit_breaker",
    "daily_loss_lock",
    "bodyguard_lock",
    "training_gate",
]


class RiskLockState:
    """
    Tracks which risk locks are active.  Enforces precedence so that
    higher-priority locks are evaluated first and cannot be overridden
    by lower-priority unlocks.
    """

    def __init__(self):
        self._locks: Dict[str, bool] = {name: False for name in RISK_LOCK_PRECEDENCE}
        self._lock_reasons: Dict[str, str] = {}

    def engage(self, lock_name: str, reason: str = "") -> None:
        if lock_name in self._locks:
            self._locks[lock_name] = True
            self._lock_reasons[lock_name] = reason
            logger.warning("🔒 Risk lock ENGAGED: %s — %s", lock_name, reason)

    def release(self, lock_name: str) -> None:
        if lock_name in self._locks:
            self._locks[lock_name] = False
            self._lock_reasons.pop(lock_name, None)
            logger.info("🔓 Risk lock RELEASED: %s", lock_name)

    def is_locked(self) -> bool:
        """Return True if any lock is active."""
        return any(self._locks.values())

    def highest_active_lock(self) -> Optional[str]:
        """Return the name of the highest-priority active lock, or None."""
        for name in RISK_LOCK_PRECEDENCE:
            if self._locks.get(name):
                return name
        return None

    def get_state(self) -> Dict:
        return {
            "locked": self.is_locked(),
            "highest_lock": self.highest_active_lock(),
            "locks": dict(self._locks),
            "reasons": dict(self._lock_reasons),
        }


class QuarantineManager:
    """Manages quarantined bots that triggered hard stops."""

    def __init__(self):
        self._quarantined: Dict[str, Dict] = {}  # bot_id → info

    def quarantine(self, bot_id: str, reason: str) -> None:
        self._quarantined[bot_id] = {
            "reason": reason,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning("🚫 Bot %s quarantined: %s", bot_id, reason)

    def release(self, bot_id: str) -> bool:
        if bot_id in self._quarantined:
            del self._quarantined[bot_id]
            logger.info("✅ Bot %s released from quarantine", bot_id)
            return True
        return False

    def is_quarantined(self, bot_id: str) -> bool:
        return bot_id in self._quarantined

    def get_all(self) -> Dict[str, Dict]:
        return dict(self._quarantined)


class DailyLossTracker:
    """Tracks cumulative daily loss per user for dynamic threshold enforcement."""

    def __init__(self):
        self._daily_losses: Dict[str, Dict] = {}  # user_id → {date, loss}

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def record_loss(self, user_id: str, loss_amount: float) -> None:
        today = self._today()
        entry = self._daily_losses.get(user_id, {})
        if entry.get("date") != today:
            entry = {"date": today, "loss": 0.0}
        entry["loss"] += abs(loss_amount)
        self._daily_losses[user_id] = entry

    def get_daily_loss(self, user_id: str) -> float:
        entry = self._daily_losses.get(user_id, {})
        if entry.get("date") != self._today():
            return 0.0
        return entry.get("loss", 0.0)

    def check_limit(self, user_id: str, equity: float) -> bool:
        """Return True if daily loss exceeds the dynamic threshold."""
        if equity <= 0:
            return False
        loss = self.get_daily_loss(user_id)
        return (loss / equity) >= DAILY_LOSS_LIMIT

    def reset(self, user_id: str) -> None:
        self._daily_losses.pop(user_id, None)


class RiskManagement:
    def __init__(self):
        self.active_positions = {}  # Track entry prices and stops
        self.is_running = False
        self.task = None
        self.lock_state = RiskLockState()
        self.quarantine = QuarantineManager()
        self.daily_loss_tracker = DailyLossTracker()
    
    # ------------------------------------------------------------------
    # Risk-lock precedence check
    # ------------------------------------------------------------------

    def check_risk_locks(self, bot_id: str) -> Optional[Dict]:
        """
        Evaluate risk locks in precedence order.
        Returns a dict describing the blocking lock, or None if clear.

        Precedence: Emergency Stop → Circuit Breaker → Daily Loss Lock
                    → Bodyguard Lock → Training Gate
        """
        if self.quarantine.is_quarantined(bot_id):
            return {
                "blocked": True,
                "lock": "quarantine",
                "reason": self.quarantine.get_all().get(bot_id, {}).get("reason", "Bot quarantined"),
            }

        lock = self.lock_state.highest_active_lock()
        if lock:
            return {
                "blocked": True,
                "lock": lock,
                "reason": self.lock_state._lock_reasons.get(lock, lock),
            }
        return None

    # ------------------------------------------------------------------
    # Dynamic threshold helpers
    # ------------------------------------------------------------------

    @staticmethod
    def compute_drawdown(current_equity: float, peak_equity: float) -> float:
        """Return drawdown as a positive fraction clamped to [0.0, 1.0]."""
        if peak_equity <= 0:
            return 0.0
        raw = (peak_equity - current_equity) / peak_equity
        return max(0.0, min(1.0, raw))

    def check_max_drawdown(self, current_equity: float, peak_equity: float) -> bool:
        """Return True if drawdown exceeds MAX_DRAW_DOWN threshold."""
        dd = self.compute_drawdown(current_equity, peak_equity)
        return dd >= MAX_DRAW_DOWN

    # ------------------------------------------------------------------
    # Position management (preserved from original)
    # ------------------------------------------------------------------

    async def set_position(self, bot_id: str, entry_price: float, 
                          stop_loss_pct: float = None, 
                          take_profit_pct: float = None,
                          trailing_stop_pct: float = None):
        """
        Set stop loss and take profit for a new position
        
        Args:
            bot_id: Bot identifier
            entry_price: Entry price of the trade
            stop_loss_pct: Stop loss percentage (default 2%)
            take_profit_pct: Take profit percentage (default 5%)
            trailing_stop_pct: Trailing stop percentage (default 3%)
        """
        stop_loss = stop_loss_pct or DEFAULT_STOP_LOSS_PCT
        take_profit = take_profit_pct or DEFAULT_TAKE_PROFIT_PCT
        trailing = trailing_stop_pct or DEFAULT_TRAILING_STOP_PCT
        
        # Calculate absolute prices
        stop_loss_price = entry_price * (1 - stop_loss / 100)
        take_profit_price = entry_price * (1 + take_profit / 100)
        trailing_stop_price = entry_price * (1 - trailing / 100)
        
        self.active_positions[bot_id] = {
            'entry_price': entry_price,
            'stop_loss_pct': stop_loss,
            'take_profit_pct': take_profit,
            'trailing_stop_pct': trailing,
            'stop_loss_price': stop_loss_price,
            'take_profit_price': take_profit_price,
            'trailing_stop_price': trailing_stop_price,
            'highest_price': entry_price,
            'opened_at': datetime.now(timezone.utc)
        }
        
        logger.info(f"🎯 Risk set for bot {bot_id}: SL={stop_loss}%, TP={take_profit}%, Trail={trailing}%")
    
    async def check_position(self, bot_id: str, current_price: float) -> Optional[Dict]:
        """
        Check if stop loss or take profit is triggered
        
        Returns:
            Dict with action ('stop_loss', 'take_profit', 'trailing_stop') or None
        """
        if bot_id not in self.active_positions:
            return None
        
        position = self.active_positions[bot_id]
        entry_price = position['entry_price']
        
        # Calculate current profit/loss percentage
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Check STOP LOSS
        if current_price <= position['stop_loss_price']:
            logger.warning(f"🛑 STOP LOSS triggered for bot {bot_id}: {pnl_pct:.2f}%")
            return {
                'action': 'stop_loss',
                'reason': f"Stop loss triggered at {pnl_pct:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        # Check TAKE PROFIT
        if current_price >= position['take_profit_price']:
            logger.info(f"✅ TAKE PROFIT triggered for bot {bot_id}: +{pnl_pct:.2f}%")
            return {
                'action': 'take_profit',
                'reason': f"Take profit triggered at +{pnl_pct:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        # Update TRAILING STOP
        if current_price > position['highest_price']:
            position['highest_price'] = current_price
            # Move trailing stop up
            new_trailing_price = current_price * (1 - position['trailing_stop_pct'] / 100)
            if new_trailing_price > position['trailing_stop_price']:
                position['trailing_stop_price'] = new_trailing_price
                logger.debug(f"📈 Trailing stop updated for bot {bot_id}: R{new_trailing_price:.2f}")
        
        # Check TRAILING STOP
        if current_price <= position['trailing_stop_price'] and position['highest_price'] > entry_price:
            profit_secured = ((position['trailing_stop_price'] - entry_price) / entry_price) * 100
            logger.info(f"🔒 TRAILING STOP triggered for bot {bot_id}: Secured +{profit_secured:.2f}%")
            return {
                'action': 'trailing_stop',
                'reason': f"Trailing stop triggered, profit secured: +{profit_secured:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        return None
    
    async def close_position(self, bot_id: str):
        """Remove position from tracking"""
        if bot_id in self.active_positions:
            del self.active_positions[bot_id]
            logger.debug(f"Position closed for bot {bot_id}")
    
    async def execute_exit(self, bot_id: str, exit_price: float, reason: str) -> bool:
        """
        Execute exit order for a position
        
        Args:
            bot_id: Bot identifier
            exit_price: Exit price
            reason: Reason for exit (stop_loss, take_profit, trailing_stop)
        
        Returns:
            True if successful
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return False
            
            # Calculate final P&L
            position = self.active_positions.get(bot_id)
            if position:
                entry_price = position['entry_price']
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                pnl_amount = bot.get('current_capital', 0) * (pnl_pct / 100)
            else:
                pnl_amount = 0
                pnl_pct = 0
            
            # Track daily losses
            if pnl_amount < 0:
                self.daily_loss_tracker.record_loss(
                    bot.get("user_id", ""), abs(pnl_amount)
                )

            # Update bot capital
            new_capital = bot.get('current_capital', 0) + pnl_amount
            new_total_profit = bot.get('total_profit', 0) + pnl_amount
            
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "total_profit": new_total_profit,
                        "last_trade_time": datetime.now(timezone.utc)
                    },
                    "$inc": {
                        "trades_count": 1,
                        "win_count": 1 if pnl_amount > 0 else 0,
                        "loss_count": 1 if pnl_amount < 0 else 0
                    }
                }
            )
            
            # Record trade
            from utils.trade_utils import build_trade_record

            trade = build_trade_record(
                {
                    "id": f"{bot_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    "bot_id": bot_id,
                    "bot_name": bot.get('name'),
                    "user_id": bot.get('user_id'),
                    "pair": bot.get('pair', 'BTC/ZAR'),
                    "exchange": bot.get('exchange'),
                    "side": "sell",
                    "amount": 0.01,
                    "price": exit_price,
                    "profit_loss": pnl_amount,
                    "profit_loss_pct": pnl_pct,
                    "exit_reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trading_mode": bot.get("trading_mode", "paper"),
                    "is_live": bot.get("trading_mode") == "live"
                },
                user_id=bot.get('user_id'),
                bot=bot
            )
            
            await db.trades_collection.insert_one(trade)
            
            # Quarantine bot on hard stop-loss
            if reason == "stop_loss":
                self.quarantine.quarantine(bot_id, f"Hard stop-loss at {pnl_pct:.2f}%")

            # Send real-time notification
            try:
                from realtime_events import rt_events
                await rt_events.trade_executed(bot['user_id'], trade)
                await rt_events.profit_updated(bot['user_id'], new_total_profit, bot.get('name'))
            except:
                pass
            
            # Close position tracking
            await self.close_position(bot_id)
            
            emoji = "🛑" if reason == "stop_loss" else "✅" if reason == "take_profit" else "🔒"
            logger.info(f"{emoji} Exit executed for {bot.get('name')}: {reason} at R{exit_price:.2f} ({pnl_pct:+.2f}%)")
            
            return True
        
        except Exception as e:
            logger.error(f"Exit execution error for bot {bot_id}: {e}")
            return False
    
    async def monitoring_loop(self):
        """Monitor all active positions every 10 seconds"""
        logger.info("🎯 Risk management monitoring started")
        
        while self.is_running:
            try:
                if not self.active_positions:
                    await asyncio.sleep(10)
                    continue
                
                # Check each active position
                for bot_id in list(self.active_positions.keys()):
                    # Skip quarantined bots
                    if self.quarantine.is_quarantined(bot_id):
                        await self.close_position(bot_id)
                        continue

                    bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                    if not bot or bot.get('status') != 'active':
                        await self.close_position(bot_id)
                        continue
                    
                    # Get current price (simulated for now)
                    import random
                    position = self.active_positions[bot_id]
                    # Simulate price movement around entry
                    current_price = position['entry_price'] * random.uniform(0.95, 1.08)
                    
                    # Check if exit triggered
                    exit_signal = await self.check_position(bot_id, current_price)
                    
                    if exit_signal:
                        # Execute exit
                        await self.execute_exit(
                            bot_id, 
                            exit_signal['exit_price'], 
                            exit_signal['action']
                        )
                
                await asyncio.sleep(10)  # Check every 10 seconds
            
            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(60)
    
    def start(self):
        """Start risk management monitoring"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.monitoring_loop())
            logger.info("✅ Risk management started - Stop Loss, Take Profit, Trailing Stop active")
    
    def stop(self):
        """Stop risk management monitoring"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("⏹️ Risk management stopped")


# Global instance
risk_management = RiskManagement()
