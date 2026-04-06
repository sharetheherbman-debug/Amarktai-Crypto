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
River Online Learner — per-user Hoeffding Tree that updates after every trade.

The River library (https://riverml.xyz) supports true online ML: each sample
updates the model in O(1) time so the model continuously adapts to the current
market without waiting for nightly retraining.

Architecture
-----------
* One LogisticRegression + StandardScaler pipeline per user, keyed by user_id.
* record_outcome(user_id, features, net_profit) — called after every trade close.
  Labels: net_profit > 0  → 1 (win), else → 0 (loss).
* predict_edge(user_id, features) → float [0, 1] — probability the next trade wins.
  Returns 0.5 (neutral) if there are fewer than MIN_SAMPLES observations.
* Persists each model to disk under RIVER_MODEL_DIR so it survives server restarts.

All methods are non-fatal: any exception is logged and swallowed so that
an online-learning failure never blocks a trade.
"""
from __future__ import annotations

import logging
import math
import os
import pickle
from pathlib import Path
from typing import Dict, Any, Optional

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
    from river import linear_model, preprocessing, compose, metrics as river_metrics
    _RIVER_AVAILABLE = True
except ImportError:
    _RIVER_AVAILABLE = False
    logger.warning(
        "river library not installed – RiverLearner will use neutral predictions. "
        "Install with: pip install river>=0.21.0"
    )

# Minimum number of labelled samples before we trust the model's prediction.
MIN_SAMPLES: int = 20

# Directory where per-user model files are persisted.
RIVER_MODEL_DIR = Path(
    os.getenv("RIVER_MODEL_DIR", str(Path(__file__).resolve().parent.parent / "models" / "river"))
)


def _make_pipeline():
    """Create a fresh River pipeline: StandardScaler → LogisticRegression."""
    return compose.Pipeline(
        preprocessing.StandardScaler(),
        linear_model.LogisticRegression(),
    )


class _UserModel:
    """Wraps a River pipeline and tracks how many samples it has seen."""

    def __init__(self) -> None:
        self.pipeline = _make_pipeline()
        self.n_samples: int = 0
        self.accuracy = river_metrics.Accuracy() if _RIVER_AVAILABLE else None

    def learn(self, x: Dict[str, float], y: int) -> None:
        pred = self.pipeline.predict_one(x)
        self.pipeline.learn_one(x, y)
        if self.accuracy is not None and pred is not None:
            self.accuracy.update(y, pred)
        self.n_samples += 1

    def predict(self, x: Dict[str, float]) -> float:
        """Return win probability in [0, 1]."""
        if self.n_samples < MIN_SAMPLES:
            return 0.5
        try:
            prob = self.pipeline.predict_proba_one(x)
            return float(prob.get(1, 0.5))
        except Exception:
            return 0.5


class RiverLearner:
    """
    Singleton that manages one online ML model per user.
    Call record_outcome() after every trade, predict_edge() before entry.
    """

    def __init__(self) -> None:
        self._models: Dict[str, _UserModel] = {}
        RIVER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "RiverLearner initialised (river_available=%s, model_dir=%s)",
            _RIVER_AVAILABLE,
            RIVER_MODEL_DIR,
        )

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
    def record_outcome(
        self,
        user_id: str,
        features: Dict[str, float],
        net_profit: float,
    ) -> None:
        """
        Update the per-user model with the result of a closed trade.

        Parameters
        ----------
        user_id     : User whose model should be updated.
        features    : Dict of numeric feature values used at entry
                      (same keys as FEATURE_COLUMNS in ml_predictor.py).
        net_profit  : Realized net profit (after fees).  Positive → win.
        """
        if not _RIVER_AVAILABLE:
            return
        try:
            label = 1 if net_profit > 0 else 0
            clean = _sanitize_features(features)
            model = self._get_or_load(user_id)
            model.learn(clean, label)
            self._maybe_persist(user_id, model)
        except Exception as exc:
            logger.debug("RiverLearner.record_outcome error (%s): %s", user_id, exc)

    def predict_edge(
        self,
        user_id: str,
        features: Dict[str, float],
    ) -> float:
        """
        Return estimated win probability for the next trade.

        Returns 0.5 (neutral) if the model has seen fewer than MIN_SAMPLES trades.
        """
        if not _RIVER_AVAILABLE:
            return 0.5
        try:
            clean = _sanitize_features(features)
            model = self._get_or_load(user_id)
            return model.predict(clean)
        except Exception as exc:
            logger.debug("RiverLearner.predict_edge error (%s): %s", user_id, exc)
            return 0.5

    def sample_count(self, user_id: str) -> int:
        """Return number of labelled samples seen for this user."""
        return self._get_or_load(user_id).n_samples

    def accuracy_score(self, user_id: str) -> Optional[float]:
        """Return rolling accuracy for this user's model, or None if < MIN_SAMPLES."""
        model = self._get_or_load(user_id)
        if model.n_samples < MIN_SAMPLES or model.accuracy is None:
            return None
        try:
            return round(model.accuracy.get(), 4)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_load(self, user_id: str) -> _UserModel:
        if user_id not in self._models:
            loaded = _load_model(user_id)
            self._models[user_id] = loaded if loaded is not None else _UserModel()
        return self._models[user_id]

    def _maybe_persist(self, user_id: str, model: _UserModel) -> None:
        """Persist the model every 10 updates to avoid excessive I/O."""
        if model.n_samples % 10 == 0:
            _save_model(user_id, model)


# -----------------------------------------------------------------------
# Disk persistence helpers
# -----------------------------------------------------------------------

def _model_path(user_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    return RIVER_MODEL_DIR / f"river_{safe}.pkl"


def _save_model(user_id: str, model: _UserModel) -> None:
    try:
        path = _model_path(user_id)
        with open(path, "wb") as fh:
            pickle.dump(model, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        logger.debug("RiverLearner: could not persist model for %s: %s", user_id, exc)


def _load_model(user_id: str) -> Optional[_UserModel]:
    try:
        path = _model_path(user_id)
        if path.exists():
            with open(path, "rb") as fh:
                model = pickle.load(fh)
            logger.info("RiverLearner: loaded model for %s (%d samples)", user_id, model.n_samples)
            return model
    except Exception as exc:
        logger.debug("RiverLearner: could not load model for %s: %s", user_id, exc)
    return None


def _sanitize_features(features: Dict[str, Any]) -> Dict[str, float]:
    """Convert feature dict values to floats, drop NaN/None."""
    out: Dict[str, float] = {}
    for k, v in features.items():
        try:
            fv = float(v)
            if math.isfinite(fv):
                out[k] = fv
        except (TypeError, ValueError):
            pass
    return out


# Module-level singleton — import and use directly.
river_learner = RiverLearner()
