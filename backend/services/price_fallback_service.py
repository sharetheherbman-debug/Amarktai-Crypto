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
    Fallback price service for all 5 exchanges
    
    Supports:
    - Luno (ZAR pairs)
    - Binance (USDT pairs)
    - KuCoin (USDT pairs)
    - Bybit (USDT pairs)
    - Bitget (USDT pairs)
    """
    
    def __init__(self):
        self.price_cache = {}
        self.cache_ttl = 60  # Cache for 60 seconds
        # Negative cache TTL: after a failed fetch, skip retries for 30 s.
        # This prevents hammering slow/unavailable exchanges on every request.
        self.negative_cache_ttl = 30
        self.exchanges = {}
        self.initialized = False
    
    async def init_exchanges(self):
        """Initialize public exchange connections"""
        if self.initialized:
            return
        
        # Tight timeout (5 s) keeps exchange calls well under nginx's
        # proxy_read_timeout so a slow exchange never cascades into 502s.
        _TIMEOUT_MS = 5000
        
        try:
            # Luno public
            self.exchanges['luno'] = ccxt.luno({
                'enableRateLimit': True,
                'timeout': _TIMEOUT_MS
            })
            logger.info("✅ Luno public fallback initialized")
        except Exception as e:
            logger.warning(f"Luno fallback init failed: {e}")
        
        try:
            # Binance public
            self.exchanges['binance'] = ccxt.binance({
                'enableRateLimit': True,
                'timeout': _TIMEOUT_MS,
                'options': {'defaultType': 'spot'}
            })
            logger.info("✅ Binance public fallback initialized")
        except Exception as e:
            logger.warning(f"Binance fallback init failed: {e}")
        
        try:
            # KuCoin public
            self.exchanges['kucoin'] = ccxt.kucoin({
                'enableRateLimit': True,
                'timeout': _TIMEOUT_MS
            })
            logger.info("✅ KuCoin public fallback initialized")
        except Exception as e:
            logger.warning(f"KuCoin fallback init failed: {e}")
        
        try:
            # Bybit public
            self.exchanges['bybit'] = ccxt.bybit({
                'enableRateLimit': True,
                'timeout': _TIMEOUT_MS
            })
            logger.info("✅ Bybit public fallback initialized")
        except Exception as e:
            logger.warning(f"Bybit fallback init failed: {e}")
        
        try:
            # Bitget public
            self.exchanges['bitget'] = ccxt.bitget({
                'enableRateLimit': True,
                'timeout': _TIMEOUT_MS
            })
            logger.info("✅ Bitget public fallback initialized")
        except Exception as e:
            logger.warning(f"Bitget fallback init failed: {e}")
        
        self.initialized = True
    
    def _get_cache_key(self, exchange: str, symbol: str) -> str:
        """Generate cache key"""
        return f"{exchange}:{symbol}"
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid (handles both positive and negative entries)."""
        if not cache_entry:
            return False
        
        cached_at = cache_entry.get('timestamp')
        if not cached_at:
            return False
        
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        # Negative cache entries have price=None and use negative_cache_ttl.
        if cache_entry.get('price') is None:
            return age < self.negative_cache_ttl
        return age < self.cache_ttl
    
    async def get_price(self, exchange: str, symbol: str) -> Optional[float]:
        """
        Get price for symbol on exchange with fallback
        
        Args:
            exchange: Exchange name (luno, binance, kucoin, bybit, bitget)
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
                # Cache the positive result
                self.price_cache[cache_key] = {
                    'price': float(price),
                    'timestamp': datetime.now(timezone.utc)
                }
                
                logger.debug(f"Fetched price for {cache_key}: {price}")
                return float(price)
            else:
                logger.warning(f"Invalid price for {cache_key}: {price}")
                # Store negative cache so we don't retry immediately
                self.price_cache[cache_key] = {
                    'price': None,
                    'timestamp': datetime.now(timezone.utc)
                }
                return None
        
        except Exception as e:
            logger.debug(f"Error fetching price for {cache_key}: {e}")
            # Store negative cache entry to prevent repeated slow retries
            self.price_cache[cache_key] = {
                'price': None,
                'timestamp': datetime.now(timezone.utc)
            }
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
