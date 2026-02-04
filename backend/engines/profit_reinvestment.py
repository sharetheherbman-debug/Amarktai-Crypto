"""
Profit Reinvestment Module
Implements configurable profit reinvestment (0-100%) for dynamic capital allocation
"""
import logging
from typing import Dict, Optional
from datetime import datetime, timezone
import database as db

logger = logging.getLogger(__name__)

# Default reinvestment percentage
DEFAULT_REINVESTMENT_PCT = 50.0  # 50% of profits reinvested

# Minimum profit threshold for reinvestment
MIN_PROFIT_FOR_REINVESTMENT = 10.0  # R10 minimum


class ProfitReinvestment:
    """Manages profit reinvestment for bots"""
    
    async def set_reinvestment_percentage(
        self,
        bot_id: str,
        reinvestment_pct: float
    ) -> Dict:
        """Set reinvestment percentage for a bot
        
        Args:
            bot_id: Bot ID
            reinvestment_pct: Percentage of profits to reinvest (0-100)
            
        Returns:
            Dict with update status
        """
        try:
            # Validate percentage
            if reinvestment_pct < 0 or reinvestment_pct > 100:
                return {
                    "error": "Invalid reinvestment percentage",
                    "message": "Percentage must be between 0 and 100"
                }
            
            # Update bot configuration
            result = await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "reinvestment_pct": reinvestment_pct,
                        "reinvestment_updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                return {
                    "bot_id": bot_id,
                    "reinvestment_pct": reinvestment_pct,
                    "status": "updated",
                    "message": f"Reinvestment set to {reinvestment_pct}%"
                }
            else:
                return {
                    "error": "Bot not found or no change made"
                }
            
        except Exception as e:
            logger.error(f"Set reinvestment percentage error: {e}")
            return {"error": str(e)}
    
    async def calculate_reinvestment_amount(
        self,
        bot_id: str,
        realized_profit: float
    ) -> Dict:
        """Calculate how much profit should be reinvested
        
        Args:
            bot_id: Bot ID
            realized_profit: Realized profit amount
            
        Returns:
            Dict with reinvestment breakdown
        """
        try:
            # Get bot configuration
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            # Get reinvestment percentage (default 50%)
            reinvestment_pct = bot.get('reinvestment_pct', DEFAULT_REINVESTMENT_PCT)
            
            # Check minimum profit threshold
            if realized_profit < MIN_PROFIT_FOR_REINVESTMENT:
                return {
                    "bot_id": bot_id,
                    "realized_profit": round(realized_profit, 2),
                    "reinvestment_amount": 0,
                    "withdrawal_amount": round(realized_profit, 2),
                    "reinvestment_pct": reinvestment_pct,
                    "reason": f"Below minimum threshold (R{MIN_PROFIT_FOR_REINVESTMENT})"
                }
            
            # Calculate reinvestment amount
            reinvestment_amount = realized_profit * (reinvestment_pct / 100)
            withdrawal_amount = realized_profit - reinvestment_amount
            
            return {
                "bot_id": bot_id,
                "realized_profit": round(realized_profit, 2),
                "reinvestment_amount": round(reinvestment_amount, 2),
                "withdrawal_amount": round(withdrawal_amount, 2),
                "reinvestment_pct": reinvestment_pct
            }
            
        except Exception as e:
            logger.error(f"Calculate reinvestment error: {e}")
            return {"error": str(e)}
    
    async def apply_reinvestment(
        self,
        bot_id: str,
        realized_profit: float
    ) -> Dict:
        """Apply profit reinvestment to bot capital
        
        Args:
            bot_id: Bot ID
            realized_profit: Realized profit to process
            
        Returns:
            Dict with reinvestment result
        """
        try:
            # Calculate reinvestment breakdown
            breakdown = await self.calculate_reinvestment_amount(bot_id, realized_profit)
            
            if "error" in breakdown:
                return breakdown
            
            reinvestment_amount = breakdown.get('reinvestment_amount', 0)
            withdrawal_amount = breakdown.get('withdrawal_amount', 0)
            
            if reinvestment_amount <= 0:
                return {
                    "bot_id": bot_id,
                    "status": "no_reinvestment",
                    "message": "No reinvestment applied",
                    "breakdown": breakdown
                }
            
            # Update bot capital
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            current_capital = bot.get('current_capital', 0)
            new_capital = current_capital + reinvestment_amount
            
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "last_reinvestment_at": datetime.now(timezone.utc).isoformat(),
                        "last_reinvestment_amount": reinvestment_amount
                    },
                    "$inc": {
                        "total_reinvested": reinvestment_amount,
                        "total_withdrawn": withdrawal_amount
                    }
                }
            )
            
            # Log reinvestment event
            await db.reinvestment_log_collection.insert_one({
                "bot_id": bot_id,
                "user_id": bot.get('user_id'),
                "realized_profit": realized_profit,
                "reinvestment_amount": reinvestment_amount,
                "withdrawal_amount": withdrawal_amount,
                "reinvestment_pct": breakdown.get('reinvestment_pct'),
                "capital_before": current_capital,
                "capital_after": new_capital,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "bot_id": bot_id,
                "status": "success",
                "realized_profit": round(realized_profit, 2),
                "reinvestment_amount": round(reinvestment_amount, 2),
                "withdrawal_amount": round(withdrawal_amount, 2),
                "capital_before": round(current_capital, 2),
                "capital_after": round(new_capital, 2),
                "message": f"Reinvested R{reinvestment_amount:.2f} ({breakdown.get('reinvestment_pct')}%)"
            }
            
        except Exception as e:
            logger.error(f"Apply reinvestment error: {e}")
            return {"error": str(e)}
    
    async def adjust_position_size_after_outcome(
        self,
        bot_id: str,
        last_trade_profit: float,
        base_position_size: float
    ) -> Dict:
        """Adjust position size based on recent trading outcome
        
        Increase position size after wins, decrease after losses
        
        Args:
            bot_id: Bot ID
            last_trade_profit: Profit/loss from last trade
            base_position_size: Base position size before adjustment
            
        Returns:
            Dict with adjusted position size
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            reinvestment_pct = bot.get('reinvestment_pct', DEFAULT_REINVESTMENT_PCT)
            
            # Calculate adjustment factor based on outcome
            if last_trade_profit > 0:
                # Win: increase position size based on reinvestment percentage
                # Higher reinvestment = more aggressive position increase
                # Multiplier 0.2 = max 20% increase at 100% reinvestment
                adjustment_factor = 1.0 + (reinvestment_pct / 100) * 0.2
            else:
                # Loss: decrease position size
                # Lower reinvestment = more conservative position decrease
                # Multiplier 0.15 = max 15% decrease at 0% reinvestment
                adjustment_factor = 1.0 - (1 - reinvestment_pct / 100) * 0.15
            
            # Clamp adjustment to reasonable bounds
            adjustment_factor = max(0.75, min(1.25, adjustment_factor))
            
            adjusted_position_size = base_position_size * adjustment_factor
            
            return {
                "bot_id": bot_id,
                "last_trade_profit": round(last_trade_profit, 2),
                "base_position_size": round(base_position_size, 2),
                "adjusted_position_size": round(adjusted_position_size, 2),
                "adjustment_factor": round(adjustment_factor, 3),
                "reinvestment_pct": reinvestment_pct,
                "adjustment_reason": "win" if last_trade_profit > 0 else "loss"
            }
            
        except Exception as e:
            logger.error(f"Position size adjustment error: {e}")
            return {"error": str(e)}
    
    async def get_reinvestment_history(
        self,
        bot_id: str,
        limit: int = 10
    ) -> Dict:
        """Get reinvestment history for a bot
        
        Args:
            bot_id: Bot ID
            limit: Maximum number of records to return
            
        Returns:
            Dict with reinvestment history
        """
        try:
            history = await db.reinvestment_log_collection.find(
                {"bot_id": bot_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit).to_list(limit)
            
            # Calculate totals
            total_reinvested = sum(h.get('reinvestment_amount', 0) for h in history)
            total_withdrawn = sum(h.get('withdrawal_amount', 0) for h in history)
            
            return {
                "bot_id": bot_id,
                "history": history,
                "total_reinvested": round(total_reinvested, 2),
                "total_withdrawn": round(total_withdrawn, 2),
                "count": len(history)
            }
            
        except Exception as e:
            logger.error(f"Get reinvestment history error: {e}")
            return {"error": str(e)}


# Global singleton instance
profit_reinvestment = ProfitReinvestment()
