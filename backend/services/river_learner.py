"""
River Online Learner — real-time incremental learning using river.

Maintains a per-user online model that updates on every closed trade.
Provides edge predictions for the trading brain signal aggregator.

Architecture:
- StandardScaler + LogisticRegression pipeline
- Features: rsi, macd_hist, atr_pct, close_vs_sma20, volume_ratio
- Target: binary win/loss (net_pnl > 0)
- Thread-safe via asyncio lock
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

try:
    from river import compose, linear_model, preprocessing, metrics as river_metrics
    HAS_RIVER = True
except ImportError:
    HAS_RIVER = False
    logger.warning("river not installed — online learning disabled")

# Feature names expected from the trading engine
RIVER_FEATURES = [
    "rsi", "macd_hist", "atr_pct", "close_vs_sma20", "volume_ratio"
]


class RiverLearner:
    """Singleton online learner backed by river."""

    def __init__(self):
        self.active = HAS_RIVER and os.getenv("ENABLE_RIVER_LEARNING", "true").lower() == "true"
        self._lock = asyncio.Lock()
        self._model = None
        self._scaler = None
        self._metric = None
        self._samples_seen = 0
        self._last_update: Optional[str] = None

        if self.active:
            self._build_pipeline()
            logger.info("🌊 River online learner initialised")
        else:
            logger.info("🌊 River online learner disabled (ENABLE_RIVER_LEARNING or river missing)")

    def _build_pipeline(self):
        """Construct a fresh river pipeline."""
        self._scaler = preprocessing.StandardScaler()
        self._model = compose.Pipeline(
            self._scaler,
            linear_model.LogisticRegression()  # uses default SGD optimizer
        )
        self._metric = river_metrics.Accuracy()
        self._samples_seen = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_outcome(self, features: Dict[str, float], net_profit: float) -> None:
        """Learn from a single closed trade.

        Args:
            features: dict with keys from RIVER_FEATURES
            net_profit: realised PnL of the trade (positive = win)
        """
        if not self.active or self._model is None:
            return

        x = self._sanitise(features)
        if x is None:
            return

        y = 1 if net_profit > 0 else 0

        async with self._lock:
            # Update metric with current prediction before learning
            try:
                y_pred = self._model.predict_one(x)
                if y_pred is not None:
                    self._metric.update(y, y_pred)
            except Exception:
                pass

            # Learn from observation
            try:
                self._model.learn_one(x, y)
                self._samples_seen += 1
                self._last_update = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                logger.debug("River learn_one error: %s", exc)

    async def predict_edge(self, features: Dict[str, float]) -> float:
        """Predict probability of a winning trade.

        Returns a float in [0, 1] where >0.5 suggests a likely winner.
        Falls back to 0.5 (neutral) on any error.
        """
        if not self.active or self._model is None or self._samples_seen < 10:
            return 0.5

        x = self._sanitise(features)
        if x is None:
            return 0.5

        async with self._lock:
            try:
                proba = self._model.predict_proba_one(x)
                if proba and 1 in proba:
                    return float(proba[1])
                return 0.5
            except Exception:
                return 0.5

    def get_diagnostics(self) -> dict:
        """Return current learner diagnostics."""
        return {
            "river_active": self.active,
            "river_installed": HAS_RIVER,
            "samples_seen": self._samples_seen,
            "accuracy": round(float(self._metric.get()), 4) if self._metric and self._samples_seen > 0 else None,
            "last_update": self._last_update,
            "min_samples_for_prediction": 10,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise(features: Dict[str, float]) -> Optional[Dict[str, float]]:
        """Pick only expected features and drop NaN/None."""
        if not features:
            return None
        x = {}
        for key in RIVER_FEATURES:
            val = features.get(key)
            if val is None:
                val = 0.0
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            # Replace NaN
            if val != val:  # NaN check
                val = 0.0
            x[key] = val
        return x


# Module-level singleton
river_learner = RiverLearner()
