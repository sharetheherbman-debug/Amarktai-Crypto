"""
Fetch.ai Integration
- Fetch market signals and predictions from Fetch.ai network
- Provide AI-powered trading insights
"""

import asyncio
import aiohttp
from datetime import datetime, timezone
from logger_config import logger
import database as db


class FetchAIIntegration:
    def __init__(self):
        self.api_key = None
        self.api_url = "https://api.fetch.ai/v1"
        self.cache = {}
    
    def set_credentials(self, api_key: str):
        """Set Fetch.ai API credentials"""
        self.api_key = api_key
        logger.info("Fetch.ai credentials configured")
    
    async def test_connection(self, api_key: str) -> bool:
        """Test Fetch.ai API connection"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                async with session.get(
                    f"{self.api_url}/health",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Fetch.ai connection test failed: {e}")
            return False
    
    async def fetch_market_signals(self, pair: str = "BTC/USD") -> dict:
        """Fetch AI-powered market signals from Fetch.ai"""
        if not self.api_key:
            logger.warning("Fetch.ai API key not configured — returning unavailable signal")
            return self._unavailable_signal(pair)
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                async with session.get(
                    f"{self.api_url}/signals/market",
                    params={"pair": pair},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.cache[pair] = data
                        return data
                    else:
                        logger.error(f"Fetch.ai API error: {response.status}")
                        return self._unavailable_signal(pair)
        
        except Exception as e:
            logger.error(f"Fetch.ai fetch failed: {e}")
            return self._unavailable_signal(pair)
    
    def _unavailable_signal(self, pair: str) -> dict:
        """Return a neutral, clearly-marked unavailable signal.

        NEVER returns random values — callers must check ``is_simulated=True``
        and zero-weight this signal in live trading decisions.
        """
        return {
            "pair": pair,
            "signal": "HOLD",
            "strength": "UNAVAILABLE",
            "confidence": 0.0,
            "is_simulated": True,
            "source": "unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    async def get_trading_recommendation(self, pair: str, risk_level: str = "moderate") -> dict:
        """Get AI-powered trading recommendation"""
        signals = await self.fetch_market_signals(pair)
        
        # When signals are unavailable, all price levels are None — callers must
        # check is_simulated before using entry_price / stop_loss / take_profit.
        is_unavailable = signals.get("is_simulated", False)
        recommendation = {
            "pair": pair,
            "action": signals.get("signal", "HOLD"),
            "confidence": signals.get("confidence", 0),
            "entry_price": signals.get("price_target") if not is_unavailable else None,
            "stop_loss": signals.get("stop_loss") if not is_unavailable else None,
            "take_profit": signals.get("price_target") if not is_unavailable else None,
            "risk_reward_ratio": None,
            "is_simulated": is_unavailable,
            "timeframe": signals.get("timeframe", "4h"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return recommendation


# Global instance
fetchai = FetchAIIntegration()
