"""
ML Price Predictor
- Momentum-based price prediction using CCXT candle data
- Falls back to a clear error payload when market data is unavailable
- NEVER returns random/fabricated direction/confidence
"""

import asyncio
import os
from datetime import datetime, timezone
from logger_config import logger


def _compute_momentum(closes: list) -> tuple:
    """
    Compute price momentum from a list of closing prices.

    Uses a simple short-EMA vs. long-EMA crossover:
      - short window = 5 candles, long window = 20 candles
      - direction: 'up' if short_ema > long_ema, 'down' if short_ema < long_ema, else 'neutral'
      - confidence: scaled by the relative divergence of the two EMAs

    Args:
        closes: List of closing prices (oldest first), requires >= 20 values.

    Returns:
        (direction, confidence, predicted_change_pct)  -- all deterministic from inputs.
    """
    if len(closes) < 20:
        return "neutral", 0.3, 0.0

    def _ema(prices, window):
        k = 2 / (window + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = p * k + ema * (1 - k)
        return ema

    short_ema = _ema(closes[-5:], 5)
    long_ema = _ema(closes[-20:], 20)

    if long_ema == 0:
        return "neutral", 0.3, 0.0

    divergence = (short_ema - long_ema) / long_ema  # e.g. +0.005 = 0.5 % above long EMA

    if divergence > 0.002:
        direction = "up"
    elif divergence < -0.002:
        direction = "down"
    else:
        direction = "neutral"

    # Confidence scaling:
    #   - Base 0.4 ensures we always have a meaningful lower bound.
    #   - Multiplier 50 maps a 1% divergence (0.01) to +0.50 confidence boost.
    #   - Capped at 0.9 to acknowledge that no indicator is 100% reliable.
    confidence = min(0.4 + abs(divergence) * 50, 0.9)
    predicted_change_pct = round(divergence * 100, 4)  # convert to percent

    return direction, round(confidence, 2), predicted_change_pct


class MLPredictor:
    def __init__(self):
        self.model_loaded = False
        self.predictions_cache = {}

    async def predict_price(self, pair: str, timeframe: str = "1h") -> dict:
        """
        Predict future price movement using CCXT momentum analysis.

        Returns a deterministic prediction derived from live candle data.
        If CCXT is unavailable or the pair is unsupported, returns an error payload
        with ``is_simulated=True`` so callers can gate it from live trading decisions.
        """
        # Normalise pair format for CCXT (BTC_USDT -> BTC/USDT)
        ccxt_symbol = pair.replace("_", "/")

        try:
            import ccxt.async_support as ccxt_async

            # Try exchanges in order of preference
            _exchanges_to_try = ["binance", "kucoin", "bybit"]
            _exchange_override = os.getenv("ML_PREDICTOR_EXCHANGE", "")
            if _exchange_override:
                _exchanges_to_try = [_exchange_override] + _exchanges_to_try

            closes = None
            for exchange_name in _exchanges_to_try:
                try:
                    exchange_cls = getattr(ccxt_async, exchange_name, None)
                    if exchange_cls is None:
                        continue
                    exchange = exchange_cls({"enableRateLimit": True})
                    try:
                        ohlcv = await asyncio.wait_for(
                            exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=30),
                            timeout=10,
                        )
                        if ohlcv and len(ohlcv) >= 20:
                            closes = [candle[4] for candle in ohlcv]  # index 4 = close
                            break
                    finally:
                        try:
                            await exchange.close()
                        except Exception:
                            pass
                except Exception as exc:
                    logger.debug(f"ML predictor: {exchange_name} failed for {ccxt_symbol}: {exc}")
                    continue

            if not closes or len(closes) < 20:
                return {
                    "pair": pair,
                    "timeframe": timeframe,
                    "error": f"Insufficient candle data for {ccxt_symbol} (got {len(closes) if closes else 0} candles)",
                    "is_simulated": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            direction, confidence, predicted_change = _compute_momentum(closes)

            prediction = {
                "pair": pair,
                "timeframe": timeframe,
                "direction": direction,
                "confidence": confidence,
                "predicted_change": predicted_change,
                "is_simulated": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.predictions_cache[pair] = prediction
            return prediction

        except Exception as e:
            logger.error(f"Price prediction failed for {pair}: {e}")
            return {
                "pair": pair,
                "timeframe": timeframe,
                "error": str(e),
                "is_simulated": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def analyze_sentiment(self, pair: str) -> dict:
        """Placeholder sentiment analysis – always returns simulated=True."""
        return {
            "pair": pair,
            "sentiment": "neutral",
            "score": 0.0,
            "sources": [],
            "is_simulated": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def detect_anomalies(self, user_id: str) -> dict:
        """Detect anomalous trading patterns using real DB data."""
        try:
            import database as db

            trades = await db.trades_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(100).to_list(100)

            if not trades:
                return {"anomalies": []}

            avg_pnl = sum(t.get('pnl', 0) for t in trades) / len(trades)
            std_dev = (sum((t.get('pnl', 0) - avg_pnl) ** 2 for t in trades) / len(trades)) ** 0.5

            anomalies = []
            for trade in trades:
                pnl = trade.get('pnl', 0)
                z_score = abs((pnl - avg_pnl) / std_dev) if std_dev > 0 else 0
                if z_score > 3:
                    anomalies.append({
                        "trade": trade,
                        "z_score": round(z_score, 2),
                        "type": "extreme_loss" if pnl < 0 else "extreme_win"
                    })

            return {
                "anomalies": anomalies,
                "count": len(anomalies),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return {"error": str(e)}


# Global instance
ml_predictor = MLPredictor()
