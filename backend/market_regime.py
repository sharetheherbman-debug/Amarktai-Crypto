"""
Market Regime Detection
- Detects trending up/down, sideways, high/low volatility
- Adjusts bot parameters based on market conditions
"""

import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from logger_config import logger
import math


class MarketRegimeDetector:
    def __init__(self):
        self.price_history = {}  # Store recent prices
        self.current_regime = {}
    
    async def detect_regime(self, pair: str, exchange: str = 'luno') -> dict:
        """Detect current market regime for a trading pair"""
        try:
            from paper_trading_engine import paper_engine
            
            # Get current price
            current_price = await paper_engine.get_real_price(pair, exchange)
            
            # Store in history
            if pair not in self.price_history:
                self.price_history[pair] = []
            
            self.price_history[pair].append({
                'price': current_price,
                'timestamp': datetime.now(timezone.utc)
            })
            
            # Keep only last 24 hours
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            self.price_history[pair] = [
                p for p in self.price_history[pair]
                if p['timestamp'] > cutoff_time
            ]
            
            # Need at least 10 data points — fall back to "range" so the system
            # never blocks trades with regime="unknown" during the warm-up period.
            if len(self.price_history[pair]) < 10:
                return {
                    "regime": "range",
                    "trend": "neutral",
                    "volatility": "normal",
                    "confidence": 0.25,
                    "is_fallback": True,
                }
            
            prices = [p['price'] for p in self.price_history[pair]]
            
            # Calculate trend
            first_price = prices[0]
            last_price = prices[-1]
            trend_pct = ((last_price - first_price) / first_price) * 100
            
            # Determine trend
            if trend_pct > 2:
                trend = "bullish"
            elif trend_pct < -2:
                trend = "bearish"
            else:
                trend = "sideways"
            
            # Calculate volatility (standard deviation)
            mean_price = sum(prices) / len(prices)
            variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
            std_dev = math.sqrt(variance)
            volatility_pct = (std_dev / mean_price) * 100
            
            if volatility_pct > 5:
                volatility = "high"
            elif volatility_pct > 2:
                volatility = "moderate"
            else:
                volatility = "low"
            
            # Determine overall regime
            if trend == "bullish" and volatility == "low":
                regime = "stable_uptrend"
            elif trend == "bullish" and volatility == "high":
                regime = "volatile_uptrend"
            elif trend == "bearish" and volatility == "low":
                regime = "stable_downtrend"
            elif trend == "bearish" and volatility == "high":
                regime = "volatile_downtrend"
            elif trend == "sideways" and volatility == "low":
                regime = "consolidation"
            else:
                regime = "choppy"
            
            result = {
                "regime": regime,
                "trend": trend,
                "volatility": volatility,
                "trend_pct": round(trend_pct, 2),
                "volatility_pct": round(volatility_pct, 2),
                "confidence": min(len(prices) / 50, 1.0),  # More data = higher confidence
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self.current_regime[pair] = result
            logger.info(f"{pair} regime: {regime} (trend: {trend}, vol: {volatility})")
            
            return result
            
        except Exception as e:
            logger.error(f"Regime detection failed for {pair}: {e}")
            # Never return "unknown" or "error" — use "range" fallback so regime
            # detection never blocks trades during error conditions.
            return {
                "regime": "range",
                "trend": "neutral",
                "volatility": "normal",
                "confidence": 0.20,
                "is_fallback": True,
            }
    
    async def adjust_bot_for_regime(self, bot: dict, regime: dict):
        """Adjust bot parameters based on market regime"""
        try:
            # Get recommended risk mode based on regime
            regime_type = regime.get('regime')
            
            adjustments = {}
            
            if regime_type == "stable_uptrend":
                # Increase position sizes in stable uptrends
                adjustments['suggested_risk'] = "risky"
                adjustments['rationale'] = "Stable uptrend - favorable for aggressive trading"
                
            elif regime_type == "volatile_uptrend":
                # Moderate risk in volatile markets
                adjustments['suggested_risk'] = "safe"
                adjustments['rationale'] = "Volatile uptrend - use caution"
                
            elif regime_type == "stable_downtrend":
                # Reduce exposure in downtrends
                adjustments['suggested_risk'] = "safe"
                adjustments['rationale'] = "Downtrend - preserve capital"
                
            elif regime_type == "volatile_downtrend":
                # Minimal trading in volatile downtrends
                adjustments['suggested_risk'] = "safe"
                adjustments['rationale'] = "Volatile downtrend - high risk"
                
            elif regime_type == "consolidation":
                # Range trading in consolidation
                adjustments['suggested_risk'] = "safe"
                adjustments['rationale'] = "Consolidation - scalping opportunities"
                
            else:  # choppy
                # Minimal trading in choppy markets
                adjustments['suggested_risk'] = "safe"
                adjustments['rationale'] = "Choppy market - wait for clarity"
            
            # Store regime insights in bot metadata
            await db.bots_collection.update_one(
                {"id": bot['id']},
                {
                    "$set": {
                        "current_regime": regime,
                        "regime_adjustments": adjustments,
                        "regime_updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            return adjustments
            
        except Exception as e:
            logger.error(f"Bot regime adjustment failed: {e}")
            return {}


# Global instance
market_regime_detector = MarketRegimeDetector()
