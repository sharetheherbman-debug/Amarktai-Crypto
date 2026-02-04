"""
Advanced Position Sizing - Kelly Criterion and Volatility-Based
Implements sophisticated position sizing strategies for optimal capital allocation
"""
import logging
from typing import Dict, Optional
import numpy as np
from datetime import datetime, timezone, timedelta
import database as db

logger = logging.getLogger(__name__)

# Kelly Criterion configuration
KELLY_FRACTION = 0.25  # Use 25% of full Kelly for stability
MIN_KELLY_POSITION_SIZE = 0.01  # Minimum 1% of capital
MAX_KELLY_POSITION_SIZE = 0.25  # Maximum 25% of capital

# Volatility-based configuration
VOLATILITY_LOOKBACK_PERIODS = 20  # Number of periods for volatility calculation
MIN_VOLATILITY_ADJUSTMENT = 0.5  # Minimum 50% of base size
MAX_VOLATILITY_ADJUSTMENT = 2.0  # Maximum 200% of base size


class PositionSizer:
    """Advanced position sizing using Kelly Criterion and volatility adjustment"""
    
    async def calculate_kelly_position_size(
        self, 
        bot_id: str, 
        win_probability: Optional[float] = None,
        avg_win_ratio: Optional[float] = None
    ) -> Dict:
        """Calculate position size using Kelly Criterion
        
        Kelly Formula: f* = (p * b - q) / b
        Where:
        - f* = fraction of capital to bet
        - p = probability of win
        - q = probability of loss (1-p)
        - b = win/loss ratio (avg_win / avg_loss)
        
        Args:
            bot_id: Bot ID
            win_probability: Win probability (if None, calculate from history)
            avg_win_ratio: Average win/loss ratio (if None, calculate from history)
            
        Returns:
            Dict with position size recommendation
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            # Get bot's trade history
            if win_probability is None or avg_win_ratio is None:
                win_prob, win_ratio = await self._calculate_win_stats(bot_id)
            else:
                win_prob = win_probability
                win_ratio = avg_win_ratio
            
            # Validate inputs
            if win_prob <= 0 or win_prob >= 1:
                logger.warning(f"Invalid win probability {win_prob} for bot {bot_id}, using conservative default 0.5")
                win_prob = 0.5
            
            if win_ratio <= 0:
                logger.warning(f"Invalid win ratio {win_ratio} for bot {bot_id}, using conservative default 1.5")
                win_ratio = 1.5
                
                # Note: These defaults may indicate insufficient trading history
                # Recommendation: Wait for more trades before using Kelly sizing
            
            # Calculate Kelly percentage
            loss_prob = 1 - win_prob
            kelly_pct = (win_prob * win_ratio - loss_prob) / win_ratio
            
            # Apply Kelly fraction for safety (25% of full Kelly)
            fractional_kelly = kelly_pct * KELLY_FRACTION
            
            # Clamp to min/max bounds
            fractional_kelly = max(MIN_KELLY_POSITION_SIZE, min(MAX_KELLY_POSITION_SIZE, fractional_kelly))
            
            # Calculate position size in capital
            current_capital = bot.get('current_capital', 1000)
            position_size = current_capital * fractional_kelly
            
            return {
                "bot_id": bot_id,
                "method": "kelly_criterion",
                "win_probability": round(win_prob, 3),
                "avg_win_ratio": round(win_ratio, 2),
                "kelly_percentage": round(kelly_pct * 100, 2),
                "fractional_kelly_percentage": round(fractional_kelly * 100, 2),
                "recommended_position_size": round(position_size, 2),
                "current_capital": round(current_capital, 2),
                "kelly_fraction_used": KELLY_FRACTION
            }
            
        except Exception as e:
            logger.error(f"Kelly position sizing error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def calculate_volatility_adjusted_position_size(
        self, 
        bot_id: str,
        base_position_size: float,
        pair: str
    ) -> Dict:
        """Adjust position size based on recent volatility
        
        Args:
            bot_id: Bot ID
            base_position_size: Base position size before adjustment
            pair: Trading pair (e.g., "BTC/ZAR")
            
        Returns:
            Dict with volatility-adjusted position size
        """
        try:
            # Get recent trades for volatility calculation
            recent_trades = await db.trades_collection.find(
                {
                    "bot_id": bot_id,
                    "pair": pair,
                    "status": "closed"
                },
                {"_id": 0, "profit_loss": 1}
            ).sort("timestamp", -1).limit(VOLATILITY_LOOKBACK_PERIODS).to_list(VOLATILITY_LOOKBACK_PERIODS)
            
            if len(recent_trades) < 5:
                # Not enough data, return base size
                return {
                    "bot_id": bot_id,
                    "method": "volatility_adjusted",
                    "base_position_size": round(base_position_size, 2),
                    "adjusted_position_size": round(base_position_size, 2),
                    "volatility_factor": 1.0,
                    "note": "Insufficient data for volatility adjustment"
                }
            
            # Calculate returns volatility (standard deviation of returns)
            returns = [t.get('profit_loss', 0) for t in recent_trades]
            volatility = np.std(returns)
            mean_return = np.mean(returns)
            
            # Calculate volatility adjustment factor
            # Lower volatility = larger position, higher volatility = smaller position
            if volatility > 0 and len(returns) > 1:
                # Use baseline volatility (average) for comparison
                avg_volatility = np.mean([np.std(returns[i:i+5]) for i in range(0, len(returns)-4, 5)]) if len(returns) >= 10 else volatility
                volatility_factor = avg_volatility / volatility if volatility > 0 else 1.0
                
                # Clamp to reasonable bounds
                volatility_factor = max(MIN_VOLATILITY_ADJUSTMENT, min(MAX_VOLATILITY_ADJUSTMENT, volatility_factor))
            else:
                volatility_factor = 1.0
            
            # Apply volatility adjustment
            adjusted_position_size = base_position_size * volatility_factor
            
            return {
                "bot_id": bot_id,
                "method": "volatility_adjusted",
                "pair": pair,
                "base_position_size": round(base_position_size, 2),
                "adjusted_position_size": round(adjusted_position_size, 2),
                "volatility_factor": round(volatility_factor, 3),
                "returns_volatility": round(volatility, 2),
                "mean_return": round(mean_return, 2),
                "trades_analyzed": len(recent_trades)
            }
            
        except Exception as e:
            logger.error(f"Volatility adjustment error: {e}", exc_info=True)
            return {
                "bot_id": bot_id,
                "base_position_size": round(base_position_size, 2),
                "adjusted_position_size": round(base_position_size, 2),
                "volatility_factor": 1.0,
                "error": str(e)
            }
    
    async def get_recommended_position_size(
        self,
        bot_id: str,
        pair: str,
        use_kelly: bool = True,
        use_volatility: bool = True
    ) -> Dict:
        """Get recommended position size using both Kelly and volatility
        
        Args:
            bot_id: Bot ID
            pair: Trading pair
            use_kelly: Whether to use Kelly criterion
            use_volatility: Whether to use volatility adjustment
            
        Returns:
            Dict with final position size recommendation
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            current_capital = bot.get('current_capital', 1000)
            risk_mode = bot.get('risk_mode', 'balanced')
            
            # Default base position size by risk mode
            base_pct = {
                'safe': 0.10,       # 10%
                'balanced': 0.15,   # 15%
                'risky': 0.20,      # 20%
                'aggressive': 0.25  # 25%
            }
            base_size = current_capital * base_pct.get(risk_mode, 0.15)
            
            # Apply Kelly criterion if enabled
            if use_kelly:
                kelly_result = await self.calculate_kelly_position_size(bot_id)
                if "error" not in kelly_result:
                    base_size = kelly_result.get('recommended_position_size', base_size)
            
            # Apply volatility adjustment if enabled
            if use_volatility:
                vol_result = await self.calculate_volatility_adjusted_position_size(
                    bot_id, base_size, pair
                )
                if "error" not in vol_result:
                    final_size = vol_result.get('adjusted_position_size', base_size)
                else:
                    final_size = base_size
            else:
                final_size = base_size
            
            return {
                "bot_id": bot_id,
                "pair": pair,
                "current_capital": round(current_capital, 2),
                "risk_mode": risk_mode,
                "recommended_position_size": round(final_size, 2),
                "position_percentage": round((final_size / current_capital) * 100, 2),
                "kelly_enabled": use_kelly,
                "volatility_enabled": use_volatility
            }
            
        except Exception as e:
            logger.error(f"Position size recommendation error: {e}")
            return {"error": str(e)}
    
    async def _calculate_win_stats(self, bot_id: str) -> tuple[float, float]:
        """Calculate win probability and win/loss ratio from trade history
        
        Args:
            bot_id: Bot ID
            
        Returns:
            Tuple of (win_probability, avg_win_ratio)
        """
        try:
            # Get closed trades
            trades = await db.trades_collection.find(
                {
                    "bot_id": bot_id,
                    "status": "closed"
                },
                {"_id": 0, "profit_loss": 1, "net_pnl": 1}
            ).to_list(1000)
            
            if len(trades) < 10:
                # Not enough data, return conservative defaults
                return 0.5, 1.5
            
            # Calculate wins and losses
            wins = []
            losses = []
            
            for trade in trades:
                pnl = trade.get('net_pnl', trade.get('profit_loss', 0))
                if pnl > 0:
                    wins.append(pnl)
                elif pnl < 0:
                    losses.append(abs(pnl))
            
            # Calculate win probability
            total_trades = len(trades)
            win_count = len(wins)
            win_prob = win_count / total_trades if total_trades > 0 else 0.5
            
            # Calculate average win/loss ratio
            avg_win = np.mean(wins) if wins else 1.0
            avg_loss = np.mean(losses) if losses else 1.0
            win_ratio = avg_win / avg_loss if avg_loss > 0 else 1.5
            
            return win_prob, win_ratio
            
        except Exception as e:
            logger.error(f"Win stats calculation error: {e}")
            return 0.5, 1.5


# Global singleton instance
position_sizer = PositionSizer()
