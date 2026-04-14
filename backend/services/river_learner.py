"""
River Online Learner — real-time incremental learning using river.

Maintains a per-user online model that updates on every closed trade.
Provides edge predictions for the trading brain signal aggregator.

Architecture:
- StandardScaler + LogisticRegression pipeline
- Features: rsi, macd_hist, atr_pct, close_vs_sma20, volume_ratio
- Target: binary win/loss (net_pnl > 0)
- Thread-safe via asyncio lock

Callers must use the module-level singleton:
    from services.river_learner import river_learner

    # Record outcome after a closed trade (async path in close_trade)
    await river_learner.record_outcome(features, net_profit)

    # Record outcome from a sync trading cycle path (kwargs form also accepted)
    river_learner.record_outcome_sync(user_id=uid, features=feats, net_profit=pnl)

    # Predict win probability before entry
    edge = await river_learner.predict_edge(features)
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Optional river import
# -----------------------------------------------------------------------
try:
    from river import compose, linear_model, preprocessing, metrics as river_metrics
    _RIVER_AVAILABLE = True
except ImportError:
    _RIVER_AVAILABLE = False
    logger.warning("river not installed — online learning disabled")

# Feature names expected from the trading engine
RIVER_FEATURES = ["rsi", "macd_hist", "atr_pct", "close_vs_sma20", "volume_ratio"]

# Minimum labelled samples before predict_edge returns non-neutral values
MIN_SAMPLES = 10

# Where to persist models
RIVER_MODEL_DIR = Path(os.getenv("RIVER_MODEL_DIR", "/tmp/river_models"))


# -----------------------------------------------------------------------
# Per-user model container
# -----------------------------------------------------------------------

class _UserModel:
    """Wraps a river pipeline and tracks metadata for one user."""

    def __init__(self) -> None:
        if _RIVER_AVAILABLE:
            self.pipeline = (
                preprocessing.StandardScaler()
                | linear_model.LogisticRegression()
            )
            self.accuracy = river_metrics.Accuracy()
        else:
            self.pipeline = None
            self.accuracy = None
        self.n_samples: int = 0
        self.last_update: Optional[str] = None

    def learn(self, features: Dict[str, float], label: int) -> None:
        if self.pipeline is None:
            return
        try:
            if self.accuracy is not None:
                y_pred = self.pipeline.predict_one(features)
                if y_pred is not None:
                    self.accuracy.update(label, y_pred)
            self.pipeline.learn_one(features, label)
            self.n_samples += 1
            self.last_update = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            logger.debug("_UserModel.learn error: %s", exc)

    def predict(self, features: Dict[str, float]) -> float:
        if self.pipeline is None or self.n_samples < MIN_SAMPLES:
            return 0.5
        try:
            proba = self.pipeline.predict_proba_one(features)
            if proba and 1 in proba:
                return float(proba[1])
        except Exception as exc:
            logger.debug("_UserModel.predict error: %s", exc)
        return 0.5


# -----------------------------------------------------------------------
# Disk persistence helpers
# -----------------------------------------------------------------------

def _model_path(user_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(user_id))
    return RIVER_MODEL_DIR / f"river_{safe}.pkl"


def _save_model(user_id: str, model: _UserModel) -> None:
    try:
        path = _model_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
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
            logger.info(
                "RiverLearner: loaded model for %s (%d samples)", user_id, model.n_samples
            )
            return model
    except Exception as exc:
        logger.debug("RiverLearner: could not load model for %s: %s", user_id, exc)
    return None


def _sanitize_features(features: Dict[str, Any]) -> Dict[str, float]:
    """Keep only RIVER_FEATURES keys; convert to float; drop NaN/None."""
    out: Dict[str, float] = {}
    for key in RIVER_FEATURES:
        val = features.get(key)
        if val is None:
            out[key] = 0.0
            continue
        try:
            fv = float(val)
            out[key] = fv if math.isfinite(fv) else 0.0
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


# -----------------------------------------------------------------------
# RiverLearner — module-level singleton, one model per user
# -----------------------------------------------------------------------

class RiverLearner:
    """
    Thread-safe online learner.  One river pipeline per user_id.

    Attributes exposed for signal_aggregator compatibility:
        active           : True when river is installed
        _samples_seen    : Total labelled samples across all users (approximation)
    """

    def __init__(self) -> None:
        self._models: Dict[str, _UserModel] = {}
        self._lock = asyncio.Lock()
        RIVER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "RiverLearner initialised (river_available=%s, model_dir=%s)",
            _RIVER_AVAILABLE,
            RIVER_MODEL_DIR,
        )

    # ------------------------------------------------------------------
    # Attributes expected by signal_aggregator
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return _RIVER_AVAILABLE

    @property
    def _samples_seen(self) -> int:
        """Approximate total samples across all user models."""
        return sum(m.n_samples for m in self._models.values())

    # ------------------------------------------------------------------
    # Primary async API  (used by paper_trading_engine.close_trade)
    # ------------------------------------------------------------------

    async def record_outcome(
        self,
        features: Dict[str, float],
        net_profit: float,
        user_id: str = "default",
    ) -> None:
        """Learn from a single closed trade (async, non-blocking).

        Parameters
        ----------
        features   : feature dict — keys from RIVER_FEATURES
        net_profit : realised PnL after fees (positive = win)
        user_id    : optional user identifier (default "default")
        """
        if not _RIVER_AVAILABLE:
            return
        try:
            clean = _sanitize_features(features)
            label = 1 if net_profit > 0 else 0
            async with self._lock:
                model = self._get_or_load(user_id)
                model.learn(clean, label)
                self._maybe_persist(user_id, model)
        except Exception as exc:
            logger.debug("RiverLearner.record_outcome error: %s", exc)

    async def predict_edge(self, features: Dict[str, float], user_id: str = "default") -> float:
        """Predict probability of a winning trade (async).

        Returns float in [0, 1]; 0.5 = neutral (< MIN_SAMPLES or any error).
        """
        if not _RIVER_AVAILABLE:
            return 0.5
        try:
            model = self._get_or_load(user_id)
            if model.n_samples < MIN_SAMPLES:
                return 0.5
            clean = _sanitize_features(features)
            async with self._lock:
                return model.predict(clean)
        except Exception as exc:
            logger.debug("RiverLearner.predict_edge error: %s", exc)
            return 0.5

    # ------------------------------------------------------------------
    # Sync API  (used by run_trading_cycle which is not async at that call site)
    # ------------------------------------------------------------------

    def record_outcome_sync(
        self,
        user_id: str,
        features: Dict[str, float],
        net_profit: float,
    ) -> None:
        """Sync version of record_outcome for non-async call sites."""
        if not _RIVER_AVAILABLE:
            return
        try:
            clean = _sanitize_features(features)
            label = 1 if net_profit > 0 else 0
            model = self._get_or_load(user_id)
            model.learn(clean, label)
            self._maybe_persist(user_id, model)
        except Exception as exc:
            logger.debug("RiverLearner.record_outcome_sync error (%s): %s", user_id, exc)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> dict:
        users = list(self._models.keys())
        per_user = {
            uid: {"n_samples": m.n_samples, "last_update": m.last_update}
            for uid, m in self._models.items()
        }
        return {
            "river_active": self.active,
            "river_installed": _RIVER_AVAILABLE,
            "total_samples": self._samples_seen,
            "user_count": len(users),
            "per_user": per_user,
            "min_samples_for_prediction": MIN_SAMPLES,
        }

    def sample_count(self, user_id: str) -> int:
        return self._get_or_load(user_id).n_samples

    def accuracy_score(self, user_id: str) -> Optional[float]:
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
        """Persist every 10 updates to limit I/O."""
        if model.n_samples > 0 and model.n_samples % 10 == 0:
            _save_model(user_id, model)


# Module-level singleton — import and use directly.
river_learner = RiverLearner()
