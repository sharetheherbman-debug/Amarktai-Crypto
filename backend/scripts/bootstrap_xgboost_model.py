#!/usr/bin/env python3
"""
Bootstrap XGBoost Model Generator

Creates an initial XGBoost model from synthetic data so the system has a
real model artifact on first deploy.  The model will be replaced once
enough real trade data accumulates via the nightly retraining pipeline.

Usage:
    cd backend && python scripts/bootstrap_xgboost_model.py
"""

import sys
from pathlib import Path

# Ensure backend is on path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.retrain_xgboost import build_dataset_from_synthetic, train_model, safe_swap_model, MODEL_PATH
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("bootstrap_xgb")


def main():
    if MODEL_PATH.exists():
        logger.info("Model already exists at %s — skipping bootstrap", MODEL_PATH)
        return

    logger.info("🏗️  Generating bootstrap XGBoost model from synthetic data ...")
    X, y = build_dataset_from_synthetic(5000)
    clf, acc = train_model(X, y, use_optuna=False, min_accuracy=0.40)
    safe_swap_model(clf, acc, dry_run=False)
    logger.info("✅ Bootstrap model created at %s (accuracy %.4f)", MODEL_PATH, acc)


if __name__ == "__main__":
    main()
