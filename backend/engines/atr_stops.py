"""
ATR-Based Stop-Loss and Trailing Stops
Implements dynamic stop-loss using Average True Range (ATR) for volatility-adjusted risk management
"""
import logging
from typing import Dict, Optional, List
import numpy as np
from datetime import datetime, timezone, timedelta
import database as db

logger = logging.getLogger(__name__)

# ATR configuration
ATR_PERIOD = 14  # Standard ATR period
ATR_MULTIPLIER_STOP = 2.0  # Stop-loss distance in ATR multiples
ATR_MULTIPLIER_TRAILING = 3.0  # Trailing stop distance in ATR multiples
MIN_STOP_LOSS_PCT = 0.02  # Minimum 2% stop-loss
MAX_STOP_LOSS_PCT = 0.15  # Maximum 15% stop-loss


class ATRStopLoss:
    """ATR-based dynamic stop-loss and trailing stops"""
    
    async def calculate_atr(self, bot_id: str, pair: str, period: int = ATR_PERIOD) -> Optional[float]:
        """Calculate Average True Range (ATR) from recent price data
        
        ATR = Average of True Range over N periods
        True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        
        Args:
            bot_id: Bot ID
            pair: Trading pair
            period: Number of periods for ATR calculation
            
        Returns:
            ATR value or None if insufficient data
        """
        try:
            # Get recent trades for price data
            trades = await db.trades_collection.find(
                {
                    "bot_id": bot_id,
                    "pair": pair,
                    "status": {"$in": ["closed", "open"]}
                },
                {"_id": 0, "entry_price": 1, "exit_price": 1, "timestamp": 1}
            ).sort("timestamp", -1).limit(period + 1).to_list(period + 1)
            
            if len(trades) < period:
                logger.warning(f"Insufficient data for ATR calculation: {len(trades)} < {period}")
                return None
            
            # Calculate True Range for each period
            true_ranges = []
            prev_close = None
            
            for trade in reversed(trades):
                entry = trade.get('entry_price', 0)
                exit_price = trade.get('exit_price', entry)
                
                if prev_close is not None:
                    # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
                    high = max(entry, exit_price)
                    low = min(entry, exit_price)
                    
                    tr1 = high - low
                    tr2 = abs(high - prev_close)
                    tr3 = abs(low - prev_close)
                    
                    true_range = max(tr1, tr2, tr3)
                    true_ranges.append(true_range)
                
                prev_close = exit_price
            
            if not true_ranges:
                return None
            
            # ATR is the average of true ranges
            atr = np.mean(true_ranges)
            
            return float(atr)
            
        except Exception as e:
            logger.error(f"ATR calculation error: {e}", exc_info=True)
            return None
    
    async def calculate_atr_stop_loss(
        self, 
        bot_id: str,
        pair: str,
        entry_price: float,
        direction: str = "long",
        atr_multiplier: float = ATR_MULTIPLIER_STOP
    ) -> Dict:
        """Calculate stop-loss level using ATR
        
        Args:
            bot_id: Bot ID
            pair: Trading pair
            entry_price: Entry price of the position
            direction: "long" or "short"
            atr_multiplier: Multiplier for ATR (default 2.0)
            
        Returns:
            Dict with stop-loss information
        """
        try:
            # Calculate ATR
            atr = await self.calculate_atr(bot_id, pair)
            
            if atr is None:
                # Fallback to percentage-based stop
                bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                risk_mode = bot.get('risk_mode', 'balanced') if bot else 'balanced'
                
                stop_pct = {
                    'safe': 0.05,       # 5%
                    'balanced': 0.07,   # 7%
                    'risky': 0.10,      # 10%
                    'aggressive': 0.12  # 12%
                }.get(risk_mode, 0.07)
                
                if direction == "long":
                    stop_loss = entry_price * (1 - stop_pct)
                else:
                    stop_loss = entry_price * (1 + stop_pct)
                
                return {
                    "bot_id": bot_id,
                    "pair": pair,
                    "entry_price": round(entry_price, 2),
                    "stop_loss": round(stop_loss, 2),
                    "stop_loss_distance": round(abs(entry_price - stop_loss), 2),
                    "stop_loss_pct": round(stop_pct * 100, 2),
                    "method": "percentage_fallback",
                    "direction": direction
                }
            
            # Calculate ATR-based stop-loss distance
            stop_distance = atr * atr_multiplier
            
            # Calculate stop-loss price
            if direction == "long":
                stop_loss = entry_price - stop_distance
            else:
                stop_loss = entry_price + stop_distance
            
            # Calculate percentage
            stop_pct = abs(stop_distance / entry_price)
            
            # Clamp to min/max bounds using helper
            stop_pct, stop_distance, stop_loss = self._clamp_stop_loss(
                stop_pct, stop_distance, entry_price, direction
            )
            
            return {
                "bot_id": bot_id,
                "pair": pair,
                "entry_price": round(entry_price, 2),
                "stop_loss": round(stop_loss, 2),
                "stop_loss_distance": round(stop_distance, 2),
                "stop_loss_pct": round(stop_pct * 100, 2),
                "atr": round(atr, 2),
                "atr_multiplier": atr_multiplier,
                "method": "atr_based",
                "direction": direction
            }
            
        except Exception as e:
            logger.error(f"ATR stop-loss calculation error: {e}")
            return {"error": str(e)}
    
    async def update_trailing_stop(
        self,
        trade_id: str,
        current_price: float,
        atr_multiplier: float = ATR_MULTIPLIER_TRAILING
    ) -> Dict:
        """Update trailing stop for an open trade using ATR
        
        Args:
            trade_id: Trade ID
            current_price: Current market price
            atr_multiplier: Multiplier for ATR trailing distance
            
        Returns:
            Dict with updated trailing stop information
        """
        try:
            # Get trade data
            trade = await db.trades_collection.find_one({"id": trade_id}, {"_id": 0})
            if not trade:
                return {"error": "Trade not found"}
            
            bot_id = trade.get('bot_id')
            pair = trade.get('pair')
            entry_price = trade.get('entry_price', 0)
            direction = trade.get('direction', 'long')
            current_stop = trade.get('stop_loss', entry_price * 0.95)  # Default 5% stop
            
            # Calculate ATR
            atr = await self.calculate_atr(bot_id, pair)
            
            if atr is None:
                # Keep existing stop-loss
                return {
                    "trade_id": trade_id,
                    "current_stop_loss": round(current_stop, 2),
                    "new_stop_loss": round(current_stop, 2),
                    "stop_updated": False,
                    "reason": "Insufficient data for ATR"
                }
            
            # Calculate trailing stop distance
            trailing_distance = atr * atr_multiplier
            
            # Calculate new stop-loss based on current price
            if direction == "long":
                new_stop = current_price - trailing_distance
                # Only move stop up, never down
                if new_stop > current_stop:
                    should_update = True
                else:
                    new_stop = current_stop
                    should_update = False
            else:  # short
                new_stop = current_price + trailing_distance
                # Only move stop down, never up
                if new_stop < current_stop:
                    should_update = True
                else:
                    new_stop = current_stop
                    should_update = False
            
            # Update trade if stop moved
            if should_update:
                await db.trades_collection.update_one(
                    {"id": trade_id},
                    {
                        "$set": {
                            "stop_loss": new_stop,
                            "trailing_stop_updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
            
            return {
                "trade_id": trade_id,
                "pair": pair,
                "direction": direction,
                "entry_price": round(entry_price, 2),
                "current_price": round(current_price, 2),
                "current_stop_loss": round(current_stop, 2),
                "new_stop_loss": round(new_stop, 2),
                "trailing_distance": round(trailing_distance, 2),
                "atr": round(atr, 2),
                "atr_multiplier": atr_multiplier,
                "stop_updated": should_update
            }
            
        except Exception as e:
            logger.error(f"Trailing stop update error: {e}")
            return {"error": str(e)}
    
    def _clamp_stop_loss(
        self,
        stop_pct: float,
        stop_distance: float,
        entry_price: float,
        direction: str
    ) -> tuple[float, float, float]:
        """Helper to clamp stop-loss to min/max bounds
        
        Args:
            stop_pct: Stop-loss percentage
            stop_distance: Stop-loss distance
            entry_price: Entry price
            direction: "long" or "short"
            
        Returns:
            Tuple of (clamped_pct, clamped_distance, stop_loss_price)
        """
        if stop_pct < MIN_STOP_LOSS_PCT:
            stop_pct = MIN_STOP_LOSS_PCT
            stop_distance = entry_price * MIN_STOP_LOSS_PCT
        elif stop_pct > MAX_STOP_LOSS_PCT:
            stop_pct = MAX_STOP_LOSS_PCT
            stop_distance = entry_price * MAX_STOP_LOSS_PCT
        
        if direction == "long":
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance
        
        return stop_pct, stop_distance, stop_loss
    
    async def check_stop_loss_hit(self, trade_id: str, current_price: float) -> Dict:
        """Check if stop-loss has been hit for a trade
        
        Args:
            trade_id: Trade ID
            current_price: Current market price
            
        Returns:
            Dict with stop-loss hit status
        """
        try:
            trade = await db.trades_collection.find_one({"id": trade_id}, {"_id": 0})
            if not trade:
                return {"error": "Trade not found"}
            
            direction = trade.get('direction', 'long')
            stop_loss = trade.get('stop_loss')
            
            if not stop_loss:
                return {
                    "trade_id": trade_id,
                    "stop_loss_hit": False,
                    "reason": "No stop-loss set"
                }
            
            # Check if stop hit
            if direction == "long":
                stop_hit = current_price <= stop_loss
            else:
                stop_hit = current_price >= stop_loss
            
            if stop_hit:
                # Update trade with stop-loss event
                await db.trades_collection.update_one(
                    {"id": trade_id},
                    {
                        "$set": {
                            "stop_loss_hit": True,
                            "stop_loss_hit_at": datetime.now(timezone.utc).isoformat(),
                            "stop_loss_hit_price": current_price
                        }
                    }
                )
                
                # Update bot with stop-loss event for cooldown tracking
                bot_id = trade.get('bot_id')
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {"$set": {"last_stop_loss_at": datetime.now(timezone.utc).isoformat()}}
                )
            
            return {
                "trade_id": trade_id,
                "direction": direction,
                "current_price": round(current_price, 2),
                "stop_loss": round(stop_loss, 2),
                "stop_loss_hit": stop_hit,
                "distance_to_stop": round(abs(current_price - stop_loss), 2)
            }
            
        except Exception as e:
            logger.error(f"Stop-loss check error: {e}")
            return {"error": str(e)}


# Global singleton instance
atr_stop_loss = ATRStopLoss()
