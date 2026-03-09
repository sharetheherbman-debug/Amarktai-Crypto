"""
Order Flow Engine - public-data microstructure scoring for bot entry/exit timing.

Wraps the existing OrderFlowImbalanceCalculator and enriches it with
a composite **microstructure score** that bots can consume.

LEGAL COMPLIANCE:
  - Uses ONLY public orderbook/trade data from official exchange APIs.
  - No latency manipulation, front-running, or wash-trading logic.
  - No scraping of protected endpoints.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MicrostructureScore:
    """Composite microstructure signal for a trading pair."""
    symbol: str
    score: float           # -1.0 (strong sell) to +1.0 (strong buy)
    liquidity_imbalance: float
    aggressive_ratio: float
    spread_pct: float
    liquidity_vacuum: bool
    confidence: float      # 0-1
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OrderFlowEngine:
    """
    High-level order-flow intelligence engine.

    Uses ONLY public data:
      - orderbook depth (bids / asks)
      - recent public trades
      - spread
      - liquidity distribution

    Produces:
      - liquidity imbalance ratio
      - aggressive-trade ratio
      - liquidity-vacuum flag
      - spread expansion detection
      - composite microstructure score
    """

    # ── Composite score weights ──────────────────────────────────────────
    WEIGHT_LIQUIDITY_IMBALANCE = 0.40
    WEIGHT_AGGRESSIVE_RATIO = 0.30
    WEIGHT_SPREAD = 0.20
    WEIGHT_VACUUM = 0.10
    SPREAD_CAP_PCT = 1.0   # spreads above this % contribute zero signal

    def __init__(self, history_limit: int = 200):
        self._history_limit = history_limit
        self._trade_buffer: Dict[str, List[Dict]] = {}
        self._orderbook_cache: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def ingest_orderbook(self, symbol: str, bids: List[List[float]], asks: List[List[float]]) -> None:
        """
        Feed an orderbook snapshot.

        bids / asks: list of [price, quantity] pairs, best first.
        """
        self._orderbook_cache[symbol] = {
            "bids": bids[:50],
            "asks": asks[:50],
            "ts": time.time(),
        }

    def ingest_trade(self, symbol: str, price: float, qty: float, side: str) -> None:
        """Feed a single public trade."""
        buf = self._trade_buffer.setdefault(symbol, [])
        buf.append({"price": price, "qty": qty, "side": side.lower(), "ts": time.time()})
        if len(buf) > self._history_limit:
            self._trade_buffer[symbol] = buf[-self._history_limit:]

    # ------------------------------------------------------------------
    # Calculations (pure, no exchange API calls)
    # ------------------------------------------------------------------

    def compute_liquidity_imbalance(self, symbol: str) -> float:
        """
        Bid-side liquidity vs ask-side liquidity.
        Positive = more bids (buying pressure), negative = more asks.
        Range approx [-1, +1].
        """
        ob = self._orderbook_cache.get(symbol)
        if not ob:
            return 0.0
        bid_vol = sum(level[1] for level in ob["bids"]) if ob["bids"] else 0
        ask_vol = sum(level[1] for level in ob["asks"]) if ob["asks"] else 0
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return round((bid_vol - ask_vol) / total, 4)

    def compute_aggressive_ratio(self, symbol: str) -> float:
        """
        Fraction of recent trades that are market-buy (taker buys).
        0.5 = balanced, >0.5 = aggressive buying, <0.5 = aggressive selling.
        """
        trades = self._trade_buffer.get(symbol, [])
        if not trades:
            return 0.5
        buys = sum(1 for t in trades if t["side"] == "buy")
        return round(buys / len(trades), 4)

    def compute_spread(self, symbol: str) -> float:
        """Return current spread as a percentage of mid-price."""
        ob = self._orderbook_cache.get(symbol)
        if not ob or not ob["bids"] or not ob["asks"]:
            return 0.0
        best_bid = ob["bids"][0][0]
        best_ask = ob["asks"][0][0]
        mid = (best_bid + best_ask) / 2
        if mid == 0:
            return 0.0
        return round((best_ask - best_bid) / mid * 100, 4)

    def detect_liquidity_vacuum(self, symbol: str, gap_threshold_pct: float = 0.5) -> bool:
        """
        True if there is a large gap in the orderbook (thin liquidity zone).
        """
        ob = self._orderbook_cache.get(symbol)
        if not ob:
            return False
        for side in ("bids", "asks"):
            levels = ob.get(side, [])
            for i in range(1, min(len(levels), 10)):
                prev_price = levels[i - 1][0]
                curr_price = levels[i][0]
                if prev_price == 0:
                    continue
                gap = abs(curr_price - prev_price) / prev_price * 100
                if gap > gap_threshold_pct:
                    return True
        return False

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------

    def compute_score(self, symbol: str) -> MicrostructureScore:
        """
        Produce a composite microstructure score for *symbol*.

        score = weighted combination of:
          - liquidity imbalance  (40%)
          - aggressive ratio     (30%)
          - inverse spread       (20%)
          - vacuum penalty       (10%)
        """
        liq_imb = self.compute_liquidity_imbalance(symbol)
        agg = self.compute_aggressive_ratio(symbol)
        spread = self.compute_spread(symbol)
        vacuum = self.detect_liquidity_vacuum(symbol)

        # Normalize aggressive ratio to [-1, +1]
        agg_signal = (agg - 0.5) * 2.0

        # Spread contribution: tighter spread = better
        spread_signal = max(0.0, 1.0 - spread) if spread < self.SPREAD_CAP_PCT else 0.0

        # Vacuum penalty
        vacuum_pen = -0.2 if vacuum else 0.0

        raw = (
            self.WEIGHT_LIQUIDITY_IMBALANCE * liq_imb
            + self.WEIGHT_AGGRESSIVE_RATIO * agg_signal
            + self.WEIGHT_SPREAD * spread_signal
            + self.WEIGHT_VACUUM * vacuum_pen
        )
        score = round(max(-1.0, min(1.0, raw)), 4)

        # Confidence: higher when we have more data
        trades_count = len(self._trade_buffer.get(symbol, []))
        ob_age = time.time() - self._orderbook_cache.get(symbol, {}).get("ts", 0)
        confidence = min(1.0, trades_count / 50) * (1.0 if ob_age < 30 else 0.5)

        return MicrostructureScore(
            symbol=symbol,
            score=score,
            liquidity_imbalance=liq_imb,
            aggressive_ratio=agg,
            spread_pct=spread,
            liquidity_vacuum=vacuum,
            confidence=round(confidence, 2),
        )

    # ------------------------------------------------------------------
    # Dashboard helpers
    # ------------------------------------------------------------------

    def get_summary(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return a JSON-safe summary for dashboard / diagnostics."""
        targets = symbols or list(self._orderbook_cache.keys())
        results = {}
        for sym in targets:
            ms = self.compute_score(sym)
            results[sym] = {
                "score": ms.score,
                "liquidity_imbalance": ms.liquidity_imbalance,
                "aggressive_ratio": ms.aggressive_ratio,
                "spread_pct": ms.spread_pct,
                "liquidity_vacuum": ms.liquidity_vacuum,
                "confidence": ms.confidence,
                "timestamp": ms.timestamp,
            }
        return {
            "symbols_tracked": len(targets),
            "scores": results,
        }


# Global singleton
order_flow_engine = OrderFlowEngine()
