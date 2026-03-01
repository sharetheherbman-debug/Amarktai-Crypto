"""
Exchange Adapter - Unified CCXT wrapper for all 7 supported exchanges.

Provides a consistent interface for market metadata, precision, min notional,
fee model, order simulation, and balance queries across:
  Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io

The adapter sits between the trading engine and CCXT so the underlying
library can be swapped later if needed.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Canonical exchange identifiers
SUPPORTED_EXCHANGES = [
    "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"
]

# Default fee rates by exchange (maker/taker in percent)
DEFAULT_FEES: Dict[str, Dict[str, float]] = {
    "luno":    {"maker": 0.0, "taker": 0.10},
    "binance": {"maker": 0.10, "taker": 0.10},
    "kucoin":  {"maker": 0.10, "taker": 0.10},
    "bybit":   {"maker": 0.10, "taker": 0.10},
    "kraken":  {"maker": 0.16, "taker": 0.26},
    "bitget":  {"maker": 0.10, "taker": 0.10},
    "gate":    {"maker": 0.20, "taker": 0.20},
}

# Default quote currencies
DEFAULT_QUOTE: Dict[str, str] = {
    "luno":    "ZAR",
    "binance": "USDT",
    "kucoin":  "USDT",
    "bybit":   "USDT",
    "kraken":  "USDT",
    "bitget":  "USDT",
    "gate":    "USDT",
}

# Default viable pairs per exchange for paper trading
DEFAULT_PAIRS: Dict[str, List[str]] = {
    "luno":    ["BTC/ZAR", "ETH/ZAR"],
    "binance": ["BTC/USDT", "ETH/USDT"],
    "kucoin":  ["BTC/USDT", "ETH/USDT"],
    "bybit":   ["BTC/USDT", "ETH/USDT"],
    "kraken":  ["BTC/USDT", "ETH/USDT"],
    "bitget":  ["BTC/USDT", "ETH/USDT"],
    "gate":    ["BTC/USDT", "ETH/USDT"],
}


class ExchangeAdapter:
    """Unified exchange interface wrapping CCXT."""

    def __init__(self):
        self._instances: Dict[str, object] = {}

    def is_supported(self, exchange: str) -> bool:
        return exchange.lower() in SUPPORTED_EXCHANGES

    def get_default_quote(self, exchange: str) -> str:
        return DEFAULT_QUOTE.get(exchange.lower(), "USDT")

    def get_default_pairs(self, exchange: str) -> List[str]:
        return DEFAULT_PAIRS.get(exchange.lower(), ["BTC/USDT", "ETH/USDT"])

    def get_fee_rates(self, exchange: str) -> Dict[str, float]:
        return DEFAULT_FEES.get(exchange.lower(), {"maker": 0.10, "taker": 0.10})

    async def test_connection(self, exchange: str, api_key: str = "", secret: str = "", passphrase: str = "") -> Dict:
        """
        Test connectivity to an exchange.
        Returns: {"success": bool, "exchange": str, "error": str|None, "timestamp": str}
        """
        exchange = exchange.lower()
        if not self.is_supported(exchange):
            return {
                "success": False,
                "exchange": exchange,
                "error": f"Unsupported exchange: {exchange}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        try:
            import ccxt.async_support as ccxt_async

            exchange_class = getattr(ccxt_async, exchange if exchange != "gate" else "gateio", None)
            if exchange_class is None:
                return {
                    "success": False,
                    "exchange": exchange,
                    "error": f"CCXT does not have exchange class for '{exchange}'",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            params = {"enableRateLimit": True}
            if api_key:
                params["apiKey"] = api_key
                params["secret"] = secret
            if passphrase:
                params["password"] = passphrase

            ex = exchange_class(params)
            try:
                await ex.load_markets()
                market_count = len(ex.markets) if ex.markets else 0
                return {
                    "success": True,
                    "exchange": exchange,
                    "markets_loaded": market_count,
                    "error": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            finally:
                await ex.close()

        except Exception as e:
            logger.warning(f"Exchange test failed for {exchange}: {e}")
            return {
                "success": False,
                "exchange": exchange,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def get_exchange_status(self, exchange: str, user_id: str = "") -> Dict:
        """
        Return configuration + readiness status for a given exchange.
        Does NOT require API keys – only checks whether the exchange is recognized
        and optionally whether keys are configured for the user.
        """
        exchange = exchange.lower()
        configured = False
        last_tested = None
        test_passed = None
        error_reason = None

        if not self.is_supported(exchange):
            return {
                "exchange": exchange,
                "supported": False,
                "configured": False,
                "last_tested": None,
                "test_passed": False,
                "error_reason": "Unsupported exchange",
                "default_quote": None,
                "default_pairs": [],
            }

        # Optionally check user keys
        if user_id:
            try:
                import database as db
                key_doc = await db.database["api_keys"].find_one(
                    {"user_id": user_id, "provider": exchange}
                )
                if key_doc and key_doc.get("api_key"):
                    configured = True
                    last_tested = key_doc.get("last_tested")
                    test_passed = key_doc.get("test_passed")
                    error_reason = key_doc.get("error_reason")
            except Exception as e:
                logger.debug(f"Could not check keys for {exchange}: {e}")

        return {
            "exchange": exchange,
            "supported": True,
            "configured": configured,
            "last_tested": last_tested,
            "test_passed": test_passed,
            "error_reason": error_reason,
            "default_quote": self.get_default_quote(exchange),
            "default_pairs": self.get_default_pairs(exchange),
            "fee_rates": self.get_fee_rates(exchange),
        }

    def simulate_fill(
        self,
        exchange: str,
        side: str,
        price: float,
        quantity: float,
        slippage_pct: float = 0.1,
    ) -> Dict:
        """
        Simulate a paper fill with realistic fees and slippage.
        Returns fill details without touching any exchange.
        """
        fees = self.get_fee_rates(exchange)
        fee_rate = fees["taker"] / 100.0
        slip = slippage_pct / 100.0

        if side.lower() == "buy":
            fill_price = price * (1 + slip)
        else:
            fill_price = price * (1 - slip)

        notional = fill_price * quantity
        fee = notional * fee_rate

        return {
            "exchange": exchange,
            "side": side.lower(),
            "requested_price": price,
            "fill_price": round(fill_price, 8),
            "quantity": quantity,
            "notional": round(notional, 8),
            "fee": round(fee, 8),
            "fee_rate": fee_rate,
            "slippage_pct": slippage_pct,
            "simulated": True,
        }


# Singleton instance
exchange_adapter = ExchangeAdapter()
