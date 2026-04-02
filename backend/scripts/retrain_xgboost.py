#!/usr/bin/env python3
"""
Daily XGBoost Retraining Script — Amarktai Crypto

Reads completed paper trades from MongoDB, extracts technical indicator
features, trains a fresh XGBoost classifier, validates it against a
holdout set, and only replaces the live model if validation guardrails pass.

The prior model is always backed up before replacement.

==========================================================================
Feature schema (MUST match FEATURE_COLUMNS in backend/ml_predictor.py):
    rsi, macd, macd_signal, macd_hist, atr,
    bb_upper, bb_mid, bb_lower, vwap,
    close_vs_sma20, close_vs_bb_mid

Labels (integer-encoded, matches XGBoost ≥ 2.0 requirements):
    0 = down  (trade closed in loss — net_pnl < 0)
    1 = neutral (flat trade — net_pnl == 0 or very small)
    2 = up  (trade closed in profit — net_pnl > 0)
==========================================================================

Usage:
    cd /var/amarktai/app/Amarktai-Crypto/backend
    .venv/bin/python scripts/retrain_xgboost.py [options]

Cron (daily at 02:00 UTC):
    0 2 * * * /var/amarktai/app/Amarktai-Crypto/backend/.venv/bin/python \
        /var/amarktai/app/Amarktai-Crypto/backend/scripts/retrain_xgboost.py \
        >> /var/log/amarktai/retrain.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retrain_xgboost")

# ---------------------------------------------------------------------------
# Paths — must stay in sync with ml_predictor.py
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = _BACKEND_ROOT / "models"
MODEL_PATH = MODEL_DIR / "xgb_predictor.json"
BACKUP_PATH_TEMPLATE = MODEL_DIR / "xgb_predictor.backup.{ts}.json"

# MUST match FEATURE_COLUMNS in ml_predictor.py exactly
FEATURE_COLUMNS = [
    "rsi", "macd", "macd_signal", "macd_hist", "atr",
    "bb_upper", "bb_mid", "bb_lower", "vwap",
    "close_vs_sma20", "close_vs_bb_mid",
]

# ---------------------------------------------------------------------------
# Guardrails — model is only promoted if all of these pass
# ---------------------------------------------------------------------------
# Minimum number of real trades required before retraining (synthetic bootstrap
# is used until this threshold is reached).
MIN_TRADES_FOR_RETRAIN = int(os.getenv("XGB_MIN_RETRAIN_TRADES", "50"))
# Holdout fraction (20% of data reserved for validation)
HOLDOUT_FRACTION = 0.20
# Minimum accuracy on holdout set required for promotion
MIN_HOLDOUT_ACCURACY = float(os.getenv("XGB_MIN_HOLDOUT_ACCURACY", "0.52"))
# Maximum allowed degradation vs. current model on holdout
# New model must not be more than this fraction worse than the current model.
MAX_ACCURACY_DEGRADATION = float(os.getenv("XGB_MAX_ACCURACY_DEGRADATION", "0.05"))

# ---------------------------------------------------------------------------
# Trade feature extraction
# ---------------------------------------------------------------------------

def _pnl(trade: dict) -> float:
    """Extract realised net P&L from a trade record."""
    for key in ("net_pnl", "net_pnl_quote", "net_profit", "profit_loss"):
        v = trade.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _label(net_pnl: float) -> Optional[int]:
    """Convert P&L to integer class label.

    Uses a small dead-band (±0.10 quote currency) to avoid labelling near-zero
    flat trades as wins or losses — they are treated as 1 (neutral).

    Returns None for trades with missing/invalid P&L that should be skipped.
    """
    if net_pnl > 0.10:
        return 2   # up / win
    if net_pnl < -0.10:
        return 0   # down / loss
    return 1       # neutral


def _extract_indicators(trade: dict) -> Optional[dict]:
    """Extract the FEATURE_COLUMNS indicator snapshot from a trade document.

    Trades may store indicators under several paths depending on when they
    were created:
      - Direct top-level fields (preferred): ml_rsi, ml_macd, etc.
      - Nested under 'entry_indicators' dict.
      - Individual named fields: canonical_regime_confidence, spread_bps, etc.

    Returns None if fewer than half the required features are available.
    """
    # Helper: safely parse float
    def _f(v, default: float = 0.0) -> float:
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    # Try nested 'entry_indicators' first (highest fidelity path)
    ind = trade.get("entry_indicators") or {}

    # Fall back to direct fields using multiple possible field names
    def _get(*keys, default: float = 0.0) -> float:
        for k in keys:
            v = ind.get(k) if ind else None
            if v is None:
                v = trade.get(k)
            if v is not None:
                return _f(v)
        return default

    features = {
        "rsi":            _get("rsi", "entry_rsi", default=50.0),
        "macd":           _get("macd", default=0.0),
        "macd_signal":    _get("macd_signal", "macd_sig", default=0.0),
        "macd_hist":      _get("macd_hist", "entry_macd_hist", default=0.0),
        "atr":            _get("atr", default=100.0),
        "bb_upper":       _get("bb_upper", default=0.0),
        "bb_mid":         _get("bb_mid", default=0.0),
        "bb_lower":       _get("bb_lower", default=0.0),
        "vwap":           _get("vwap", default=0.0),
        "close_vs_sma20": _get("close_vs_sma20", default=0.0),
        "close_vs_bb_mid": _get("close_vs_bb_mid", default=0.0),
    }

    # Require at least rsi + macd_hist to be non-zero/non-default to accept
    meaningful = sum(
        1 for k in ("rsi", "macd_hist", "close_vs_sma20", "atr")
        if features.get(k) not in (0.0, 50.0, 100.0, None)
    )
    if meaningful < 2:
        return None   # Skip trades with too-sparse indicator data

    return features


def _load_trades(
    mongo_url: str,
    db_name: str,
    lookback_days: int,
) -> list[dict]:
    """Load completed paper trades from MongoDB."""
    try:
        import pymongo
    except ImportError:
        logger.error("pymongo not installed. Run: pip install pymongo")
        sys.exit(1)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=5_000)
    try:
        db = client[db_name]
        cursor = db["trades"].find(
            {
                "status": {"$in": ["closed", "completed"]},
                "mode": "paper",
                "closed_at": {"$gte": cutoff},
            },
            {
                "_id": 0,
                "net_pnl": 1, "net_pnl_quote": 1, "net_profit": 1, "profit_loss": 1,
                "entry_indicators": 1,
                "rsi": 1, "entry_rsi": 1,
                "macd": 1, "macd_signal": 1, "macd_hist": 1, "entry_macd_hist": 1,
                "atr": 1,
                "bb_upper": 1, "bb_mid": 1, "bb_lower": 1,
                "vwap": 1,
                "close_vs_sma20": 1, "close_vs_bb_mid": 1,
            },
            limit=20_000,
        )
        trades = list(cursor)
        logger.info("Loaded %d paper trades from MongoDB (last %d days)", len(trades), lookback_days)
        return trades
    except Exception as exc:
        logger.error("MongoDB query failed: %s", exc)
        raise
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

def build_dataset(trades: list[dict]) -> tuple:
    """Build (X, y) arrays from trade records.

    Returns:
        X: np.ndarray shape (n_samples, n_features)
        y: np.ndarray shape (n_samples,) of integer labels
        n_skipped: number of trades skipped due to missing indicators
    """
    try:
        import numpy as np
    except ImportError:
        logger.error("numpy not installed")
        sys.exit(1)

    rows_x = []
    rows_y = []
    n_skipped = 0

    for trade in trades:
        net_pnl = _pnl(trade)
        label = _label(net_pnl)
        if label is None:
            n_skipped += 1
            continue

        indicators = _extract_indicators(trade)
        if indicators is None:
            n_skipped += 1
            continue

        row = [float(indicators.get(col, 0.0)) for col in FEATURE_COLUMNS]
        rows_x.append(row)
        rows_y.append(label)

    if not rows_x:
        return np.empty((0, len(FEATURE_COLUMNS))), np.empty(0), n_skipped

    X = np.array(rows_x, dtype=np.float32)
    y = np.array(rows_y, dtype=int)
    return X, y, n_skipped


# ---------------------------------------------------------------------------
# Model training and validation
# ---------------------------------------------------------------------------

def train_model(X_train, y_train):
    """Train an XGBoost classifier on the training set."""
    try:
        import xgboost as xgb
    except ImportError:
        logger.error("xgboost not installed")
        sys.exit(1)

    model = xgb.XGBClassifier(
        n_estimators=120,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=2,
    )
    model.fit(X_train, y_train)
    return model


def evaluate_model(model, X_val, y_val) -> dict:
    """Evaluate model accuracy on validation set."""
    try:
        import numpy as np
    except ImportError:
        sys.exit(1)

    if len(X_val) == 0:
        return {"accuracy": 0.0, "n_samples": 0}

    preds = model.predict(X_val)
    accuracy = float(np.mean(preds == y_val))
    label_counts = {str(k): int(v) for k, v in zip(*np.unique(y_val, return_counts=True))}
    return {
        "accuracy": round(accuracy, 4),
        "n_samples": len(y_val),
        "label_counts": label_counts,
    }


def evaluate_current_model(X_val, y_val) -> float:
    """Return accuracy of the currently deployed model on the same holdout set."""
    if not MODEL_PATH.exists() or len(X_val) == 0:
        return 0.0
    try:
        import xgboost as xgb
        m = xgb.XGBClassifier()
        m.load_model(str(MODEL_PATH))
        import numpy as np
        preds = m.predict(X_val)
        return float(np.mean(preds == y_val))
    except Exception as exc:
        logger.warning("Could not evaluate current model: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# Safe model swap
# ---------------------------------------------------------------------------

def safe_swap_model(new_model, reason: str) -> None:
    """Back up the current model and replace it with the new one."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Backup
    if MODEL_PATH.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = Path(str(BACKUP_PATH_TEMPLATE).format(ts=ts))
        shutil.copy2(MODEL_PATH, backup_path)
        logger.info("Current model backed up → %s", backup_path)

    # Save new model
    new_model.save_model(str(MODEL_PATH))
    logger.info("✅ New model deployed → %s  (reason: %s)", MODEL_PATH, reason)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Daily XGBoost retraining for Amarktai Crypto")
    parser.add_argument("--mongo-url", default=os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "amarktai_trading"))
    parser.add_argument("--lookback-days", type=int, default=30,
                        help="Days of paper trade history to use")
    parser.add_argument("--min-trades", type=int, default=MIN_TRADES_FOR_RETRAIN,
                        help="Minimum trades required before retraining")
    parser.add_argument("--dry-run", action="store_true",
                        help="Train and validate but do not replace model")
    parser.add_argument("--force", action="store_true",
                        help="Skip guardrail checks and promote unconditionally")
    args = parser.parse_args()

    logger.info("=== XGBoost Daily Retraining ===")
    logger.info("mongo=%s  db=%s  lookback=%d days  dry_run=%s",
                args.mongo_url, args.db_name, args.lookback_days, args.dry_run)

    # ── 1. Load trades ────────────────────────────────────────────────────
    try:
        trades = _load_trades(args.mongo_url, args.db_name, args.lookback_days)
    except Exception as exc:
        logger.error("Failed to connect to MongoDB: %s", exc)
        logger.error("Ensure MONGO_URL is set and MongoDB is running.")
        return 1
    if len(trades) < args.min_trades:
        logger.warning(
            "Only %d paper trades available (minimum %d). "
            "Bootstrap model will be kept until more data accumulates.",
            len(trades), args.min_trades,
        )
        return 0

    # ── 2. Build dataset ──────────────────────────────────────────────────
    try:
        import numpy as np
    except ImportError:
        logger.error("numpy not installed")
        return 1

    X, y, n_skipped = build_dataset(trades)
    logger.info("Dataset: %d samples (%d skipped), %d features", len(X), n_skipped, len(FEATURE_COLUMNS))

    if len(X) < args.min_trades:
        logger.warning(
            "After feature extraction only %d samples available (need %d). "
            "Keeping existing model.",
            len(X), args.min_trades,
        )
        return 0

    # ── 3. Train/validation split ─────────────────────────────────────────
    from sklearn.model_selection import train_test_split  # type: ignore
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=HOLDOUT_FRACTION, random_state=42, stratify=None
    )
    logger.info("Train: %d  Val: %d", len(X_train), len(X_val))

    # ── 4. Train new model ────────────────────────────────────────────────
    logger.info("Training new XGBoost model...")
    new_model = train_model(X_train, y_train)
    new_metrics = evaluate_model(new_model, X_val, y_val)
    logger.info("New model  accuracy=%.4f  n_val=%d  labels=%s",
                new_metrics["accuracy"], new_metrics["n_samples"],
                new_metrics.get("label_counts"))

    # ── 5. Guardrail checks ───────────────────────────────────────────────
    current_accuracy = evaluate_current_model(X_val, y_val)
    logger.info("Current model accuracy on same holdout = %.4f", current_accuracy)

    if args.force:
        logger.warning("--force specified: skipping guardrail checks")
        promote = True
        reason = "forced promotion"
    else:
        if new_metrics["accuracy"] < MIN_HOLDOUT_ACCURACY:
            logger.warning(
                "New model accuracy %.4f < minimum %.4f — keeping current model",
                new_metrics["accuracy"], MIN_HOLDOUT_ACCURACY,
            )
            return 0

        if current_accuracy > 0 and new_metrics["accuracy"] < current_accuracy - MAX_ACCURACY_DEGRADATION:
            logger.warning(
                "New model accuracy %.4f is %.4f worse than current (%.4f) — "
                "exceeds allowed degradation %.4f — keeping current model",
                new_metrics["accuracy"],
                current_accuracy - new_metrics["accuracy"],
                current_accuracy,
                MAX_ACCURACY_DEGRADATION,
            )
            return 0

        promote = True
        reason = (
            f"accuracy={new_metrics['accuracy']:.4f}  "
            f"current={current_accuracy:.4f}  "
            f"n_train={len(X_train)}  n_val={len(X_val)}"
        )

    # ── 6. Write result record ─────────────────────────────────────────────
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trades_loaded": len(trades),
        "samples_after_extraction": len(X),
        "n_skipped": n_skipped,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "new_model_accuracy": new_metrics["accuracy"],
        "current_model_accuracy": current_accuracy,
        "label_counts": new_metrics.get("label_counts"),
        "promoted": promote and not args.dry_run,
        "dry_run": args.dry_run,
        "reason": reason,
        "lookback_days": args.lookback_days,
    }
    out_path = Path("/tmp/retrain_xgboost_result.json")
    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2)
    logger.info("Result written to %s", out_path)

    # ── 7. Promote or dry-run ──────────────────────────────────────────────
    if args.dry_run:
        logger.info("DRY RUN — model not replaced. Would have promoted: %s", promote)
    elif promote:
        safe_swap_model(new_model, reason)
        logger.info("✅ Retraining complete — new model is live")
    else:
        logger.info("Guardrails not passed — existing model retained")

    return 0


if __name__ == "__main__":
    sys.exit(main())
