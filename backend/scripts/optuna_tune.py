#!/usr/bin/env python3
"""
Optuna Threshold Optimiser — offline strategy parameter tuner.

Runs an Optuna hyperparameter study against MongoDB paper-trade history
to find the best Trading Brain V2 entry/exit threshold values.

IMPORTANT: This script is 100% offline and read-only against MongoDB.
It does NOT modify any live trading parameters.  Results are printed
and saved to /tmp/optuna_study_results.json for review.  To apply
the recommended thresholds, update the relevant env variables manually
after reviewing the output.

Usage:
    cd /var/amarktai/app/Amarktai-Crypto/backend
    ENVIRONMENT=production ./.venv/bin/python scripts/optuna_tune.py \
        --n-trials 200 \
        --min-trades 50 \
        --mongo-url mongodb://localhost:27017 \
        --db-name amarktai_trading

Requirements:
    optuna, pymongo, numpy  (all installed in backend venv)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("optuna_tune")

# ---------------------------------------------------------------------------
# Optional deps — script exits gracefully if missing
# ---------------------------------------------------------------------------
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    logger.error("optuna not installed. Run: pip install optuna")
    sys.exit(1)

try:
    import pymongo
except ImportError:
    logger.error("pymongo not installed. Run: pip install pymongo")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    logger.error("numpy not installed.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Objective function
# ---------------------------------------------------------------------------

def _load_trades(mongo_url: str, db_name: str, min_trades: int) -> list[dict]:
    """Load completed paper trades from MongoDB."""
    client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    cursor = db["trades"].find(
        {"status": {"$in": ["closed", "completed"]}, "mode": "paper"},
        {
            "_id": 0,
            "net_pnl": 1,
            "net_pnl_quote": 1,
            "profit_loss": 1,
            "confidence": 1,
            "entry_confidence": 1,
            "spread_pct": 1,
            "regime_confidence": 1,
            "hold_seconds": 1,
            "bot_type": 1,
        },
        limit=5000,
    )
    trades = list(cursor)
    client.close()
    if len(trades) < min_trades:
        logger.warning(
            "Only %d paper trades found (minimum %d). "
            "Results will not be statistically reliable.",
            len(trades), min_trades,
        )
    return trades


def _pnl(t: dict) -> float:
    """Extract realised net P&L from a trade record (handles multiple field names)."""
    for key in ("net_pnl", "net_pnl_quote", "profit_loss"):
        v = t.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _build_objective(trades: list[dict]):
    """Return an Optuna objective function closed over `trades`."""

    def objective(trial: optuna.Trial) -> float:
        # ── Suggest thresholds ──────────────────────────────────────────
        min_confidence = trial.suggest_float("min_entry_confidence", 0.35, 0.75, step=0.01)
        min_regime_conf = trial.suggest_float("min_regime_confidence", 0.30, 0.65, step=0.01)
        max_spread_pct = trial.suggest_float("max_spread_pct", 0.10, 0.50, step=0.01)
        min_hold_seconds = trial.suggest_int("min_hold_seconds", 30, 300, step=30)
        max_hold_seconds = trial.suggest_int("max_hold_seconds", 600, 7200, step=300)

        # ── Filter and score ─────────────────────────────────────────────
        qualified = []
        for t in trades:
            conf = float(t.get("confidence") or t.get("entry_confidence") or 0)
            regime_conf = float(t.get("regime_confidence") or 0)
            spread = float(t.get("spread_pct") or 0)
            hold = float(t.get("hold_seconds") or 0)

            if conf < min_confidence:
                continue
            if regime_conf < min_regime_conf:
                continue
            if spread > max_spread_pct:
                continue
            if hold < min_hold_seconds:
                continue
            if hold > max_hold_seconds:
                continue
            qualified.append(t)

        if len(qualified) < 5:
            return -999.0  # Not enough trades to evaluate

        pnls = [_pnl(t) for t in qualified]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p <= 0)
        total = wins + losses
        win_rate = wins / total if total > 0 else 0
        avg_pnl = float(np.mean(pnls))
        trade_count_bonus = min(len(qualified) / len(trades), 1.0) * 0.1  # volume bonus

        # Objective: maximise risk-adjusted return
        # Penalise low win rate and low trade count simultaneously
        score = avg_pnl * win_rate + trade_count_bonus
        return float(score)

    return objective


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Optuna threshold optimiser for Trading Brain V2")
    parser.add_argument("--n-trials", type=int, default=200, help="Number of Optuna trials")
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum trades required")
    parser.add_argument("--mongo-url", default=os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "amarktai_trading"))
    parser.add_argument("--output", default="/tmp/optuna_study_results.json")
    args = parser.parse_args()

    logger.info("Loading paper trades from MongoDB (%s / %s)...", args.mongo_url, args.db_name)
    try:
        trades = _load_trades(args.mongo_url, args.db_name, args.min_trades)
    except Exception as exc:
        logger.error("Failed to load trades: %s", exc)
        sys.exit(1)

    logger.info("Loaded %d paper trades. Running %d Optuna trials...", len(trades), args.n_trials)

    study = optuna.create_study(direction="maximize")
    study.optimize(_build_objective(trades), n_trials=args.n_trials, show_progress_bar=False)

    best = study.best_params
    best_value = study.best_value

    logger.info("=== OPTUNA RESULTS ===")
    logger.info("Best score:  %.6f", best_value)
    for k, v in best.items():
        logger.info("  %-35s = %s", k, v)

    # ── Env variable recommendations ─────────────────────────────────────
    print("\n=== RECOMMENDED ENV OVERRIDES (review before applying) ===")
    print(f"MIN_ENTRY_CONFIDENCE={best.get('min_entry_confidence', 0.40):.2f}")
    print(f"SCALPER_REGIME_CONF_THRESHOLD={best.get('min_regime_confidence', 0.55):.2f}")
    print(f"PAPER_MAX_SPREAD_PCT={best.get('max_spread_pct', 0.35):.2f}")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_trials": args.n_trials,
        "n_trades_used": len(trades),
        "best_score": best_value,
        "best_params": best,
        "env_recommendations": {
            "MIN_ENTRY_CONFIDENCE": f"{best.get('min_entry_confidence', 0.40):.2f}",
            "SCALPER_REGIME_CONF_THRESHOLD": f"{best.get('min_regime_confidence', 0.55):.2f}",
            "PAPER_MAX_SPREAD_PCT": f"{best.get('max_spread_pct', 0.35):.2f}",
        },
        "note": (
            "These are data-driven suggestions. Review carefully before "
            "updating production env variables. Rerun after 7-day beta for "
            "more reliable results."
        ),
    }

    with open(args.output, "w") as fh:
        json.dump(result, fh, indent=2)
    logger.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
