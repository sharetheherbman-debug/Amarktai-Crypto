"""
Public Price Fallback Service

Provides price feeds for all 5 exchanges even without user API keys.
Uses public endpoints with caching and rate limiting.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import ccxt.async_support as ccxt
import asyncio

logger = logging.getLogger(__name__)


class PriceFallbackService:
    """
    Fallback price service for all 7 exchanges
    
    Supports:
    - Luno (ZAR pairs)
    - Binance (USDT pairs)
    - KuCoin (USDT pairs)
    - Bybit (USDT pairs)
    - Kraken (USDT pairs)
    - Bitget (USDT pairs)
    - Gate.io (USDT pairs)
    """
    
    def __init__(self):
        self.price_cache = {}
        self.cache_ttl = 60  # Cache for 60 seconds
        self.exchanges = {}
        self.initialized = False
    
    async def init_exchanges(self):
        """Initialize public exchange connections"""
        if self.initialized:
            return
        
        try:
            # Luno public
            self.exchanges['luno'] = ccxt.luno({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ Luno public fallback initialized")
        except Exception as e:
            logger.warning(f"Luno fallback init failed: {e}")
        
        try:
            # Binance public
            self.exchanges['binance'] = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            logger.info("✅ Binance public fallback initialized")
        except Exception as e:
            logger.warning(f"Binance fallback init failed: {e}")
        
        try:
            # KuCoin public
            self.exchanges['kucoin'] = ccxt.kucoin({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ KuCoin public fallback initialized")
        except Exception as e:
            logger.warning(f"KuCoin fallback init failed: {e}")
        
        try:
            # Bybit public
            self.exchanges['bybit'] = ccxt.bybit({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ Bybit public fallback initialized")
        except Exception as e:
            logger.warning(f"Bybit fallback init failed: {e}")
        
        try:
            # Kraken public
            self.exchanges['kraken'] = ccxt.kraken({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ Kraken public fallback initialized")
        except Exception as e:
            logger.warning(f"Kraken fallback init failed: {e}")
        
        try:
            # Bitget public
            self.exchanges['bitget'] = ccxt.bitget({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ Bitget public fallback initialized")
        except Exception as e:
            logger.warning(f"Bitget fallback init failed: {e}")
        
        try:
            # Gate.io public
            self.exchanges['gate'] = ccxt.gateio({
                'enableRateLimit': True,
                'timeout': 30000
            })
            logger.info("✅ Gate.io public fallback initialized")
        except Exception as e:
            logger.warning(f"Gate.io fallback init failed: {e}")
        
        self.initialized = True
    
    def _get_cache_key(self, exchange: str, symbol: str) -> str:
        """Generate cache key"""
        return f"{exchange}:{symbol}"
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid"""
        if not cache_entry:
            return False
        
        cached_at = cache_entry.get('timestamp')
        if not cached_at:
            return False
        
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        return age < self.cache_ttl
    
    async def get_price(self, exchange: str, symbol: str) -> Optional[float]:
        """
        Get price for symbol on exchange with fallback
        
        Args:
            exchange: Exchange name (luno, binance, kucoin, bybit, kraken, bitget, gate)
            symbol: Trading pair (e.g., 'BTC/ZAR', 'BTC/USDT')
        
        Returns:
            Price as float, or None if unavailable
        """
        await self.init_exchanges()
        
        # Check cache first
        cache_key = self._get_cache_key(exchange, symbol)
        cache_entry = self.price_cache.get(cache_key)
        
        if self._is_cache_valid(cache_entry):
            logger.debug(f"Cache hit for {cache_key}")
            return cache_entry['price']
        
        # Get exchange object
        exchange_obj = self.exchanges.get(exchange)
        if not exchange_obj:
            logger.warning(f"Exchange {exchange} not available in fallback service")
            return None
        
        try:
            # Fetch ticker
            ticker = await exchange_obj.fetch_ticker(symbol)
            price = ticker.get('last') or ticker.get('close') or ticker.get('bid')
            
            if price and price > 0:
                # Cache the result
                self.price_cache[cache_key] = {
                    'price': float(price),
                    'timestamp': datetime.now(timezone.utc)
                }
                
                logger.debug(f"Fetched price for {cache_key}: {price}")
                return float(price)
            else:
                logger.warning(f"Invalid price for {cache_key}: {price}")
                return None
        
        except Exception as e:
            logger.debug(f"Error fetching price for {cache_key}: {e}")
            return None
    
    async def get_multiple_prices(self, requests: list) -> Dict[str, Optional[float]]:
        """
        Get multiple prices concurrently
        
        Args:
            requests: List of (exchange, symbol) tuples
        
        Returns:
            Dict mapping "exchange:symbol" to price
        """
        tasks = []
        keys = []
        
        for exchange, symbol in requests:
            task = self.get_price(exchange, symbol)
            tasks.append(task)
            keys.append(self._get_cache_key(exchange, symbol))
        
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for key, price in zip(keys, prices):
            if isinstance(price, Exception):
                logger.debug(f"Error in batch fetch for {key}: {price}")
                result[key] = None
            else:
                result[key] = price
        
        return result
    
    async def close(self):
        """Close all exchange connections"""
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Closed {name} fallback exchange")
            except Exception as e:
                logger.warning(f"Error closing {name} fallback: {e}")
        
        self.exchanges = {}
        self.initialized = False


# Global instance
price_fallback_service = PriceFallbackService()
