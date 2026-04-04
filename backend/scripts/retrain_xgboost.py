#!/usr/bin/env python3
"""
XGBoost Retrain Script with Optuna Hyperparameter Tuning.

Reads closed trades from MongoDB, builds an OHLCV-based feature dataset,
trains a fresh XGBoost classifier with Optuna-optimised hyperparameters,
validates it, and atomically replaces the production model file.

Usage
-----
    python3 retrain_xgboost.py [--dry-run] [--min-trades N] [--trials N]

Environment variables
---------------------
    MONGODB_URI               MongoDB connection string (required)
    XGB_MIN_RETRAIN_TRADES    Minimum closed trades required (default 50)
    XGB_OPTUNA_TRIALS         Number of Optuna search trials (default 30)
    ENABLE_LEARNING_LOOP      Must be "true" to allow retraining (default false)
    XGB_MODEL_PATH            Override model output path
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("retrain_xgboost")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(os.getenv("XGB_MODEL_PATH", str(BACKEND_DIR / "models" / "xgb_predictor.json")))
BACKUP_PATH = MODEL_PATH.with_suffix(".backup.json")
MIN_RETRAIN_TRADES = int(os.getenv("XGB_MIN_RETRAIN_TRADES", "50"))
OPTUNA_TRIALS = int(os.getenv("XGB_OPTUNA_TRIALS", "30"))
TEST_SPLIT = 0.20
MIN_ACCURACY = 0.52

FEATURE_COLUMNS = [
    "rsi", "macd", "macd_signal", "macd_hist", "atr",
    "bb_upper", "bb_mid", "bb_lower", "vwap", "close_vs_sma20", "close_vs_bb_mid",
]

# ---------------------------------------------------------------------------
# Imports (bail early with clear messages if deps unavailable)
# ---------------------------------------------------------------------------
try:
    import xgboost as xgb
except ImportError:
    logger.error("xgboost is not installed. Run: pip install xgboost>=2.0.0")
    sys.exit(1)

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    logger.error("optuna is not installed. Run: pip install optuna>=3.6.0")
    sys.exit(1)

try:
    from sklearn.model_selection import StratifiedShuffleSplit
    from sklearn.metrics import accuracy_score
except ImportError:
    logger.error("scikit-learn is not installed. Run: pip install scikit-learn")
    sys.exit(1)

try:
    import motor.motor_asyncio as motor
except ImportError:
    logger.error("motor is not installed. Run: pip install motor")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

async def _load_trades(uri: str, days: int = 90) -> list[dict]:
    """Fetch closed trades from MongoDB from the past `days` days."""
    client = motor.AsyncIOMotorClient(uri)
    db = client.get_default_database()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    trades = await db.trades.find(
        {"status": "closed", "timestamp": {"$gte": cutoff}},
        {
            "_id": 0,
            "entry_price": 1, "exit_price": 1, "profit_loss": 1,
            "rsi": 1, "macd": 1, "macd_signal": 1, "macd_hist": 1,
            "atr": 1, "bb_upper": 1, "bb_mid": 1, "bb_lower": 1,
            "vwap": 1, "close_vs_sma20": 1, "close_vs_bb_mid": 1,
            "timestamp": 1,
        }
    ).sort("timestamp", -1).limit(10_000).to_list(10_000)
    client.close()
    return trades


def _build_dataset(trades: list[dict]) -> tuple[pd.DataFrame, pd.Series]:
    """
    Convert trade records to (X, y).
    Label: 2 = up (profitable long), 0 = down (loss), 1 = neutral (near zero).
    """
    rows = []
    for t in trades:
        row = {}
        for col in FEATURE_COLUMNS:
            val = t.get(col)
            if val is None:
                break
            try:
                row[col] = float(val)
            except (TypeError, ValueError):
                break
        else:
            pnl = float(t.get("profit_loss", 0) or 0)
            entry = float(t.get("entry_price", 1) or 1)
            pct = pnl / entry if entry else 0
            if pct > 0.002:
                row["label"] = 2  # up / win
            elif pct < -0.002:
                row["label"] = 0  # down / loss
            else:
                row["label"] = 1  # neutral
            rows.append(row)

    if not rows:
        raise ValueError("No complete feature rows found in trade data")

    df = pd.DataFrame(rows)
    X = df[FEATURE_COLUMNS].fillna(0.0)
    y = df["label"].astype(int)
    return X, y


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def _make_objective(X_train, y_train, X_val, y_val):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0.0, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 2.0),
            "objective": "multi:softprob",
            "num_class": 3,
            "eval_metric": "mlogloss",
            "use_label_encoder": False,
            "verbosity": 0,
            "tree_method": "hist",
        }
        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        preds = model.predict(X_val)
        return accuracy_score(y_val, preds)

    return objective


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

def _train_model(X: pd.DataFrame, y: pd.Series, n_trials: int) -> xgb.XGBClassifier:
    sss = StratifiedShuffleSplit(n_splits=1, test_size=TEST_SPLIT, random_state=42)
    train_idx, val_idx = next(sss.split(X, y))
    X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
    y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

    logger.info(
        "Optimising XGBoost with Optuna (%d trials, %d train / %d val samples)…",
        n_trials, len(X_train), len(X_val),
    )
    study = optuna.create_study(direction="maximize")
    study.optimize(_make_objective(X_train, y_train, X_val, y_val), n_trials=n_trials)

    best = study.best_params
    logger.info("Best params: %s  (val accuracy=%.4f)", best, study.best_value)

    final_params = {
        **best,
        "objective": "multi:softprob",
        "num_class": 3,
        "eval_metric": "mlogloss",
        "use_label_encoder": False,
        "verbosity": 0,
        "tree_method": "hist",
    }
    model = xgb.XGBClassifier(**final_params)
    model.fit(X, y)
    return model, study.best_value


def _validate(model: xgb.XGBClassifier, X: pd.DataFrame, y: pd.Series) -> float:
    preds = model.predict(X)
    return float(accuracy_score(y, preds))


# ---------------------------------------------------------------------------
# Atomic model swap
# ---------------------------------------------------------------------------

def _safe_swap_model(model: xgb.XGBClassifier, dry_run: bool = False) -> None:
    tmp = MODEL_PATH.with_suffix(".tmp.json")
    model.save_model(str(tmp))
    if dry_run:
        logger.info("[DRY-RUN] Would replace %s with new model.", MODEL_PATH)
        tmp.unlink(missing_ok=True)
        return
    if MODEL_PATH.exists():
        shutil.copy2(MODEL_PATH, BACKUP_PATH)
        logger.info("Backed up existing model to %s", BACKUP_PATH)
    tmp.replace(MODEL_PATH)
    logger.info("✅ Model atomically replaced at %s", MODEL_PATH)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(dry_run: bool = False, min_trades: int = MIN_RETRAIN_TRADES, n_trials: int = OPTUNA_TRIALS) -> int:
    if os.getenv("ENABLE_LEARNING_LOOP", "false").lower() != "true":
        logger.info("ENABLE_LEARNING_LOOP is not 'true' — skipping retrain.")
        return 0

    uri = os.getenv("MONGODB_URI")
    if not uri:
        logger.error("MONGODB_URI environment variable is not set.")
        return 1

    logger.info("Loading trades from MongoDB…")
    trades = await _load_trades(uri)
    logger.info("Loaded %d closed trades.", len(trades))

    if len(trades) < min_trades:
        logger.warning(
            "Only %d trades found (minimum %d). Skipping retrain.",
            len(trades), min_trades,
        )
        return 0

    logger.info("Building feature dataset…")
    X, y = _build_dataset(trades)
    logger.info("Dataset: %d samples, %d classes", len(X), y.nunique())

    if len(X) < min_trades:
        logger.warning("Insufficient complete feature rows (%d). Skipping.", len(X))
        return 0

    model, val_accuracy = _train_model(X, y, n_trials=n_trials)

    full_accuracy = _validate(model, X, y)
    logger.info("Full-set accuracy: %.4f  |  Validation accuracy: %.4f", full_accuracy, val_accuracy)

    if val_accuracy < MIN_ACCURACY:
        logger.warning(
            "Validation accuracy %.4f < minimum %.4f. Model not saved.",
            val_accuracy, MIN_ACCURACY,
        )
        return 0

    _safe_swap_model(model, dry_run=dry_run)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrain XGBoost model with Optuna tuning")
    parser.add_argument("--dry-run", action="store_true", help="Do not write model to disk")
    parser.add_argument("--min-trades", type=int, default=MIN_RETRAIN_TRADES)
    parser.add_argument("--trials", type=int, default=OPTUNA_TRIALS, dest="n_trials")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(dry_run=args.dry_run, min_trades=args.min_trades, n_trials=args.n_trials)))
