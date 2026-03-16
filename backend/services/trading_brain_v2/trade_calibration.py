"""
Trade Calibration — projected-vs-realized tracking and policy-pack scorecard.

This module tracks the divergence between what the entry gate expected (projected
edge, projected net profit) and what actually materialized at close (realized PnL,
exit reason, time held).

It also provides:
  - Per-pack scorecards (qualified win rate, micro win rate, realized/projection ratio)
  - Daily evaluator scaffold that computes scores and recommends next pack
    (no automatic promotion yet — diagnostics only)

Key data structures
-------------------
TradeCalibrationRecord:
    Fields recorded at ENTRY and updated at CLOSE.
    Always stored in quote currency.  ZAR truth preserved where applicable.

PolicyPackScorecard:
    Aggregated performance metrics for a policy pack, computed by
    daily_evaluator over a rolling window of closed trades.

Usage
-----
    from services.trading_brain_v2.trade_calibration import (
        build_entry_calibration,
        enrich_exit_calibration,
        compute_pack_scorecard,
        daily_evaluator,
    )
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Outcome constants (re-imported for convenience) ───────────────────────
OUTCOME_LOSS = "LOSS"
OUTCOME_MICRO_WIN = "MICRO_WIN"
OUTCOME_QUALIFIED_WIN = "QUALIFIED_WIN"


def build_entry_calibration(
    *,
    bot_id: str,
    bot_type: str,
    exchange: str,
    symbol: str,
    policy_pack_name: str,
    regime_label: str,
    projected_net_profit_quote: float,
    projected_gross_edge_bps: float,
    all_in_cost_bps: float,
    paper_edge_floor_applied: bool = False,
    raw_gross_edge_bps: float = 0.0,
    entry_confidence: float = 0.0,
    spread_pct: float = 0.0,
    estimated_slippage_pct: float = 0.0,
    entry_ts: float = None,
) -> Dict:
    """
    Build a calibration record at trade entry.

    This is stored alongside the trade document and updated at close via
    enrich_exit_calibration().

    Returns a dict that can be merged into the trade record or stored in
    a separate calibration collection.
    """
    return {
        # ── Identity ──
        "bot_id":                  bot_id,
        "bot_type":                (bot_type or "normal").lower(),
        "exchange":                (exchange or "").lower(),
        "symbol":                  (symbol or "").upper(),
        "policy_pack_name":        policy_pack_name,
        "regime_label_at_entry":   (regime_label or "unknown").lower(),
        # ── Entry projections ──
        "projected_net_profit_quote":    round(float(projected_net_profit_quote or 0), 6),
        "projected_gross_edge_bps":      round(float(projected_gross_edge_bps or 0), 4),
        "all_in_cost_bps_at_entry":      round(float(all_in_cost_bps or 0), 4),
        "paper_edge_floor_applied":      bool(paper_edge_floor_applied),
        "raw_gross_edge_bps":            round(float(raw_gross_edge_bps or 0), 4),
        "entry_confidence":              round(float(entry_confidence or 0), 4),
        "spread_pct_at_entry":           round(float(spread_pct or 0), 4),
        "slippage_pct_at_entry":         round(float(estimated_slippage_pct or 0), 4),
        # ── Lifecycle ──
        "entry_ts":                      float(entry_ts or time.time()),
        "exit_ts":                       None,
        "hold_seconds":                  None,
        # ── Realized (set at exit) ──
        "realized_net_profit_quote":     None,
        "realized_gross_pnl_quote":      None,
        "realized_projection_ratio":     None,   # realized / projected (1.0 = perfect)
        "exit_reason_code":              None,
        "outcome_class":                 None,   # LOSS / MICRO_WIN / QUALIFIED_WIN
        "regime_label_at_exit":          None,
        # ── Calibration state ──
        "calibration_complete":          False,
    }


def enrich_exit_calibration(
    record: Dict,
    *,
    realized_net_profit_quote: float,
    realized_gross_pnl_quote: float = 0.0,
    exit_reason_code: str = "unknown",
    outcome_class: str = OUTCOME_LOSS,
    regime_label_at_exit: str = "unknown",
    exit_ts: float = None,
) -> Dict:
    """
    Update a calibration record with exit data.

    Computes:
      - hold_seconds
      - realized_projection_ratio (realized_net / projected_net, capped)
      - calibration_complete = True

    Returns the updated record (mutates and returns).
    """
    _exit_ts = float(exit_ts or time.time())
    _entry_ts = float(record.get("entry_ts") or _exit_ts)
    _hold = max(0.0, _exit_ts - _entry_ts)

    projected = float(record.get("projected_net_profit_quote") or 0)
    realized = float(realized_net_profit_quote or 0)

    # Realized/projection ratio — clamped to [-3.0, 3.0] to avoid inf on tiny projections
    if projected > 0:
        ratio = max(-3.0, min(3.0, realized / projected))
    else:
        # Negative or zero projected means gate was wrong at entry; ratio not meaningful
        ratio = None

    record.update({
        "exit_ts":                    _exit_ts,
        "hold_seconds":               round(_hold, 1),
        "realized_net_profit_quote":  round(realized, 6),
        "realized_gross_pnl_quote":   round(float(realized_gross_pnl_quote or 0), 6),
        "realized_projection_ratio":  round(ratio, 4) if ratio is not None else None,
        "exit_reason_code":           str(exit_reason_code or "unknown"),
        "outcome_class":              str(outcome_class or OUTCOME_LOSS),
        "regime_label_at_exit":       str(regime_label_at_exit or "unknown").lower(),
        "calibration_complete":       True,
    })
    return record


def compute_pack_scorecard(
    records: List[Dict],
    *,
    pack_name: str,
    window_days: int = 7,
) -> Dict:
    """
    Compute a policy-pack scorecard from a list of completed calibration records.

    Aggregates:
      - total trades, qualified wins, micro wins, losses
      - qualified_win_rate_pct
      - micro_win_rate_pct
      - avg_realized_projection_ratio
      - avg_hold_seconds (overall + by exit reason)
      - avg_realized_net_profit
      - paper_floor_usage_pct
      - drawdown proxy: consecutive losses streak

    Parameters
    ----------
    records : list of calibration dicts (must have calibration_complete=True)
    pack_name : str — which pack this scorecard is for
    window_days : int — informational (records should already be filtered)
    """
    complete = [r for r in records if r.get("calibration_complete")]
    total = len(complete)

    if total == 0:
        return _empty_scorecard(pack_name, window_days)

    qualified = 0
    micro = 0
    losses = 0
    ratios = []
    hold_secs = []
    realized_profits = []
    floor_count = 0
    exit_holds: Dict[str, List[float]] = {}
    consecutive_loss = 0
    max_consecutive_loss = 0
    current_streak = 0

    for r in complete:
        oc = r.get("outcome_class", OUTCOME_LOSS)
        ratio = r.get("realized_projection_ratio")
        hold = r.get("hold_seconds")
        realized = r.get("realized_net_profit_quote")
        floor = r.get("paper_edge_floor_applied", False)
        exit_rc = str(r.get("exit_reason_code") or "unknown")

        if oc == OUTCOME_QUALIFIED_WIN:
            qualified += 1
            current_streak = 0
        elif oc == OUTCOME_MICRO_WIN:
            micro += 1
            current_streak = 0
        else:
            losses += 1
            current_streak += 1
            max_consecutive_loss = max(max_consecutive_loss, current_streak)

        if ratio is not None:
            ratios.append(ratio)
        if hold is not None:
            hold_secs.append(float(hold))
            exit_holds.setdefault(exit_rc, []).append(float(hold))
        if realized is not None:
            realized_profits.append(float(realized))
        if floor:
            floor_count += 1

    def _avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else None

    avg_hold_by_exit = {rc: round(sum(h) / len(h), 1) for rc, h in exit_holds.items()}

    return {
        "pack_name":                  pack_name,
        "window_days":                window_days,
        "total_trades":               total,
        "qualified_win_count":        qualified,
        "micro_win_count":            micro,
        "loss_count":                 losses,
        "qualified_win_rate_pct":     round(qualified / total * 100, 2),
        "micro_win_rate_pct":         round(micro / total * 100, 2),
        "loss_rate_pct":              round(losses / total * 100, 2),
        "avg_realized_projection_ratio": _avg(ratios),
        "avg_hold_seconds":           _avg(hold_secs),
        "avg_realized_net_profit":    _avg(realized_profits),
        "paper_floor_usage_pct":      round(floor_count / total * 100, 2),
        "max_consecutive_loss":       max_consecutive_loss,
        "avg_hold_by_exit_reason":    avg_hold_by_exit,
        "scorecard_version":          "v1",
    }


def _empty_scorecard(pack_name: str, window_days: int) -> Dict:
    return {
        "pack_name":                  pack_name,
        "window_days":                window_days,
        "total_trades":               0,
        "qualified_win_count":        0,
        "micro_win_count":            0,
        "loss_count":                 0,
        "qualified_win_rate_pct":     0.0,
        "micro_win_rate_pct":         0.0,
        "loss_rate_pct":              0.0,
        "avg_realized_projection_ratio": None,
        "avg_hold_seconds":           None,
        "avg_realized_net_profit":    None,
        "paper_floor_usage_pct":      0.0,
        "max_consecutive_loss":       0,
        "avg_hold_by_exit_reason":    {},
        "scorecard_version":          "v1",
    }


def daily_evaluator(
    scorecards: Dict[str, Dict],
    *,
    bot_type: str = "normal",
    exchange: str = "",
    min_trades_for_recommendation: int = 10,
) -> Dict:
    """
    Self-learning scaffold: compare policy-pack scorecards and recommend
    the best pack for a given bot type / exchange combination.

    This does NOT automatically promote any pack.  It produces a diagnostics
    recommendation only.  Autonomous promotion is a future phase.

    Scoring formula (higher = better):
        score = qualified_win_rate × 2.0
              + avg_realized_projection_ratio × 1.5  (if available)
              - micro_win_rate × 0.5
              - paper_floor_usage × 0.3
              - max_consecutive_loss × 0.1

    Parameters
    ----------
    scorecards : dict of {pack_name: scorecard_dict}
    bot_type : str — filter to packs valid for this bot type
    exchange : str — informational (used in recommendation metadata)
    min_trades_for_recommendation : int — minimum trades for a pack to be recommended

    Returns
    -------
    dict:
        recommended_pack_name    — pack with highest score
        recommended_score        — score value
        pack_scores              — {pack_name: score} for all evaluated packs
        reasoning                — human-readable explanation
        insufficient_data_packs  — packs with < min_trades_for_recommendation
        evaluated_at_ts          — unix timestamp
    """
    from .policy_packs import list_packs_for_bot_type

    eligible_packs = {p["pack_name"] for p in list_packs_for_bot_type(bot_type)}

    pack_scores: Dict[str, float] = {}
    insufficient: list = []
    reasoning_parts: list = []

    for pack_name, sc in scorecards.items():
        if pack_name not in eligible_packs:
            continue
        total = sc.get("total_trades", 0)
        if total < min_trades_for_recommendation:
            insufficient.append(pack_name)
            continue

        qw = float(sc.get("qualified_win_rate_pct", 0) or 0) / 100.0
        mw = float(sc.get("micro_win_rate_pct", 0) or 0) / 100.0
        ratio = sc.get("avg_realized_projection_ratio")
        floor_pct = float(sc.get("paper_floor_usage_pct", 0) or 0) / 100.0
        streak = int(sc.get("max_consecutive_loss", 0) or 0)

        score = qw * 2.0
        if ratio is not None:
            score += float(ratio) * 1.5
        score -= mw * 0.5
        score -= floor_pct * 0.3
        score -= streak * 0.1

        pack_scores[pack_name] = round(score, 4)
        reasoning_parts.append(
            f"{pack_name}: score={score:.3f} "
            f"(qw={qw:.0%} mw={mw:.0%} ratio={ratio} streak={streak})"
        )

    if not pack_scores:
        return {
            "recommended_pack_name":   None,
            "recommended_score":       None,
            "pack_scores":             {},
            "reasoning":               "Insufficient data to recommend a pack.",
            "insufficient_data_packs": insufficient,
            "evaluated_at_ts":         time.time(),
        }

    best_name = max(pack_scores, key=pack_scores.__getitem__)
    best_score = pack_scores[best_name]

    return {
        "recommended_pack_name":   best_name,
        "recommended_score":       best_score,
        "pack_scores":             pack_scores,
        "reasoning":               "; ".join(reasoning_parts),
        "insufficient_data_packs": insufficient,
        "evaluated_at_ts":         time.time(),
    }
