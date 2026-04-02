"""
ML Price Predictor
- XGBoost-based price prediction with rule-based fallback
- Keyword-based sentiment analysis
- Anomaly detection
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from logger_config import logger

# Graceful optional imports
try:
    import ccxt
    HAS_CCXT = True
except ImportError:
    HAS_CCXT = False
    logger.warning("ccxt not available – fetch_ohlcv will be disabled")

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    logger.warning("pandas-ta not available – indicators will use manual fallback")

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    logger.warning("xgboost not available – model predictions will use rule-based fallback")

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "xgb_predictor.json"

BULLISH_KEYWORDS = [
    "bull", "buy", "long", "moon", "pump", "rally", "breakout",
    "upgrade", "adoption", "partnership", "launch", "surge", "gain",
    "accumulate", "support", "bullish", "uptrend", "recovery",
]

BEARISH_KEYWORDS = [
    "bear", "sell", "short", "dump", "crash", "drop", "hack",
    "ban", "regulation", "lawsuit", "scam", "fraud", "rug",
    "liquidation", "resistance", "bearish", "downtrend", "decline",
]

# XGBoost feature order – must match training pipeline
FEATURE_COLUMNS = ["rsi", "macd", "macd_signal", "macd_hist", "atr",
                   "bb_upper", "bb_mid", "bb_lower", "vwap",
                   "close_vs_sma20", "close_vs_bb_mid"]


def fetch_ohlcv(
    pair: str,
    timeframe: str = "1h",
    limit: int = 100,
    exchange_id: str = "binance",
) -> pd.DataFrame:
    """Fetch OHLCV candle data from a CCXT exchange.

    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    if not HAS_CCXT:
        raise RuntimeError("ccxt is not installed")

    exchange_cls = getattr(ccxt, exchange_id, None)
    if exchange_cls is None:
        raise ValueError(f"Unknown exchange: {exchange_id}")

    exchange = exchange_cls({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators on an OHLCV DataFrame.

    Adds: RSI(14), MACD(12,26,9), ATR(14), Bollinger Bands(20,2),
    VWAP, SMA(20), and derived features.
    """
    if len(df) < 26:
        raise ValueError("Need at least 26 candles to compute indicators")

    out = df.copy()

    if HAS_PANDAS_TA:
        # VWAP and some indicators require a DatetimeIndex
        if "timestamp" in out.columns:
            out = out.set_index("timestamp")

        out.ta.rsi(length=14, append=True, col_names=["rsi"])
        macd = out.ta.macd(fast=12, slow=26, signal=9, append=False)
        out["macd"] = macd.iloc[:, 0]
        out["macd_signal"] = macd.iloc[:, 1]
        out["macd_hist"] = macd.iloc[:, 2]
        out.ta.atr(length=14, append=True, col_names=["atr"])
        bbands = out.ta.bbands(length=20, std=2, append=False)
        out["bb_lower"] = bbands.iloc[:, 0]
        out["bb_mid"] = bbands.iloc[:, 1]
        out["bb_upper"] = bbands.iloc[:, 2]
        out.ta.vwap(append=True, col_names=["vwap"])
        out.ta.sma(length=20, append=True, col_names=["sma20"])

        out = out.reset_index()
    else:
        # Manual fallback (simplified)
        delta = out["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        out["rsi"] = 100 - (100 / (1 + rs))

        ema12 = out["close"].ewm(span=12, adjust=False).mean()
        ema26 = out["close"].ewm(span=26, adjust=False).mean()
        out["macd"] = ema12 - ema26
        out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
        out["macd_hist"] = out["macd"] - out["macd_signal"]

        tr = pd.concat([
            out["high"] - out["low"],
            (out["high"] - out["close"].shift()).abs(),
            (out["low"] - out["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        out["atr"] = tr.rolling(14).mean()

        out["sma20"] = out["close"].rolling(20).mean()
        std20 = out["close"].rolling(20).std()
        out["bb_mid"] = out["sma20"]
        out["bb_upper"] = out["sma20"] + 2 * std20
        out["bb_lower"] = out["sma20"] - 2 * std20

        typical = (out["high"] + out["low"] + out["close"]) / 3
        cum_tp_vol = (typical * out["volume"]).cumsum()
        cum_vol = out["volume"].cumsum()
        out["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)

    out["close_vs_sma20"] = out["close"] / out["sma20"].replace(0, np.nan) - 1
    out["close_vs_bb_mid"] = out["close"] / out["bb_mid"].replace(0, np.nan) - 1

    return out


def _rule_based_prediction(indicators: pd.Series) -> tuple[str, float, float]:
    """Deterministic rule-based prediction from a single row of indicators.

    Returns (direction, confidence, predicted_change_pct).
    """
    signals: list[int] = []  # +1 bullish, -1 bearish, 0 neutral
    weights: list[float] = []

    # RSI signal (weight 0.35)
    rsi = indicators.get("rsi", 50.0)
    if pd.isna(rsi):
        rsi = 50.0
    if rsi < 30:
        signals.append(1)
    elif rsi > 70:
        signals.append(-1)
    else:
        signals.append(0)
    weights.append(0.35)

    # MACD signal (weight 0.35)
    macd_hist = indicators.get("macd_hist", 0.0)
    if pd.isna(macd_hist):
        macd_hist = 0.0
    if macd_hist > 0:
        signals.append(1)
    elif macd_hist < 0:
        signals.append(-1)
    else:
        signals.append(0)
    weights.append(0.35)

    # Trend alignment – close vs SMA20 (weight 0.30)
    close_vs_sma = indicators.get("close_vs_sma20", 0.0)
    if pd.isna(close_vs_sma):
        close_vs_sma = 0.0
    if close_vs_sma > 0:
        signals.append(1)
    elif close_vs_sma < 0:
        signals.append(-1)
    else:
        signals.append(0)
    weights.append(0.30)

    # Weighted vote
    weighted_sum = sum(s * w for s, w in zip(signals, weights))
    total_weight = sum(weights)

    # Direction from majority vote
    bullish_count = signals.count(1)
    bearish_count = signals.count(-1)

    if bullish_count > bearish_count:
        direction = "up"
    elif bearish_count > bullish_count:
        direction = "down"
    else:
        direction = "neutral"

    # Confidence: how strongly signals agree (0–1)
    agreement = abs(weighted_sum) / total_weight if total_weight > 0 else 0.0
    confidence = 0.5 + 0.5 * agreement  # maps [0,1] → [0.5,1.0]
    confidence = round(min(max(confidence, 0.0), 1.0), 4)

    # Predicted change: scale agreement by ATR-relative magnitude
    atr = indicators.get("atr", 0.0)
    close = indicators.get("close", 1.0)
    if pd.isna(atr) or pd.isna(close) or close == 0:
        pct_change = round(weighted_sum * 0.5, 4)
    else:
        atr_pct = (atr / close) * 100
        pct_change = round(weighted_sum * atr_pct, 4)

    return direction, confidence, pct_change


# Mapping from XGBoost integer class labels (used in >= 2.0) to direction strings.
# XGBoost >= 2.0 requires integer labels during training and stores classes_ as
# [0, 1, 2] rather than ['down', 'neutral', 'up'].
_INT_TO_DIR: dict[int, str] = {0: "down", 1: "neutral", 2: "up"}
# Direction → signed float for predicted-change calculation
_DIR_SIGN: dict[str, float] = {"up": 1.0, "down": -1.0, "neutral": 0.0}


def _class_to_direction(cls) -> str:
    """Normalise an XGBoost class label (int or string) to a direction string."""
    if isinstance(cls, str):
        return cls
    # numpy integer subtypes (np.int64 etc.) or plain Python int/float
    try:
        return _INT_TO_DIR.get(int(cls), "neutral")
    except (TypeError, ValueError):
        return str(cls)



    def __init__(self):
        self.model_loaded = False
        self.model = None
        self.predictions_cache: dict = {}
        self._load_model()

    def _load_model(self) -> None:
        """Try to load a persisted XGBoost model."""
        if not HAS_XGB:
            return
        if MODEL_PATH.exists():
            try:
                self.model = xgb.XGBClassifier()
                self.model.load_model(str(MODEL_PATH))
                self.model_loaded = True
                logger.info("XGBoost model loaded from %s", MODEL_PATH)
            except Exception as exc:
                logger.error("Failed to load XGBoost model: %s", exc)
                self.model = None
                self.model_loaded = False

    def _predict_with_model(self, features: np.ndarray) -> tuple[str, float, float]:
        """Run XGBoost inference.  Returns (direction, confidence, predicted_change).

        Handles both string-class models (classes_ = ['down','neutral','up'])
        and integer-class models produced by XGBoost >= 2.0 (classes_ = [0, 1, 2]).
        The canonical mapping for integer classes is: 0→down, 1→neutral, 2→up.
        """
        proba = self.model.predict_proba(features)
        classes = list(self.model.classes_)
        pred_idx = int(np.argmax(proba[0]))

        direction = _class_to_direction(classes[pred_idx])
        confidence = round(float(proba[0][pred_idx]), 4)

        # Predicted change: probability-weighted signed sum of all classes.
        predicted_change = sum(
            _DIR_SIGN.get(_class_to_direction(c), 0.0) * float(proba[0][i])
            for i, c in enumerate(classes)
        )
        return direction, confidence, round(predicted_change, 4)

    async def predict_price(self, pair: str, timeframe: str = "1h") -> dict:
        """Predict future price movement using XGBoost or rule-based fallback."""
        try:
            df = await asyncio.get_event_loop().run_in_executor(
                None, fetch_ohlcv, pair, timeframe, 100, "binance"
            )
            df = compute_indicators(df)
            valid = df.dropna(subset=["rsi", "macd"])
            if valid.empty:
                raise ValueError("Not enough data to compute indicators")
            latest = valid.iloc[-1]

            if self.model_loaded and self.model is not None:
                feature_values = np.array(
                    [[float(v) if pd.notna(v := latest.get(c)) else 0.0
                      for c in FEATURE_COLUMNS]]
                )
                direction, confidence, predicted_change = self._predict_with_model(
                    feature_values
                )
                method = "xgboost"
            else:
                direction, confidence, predicted_change = _rule_based_prediction(latest)
                method = "rule_based"

            prediction = {
                "pair": pair,
                "timeframe": timeframe,
                "direction": direction,
                "confidence": round(confidence, 2),
                "predicted_change": round(predicted_change, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": method,
            }
            self.predictions_cache[pair] = prediction
            return prediction

        except Exception as e:
            logger.error("Price prediction failed: %s", e)
            # Fallback: return neutral with zero confidence when data unavailable
            return {
                "pair": pair,
                "timeframe": timeframe,
                "direction": "neutral",
                "confidence": 0.0,
                "predicted_change": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": "fallback",
            }

    async def analyze_sentiment(self, pair: str) -> dict:
        """Analyze market sentiment using keyword-based scoring."""
        try:
            text = pair.lower().replace("/", " ").replace("-", " ")
            # Expand common ticker symbols to full names for richer matching
            ticker_expansions = {
                "btc": "bitcoin",
                "eth": "ethereum",
                "sol": "solana",
                "xrp": "ripple",
                "ada": "cardano",
                "doge": "dogecoin",
                "bnb": "binance",
                "dot": "polkadot",
                "avax": "avalanche",
                "matic": "polygon",
                "link": "chainlink",
            }
            tokens = text.split()
            for tok in tokens:
                if tok in ticker_expansions:
                    text += " " + ticker_expansions[tok]

            bullish_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
            bearish_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)

            total = bullish_hits + bearish_hits
            if total > 0:
                sentiment_score = round((bullish_hits - bearish_hits) / total, 2)
            else:
                sentiment_score = 0.0

            if sentiment_score > 0.3:
                sentiment = "bullish"
            elif sentiment_score < -0.3:
                sentiment = "bearish"
            else:
                sentiment = "neutral"

            return {
                "pair": pair,
                "sentiment": sentiment,
                "score": sentiment_score,
                "sources": ["keyword_analysis"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("Sentiment analysis failed: %s", e)
            return {"error": str(e)}

    async def detect_anomalies(self, user_id: str) -> dict:
        """Detect anomalous trading patterns"""
        try:
            import database as db

            # Get recent trades
            trades = await db.trades_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(100).to_list(100)

            if not trades:
                return {"anomalies": []}

            # Simple anomaly detection
            anomalies = []
            avg_pnl = sum(t.get('pnl', 0) for t in trades) / len(trades)
            std_dev = (sum((t.get('pnl', 0) - avg_pnl) ** 2 for t in trades) / len(trades)) ** 0.5

            for trade in trades:
                pnl = trade.get('pnl', 0)
                z_score = abs((pnl - avg_pnl) / std_dev) if std_dev > 0 else 0

                if z_score > 3:  # 3 standard deviations
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
