import ccxt
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class CCXTService:
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.paper_balances: Dict[str, Dict[str, float]] = {}  # user_id -> {currency: balance}
    
    def init_exchange(self, exchange_name: str, api_key: str, api_secret: str, 
                     testnet: bool = False, passphrase: Optional[str] = None) -> ccxt.Exchange:
        """Initialize exchange connection"""
        try:
            exchange_class = getattr(ccxt, exchange_name.lower())
            config = {
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            }
            
            if passphrase:
                config['password'] = passphrase

            # Binance: always use Spot endpoints by default so we never
            # accidentally probe fapi.binance.com (futures) or
            # sapi/v1/margin/* (margin) for Spot-only API keys.
            if exchange_name.lower() == 'binance':
                config['options'] = {'defaultType': 'spot'}
                if testnet:
                    config['options']['testnet'] = True
            elif testnet:
                config.setdefault('options', {})['defaultType'] = 'spot'
            
            exchange = exchange_class(config)
            return exchange
        except Exception as e:
            logger.error(f"Failed to initialize {exchange_name}: {e}")
            raise
    
    async def test_connection(self, exchange_name: str, api_key: str, api_secret: str, 
                            passphrase: Optional[str] = None) -> bool:
        """Test exchange API connection by creating temporary instance"""
        try:
            exchange = self.init_exchange(exchange_name, api_key, api_secret, testnet=False, passphrase=passphrase)
            await asyncio.wait_for(asyncio.to_thread(exchange.fetch_balance), timeout=3.0)
            return True
        except asyncio.TimeoutError:
            logger.error(f"Connection test timed out for {exchange_name}")
            return False
        except Exception as e:
            logger.error(f"Connection test failed for {exchange_name}: {e}")
            return False
    
    async def get_balance(self, exchange: ccxt.Exchange, currency: str = 'USDT') -> float:
        """Get balance for specific currency"""
        try:
            balance = await asyncio.wait_for(asyncio.to_thread(exchange.fetch_balance), timeout=3.0)
            return balance.get(currency, {}).get('free', 0.0)
        except asyncio.TimeoutError:
            logger.error(f"fetch_balance timed out for {currency}")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0
    
    async def fetch_ticker(self, exchange: ccxt.Exchange, symbol: str) -> Dict:
        """Fetch ticker data"""
        try:
            ticker = await asyncio.wait_for(asyncio.to_thread(exchange.fetch_ticker, symbol), timeout=3.0)
            return ticker
        except asyncio.TimeoutError:
            logger.error(f"fetch_ticker timed out for {symbol}")
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return {}
    
    async def create_market_order(self, exchange: ccxt.Exchange, symbol: str, 
                                 side: str, amount: float, paper_trading: bool = True,
                                 _internal_only: bool = False) -> Dict:
        """
        Create market order (paper or live)
        
        WARNING: This method should ONLY be called internally by OrderPipeline.
        All external order requests must go through services/order_pipeline.py -> submit_order()
        
        Args:
            _internal_only: Must be True to execute. Prevents direct external calls.
        """
        if not _internal_only:
            raise RuntimeError(
                "Direct order placement is not allowed. "
                "All orders must go through OrderPipeline.submit_order() for safety gates. "
                "This prevents bypassing: idempotency, fee coverage, rate limits, and circuit breakers."
            )
        try:
            if paper_trading:
                # Simulate paper trading
                ticker = await self.fetch_ticker(exchange, symbol)
                price = ticker.get('last', 0)
                return {
                    'id': f'paper_{datetime.now(timezone.utc).timestamp()}',
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'cost': amount * price,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'status': 'closed',
                    'paper': True
                }
            else:
                # Real trading
                order = await asyncio.wait_for(
                    asyncio.to_thread(exchange.create_market_order, symbol, side, amount),
                    timeout=3.0,
                )
                return order
        except asyncio.TimeoutError:
            logger.error(f"create_market_order timed out for {symbol}")
            raise
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise
    
    def init_paper_balance(self, user_id: str, currency: str, amount: float):
        """Initialize paper trading balance"""
        if user_id not in self.paper_balances:
            self.paper_balances[user_id] = {}
        self.paper_balances[user_id][currency] = amount
    
    def get_paper_balance(self, user_id: str, currency: str) -> float:
        """Get paper trading balance"""
        return self.paper_balances.get(user_id, {}).get(currency, 0.0)
    
    def update_paper_balance(self, user_id: str, currency: str, amount: float):
        """Update paper trading balance"""
        if user_id not in self.paper_balances:
            self.paper_balances[user_id] = {}
        current = self.paper_balances[user_id].get(currency, 0.0)
        self.paper_balances[user_id][currency] = current + amount

    async def get_exchange_instance(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        testnet: bool = False,
    ) -> ccxt.Exchange:
        """Create and return an async-ready exchange instance.

        This is the async companion to :meth:`init_exchange` and is used
        by routes that need an exchange object for balance/order calls.
        """
        import ccxt.async_support as accxt

        ccxt_id = "gateio" if exchange_name.lower() == "gate" else exchange_name.lower()
        exchange_cls = getattr(accxt, ccxt_id, None)
        if exchange_cls is None:
            raise ValueError(f"Unknown exchange: {exchange_name}")

        config: Dict = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }
        if passphrase:
            config["password"] = passphrase
        if testnet and exchange_name.lower() == "binance":
            config.setdefault("options", {})["testnet"] = True

        return exchange_cls(config)

# Global instance
ccxt_service = CCXTService()
