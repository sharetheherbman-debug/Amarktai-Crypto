"""
Canonical trade outcome classifier for Trading Brain V2.

Every trade must be classified as:
  OUTCOME_LOSS       — net_pnl < 0 or gross_pnl <= 0
  OUTCOME_MICRO_WIN  — gross_pnl > 0 but net_pnl too small to count as meaningful
  OUTCOME_QUALIFIED_WIN — net_pnl clears the meaningful-profit threshold

A "meaningful win" is one that:
  1. Has net_pnl > 0 (positive after fees + slippage)
  2. Clears the venue/bot-type/tier meaningful-profit threshold

Only OUTCOME_QUALIFIED_WIN counts as a true win (win_count=1).
OUTCOME_MICRO_WIN is tracked separately — these are gross-positive but
economically trivial and should NOT be celebrated in dashboard reporting.

Flat trades (net_pnl == 0) are OUTCOME_LOSS but do not increment loss_count.

Usage
-----
    from services.trading_brain_v2.trade_outcome_classifier import (
        classify_trade_outcome,
        build_outcome_counts,
        OUTCOME_LOSS,
        OUTCOME_MICRO_WIN,
        OUTCOME_QUALIFIED_WIN,
    )

    result = classify_trade_outcome(
        gross_pnl=1.50,
        net_pnl=0.80,
        bot_type="normal",
        exchange="luno",
        bot_equity=2000.0,
        notional=500.0,
        all_in_cost_bps=30.0,
    )
    # result["outcome_class"]       → "QUALIFIED_WIN" or "MICRO_WIN" or "LOSS"
    # result["is_gross_win"]        → bool
    # result["is_net_win"]          → bool
    # result["is_meaningful_win"]   → bool
    # result["win_count"]           → 1 or 0
    # result["loss_count"]          → 1 or 0
    # result["meaningful_win_count"] → 1 or 0
"""
from __future__ import annotations

from typing import Dict, List

from .entry_thresholds import compute_min_net_profit_required, MEANINGFUL_WIN_THRESHOLD_MULTIPLE

# ── Outcome constants ──────────────────────────────────────────────────────
OUTCOME_LOSS = "LOSS"
OUTCOME_MICRO_WIN = "MICRO_WIN"
OUTCOME_QUALIFIED_WIN = "QUALIFIED_WIN"


def classify_trade_outcome(
    *,
    gross_pnl: float,
    net_pnl: float,
    bot_type: str = "normal",
    exchange: str = "luno",
    bot_equity: float = 0.0,
    notional: float = 0.0,
    all_in_cost_bps: float = 25.0,
) -> Dict:
    """
    Classify a single closed trade into LOSS / MICRO_WIN / QUALIFIED_WIN.

    Parameters
    ----------
    gross_pnl : float
        Gross profit/loss before fees and slippage (in quote currency)
    net_pnl : float
        Net profit/loss after fees and slippage (in quote currency)
    bot_type : str
        "normal", "scalper", "mean_reversion", etc.
    exchange : str
        Exchange name (e.g. "luno", "binance")
    bot_equity : float
        Bot capital in quote currency (used for tier calculation)
    notional : float
        Trade notional in quote currency
    all_in_cost_bps : float
        Round-trip cost in basis points (for meaningful threshold computation)

    Returns
    -------
    dict with:
        outcome_class        — LOSS / MICRO_WIN / QUALIFIED_WIN
        is_gross_win         — bool: gross_pnl > 0
        is_net_win           — bool: net_pnl > 0
        is_meaningful_win    — bool: net_pnl >= meaningful_threshold
        win_count            — int: 1 if QUALIFIED_WIN, else 0
        loss_count           — int: 1 if LOSS and net_pnl != 0, else 0
        meaningful_win_count — int: 1 if QUALIFIED_WIN, else 0
        gross_win_count      — int: 1 if gross_pnl > 0, else 0
        net_win_count        — int: 1 if net_pnl > 0, else 0
        meaningful_threshold — float: the threshold net_pnl must meet
        policy_version       — str
        outcome_reason       — str: human-readable explanation
    """
    safe_gross = float(gross_pnl or 0.0)
    safe_net = float(net_pnl or 0.0)

    is_gross_win = safe_gross > 0
    is_net_win = safe_net > 0

    # Compute the meaningful-profit threshold for this trade profile
    policy = compute_min_net_profit_required(
        strategy=bot_type,
        venue=exchange,
        notional=max(float(notional or 0.0), 0.0),
        bot_equity=max(float(bot_equity or 0.0), 0.0),
        all_in_cost_bps=max(float(all_in_cost_bps or 0.0), 0.0),
        exchange=exchange,
    )
    # Apply multiplier: meaningful win must clear the min-profit threshold × multiplier
    meaningful_threshold = policy["min_net_profit_quote"] * MEANINGFUL_WIN_THRESHOLD_MULTIPLE
    is_meaningful_win = safe_net >= meaningful_threshold

    # Classify
    if not is_net_win:
        outcome_class = OUTCOME_LOSS
        outcome_reason = (
            "Net PnL is zero (flat trade)" if safe_net == 0.0
            else f"Net PnL is negative ({safe_net:.4f})"
        )
    elif not is_meaningful_win:
        outcome_class = OUTCOME_MICRO_WIN
        outcome_reason = (
            f"Net PnL {safe_net:.4f} < meaningful threshold {meaningful_threshold:.4f} "
            f"({bot_type}/{policy['capital_tier']}/{policy['venue_class']}) — "
            "positive but economically trivial"
        )
    else:
        outcome_class = OUTCOME_QUALIFIED_WIN
        outcome_reason = (
            f"Net PnL {safe_net:.4f} >= meaningful threshold {meaningful_threshold:.4f} "
            f"({bot_type}/{policy['capital_tier']}/{policy['venue_class']}) — qualified win"
        )

    is_loss = outcome_class == OUTCOME_LOSS
    is_qualified = outcome_class == OUTCOME_QUALIFIED_WIN

    return {
        "outcome_class":         outcome_class,
        "is_gross_win":          is_gross_win,
        "is_net_win":            is_net_win,
        "is_meaningful_win":     is_meaningful_win,
        "win_count":             1 if is_qualified else 0,
        "loss_count":            1 if (is_loss and safe_net != 0.0) else 0,
        "meaningful_win_count":  1 if is_qualified else 0,
        "gross_win_count":       1 if is_gross_win else 0,
        "net_win_count":         1 if is_net_win else 0,
        "meaningful_threshold":  round(meaningful_threshold, 6),
        "policy_version":        policy["policy_version"],
        "capital_tier":          policy["capital_tier"],
        "venue_class":           policy["venue_class"],
        "strategy_class":        policy["strategy_class"],
        "outcome_reason":        outcome_reason,
    }


def build_outcome_counts(trades: List[Dict]) -> Dict:
    """
    Aggregate outcome counts across a list of classified trade records.

    Each trade in the list should already have been through classify_trade_outcome()
    OR have net_pnl and gross_pnl fields.  If outcome_class is present it is used
    directly; otherwise classify_trade_outcome() is called with defaults.

    Returns
    -------
    dict with:
        total_trades         — int
        gross_green_count    — int: gross_pnl > 0
        net_green_count      — int: net_pnl > 0
        qualified_win_count  — int: is_meaningful_win
        win_count            — int: QUALIFIED_WIN only
        loss_count           — int: LOSS with net_pnl != 0
        flat_count           — int: net_pnl == 0
        micro_win_count      — int: MICRO_WIN
        meaningful_win_rate_pct — float: win_count / total_trades × 100
        gross_win_rate_pct   — float: gross_green_count / total_trades × 100
        net_win_rate_pct     — float: net_green_count / total_trades × 100
    """
    total = len(trades)
    gross_green = 0
    net_green = 0
    qualified = 0
    wins = 0
    losses = 0
    flats = 0
    micro_wins = 0

    for t in trades:
        outcome = t.get("outcome_class")
        gross_pnl = float(t.get("gross_pnl", 0) or 0)
        net_pnl = float(t.get("net_pnl", 0) or 0)

        if gross_pnl > 0:
            gross_green += 1
        if net_pnl > 0:
            net_green += 1

        if outcome == OUTCOME_QUALIFIED_WIN:
            qualified += 1
            wins += 1
        elif outcome == OUTCOME_MICRO_WIN:
            micro_wins += 1
        elif outcome == OUTCOME_LOSS:
            if net_pnl == 0.0:
                flats += 1
            else:
                losses += 1
        else:
            # outcome_class not present — use net_pnl heuristic
            if net_pnl > 0:
                qualified += 1
                wins += 1
            elif net_pnl < 0:
                losses += 1
            else:
                flats += 1

    return {
        "total_trades":              total,
        "gross_green_count":         gross_green,
        "net_green_count":           net_green,
        "qualified_win_count":       qualified,
        "win_count":                 wins,
        "loss_count":                losses,
        "flat_count":                flats,
        "micro_win_count":           micro_wins,
        "meaningful_win_rate_pct":   round(wins / total * 100, 2) if total > 0 else 0.0,
        "gross_win_rate_pct":        round(gross_green / total * 100, 2) if total > 0 else 0.0,
        "net_win_rate_pct":          round(net_green / total * 100, 2) if total > 0 else 0.0,
    }
