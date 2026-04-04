"""
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
import os
import pickle
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
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

    def accuracy_score(self, user_id: str) -> float | None:
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


def _load_model(user_id: str) -> _UserModel | None:
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
    import math
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
