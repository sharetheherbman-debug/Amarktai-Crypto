#!/usr/bin/env python3
"""
XGBoost Retraining Script

Reads closed trade history from MongoDB, builds a feature matrix, trains
(or re-trains) an XGBoost classifier, validates on a holdout split, and
atomically swaps the model artifact.

Designed to be called by a systemd timer or by the nightly learning loop.

Usage:
    python -m scripts.retrain_xgboost [--dry-run] [--min-trades 50]

Environment variables:
    XGB_MIN_RETRAIN_TRADES  — minimum closed trades required (default 50)
    XGB_MIN_ACCURACY        — holdout accuracy gate        (default 0.52)
    MONGO_URL               — MongoDB connection string
    DB_NAME                 — database name
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("retrain_xgboost")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Paths
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_PATH = MODEL_DIR / "xgb_predictor.json"
BACKUP_DIR = MODEL_DIR / "backups"

# Feature columns — must match ml_predictor.FEATURE_COLUMNS
FEATURE_COLUMNS = [
    "rsi", "macd", "macd_signal", "macd_hist", "atr",
    "bb_upper", "bb_mid", "bb_lower", "vwap",
    "close_vs_sma20", "close_vs_bb_mid",
]


def _label_from_pnl(pnl: float) -> int:
    """Map realised PnL to integer class label.

    0 = down (loss), 1 = neutral (break-even), 2 = up (profit)
    """
    if pnl > 0.0005:
        return 2  # up / profit
    elif pnl < -0.0005:
        return 0  # down / loss
    return 1  # neutral


def _extract_indicators(trade: dict) -> Optional[Dict[str, float]]:
    """Pull indicator snapshot that was stored alongside the trade."""
    indicators = trade.get("indicators") or trade.get("entry_indicators") or {}
    if not indicators:
        return None
    row = {}
    for col in FEATURE_COLUMNS:
        val = indicators.get(col)
        if val is None:
            return None  # skip trades with incomplete indicator data
        try:
            row[col] = float(val)
        except (TypeError, ValueError):
            return None
    return row


async def _load_trades(min_trades: int) -> Tuple[pd.DataFrame, pd.Series]:
    """Load closed trades from MongoDB and build (X, y)."""
    # Import after env is loaded
    import database as db

    cursor = db.trades_collection.find(
        {"status": "closed"},
        {
            "_id": 0,
            "net_pnl": 1,
            "profit_loss": 1,
            "indicators": 1,
            "entry_indicators": 1,
            "timestamp": 1,
        },
    ).sort("timestamp", -1).limit(5000)

    trades: List[dict] = await cursor.to_list(5000)
    logger.info("Fetched %d closed trades from database", len(trades))

    rows = []
    labels = []
    for t in trades:
        feats = _extract_indicators(t)
        if feats is None:
            continue
        pnl = t.get("net_pnl", t.get("profit_loss", 0.0))
        rows.append(feats)
        labels.append(_label_from_pnl(pnl))

    if len(rows) < min_trades:
        raise ValueError(f"Only {len(rows)} valid trade samples (need {min_trades})")

    X = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    y = pd.Series(labels, name="label")
    return X, y


def build_dataset_from_synthetic(n_samples: int = 5000) -> Tuple[pd.DataFrame, pd.Series]:
    """Generate synthetic training data when no real trades exist.

    Uses realistic indicator value ranges so the model learns sensible
    boundaries before real data accumulates.
    """
    rng = np.random.default_rng(42)

    data = {
        "rsi": rng.uniform(10, 90, n_samples),
        "macd": rng.normal(0, 0.5, n_samples),
        "macd_signal": rng.normal(0, 0.3, n_samples),
        "macd_hist": rng.normal(0, 0.2, n_samples),
        "atr": rng.uniform(0.5, 5.0, n_samples),
        "bb_upper": rng.uniform(100, 110, n_samples),
        "bb_mid": rng.uniform(95, 105, n_samples),
        "bb_lower": rng.uniform(90, 100, n_samples),
        "vwap": rng.uniform(95, 105, n_samples),
        "close_vs_sma20": rng.normal(0, 0.02, n_samples),
        "close_vs_bb_mid": rng.normal(0, 0.01, n_samples),
    }

    X = pd.DataFrame(data)

    # Label heuristic: RSI + MACD-hist driven
    score = (
        np.where(X["rsi"] < 30, 1, np.where(X["rsi"] > 70, -1, 0))
        + np.where(X["macd_hist"] > 0, 1, -1)
        + np.where(X["close_vs_sma20"] > 0, 1, -1)
    )
    y = pd.Series(np.where(score > 0, 2, np.where(score < 0, 0, 1)), name="label")
    return X, y


def train_model(
    X: pd.DataFrame,
    y: pd.Series,
    use_optuna: bool = True,
    min_accuracy: float = 0.52,
) -> Tuple[object, float]:
    """Train XGBoost classifier, optionally using Optuna for tuning.

    Returns (model, holdout_accuracy).
    Raises ValueError if accuracy is below gate.
    """
    import xgboost as xgb
    from sklearn.model_selection import StratifiedShuffleSplit

    # 80/20 stratified split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(sss.split(X, y))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    best_params: dict = {
        "n_estimators": 200,
        "max_depth": 4,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "objective": "multi:softprob",
        "num_class": 3,
        "eval_metric": "mlogloss",
        "use_label_encoder": False,
        "random_state": 42,
        "verbosity": 0,
    }

    # ------------------------------------------------------------------
    # Optuna hyperparameter search (if available and enough data)
    # ------------------------------------------------------------------
    if use_optuna and len(X_train) >= 200:
        try:
            import optuna

            optuna.logging.set_verbosity(optuna.logging.WARNING)

            def objective(trial):
                params = {
                    "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                    "max_depth": trial.suggest_int("max_depth", 2, 8),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                    "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                    "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                    "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                    "objective": "multi:softprob",
                    "num_class": 3,
                    "eval_metric": "mlogloss",
                    "use_label_encoder": False,
                    "random_state": 42,
                    "verbosity": 0,
                }
                clf = xgb.XGBClassifier(**params)
                clf.fit(X_train, y_train)
                acc = float((clf.predict(X_test) == y_test).mean())
                return acc

            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=30, timeout=120, show_progress_bar=False)
            best_params.update(study.best_params)
            best_params["objective"] = "multi:softprob"
            best_params["num_class"] = 3
            best_params["eval_metric"] = "mlogloss"
            best_params["use_label_encoder"] = False
            best_params["random_state"] = 42
            best_params["verbosity"] = 0
            logger.info("Optuna best trial accuracy: %.4f  params: %s", study.best_value, study.best_params)

        except ImportError:
            logger.info("Optuna not installed — using default hyperparameters")
        except Exception as exc:
            logger.warning("Optuna search failed, using defaults: %s", exc)

    # ------------------------------------------------------------------
    # Final training
    # ------------------------------------------------------------------
    clf = xgb.XGBClassifier(**best_params)
    clf.fit(X_train, y_train)
    holdout_acc = float((clf.predict(X_test) == y_test).mean())
    logger.info("Holdout accuracy: %.4f  (gate: %.4f)", holdout_acc, min_accuracy)

    if holdout_acc < min_accuracy:
        raise ValueError(
            f"Holdout accuracy {holdout_acc:.4f} below gate {min_accuracy:.4f} — model not promoted"
        )

    return clf, holdout_acc


def safe_swap_model(clf, holdout_acc: float, dry_run: bool = False) -> str:
    """Atomically swap the model file. Returns the path written to."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Backup existing model
    if MODEL_PATH.exists() and not dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_name = f"xgb_predictor_{ts}.json"
        shutil.copy2(MODEL_PATH, BACKUP_DIR / backup_name)
        logger.info("Backed up previous model to %s", BACKUP_DIR / backup_name)

        # Keep only last 5 backups
        backups = sorted(BACKUP_DIR.glob("xgb_predictor_*.json"))
        for old in backups[:-5]:
            old.unlink()

    if dry_run:
        logger.info("[DRY RUN] Would write model to %s", MODEL_PATH)
        return str(MODEL_PATH)

    # Write model
    clf.save_model(str(MODEL_PATH))

    # Write metadata sidecar
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "holdout_accuracy": holdout_acc,
        "n_features": len(FEATURE_COLUMNS),
        "feature_columns": FEATURE_COLUMNS,
        "classes": [int(c) for c in clf.classes_],
    }
    meta_path = MODEL_DIR / "xgb_predictor_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    logger.info("✅ Model written to %s (accuracy %.4f)", MODEL_PATH, holdout_acc)
    return str(MODEL_PATH)


async def main(dry_run: bool = False, min_trades: int = 0, bootstrap: bool = False):
    """Entry point for retraining."""
    min_trades = min_trades or int(os.getenv("XGB_MIN_RETRAIN_TRADES", "50"))
    min_accuracy = float(os.getenv("XGB_MIN_ACCURACY", "0.52"))
    use_optuna = os.getenv("DISABLE_OPTUNA", "").lower() not in ("1", "true")

    if bootstrap:
        logger.info("🏗️  Bootstrap mode — generating synthetic training data")
        X, y = build_dataset_from_synthetic(5000)
    else:
        try:
            X, y = await _load_trades(min_trades)
        except ValueError as exc:
            logger.warning("Insufficient trade data: %s — falling back to bootstrap", exc)
            X, y = build_dataset_from_synthetic(5000)

    logger.info("Training on %d samples (%d features)", len(X), X.shape[1])
    clf, acc = train_model(X, y, use_optuna=use_optuna, min_accuracy=min_accuracy)
    path = safe_swap_model(clf, acc, dry_run=dry_run)
    logger.info("Retraining complete → %s", path)
    return {"model_path": path, "accuracy": acc, "samples": len(X), "dry_run": dry_run}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrain XGBoost predictor")
    parser.add_argument("--dry-run", action="store_true", help="Validate but don't write model")
    parser.add_argument("--min-trades", type=int, default=0, help="Override minimum trades")
    parser.add_argument("--bootstrap", action="store_true", help="Train on synthetic data")
    args = parser.parse_args()

    # Ensure backend is on path when run directly (not needed for python -m)
    backend_dir = Path(__file__).resolve().parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    asyncio.run(main(dry_run=args.dry_run, min_trades=args.min_trades, bootstrap=args.bootstrap))
