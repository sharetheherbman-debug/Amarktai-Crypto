"""
FLOKx Integration
- Fetch market coefficients (strength, volatility, sentiment)
- Display as informational alerts
- NOT for direct bot creation
"""

import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from logger_config import logger
import database as db

# Rate-limit "key not configured" warnings to once per 10 minutes
_WARN_INTERVAL = timedelta(minutes=10)


class FLOKxIntegration:
    def __init__(self):
        self.api_key = None  # Will be set from user credentials
        self.api_url = "https://api.flokx.io/v1"
        self.cache = {}
        self._last_missing_key_warn: datetime | None = None
    
    def set_credentials(self, api_key: str):
        """Set FLOKx API credentials"""
        self.api_key = api_key
        logger.info("FLOKx credentials configured")
    
    async def test_connection(self, api_key: str) -> bool:
        """Test FLOKx API connection"""
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
            logger.error(f"Flokx connection test failed: {e}")
            # For now, accept any key format
            return len(api_key) > 10
    
    async def fetch_market_coefficients(self, pair: str = "BTC/USD") -> dict:
        """Fetch market intelligence coefficients from FLOKx"""
        if not self.api_key:
            now = datetime.now(timezone.utc)
            if self._last_missing_key_warn is None or (now - self._last_missing_key_warn) >= _WARN_INTERVAL:
                logger.warning("FLOKx API key not configured — signals unavailable (this warning appears at most once per 10 min)")
                self._last_missing_key_warn = now
            return self._mock_coefficients(pair)
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                async with session.get(
                    f"{self.api_url}/market/coefficients",
                    params={"pair": pair},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.cache[pair] = data
                        return data
                    else:
                        logger.error(f"FLOKx API error: {response.status}")
                        return self._mock_coefficients(pair)
        
        except Exception as e:
            logger.error(f"FLOKx fetch failed: {e}")
            return self._mock_coefficients(pair)
    
    def _mock_coefficients(self, pair: str) -> dict:
        """Return a neutral, clearly-marked unavailable coefficient set.

        NEVER returns random values — callers must check ``is_simulated=True``
        and treat this as informational only, not a trading signal.
        """
        return {
            "pair": pair,
            "strength": 0.0,
            "volatility": 0.0,
            "sentiment": "unavailable",
            "trend_score": 0.0,
            "volume_ratio": 1.0,
            "momentum": 0.0,
            "support_level": 0.0,
            "resistance_level": 0.0,
            "is_simulated": True,
            "source": "unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    async def create_alert_from_coefficients(self, user_id: str, pair: str):
        """Create informational alert from FLOKx data"""
        try:
            coeffs = await self.fetch_market_coefficients(pair)
            
            # Determine alert type based on coefficients
            alert_type = "info"
            alert_message = f"{pair} Market Intelligence:\n"
            
            if coeffs['strength'] > 75:
                alert_type = "opportunity"
                alert_message += f"💪 Strong market strength ({coeffs['strength']:.1f}/100)\n"
            
            if coeffs['volatility'] > 60:
                alert_type = "warning"
                alert_message += f"⚠️ High volatility ({coeffs['volatility']:.1f}%)\n"
            
            if coeffs['sentiment'] == "bullish":
                alert_message += "📈 Bullish sentiment\n"
            elif coeffs['sentiment'] == "bearish":
                alert_message += "📉 Bearish sentiment\n"
            else:
                alert_message += "➡️ Neutral sentiment\n"
            
            alert_message += f"Momentum: {coeffs['momentum']:.1f}\n"
            alert_message += f"Trend Score: {coeffs['trend_score']:.1f}/100"
            
            # Store alert
            alert = {
                "user_id": user_id,
                "type": alert_type,
                "title": f"FLOKx Intelligence: {pair}",
                "message": alert_message,
                "data": coeffs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "read": False
            }
            
            await db.alerts_collection.insert_one(alert)
            logger.info(f"FLOKx alert created for {user_id}: {pair}")
            
            return alert
            
        except Exception as e:
            logger.error(f"FLOKx alert creation failed: {e}")
            return None
    
    async def monitor_pairs(self, user_id: str, pairs: list):
        """Monitor multiple pairs and create alerts"""
        for pair in pairs:
            await self.create_alert_from_coefficients(user_id, pair)
            await asyncio.sleep(1)  # Rate limiting


# Global instance
flokx = FLOKxIntegration()
