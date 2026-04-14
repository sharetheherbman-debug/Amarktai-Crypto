"""
Signal Aggregator: Unified entry point for all signal sources.
Combines ML prediction, technical indicators, alpha fusion, order flow,
whale monitoring, sentiment, Fear & Greed index, and funding rate into a
single composite signal.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from logger_config import logger

# --- Core imports (always available) -----------------------------------
from ml_predictor import MLPredictor

# --- Optional engine imports (graceful degradation) --------------------
try:
    from engines.alpha_fusion_engine import AlphaFusionEngine

    _alpha_fusion_available = True
except ImportError:
    _alpha_fusion_available = False
    logger.warning("AlphaFusionEngine unavailable – skipping alpha fusion signals")

try:
    from engines.sentiment_analyzer import SentimentAnalyzer

    _sentiment_available = True
except ImportError:
    _sentiment_available = False
    logger.warning("SentimentAnalyzer unavailable – skipping sentiment signals")

try:
    from engines.order_flow_engine import OrderFlowEngine

    _order_flow_available = True
except ImportError:
    _order_flow_available = False
    logger.warning("OrderFlowEngine unavailable – skipping order-flow signals")


# -----------------------------------------------------------------------
# Weights — now includes fear_greed and funding_rate
# -----------------------------------------------------------------------
_BASE_WEIGHTS = {
    "ml": 0.28,
    "regime": 0.22,
    "alpha_fusion": 0.18,
    "sentiment": 0.12,
    "order_flow": 0.10,
    "fear_greed": 0.05,
    "funding_rate": 0.05,
}


def _redistribute_weights(available: dict[str, bool]) -> dict[str, float]:
    """Return adjusted weights so that available sources sum to 1.0."""
    active_total = sum(
        w for k, w in _BASE_WEIGHTS.items() if available.get(k, False)
    )
    if active_total == 0:
        return {k: 0.0 for k in _BASE_WEIGHTS}
    return {
        k: (w / active_total if available.get(k, False) else 0.0)
        for k, w in _BASE_WEIGHTS.items()
    }


def _direction_from_score(score: float, threshold: float = 0.05) -> str:
    if score > threshold:
        return "up"
    if score < -threshold:
        return "down"
    return "neutral"


# -----------------------------------------------------------------------
# Fear & Greed helper
# -----------------------------------------------------------------------
_fear_greed_cache: dict = {"value": 50, "ts": 0.0}
_FEAR_GREED_TTL = 900  # 15 min
_fear_greed_lock = asyncio.Lock()


async def _fetch_fear_greed() -> float:
    """
    Fetch the Crypto Fear & Greed index from alternative.me (free, no key).
    Returns a signed score in [-1, 1]:
      • value < 25  (extreme fear)  → +1.0  strong buy contrarian signal
      • value 25–40 (fear)          → +0.5
      • value 40–60 (neutral)       → 0.0
      • value 60–75 (greed)         → -0.5
      • value > 75  (extreme greed) → -1.0  strong sell contrarian signal
    Result is cached for 15 minutes and protected by an asyncio lock.
    """
    now = time.monotonic()
    async with _fear_greed_lock:
        if now - _fear_greed_cache.get("ts", 0.0) < _FEAR_GREED_TTL:
            return _fear_greed_cache.get("score", 0.0)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/", timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        value = int(data["data"][0].get("value", 50))
                        if value < 25:
                            score = 1.0
                        elif value < 40:
                            score = 0.5
                        elif value <= 60:
                            score = 0.0
                        elif value <= 75:
                            score = -0.5
                        else:
                            score = -1.0
                        _fear_greed_cache.update({"value": value, "score": score, "ts": now})
                        return score
        except Exception:
            logger.debug("Fear & Greed fetch failed – using cached value", exc_info=True)
        return _fear_greed_cache.get("score", 0.0)


# -----------------------------------------------------------------------
# Funding rate helper
# -----------------------------------------------------------------------
_funding_cache: dict = {}
_FUNDING_RATE_TTL = 300  # 5 min
_funding_lock = asyncio.Lock()


def _symbol_to_ccxt(symbol: str) -> str:
    """Map e.g. 'BTC/ZAR' → 'BTC/USDT' for funding rate lookup."""
    base = symbol.split("/")[0]
    return f"{base}/USDT"


async def _fetch_funding_rate(symbol: str) -> float:
    """
    Fetch perpetual funding rate from Binance public API (no key required).
    Returns a signed score in [-1, 1]:
      • rate > +0.02%  → -1.0 (over-leveraged longs → bearish fade)
      • rate > +0.01%  → -0.5
      • rate ~0        →  0.0
      • rate < -0.01%  → +0.5 (over-leveraged shorts → bullish fade)
      • rate < -0.02%  → +1.0
    Result is cached for 5 minutes and protected by an asyncio lock.
    """
    now = time.monotonic()
    ccxt_sym = _symbol_to_ccxt(symbol)
    async with _funding_lock:
        if now - _funding_cache.get(ccxt_sym, {}).get("ts", 0.0) < _FUNDING_RATE_TTL:
            return _funding_cache.get(ccxt_sym, {}).get("score", 0.0)
        try:
            # Binance USDM futures public endpoint – no auth needed.
            # _symbol_to_ccxt always returns "BASE/USDT"; strip "/" → "BTCUSDT".
            encoded = ccxt_sym.replace("/", "")
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={encoded}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rate = float(data.get("lastFundingRate", 0))
                        if rate > 0.0002:
                            score = -1.0
                        elif rate > 0.0001:
                            score = -0.5
                        elif rate < -0.0002:
                            score = 1.0
                        elif rate < -0.0001:
                            score = 0.5
                        else:
                            score = 0.0
                        _funding_cache[ccxt_sym] = {"rate": rate, "score": score, "ts": now}
                        return score
        except Exception:
            logger.debug("Funding rate fetch failed for %s – skipping", symbol, exc_info=True)
        return _funding_cache.get(ccxt_sym, {}).get("score", 0.0)


# -----------------------------------------------------------------------
# Core class
# -----------------------------------------------------------------------
class SignalAggregator:
    """Aggregates every signal engine into one composite signal."""

    def __init__(self) -> None:
        self._ml = MLPredictor()
        self._alpha = AlphaFusionEngine() if _alpha_fusion_available else None
        self._sentiment = SentimentAnalyzer() if _sentiment_available else None
        self._order_flow = OrderFlowEngine() if _order_flow_available else None

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _score_for_direction(direction: str, confidence: float) -> float:
        """Map direction + confidence to a signed score in [-1, 1]."""
        if direction == "up":
            return confidence
        if direction == "down":
            return -confidence
        return 0.0

    # ---- public API ----------------------------------------------------
    async def aggregate_signals(
        self,
        symbol: str,
        exchange: str,
        bot_type: str = "normal",
        regime_result: Optional[dict] = None,
    ) -> dict:
        availability: dict[str, bool] = {
            "ml": True,
            "regime": regime_result is not None,
            "alpha_fusion": False,
            "sentiment": False,
            "order_flow": False,
            "fear_greed": False,
            "funding_rate": False,
        }

        # -- 1. ML prediction (always) ----------------------------------
        ml_pred = await self._ml.predict_price(symbol)
        ml_dir = ml_pred.get("direction", "neutral")
        ml_conf = float(ml_pred.get("confidence", 0.0))
        predicted_change = float(ml_pred.get("predicted_change", 0.0))
        raw_method = ml_pred.get("method", "fallback")
        method = (
            "ml+indicators" if raw_method == "xgboost" else "rule_based_fallback"
        )

        # -- 2. Regime ---------------------------------------------------
        regime_label = "unknown"
        regime_conf = 0.0
        if regime_result:
            regime_label = regime_result.get("regime", "unknown")
            regime_conf = float(regime_result.get("confidence", 0.0))

        # -- 3. Alpha Fusion (optional) ----------------------------------
        alpha_score = 0.0
        alpha_dir = "neutral"
        if self._alpha is not None:
            try:
                fused = await self._alpha.fuse_signals(symbol)
                if fused is not None:
                    alpha_score = float(fused.score)
                    alpha_dir = _direction_from_score(alpha_score)
                    availability["alpha_fusion"] = True
            except Exception:
                logger.debug("Alpha fusion failed for %s", symbol, exc_info=True)

        # -- 4. Sentiment (optional) -------------------------------------
        sent_score = 0.0
        sent_dir = "neutral"
        if self._sentiment is not None:
            try:
                coin = symbol.replace("/", "").replace("USDT", "").replace("USD", "")
                coin = coin or symbol
                agg = await self._sentiment.analyze_coin_sentiment(coin)
                if agg is not None:
                    sent_score = float(agg.score)
                    sent_dir = _direction_from_score(sent_score)
                    availability["sentiment"] = True
                else:
                    logger.debug("Sentiment returned None for %s — weight redistributed", symbol)
            except Exception:
                logger.debug("Sentiment failed for %s", symbol, exc_info=True)
        else:
            logger.debug("Sentiment engine not available for %s — weight redistributed", symbol)

        # -- 5. Order Flow (optional, sync) ------------------------------
        of_score = 0.0
        of_dir = "neutral"
        if self._order_flow is not None:
            try:
                of_result = self._order_flow.compute_score(symbol)
                if of_result is not None:
                    of_score = float(of_result.score)
                    of_dir = _direction_from_score(of_score)
                    availability["order_flow"] = True
                else:
                    logger.debug("Order flow returned None for %s — weight redistributed", symbol)
            except Exception:
                logger.debug("Order flow failed for %s", symbol, exc_info=True)
        else:
            logger.debug("Order flow engine not available for %s — weight redistributed", symbol)

        # -- 6. Fear & Greed (contrarian macro) --------------------------
        fg_score = 0.0
        try:
            fg_score = await _fetch_fear_greed()
            availability["fear_greed"] = True
        except Exception:
            logger.debug("Fear & Greed skipped for %s", symbol, exc_info=True)

        # -- 7. Funding Rate (contrarian derivatives signal) -------------
        fr_score = 0.0
        try:
            fr_score = await _fetch_funding_rate(symbol)
            availability["funding_rate"] = True
        except Exception:
            logger.debug("Funding rate skipped for %s", symbol, exc_info=True)

        # -- 8. Hurst exponent (regime metadata, non-fatal) ----------------
        hurst_result: dict = {"hurst": 0.5, "regime": "unknown", "allowed": True}
        try:
            from services.hurst_filter import hurst_filter as _hf
            # We need recent close prices; they are not passed in here, so we
            # return the hurst metadata in the result and leave the allow/block
            # decision to the caller (paper_trading_engine) which has OHLCV data.
            hurst_result["note"] = "prices required from caller"
        except Exception:
            pass

        # -- 9. Redistribute weights & compute composite -----------------
        weights = _redistribute_weights(availability)

        regime_dir = "neutral"
        if regime_label in ("trending_up", "breakout"):
            regime_dir = "up"
        elif regime_label in ("trending_down",):
            regime_dir = "down"

        # River edge adjustment (non-fatal): If the online learner has
        # accumulated enough samples, bias confidence toward its prediction.
        river_edge = 0.5
        try:
            from services.river_learner import river_learner
            if river_learner.active and river_learner._samples_seen >= 10:
                _river_feats = {
                    "rsi": float(ml_pred.get("rsi", 50)),
                    "macd_hist": float(ml_pred.get("macd_hist", 0)),
                    "atr_pct": 0.0,
                    "close_vs_sma20": 0.0,
                    "volume_ratio": 1.0,
                }
                river_edge = await river_learner.predict_edge(_river_feats)
        except Exception:
            pass

        signed_scores = {
            "ml": self._score_for_direction(ml_dir, ml_conf),
            "regime": self._score_for_direction(regime_dir, regime_conf),
            "alpha_fusion": alpha_score,
            "sentiment": sent_score,
            "order_flow": of_score,
            "fear_greed": fg_score,
            "funding_rate": fr_score,
        }

        weighted_sum = sum(
            weights[k] * signed_scores[k] for k in _BASE_WEIGHTS
        )

        confidences = {
            "ml": ml_conf,
            "regime": regime_conf,
            "alpha_fusion": abs(alpha_score),
            "sentiment": abs(sent_score),
            "order_flow": abs(of_score),
            "fear_greed": abs(fg_score),
            "funding_rate": abs(fr_score),
        }
        final_confidence = sum(
            weights[k] * confidences[k] for k in _BASE_WEIGHTS
        )

        # Apply river edge as a directional confidence adjustment.
        # When the online learner has enough samples (≥10), it has learned from
        # real closed-trade outcomes.  A river_edge < 0.35 means the model has
        # seen many losses in similar feature conditions — penalise confidence.
        # A river_edge > 0.65 is a mild boost (reward good-signal regimes).
        # Capped at ±0.08 to avoid overwhelming the primary signal weights.
        if river_edge != 0.5:  # Only adjust when we have a real prediction
            _river_adjustment = (river_edge - 0.5) * 0.16  # maps [0,1] → [-0.08, +0.08]
            final_confidence = max(0.0, min(1.0, final_confidence + _river_adjustment))

        final_confidence = round(final_confidence, 4)

        final_direction = _direction_from_score(weighted_sum)

        signals_used = sum(1 for v in availability.values() if v)

        return {
            "direction": final_direction,
            "confidence": final_confidence,
            "predicted_change": round(predicted_change, 4),
            "signals_used": signals_used,
            "river_edge": round(river_edge, 4),
            "hurst": hurst_result,
            "signal_breakdown": {
                "ml": {
                    "direction": ml_dir,
                    "confidence": ml_conf,
                    "weight": round(weights["ml"], 4),
                },
                "regime": {
                    "label": regime_label,
                    "confidence": regime_conf,
                    "weight": round(weights["regime"], 4),
                },
                "alpha_fusion": {
                    "score": round(alpha_score, 4),
                    "direction": alpha_dir,
                    "weight": round(weights["alpha_fusion"], 4),
                    "available": availability["alpha_fusion"],
                },
                "sentiment": {
                    "score": round(sent_score, 4),
                    "direction": sent_dir,
                    "weight": round(weights["sentiment"], 4),
                    "available": availability["sentiment"],
                },
                "order_flow": {
                    "score": round(of_score, 4),
                    "direction": of_dir,
                    "weight": round(weights["order_flow"], 4),
                    "available": availability["order_flow"],
                },
                "fear_greed": {
                    "score": round(fg_score, 4),
                    "raw_value": _fear_greed_cache.get("value", 50),
                    "weight": round(weights["fear_greed"], 4),
                    "available": availability["fear_greed"],
                },
                "funding_rate": {
                    "score": round(fr_score, 4),
                    "weight": round(weights["funding_rate"], 4),
                    "available": availability["funding_rate"],
                },
            },
            "method": method,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Module-level convenience wrapper & singleton
signal_aggregator = SignalAggregator()


async def aggregate_signals(
    symbol: str,
    exchange: str,
    bot_type: str = "normal",
    regime_result: Optional[dict] = None,
) -> dict:
    """Module-level shortcut delegating to the singleton."""
    return await signal_aggregator.aggregate_signals(
        symbol=symbol,
        exchange=exchange,
        bot_type=bot_type,
        regime_result=regime_result,
    )
