"""
Signal Aggregator: Unified entry point for all signal sources.
Combines ML prediction, technical indicators, alpha fusion, order flow,
whale monitoring, and sentiment into a single composite signal.
"""

from datetime import datetime, timezone
from typing import Optional

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
# Weights
# -----------------------------------------------------------------------
_BASE_WEIGHTS = {
    "ml": 0.30,
    "regime": 0.25,
    "alpha_fusion": 0.20,
    "sentiment": 0.15,
    "order_flow": 0.10,
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
        }

        # -- 1. ML prediction (always) ----------------------------------
        ml_pred = await self._ml.predict_price(symbol)
        ml_dir = ml_pred.get("direction", "neutral")
        ml_conf = float(ml_pred.get("confidence", 0.0))
        predicted_change = float(ml_pred.get("predicted_change", 0.0))
        raw_method = ml_pred.get("method", "fallback")
        # Map predictor methods: "xgboost" → trained model path,
        # "rule_based" / "fallback" → heuristic path.
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
                coin = coin or symbol  # guard against empty result
                agg = await self._sentiment.analyze_coin_sentiment(coin)
                if agg is not None:
                    sent_score = float(agg.score)
                    sent_dir = _direction_from_score(sent_score)
                    availability["sentiment"] = True
            except Exception:
                logger.debug("Sentiment failed for %s", symbol, exc_info=True)

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
            except Exception:
                logger.debug("Order flow failed for %s", symbol, exc_info=True)

        # -- 6. Redistribute weights & compute composite -----------------
        weights = _redistribute_weights(availability)

        regime_dir = "neutral"
        if regime_label in ("trending_up", "breakout"):
            regime_dir = "up"
        elif regime_label in ("trending_down",):
            regime_dir = "down"

        signed_scores = {
            "ml": self._score_for_direction(ml_dir, ml_conf),
            "regime": self._score_for_direction(regime_dir, regime_conf),
            "alpha_fusion": alpha_score,
            "sentiment": sent_score,
            "order_flow": of_score,
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
        }
        final_confidence = sum(
            weights[k] * confidences[k] for k in _BASE_WEIGHTS
        )
        final_confidence = round(min(max(final_confidence, 0.0), 1.0), 4)

        final_direction = _direction_from_score(weighted_sum)

        signals_used = sum(1 for v in availability.values() if v)

        return {
            "direction": final_direction,
            "confidence": final_confidence,
            "predicted_change": round(predicted_change, 4),
            "signals_used": signals_used,
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
