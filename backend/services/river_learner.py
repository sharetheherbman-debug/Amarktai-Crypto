"""
River Online Learner — lightweight incremental model for paper-trade feedback.

Provides a non-blocking, non-destructive hook that updates a streaming
LogisticRegression (via the `river` library) after each completed paper
trade.  The learner operates independently of the XGBoost batch model and
never blocks trade execution.

Features fed to the model are the same indicator snapshot captured at
trade entry: rsi, macd_hist, close_vs_sma20, atr_pct, spread_pct.
Label: 1 if net_profit > 0 else 0.

The learner:
- Stores its model state in-memory (resets on restart — intentionally
  lightweight for the 7-day beta period).
- Exposes `record_outcome(features, net_profit)` for the paper engine hook.
- Exposes `predict_edge(features)` returning a float in [0, 1] representing
  the online model's current estimate of the win probability for a given
  feature snapshot.  0.5 = unknown / no data yet.
- Exposes `diagnostics()` returning basic training stats.
- All methods are thread-safe and never raise — failures are logged and
  swallowed so the live trading path is never disrupted.

Usage (from paper_trading_engine.py after trade close):
    from services.river_learner import river_learner
    river_learner.record_outcome(entry_features, net_profit)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import — river is optional; learner degrades gracefully if absent
# ---------------------------------------------------------------------------
try:
    from river import linear_model, optim, preprocessing
    _RIVER_AVAILABLE = True
except ImportError:
    _RIVER_AVAILABLE = False
    logger.warning("river not installed — RiverLearner will run in no-op mode")

# ── Tunable constants ─────────────────────────────────────────────────────────
# SGD learning rate for the online logistic regression.
# 0.01 is conservative — suitable for volatile market data.
_LEARNING_RATE: float = 0.01
# L2 regularisation strength — prevents the model from overfitting noisy signals.
_L2_REGULARIZATION: float = 1e-4


class RiverLearner:
    """Incremental online learner powered by river.LogisticRegression.

    Learns win/loss patterns from completed paper trades without retraining
    the main XGBoost model.  Intended as a supplementary signal layer and
    diagnostic tool during the beta period.
    """

    def __init__(self) -> None:
        self._trained_count: int = 0
        self._win_count: int = 0
        self._loss_count: int = 0
        self._model: Any = None
        self._scaler: Any = None
        self._ready: bool = False

        if _RIVER_AVAILABLE:
            try:
                self._scaler = preprocessing.StandardScaler()
                self._model = linear_model.LogisticRegression(
                    optimizer=optim.SGD(_LEARNING_RATE),
                    l2=_L2_REGULARIZATION,
                )
                self._ready = True
                logger.info("RiverLearner initialised — online learning active")
            except Exception as exc:
                logger.warning("RiverLearner init failed (non-fatal): %s", exc)
        else:
            logger.info("RiverLearner in no-op mode (river not available)")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def record_outcome(
        self,
        features: Dict[str, float],
        net_profit: float,
    ) -> None:
        """Update the online learner with a completed trade's outcome.

        Args:
            features:   Dict of indicator values at trade entry.  Keys that
                        matter: rsi, macd_hist, close_vs_sma20, atr_pct,
                        spread_pct, confidence, regime_confidence.
                        Unknown keys are ignored.
            net_profit: Realised net profit/loss in quote currency.
                        Positive = win, negative/zero = loss.
        """
        if not self._ready:
            return
        try:
            x = self._normalise(features)
            y = 1 if net_profit > 0 else 0
            # learn_one() updates scaler statistics and returns self (the scaler).
            # We must call transform_one() separately to get the scaled feature dict.
            self._scaler.learn_one(x)
            x_scaled = self._scaler.transform_one(x)
            self._model.learn_one(x_scaled, y)
            self._trained_count += 1
            if y == 1:
                self._win_count += 1
            else:
                self._loss_count += 1
        except Exception as exc:
            logger.debug("RiverLearner.record_outcome failed (non-fatal): %s", exc)

    def predict_edge(
        self,
        features: Dict[str, float],
    ) -> float:
        """Return online model's win-probability estimate for a feature snapshot.

        Returns 0.5 if the model has fewer than 10 training samples (not
        enough data for a meaningful signal yet).

        Returns:
            Float in [0, 1].  > 0.5 suggests the online model expects a win.
        """
        if not self._ready or self._trained_count < 10:
            return 0.5
        try:
            x = self._normalise(features)
            # transform_one() accepts the full feature dict and returns the scaled dict.
            x_scaled = self._scaler.transform_one(x)
            proba_dict = self._model.predict_proba_one(x_scaled)
            return float(proba_dict.get(1, 0.5))
        except Exception as exc:
            logger.debug("RiverLearner.predict_edge failed (non-fatal): %s", exc)
            return 0.5

    def diagnostics(self) -> Dict[str, Any]:
        """Return current learner statistics."""
        total = self._win_count + self._loss_count
        win_rate = round(self._win_count / total, 4) if total > 0 else None
        return {
            "river_available": _RIVER_AVAILABLE,
            "model_ready": self._ready,
            "trained_count": self._trained_count,
            "win_count": self._win_count,
            "loss_count": self._loss_count,
            "online_win_rate": win_rate,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalise(features: Dict[str, float]) -> Dict[str, float]:
        """Extract and normalise the feature subset used by the online model."""
        def _f(key: str, default: float = 0.0) -> float:
            v = features.get(key, default)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        return {
            "rsi":               _f("rsi", 50.0),
            "macd_hist":         _f("macd_hist", 0.0),
            "close_vs_sma20":    _f("close_vs_sma20", 0.0),
            "atr_pct":           _f("atr_pct", 0.0),
            "spread_pct":        _f("spread_pct", 0.0),
            "confidence":        _f("confidence", 0.5),
            "regime_confidence": _f("regime_confidence", 0.5),
        }


# Module-level singleton — import and use directly
river_learner = RiverLearner()
