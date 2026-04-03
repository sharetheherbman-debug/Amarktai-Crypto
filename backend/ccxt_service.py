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
            
            if testnet:
                config['options'] = {'defaultType': 'spot'}
                if exchange_name.lower() == 'binance':
                    config['options']['testnet'] = True
            
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
            await asyncio.to_thread(exchange.fetch_balance)
            return True
        except Exception as e:
            logger.error(f"Connection test failed for {exchange_name}: {e}")
            return False
    
    async def get_balance(self, exchange: ccxt.Exchange, currency: str = 'USDT') -> float:
        """Get balance for specific currency"""
        try:
            balance = await asyncio.to_thread(exchange.fetch_balance)
            return balance.get(currency, {}).get('free', 0.0)
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0
    
    async def fetch_ticker(self, exchange: ccxt.Exchange, symbol: str) -> Dict:
        """Fetch ticker data"""
        try:
            ticker = await asyncio.to_thread(exchange.fetch_ticker, symbol)
            return ticker
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return {}
    
    async def create_market_order(self, exchange: ccxt.Exchange, symbol: str, 
                                 side: str, amount: float, paper_trading: bool = True) -> Dict:
        """Create market order (paper or live)"""
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
                order = await asyncio.to_thread(
                    exchange.create_market_order,
                    symbol, side, amount
                )
                return order
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
