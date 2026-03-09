"""
Opportunity Scanner Engine
Continuously scans market conditions for actionable trading opportunities:
  - Momentum spikes
  - Volume surges
  - Liquidity walls / order-book imbalance
  - Whale transactions
  - Volatility bursts
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OpportunityType(str, Enum):
    """Types of detected trading opportunities"""
    MOMENTUM_SPIKE = "momentum_spike"
    VOLUME_SURGE = "volume_surge"
    LIQUIDITY_WALL = "liquidity_wall"
    ORDERBOOK_IMBALANCE = "orderbook_imbalance"
    WHALE_TRANSACTION = "whale_transaction"
    VOLATILITY_BURST = "volatility_burst"


@dataclass
class Opportunity:
    """Detected market opportunity"""
    type: OpportunityType
    symbol: str
    score: float  # 0-1 relevance score
    direction: str  # "long" | "short" | "neutral"
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int = 300  # opportunity validity window (5 min)

    @property
    def expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds


class OpportunityScanner:
    """
    Scans market data streams for short-lived trading opportunities.

    Integrates with:
      - PriceAggregator (price ticks)
      - OrderBookAnalyzer (bid/ask snapshots)
      - WhaleFlowTracker (large-transfer events)
      - RegimeDetector (regime context)
    """

    def __init__(
        self,
        momentum_threshold: float = 0.02,
        volume_surge_multiplier: float = 2.5,
        imbalance_threshold: float = 0.3,
        volatility_burst_multiplier: float = 3.0,
        max_opportunities: int = 50,
    ):
        self.momentum_threshold = momentum_threshold
        self.volume_surge_multiplier = volume_surge_multiplier
        self.imbalance_threshold = imbalance_threshold
        self.volatility_burst_multiplier = volatility_burst_multiplier
        self.max_opportunities = max_opportunities

        # Internal state
        self._price_buffer: Dict[str, List[Dict]] = {}
        self._volume_baseline: Dict[str, float] = {}
        self._volatility_baseline: Dict[str, float] = {}
        self._opportunities: List[Opportunity] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_tick(self, symbol: str, price: float, volume: float = 0.0) -> None:
        """Feed a price/volume tick into the scanner."""
        now = time.time()
        buf = self._price_buffer.setdefault(symbol, [])
        buf.append({"price": price, "volume": volume, "ts": now})

        # Keep last 200 ticks per symbol
        if len(buf) > 200:
            self._price_buffer[symbol] = buf[-200:]

        self._update_baselines(symbol)

    def scan(self, symbol: Optional[str] = None) -> List[Opportunity]:
        """Run opportunity detection on one or all tracked symbols."""
        symbols = [symbol] if symbol else list(self._price_buffer.keys())
        new_opps: List[Opportunity] = []

        for sym in symbols:
            buf = self._price_buffer.get(sym, [])
            if len(buf) < 10:
                continue

            opp = self._check_momentum_spike(sym, buf)
            if opp:
                new_opps.append(opp)

            opp = self._check_volume_surge(sym, buf)
            if opp:
                new_opps.append(opp)

            opp = self._check_volatility_burst(sym, buf)
            if opp:
                new_opps.append(opp)

        # Merge into main list, deduplicate by (type, symbol)
        for opp in new_opps:
            self._add_opportunity(opp)

        return self.get_active()

    def add_whale_signal(self, symbol: str, direction: str, value_usd: float, confidence: float) -> None:
        """Register a whale transaction detected externally."""
        if confidence < 0.4:
            return
        self._add_opportunity(Opportunity(
            type=OpportunityType.WHALE_TRANSACTION,
            symbol=symbol,
            score=min(1.0, confidence),
            direction=direction,
            details={"value_usd": value_usd, "confidence": confidence},
            ttl_seconds=600,
        ))

    def add_orderbook_signal(self, symbol: str, imbalance: float, spread_pct: float) -> None:
        """Register an order-book imbalance detected externally."""
        if abs(imbalance) < self.imbalance_threshold:
            return
        direction = "long" if imbalance > 0 else "short"
        self._add_opportunity(Opportunity(
            type=OpportunityType.ORDERBOOK_IMBALANCE,
            symbol=symbol,
            score=min(1.0, abs(imbalance)),
            direction=direction,
            details={"imbalance": imbalance, "spread_pct": spread_pct},
            ttl_seconds=120,
        ))

    def add_liquidity_wall(self, symbol: str, side: str, price_level: float, volume: float) -> None:
        """Register a detected liquidity wall."""
        self._add_opportunity(Opportunity(
            type=OpportunityType.LIQUIDITY_WALL,
            symbol=symbol,
            score=0.7,
            direction="long" if side == "bid" else "short",
            details={"side": side, "price_level": price_level, "volume": volume},
            ttl_seconds=300,
        ))

    def get_active(self) -> List[Opportunity]:
        """Return all non-expired opportunities sorted by score descending."""
        self._opportunities = [o for o in self._opportunities if not o.expired]
        return sorted(self._opportunities, key=lambda o: o.score, reverse=True)

    def get_summary(self) -> Dict[str, Any]:
        """Return a dashboard-friendly summary."""
        active = self.get_active()
        by_type: Dict[str, int] = {}
        for o in active:
            by_type[o.type.value] = by_type.get(o.type.value, 0) + 1

        return {
            "total_active": len(active),
            "by_type": by_type,
            "top_opportunities": [
                {
                    "type": o.type.value,
                    "symbol": o.symbol,
                    "score": round(o.score, 3),
                    "direction": o.direction,
                    "details": o.details,
                    "age_seconds": round(
                        (datetime.now(timezone.utc) - o.timestamp).total_seconds(), 1
                    ),
                }
                for o in active[:10]
            ],
        }

    # ------------------------------------------------------------------
    # Internal detection methods
    # ------------------------------------------------------------------

    def _update_baselines(self, symbol: str) -> None:
        buf = self._price_buffer.get(symbol, [])
        if len(buf) < 20:
            return

        volumes = [t["volume"] for t in buf[-50:] if t["volume"] > 0]
        if volumes:
            self._volume_baseline[symbol] = sum(volumes) / len(volumes)

        prices = [t["price"] for t in buf[-50:]]
        if len(prices) > 1:
            returns = [
                abs(prices[i] / prices[i - 1] - 1.0)
                for i in range(1, len(prices))
                if prices[i - 1] != 0
            ]
            if returns:
                self._volatility_baseline[symbol] = sum(returns) / len(returns)

    def _check_momentum_spike(self, symbol: str, buf: List[Dict]) -> Optional[Opportunity]:
        recent = [t["price"] for t in buf[-5:]]
        older = [t["price"] for t in buf[-20:-5]]
        if not older or not recent:
            return None
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        if avg_older == 0:
            return None
        change = (avg_recent - avg_older) / avg_older
        if abs(change) >= self.momentum_threshold:
            return Opportunity(
                type=OpportunityType.MOMENTUM_SPIKE,
                symbol=symbol,
                score=min(1.0, abs(change) / self.momentum_threshold),
                direction="long" if change > 0 else "short",
                details={"change_pct": round(change * 100, 3)},
            )
        return None

    def _check_volume_surge(self, symbol: str, buf: List[Dict]) -> Optional[Opportunity]:
        baseline = self._volume_baseline.get(symbol, 0)
        if baseline <= 0:
            return None
        recent_vol = sum(t["volume"] for t in buf[-3:]) / 3.0
        ratio = recent_vol / baseline
        if ratio >= self.volume_surge_multiplier:
            return Opportunity(
                type=OpportunityType.VOLUME_SURGE,
                symbol=symbol,
                score=min(1.0, ratio / (self.volume_surge_multiplier * 2)),
                direction="neutral",
                details={"volume_ratio": round(ratio, 2)},
            )
        return None

    def _check_volatility_burst(self, symbol: str, buf: List[Dict]) -> Optional[Opportunity]:
        baseline = self._volatility_baseline.get(symbol, 0)
        if baseline <= 0:
            return None
        recent_prices = [t["price"] for t in buf[-5:]]
        if len(recent_prices) < 2:
            return None
        recent_returns = [
            abs(recent_prices[i] / recent_prices[i - 1] - 1.0)
            for i in range(1, len(recent_prices))
            if recent_prices[i - 1] != 0
        ]
        if not recent_returns:
            return None
        avg_return = sum(recent_returns) / len(recent_returns)
        ratio = avg_return / baseline
        if ratio >= self.volatility_burst_multiplier:
            return Opportunity(
                type=OpportunityType.VOLATILITY_BURST,
                symbol=symbol,
                score=min(1.0, ratio / (self.volatility_burst_multiplier * 2)),
                direction="neutral",
                details={"volatility_ratio": round(ratio, 2)},
            )
        return None

    def _add_opportunity(self, opp: Opportunity) -> None:
        # Deduplicate: replace existing opportunity of same type+symbol
        self._opportunities = [
            o for o in self._opportunities
            if not (o.type == opp.type and o.symbol == opp.symbol)
        ]
        self._opportunities.append(opp)
        # Prune oldest if over limit
        if len(self._opportunities) > self.max_opportunities:
            self._opportunities = sorted(
                self._opportunities, key=lambda o: o.score, reverse=True
            )[: self.max_opportunities]


# Global instance
opportunity_scanner = OpportunityScanner()
