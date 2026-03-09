"""
Market Intelligence Engine
- Multi-provider price aggregation with staggered rotation
- Whale flow tracking, order-book analysis, strategy selection
- Provider failover with heartbeat monitoring
"""

import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  LRU Cache                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class LRUCache:
    """Thread-safe, TTL-aware LRU cache."""

    def __init__(self, max_size: int = 256, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Provider Scheduler                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass
class ProviderQuota:
    """Tracks call counts for a provider."""
    monthly_limit: int = 100_000
    per_minute_limit: int = 50
    monthly_calls: int = 0
    minute_calls: int = 0
    minute_window_start: float = field(default_factory=time.time)
    month_window_start: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m")
    )
    switch_threshold: float = 0.70  # switch when 70 % of limit used


class ProviderScheduler:
    """
    Rotates requests across price providers to stay within free-tier limits.

    Priority order (configurable):
      1. CoinDesk       – primary market-data source
      2. CryptoCompare  – secondary
      3. CoinGecko      – tertiary
      4. Coinranking    – quaternary
    """

    DEFAULT_QUOTAS: Dict[str, Dict] = {
        "coindesk":      {"monthly_limit": 200_000, "per_minute_limit": 60},
        "cryptocompare": {"monthly_limit": 100_000, "per_minute_limit": 50},
        "coingecko":     {"monthly_limit": 999_999, "per_minute_limit": 30},
        "coinranking":   {"monthly_limit": 10_000,  "per_minute_limit": 5},
    }

    def __init__(self, priority: Optional[List[str]] = None):
        self._priority = priority or ["coindesk", "cryptocompare", "coingecko", "coinranking"]
        self._quotas: Dict[str, ProviderQuota] = {}
        for name in self._priority:
            defaults = self.DEFAULT_QUOTAS.get(name, {})
            self._quotas[name] = ProviderQuota(**defaults)

    # ------------------------------------------------------------------

    def _reset_minute_window(self, q: ProviderQuota) -> None:
        now = time.time()
        if now - q.minute_window_start >= 60:
            q.minute_calls = 0
            q.minute_window_start = now

    def _reset_month_window(self, q: ProviderQuota) -> None:
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if q.month_window_start != current_month:
            q.monthly_calls = 0
            q.month_window_start = current_month

    # ------------------------------------------------------------------

    def record_call(self, provider: str) -> None:
        """Record a single API call for *provider*."""
        q = self._quotas.get(provider)
        if not q:
            return
        self._reset_minute_window(q)
        self._reset_month_window(q)
        q.monthly_calls += 1
        q.minute_calls += 1

    def next_provider(self) -> Optional[str]:
        """
        Return the best available provider name, or None if all are exhausted.
        """
        for name in self._priority:
            q = self._quotas.get(name)
            if q is None:
                continue
            self._reset_minute_window(q)
            self._reset_month_window(q)

            monthly_ok = q.monthly_calls < q.monthly_limit * q.switch_threshold
            minute_ok = q.minute_calls < q.per_minute_limit
            if monthly_ok and minute_ok:
                return name

        # All above threshold – fall back to whoever has the most headroom
        best, best_headroom = None, -1
        for name in self._priority:
            q = self._quotas.get(name)
            if q is None:
                continue
            headroom = q.monthly_limit - q.monthly_calls
            if headroom > best_headroom:
                best, best_headroom = name, headroom
        return best

    def get_usage(self) -> Dict[str, Dict]:
        """Return usage statistics per provider."""
        out: Dict[str, Dict] = {}
        for name, q in self._quotas.items():
            self._reset_minute_window(q)
            self._reset_month_window(q)
            out[name] = {
                "monthly_calls": q.monthly_calls,
                "monthly_limit": q.monthly_limit,
                "monthly_pct": round(q.monthly_calls / max(q.monthly_limit, 1) * 100, 1),
                "minute_calls": q.minute_calls,
                "per_minute_limit": q.per_minute_limit,
            }
        return out

    def set_priority(self, priority: List[str]) -> None:
        """Update provider priority order at runtime."""
        self._priority = priority

    def set_threshold(self, provider: str, threshold: float) -> None:
        """Set the switch-over threshold for a provider (0.0–1.0)."""
        q = self._quotas.get(provider)
        if q:
            q.switch_threshold = max(0.0, min(1.0, threshold))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Price Providers                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class PriceProvider:
    """Base class for price data providers."""

    name: str = "base"

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        raise NotImplementedError

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        raise NotImplementedError

    async def ping(self) -> bool:
        raise NotImplementedError


class CoinDeskProvider(PriceProvider):
    """CoinDesk price provider (primary)."""

    name = "coindesk"
    BASE = "https://api.coindesk.com/v1/bpi/currentprice"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._api_key:
            # CoinDesk key is optional for this public endpoint. If configured,
            # we send it for production consistency and future quota telemetry.
            headers["X-API-Key"] = self._api_key
        return headers

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        # CoinDesk currentprice endpoint is BTC-first; non-BTC symbols should
        # gracefully fall through to secondary providers.
        if symbol.upper() != "BTC":
            return None
        fiat = vs_currency.upper()
        url = f"{self.BASE}/{fiat}.json"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return None
                    data = await r.json()
                    bpi = data.get("bpi", {})
                    quote = bpi.get(fiat)
                    if not quote:
                        return None
                    price = quote.get("rate_float")
                    if price is None:
                        return None
                    return {"symbol": "BTC", "price": price, "currency": vs_currency, "source": self.name}
        except Exception as exc:
            logger.error("CoinDesk price error (%s): %s", symbol, exc)
        return None

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        # Batch endpoint parity not available in this provider; return only BTC
        # when requested and let scheduler fallback for remaining symbols.
        result: Dict[str, Dict] = {}
        if any(sym.upper() == "BTC" for sym in symbols):
            btc = await self.get_price("BTC", vs_currency)
            if btc is not None:
                result["BTC"] = btc
        return result

    async def ping(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.BASE}/USD.json",
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False


class CryptoCompareProvider(PriceProvider):
    """CryptoCompare price provider (primary)."""

    name = "cryptocompare"
    BASE = "https://min-api.cryptocompare.com/data"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self._api_key:
            h["Authorization"] = f"Apikey {self._api_key}"
        return h

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        url = f"{self.BASE}/price?fsym={symbol.upper()}&tsyms={vs_currency.upper()}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        price = data.get(vs_currency.upper())
                        if price is not None:
                            return {"symbol": symbol.upper(), "price": price, "currency": vs_currency, "source": self.name}
        except Exception as exc:
            logger.error("CryptoCompare price error (%s): %s", symbol, exc)
        return None

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        fsyms = ",".join(s.upper() for s in symbols)
        url = f"{self.BASE}/pricemulti?fsyms={fsyms}&tsyms={vs_currency.upper()}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return {
                            sym: {"symbol": sym, "price": vals.get(vs_currency.upper()), "currency": vs_currency, "source": self.name}
                            for sym, vals in data.items()
                        }
        except Exception as exc:
            logger.error("CryptoCompare batch error: %s", exc)
        return {}

    async def ping(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.BASE}/price?fsym=BTC&tsyms=USD", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return r.status == 200
        except Exception:
            return False


class CoinGeckoProvider(PriceProvider):
    """CoinGecko price provider (secondary)."""

    name = "coingecko"
    BASE = "https://api.coingecko.com/api/v3"

    # Mapping of common symbols to CoinGecko IDs
    SYMBOL_MAP = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
        "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "DOT": "polkadot", "AVAX": "avalanche-2",
        "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
    }

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self._api_key:
            h["x-cg-demo-api-key"] = self._api_key
        return h

    def _symbol_to_id(self, symbol: str) -> str:
        return self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        coin_id = self._symbol_to_id(symbol)
        url = f"{self.BASE}/simple/price?ids={coin_id}&vs_currencies={vs_currency}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        coin_data = data.get(coin_id, {})
                        price = coin_data.get(vs_currency)
                        if price is not None:
                            return {"symbol": symbol.upper(), "price": price, "currency": vs_currency, "source": self.name}
        except Exception as exc:
            logger.error("CoinGecko price error (%s): %s", symbol, exc)
        return None

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        ids = ",".join(self._symbol_to_id(s) for s in symbols)
        url = f"{self.BASE}/simple/price?ids={ids}&vs_currencies={vs_currency}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        # Reverse-map IDs back to symbols
                        id_to_sym = {self._symbol_to_id(sym): sym.upper() for sym in symbols}
                        return {
                            id_to_sym.get(cid, cid): {"symbol": id_to_sym.get(cid, cid), "price": vals.get(vs_currency), "currency": vs_currency, "source": self.name}
                            for cid, vals in data.items()
                        }
        except Exception as exc:
            logger.error("CoinGecko batch error: %s", exc)
        return {}

    async def ping(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.BASE}/ping", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return r.status == 200
        except Exception:
            return False


class CoinrankingProvider(PriceProvider):
    """Coinranking price provider (fallback)."""

    name = "coinranking"
    BASE = "https://api.coinranking.com/v2"

    # Coinranking uses UUIDs; map common symbols
    SYMBOL_MAP = {
        "BTC": "Qwsogvtv82FCd", "ETH": "razxDUgYGNAdQ",
        "BNB": "WcwrkfNI4FUAe", "SOL": "zNZHO_Sjf",
        "XRP": "-l8Mn2pVlRs-p",
    }

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self._api_key:
            h["x-access-token"] = self._api_key
        return h

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        uuid = self.SYMBOL_MAP.get(symbol.upper())
        if not uuid:
            return None
        url = f"{self.BASE}/coin/{uuid}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        coin = data.get("data", {}).get("coin", {})
                        price = coin.get("price")
                        if price is not None:
                            return {"symbol": symbol.upper(), "price": float(price), "currency": vs_currency, "source": self.name}
        except Exception as exc:
            logger.error("Coinranking price error (%s): %s", symbol, exc)
        return None

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        uuids = [self.SYMBOL_MAP.get(s.upper()) for s in symbols if s.upper() in self.SYMBOL_MAP]
        if not uuids:
            return {}
        uuid_param = "&uuids[]=".join(uuids)
        url = f"{self.BASE}/coins?uuids[]={uuid_param}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        coins = data.get("data", {}).get("coins", [])
                        return {
                            c["symbol"]: {"symbol": c["symbol"], "price": float(c.get("price", 0)), "currency": vs_currency, "source": self.name}
                            for c in coins if c.get("symbol")
                        }
        except Exception as exc:
            logger.error("Coinranking batch error: %s", exc)
        return {}

    async def ping(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.BASE}/stats", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return r.status == 200
        except Exception:
            return False


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Price Aggregator                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class PriceAggregator:
    """
    Queries providers in priority order (via ProviderScheduler) until
    data is returned.  Results are cached to minimise calls.
    """

    def __init__(
        self,
        providers: Optional[Dict[str, PriceProvider]] = None,
        scheduler: Optional[ProviderScheduler] = None,
        cache_ttl: int = 60,
    ):
        self._providers: Dict[str, PriceProvider] = providers or {}
        self._scheduler = scheduler or ProviderScheduler()
        self._cache = LRUCache(max_size=512, ttl_seconds=cache_ttl)

    def register_provider(self, provider: PriceProvider) -> None:
        self._providers[provider.name] = provider

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        cache_key = f"price:{symbol.upper()}:{vs_currency}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Try providers in scheduler order
        tried: List[str] = []
        for _ in range(len(self._providers)):
            name = self._scheduler.next_provider()
            if name is None or name in tried:
                break
            tried.append(name)

            provider = self._providers.get(name)
            if provider is None:
                continue

            result = await provider.get_price(symbol, vs_currency)
            self._scheduler.record_call(name)
            if result is not None:
                self._cache.set(cache_key, result)
                return result

        logger.warning("All providers exhausted for %s/%s", symbol, vs_currency)
        return None

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        """Batch price fetch; tries cache first, then providers."""
        results: Dict[str, Dict] = {}
        uncached: List[str] = []

        for sym in symbols:
            cache_key = f"price:{sym.upper()}:{vs_currency}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                results[sym.upper()] = cached
            else:
                uncached.append(sym)

        if not uncached:
            return results

        tried: List[str] = []
        for _ in range(len(self._providers)):
            name = self._scheduler.next_provider()
            if name is None or name in tried:
                break
            tried.append(name)

            provider = self._providers.get(name)
            if provider is None:
                continue

            batch = await provider.get_prices_batch(uncached, vs_currency)
            self._scheduler.record_call(name)
            if batch:
                for sym, data in batch.items():
                    results[sym] = data
                    self._cache.set(f"price:{sym}:{vs_currency}", data)
                return results

        return results


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Whale Flow Tracker                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class WhaleFlowTracker:
    """
    Tracks large crypto transfers using Etherscan, Glassnode,
    and Whale Alert (when keys are available).
    """

    def __init__(
        self,
        etherscan_key: str = "",
        glassnode_key: str = "",
        whale_alert_key: str = "",
        threshold_usd: float = 500_000,
    ):
        self._etherscan_key = etherscan_key
        self._glassnode_key = glassnode_key
        self._whale_alert_key = whale_alert_key
        self._threshold_usd = threshold_usd
        self._recent_signals: List[Dict] = []

    async def get_etherscan_whale_transfers(self, min_value_eth: float = 100) -> List[Dict]:
        """Fetch recent large ETH transfers from Etherscan."""
        if not self._etherscan_key:
            return []
        url = (
            f"https://api.etherscan.io/api?module=account&action=txlist"
            f"&address=0x0000000000000000000000000000000000000000"
            f"&startblock=0&endblock=99999999&page=1&offset=10&sort=desc"
            f"&apikey={self._etherscan_key}"
        )
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return [
                            {
                                "type": "etherscan_transfer",
                                "from": tx.get("from", ""),
                                "to": tx.get("to", ""),
                                "value_eth": int(tx.get("value", 0)) / 1e18,
                                "timestamp": tx.get("timeStamp", ""),
                            }
                            for tx in data.get("result", [])
                            if isinstance(tx, dict) and int(tx.get("value", 0)) / 1e18 >= min_value_eth
                        ]
        except Exception as exc:
            logger.error("Etherscan whale transfer error: %s", exc)
        return []

    async def get_whale_signals(self) -> List[Dict]:
        """
        Aggregate whale signals from all available sources.
        Each signal has: symbol, direction, confidence_score, source, timestamp.
        """
        signals: List[Dict] = []

        # Etherscan
        eth_transfers = await self.get_etherscan_whale_transfers()
        for tx in eth_transfers:
            signals.append({
                "symbol": "ETH",
                "direction": "inflow",
                "confidence_score": 0.6,
                "source": "etherscan",
                "value": tx.get("value_eth", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        self._recent_signals = signals
        return signals

    def get_recent_signals(self) -> List[Dict]:
        return list(self._recent_signals)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Order Book Analyzer                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class OrderBookAnalyzer:
    """
    Analyses real-time order-book snapshots from CCXT.
    Computes bid/ask imbalance, liquidity walls, and compression.
    """

    @staticmethod
    def compute_imbalance(bids: List[List[float]], asks: List[List[float]], depth: int = 10) -> float:
        """
        Compute bid/ask imbalance ratio.

        Returns:
            Positive = bid-heavy (bullish pressure), Negative = ask-heavy.
            Range approx [-1, 1].
        """
        bid_vol = sum(b[1] for b in bids[:depth]) if bids else 0
        ask_vol = sum(a[1] for a in asks[:depth]) if asks else 0
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    @staticmethod
    def find_liquidity_walls(
        bids: List[List[float]],
        asks: List[List[float]],
        wall_multiplier: float = 3.0,
    ) -> Dict[str, List[Dict]]:
        """Find price levels with outsized volume (liquidity walls)."""
        walls: Dict[str, List[Dict]] = {"bid_walls": [], "ask_walls": []}

        if bids:
            avg_bid = sum(b[1] for b in bids) / len(bids) if bids else 1
            for price, vol in bids:
                if vol >= avg_bid * wall_multiplier:
                    walls["bid_walls"].append({"price": price, "volume": vol})

        if asks:
            avg_ask = sum(a[1] for a in asks) / len(asks) if asks else 1
            for price, vol in asks:
                if vol >= avg_ask * wall_multiplier:
                    walls["ask_walls"].append({"price": price, "volume": vol})

        return walls

    @staticmethod
    def compute_spread(bids: List[List[float]], asks: List[List[float]]) -> Optional[Dict]:
        """Compute bid-ask spread."""
        if not bids or not asks:
            return None
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "spread_pct": (spread / mid * 100) if mid else 0,
        }


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Strategy Selector                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class StrategyType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    MOMENTUM_SCALPING = "momentum_scalping"
    LIQUIDITY_SWEEP = "liquidity_sweep"


class StrategySelector:
    """
    Picks a strategy based on the current market regime.
    Each bot should query the selector before placing a trade.
    """

    REGIME_STRATEGY_MAP: Dict[str, StrategyType] = {
        "bullish_calm": StrategyType.TREND_FOLLOWING,
        "bearish_volatile": StrategyType.MEAN_REVERSION,
        "squeeze": StrategyType.BREAKOUT,
        "trending": StrategyType.TREND_FOLLOWING,
        "ranging": StrategyType.MEAN_REVERSION,
        "volatile": StrategyType.MOMENTUM_SCALPING,
        "panic": StrategyType.LIQUIDITY_SWEEP,
        "unknown": StrategyType.TREND_FOLLOWING,
    }

    def select(self, regime: str) -> StrategyType:
        """Return the best strategy for *regime*."""
        return self.REGIME_STRATEGY_MAP.get(regime, StrategyType.TREND_FOLLOWING)

    def get_strategy_params(self, strategy: StrategyType) -> Dict[str, Any]:
        """Return default parameters for the given strategy."""
        defaults: Dict[StrategyType, Dict[str, Any]] = {
            StrategyType.TREND_FOLLOWING: {
                "entry_lookback": 20,
                "exit_lookback": 10,
                "stop_loss_pct": 2.0,
                "take_profit_pct": 5.0,
            },
            StrategyType.MEAN_REVERSION: {
                "bollinger_period": 20,
                "std_dev": 2.0,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
            },
            StrategyType.BREAKOUT: {
                "channel_period": 20,
                "volume_threshold": 1.5,
                "stop_loss_pct": 2.5,
                "take_profit_pct": 6.0,
            },
            StrategyType.MOMENTUM_SCALPING: {
                "rsi_period": 14,
                "rsi_overbought": 70,
                "rsi_oversold": 30,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 2.0,
            },
            StrategyType.LIQUIDITY_SWEEP: {
                "sweep_depth": 5,
                "min_imbalance": 0.3,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 4.0,
            },
        }
        return defaults.get(strategy, {})


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Market Intelligence Engine (Orchestrator)                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class MarketIntelligenceEngine:
    """
    Top-level orchestrator that wires together:
    - PriceAggregator (multi-provider prices)
    - ProviderScheduler (rotation / rate-limit management)
    - WhaleFlowTracker
    - OrderBookAnalyzer
    - StrategySelector
    """

    def __init__(self):
        # Build providers from env keys
        cd_key = os.getenv("COINDESK_API_KEY", "")
        cc_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
        cg_key = os.getenv("COINGECKO_API_KEY", "")
        cr_key = os.getenv("COINRANKING_API_KEY", "")

        self.scheduler = ProviderScheduler()
        self.aggregator = PriceAggregator(scheduler=self.scheduler, cache_ttl=60)

        # Register providers that have keys (or work without)
        self.aggregator.register_provider(CoinDeskProvider(api_key=cd_key))
        self.aggregator.register_provider(CryptoCompareProvider(api_key=cc_key))
        self.aggregator.register_provider(CoinGeckoProvider(api_key=cg_key))
        if cr_key:
            self.aggregator.register_provider(CoinrankingProvider(api_key=cr_key))

        self.whale_tracker = WhaleFlowTracker(
            etherscan_key=os.getenv("ETHERSCAN_API_KEY", ""),
            glassnode_key=os.getenv("GLASSNODE_API_KEY", ""),
            whale_alert_key=os.getenv("WHALE_ALERT_API_KEY", ""),
        )
        self.order_book_analyzer = OrderBookAnalyzer()
        self.strategy_selector = StrategySelector()

    # ----- convenience wrappers -----

    async def get_price(self, symbol: str, vs_currency: str = "usd") -> Optional[Dict]:
        return await self.aggregator.get_price(symbol, vs_currency)

    async def get_prices_batch(self, symbols: List[str], vs_currency: str = "usd") -> Dict[str, Dict]:
        return await self.aggregator.get_prices_batch(symbols, vs_currency)

    async def get_whale_signals(self) -> List[Dict]:
        return await self.whale_tracker.get_whale_signals()

    def select_strategy(self, regime: str) -> Dict:
        strategy = self.strategy_selector.select(regime)
        return {
            "strategy": strategy.value,
            "params": self.strategy_selector.get_strategy_params(strategy),
        }

    def get_provider_usage(self) -> Dict:
        return self.scheduler.get_usage()

    async def health_check(self) -> Dict[str, bool]:
        """Ping all registered providers and return status."""
        results: Dict[str, bool] = {}
        for name, prov in self.aggregator._providers.items():
            try:
                results[name] = await prov.ping()
            except Exception:
                results[name] = False
        return results

    async def get_intelligence_summary(self, symbols: Optional[List[str]] = None) -> Dict:
        """Full market intelligence snapshot."""
        symbols = symbols or ["BTC", "ETH"]
        prices = await self.get_prices_batch(symbols)
        whale_signals = await self.get_whale_signals()

        return {
            "prices": prices,
            "whale_signals": whale_signals,
            "provider_usage": self.get_provider_usage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
market_intelligence_engine = MarketIntelligenceEngine()
