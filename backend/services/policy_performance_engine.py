"""
Policy Pack Performance Engine.
Aggregates and scores performance per policy pack.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.trading_brain_v2.trade_outcome_classifier import (
    build_outcome_counts,
    classify_trade_outcome,
)
from services.trading_brain_v2.trade_calibration import compute_pack_scorecard
from services.trading_brain_v2.policy_packs import ALL_PACKS

logger = logging.getLogger(__name__)


async def get_pack_performance(user_id: str = None) -> dict:
    """Aggregate and score performance per policy pack.

    Fetches closed trades from the database, groups them by policy pack,
    and computes per-pack scorecards including outcome classification
    and calibration metrics.

    Parameters
    ----------
    user_id : str, optional
        If provided, filter trades to this user.

    Returns
    -------
    dict with per-pack scorecards, outcome counts, and summary stats.
    """
    import database as db

    query: dict = {"status": "closed"}
    if user_id:
        query["user_id"] = user_id

    trades = await db.trades_collection.find(
        query,
        {"_id": 0},
    ).sort("closed_at", -1).to_list(5000)

    # Group trades by policy pack name
    pack_trades: Dict[str, List[dict]] = {}
    for trade in trades:
        pack_name = (
            trade.get("policy_pack_name")
            or trade.get("policy_pack")
            or _infer_pack_name(trade)
        )
        pack_trades.setdefault(pack_name, []).append(trade)

    scorecards: Dict[str, dict] = {}

    for pack_name, pack_trade_list in pack_trades.items():
        # Classify each trade that hasn't been classified yet
        classified: List[dict] = []
        for t in pack_trade_list:
            if t.get("outcome_class"):
                classified.append(t)
            else:
                result = classify_trade_outcome(
                    gross_pnl=float(t.get("gross_pnl", t.get("pnl", 0)) or 0),
                    net_pnl=float(t.get("net_pnl", t.get("profit_loss", 0)) or 0),
                    bot_type=str(t.get("bot_type", "normal")).lower(),
                    exchange=str(t.get("exchange", "luno")).lower(),
                    bot_equity=float(t.get("bot_equity", 0) or 0),
                    notional=float(t.get("notional", t.get("amount", 0)) or 0),
                )
                merged = {**t, **result}
                classified.append(merged)

        outcome_counts = build_outcome_counts(classified)

        # Build calibration records for scorecard computation
        calibration_records = _build_calibration_records(classified)
        scorecard = compute_pack_scorecard(
            calibration_records,
            pack_name=pack_name,
        )

        # Compute extra metrics
        net_pnl = sum(
            float(t.get("net_pnl", t.get("profit_loss", 0)) or 0) for t in classified
        )
        hold_times = [
            float(t.get("hold_seconds", 0) or 0)
            for t in classified
            if t.get("hold_seconds")
        ]
        n_holds = len(hold_times)
        avg_hold = round(sum(hold_times) / n_holds, 1) if n_holds > 0 else None

        # Max drawdown from sequential PnL
        max_drawdown = _compute_max_drawdown(classified)

        scorecards[pack_name] = {
            **scorecard,
            "outcome_counts": outcome_counts,
            "net_pnl": round(net_pnl, 6),
            "max_drawdown": round(max_drawdown, 6),
            "avg_hold_time_seconds": avg_hold,
        }

    # Packs with zero trades
    for pack_name in ALL_PACKS:
        if pack_name not in scorecards:
            scorecards[pack_name] = {
                "pack_name": pack_name,
                "total_trades": 0,
                "outcome_counts": build_outcome_counts([]),
                "net_pnl": 0.0,
                "max_drawdown": 0.0,
                "avg_hold_time_seconds": None,
                "note": "no closed trades for this pack",
            }

    return {
        "pack_scorecards": scorecards,
        "total_closed_trades": len(trades),
        "packs_with_trades": [p for p, s in scorecards.items() if s.get("total_trades", 0) > 0],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _infer_pack_name(trade: dict) -> str:
    """Infer a pack name from bot_type when explicit pack is absent."""
    bt = str(trade.get("bot_type", trade.get("strategy_type", "normal"))).lower()
    defaults = {
        "scalper": "scalper_active",
        "normal": "balanced",
        "mean_reversion": "balanced",
    }
    return defaults.get(bt, "balanced")


def _build_calibration_records(classified_trades: List[dict]) -> List[dict]:
    """Convert classified trade dicts into calibration-style records."""
    records = []
    for t in classified_trades:
        projected = float(t.get("projected_net_profit_quote", 0) or 0)
        realized = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
        if projected > 0:
            ratio = max(-3.0, min(3.0, realized / projected))
        else:
            ratio = None

        records.append({
            "calibration_complete": True,
            "outcome_class": t.get("outcome_class", "LOSS"),
            "realized_projection_ratio": ratio,
            "hold_seconds": t.get("hold_seconds"),
            "realized_net_profit_quote": realized,
            "paper_edge_floor_applied": t.get("paper_edge_floor_applied", False),
            "exit_reason_code": t.get("trade_close_reason", t.get("exit_reason_code", "unknown")),
        })
    return records


def _compute_max_drawdown(trades: List[dict]) -> float:
    """Compute max drawdown from sequential trade PnL."""
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for t in trades:
        pnl = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    return max_dd
