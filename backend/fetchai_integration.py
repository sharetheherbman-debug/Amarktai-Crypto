"""
Fetch.ai Integration
- Fetch market signals and predictions from Fetch.ai network
- Provide AI-powered trading insights
- When no API key is configured, returns a deterministic neutral/unavailable
  signal so that no random fabricated data flows into trading decisions.
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
        """Fetch AI-powered market signals from Fetch.ai.

        When no API key is configured or the API call fails, returns a
        deterministic UNAVAILABLE response with confidence=0 so that
        the trading brain can detect the absence of this signal source
        and adjust weights accordingly — no random fabricated signals.
        """
        if not self.api_key:
            logger.debug("Fetch.ai API key not configured — returning unavailable signal")
            return self._unavailable_signal(pair, reason="no_api_key")

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
                        return self._unavailable_signal(pair, reason=f"api_error_{response.status}")

        except Exception as e:
            logger.error(f"Fetch.ai fetch failed: {e}")
            return self._unavailable_signal(pair, reason="fetch_exception")

    @staticmethod
    def _unavailable_signal(pair: str, reason: str = "unavailable") -> dict:
        """Return a deterministic, zero-confidence unavailable signal.

        Replaces the former _mock_signals() which returned random data that
        could fabricate high-confidence BUY/SELL signals and override real
        trend analysis in the trading brain. A confidence of 0 tells the
        signal aggregator this source is absent so weights are redistributed
        to available sources.
        """
        return {
            "pair": pair,
            "signal": "HOLD",
            "strength": "NONE",
            "confidence": 0,
            "price_target": None,
            "stop_loss": None,
            "timeframe": None,
            "indicators": {},
            "ai_confidence": 0,
            "market_sentiment": "neutral",
            "available": False,
            "unavailable_reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "unavailable",
        }

    async def get_trading_recommendation(self, pair: str, risk_level: str = "moderate") -> dict:
        """Get AI-powered trading recommendation"""
        signals = await self.fetch_market_signals(pair)

        recommendation = {
            "pair": pair,
            "action": signals.get("signal", "HOLD"),
            "confidence": signals.get("confidence", 0),
            "entry_price": signals.get("price_target"),
            "stop_loss": signals.get("stop_loss"),
            "take_profit": signals.get("price_target"),
            "risk_reward_ratio": None,
            "timeframe": signals.get("timeframe"),
            "available": signals.get("available", True),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return recommendation


# Global instance
fetchai = FetchAIIntegration()
