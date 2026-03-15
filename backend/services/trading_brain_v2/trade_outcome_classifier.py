"""
Canonical Trade Outcome Classifier for Trading Brain V2.

Classifies closed trades into three canonical outcome classes:

  OUTCOME_LOSS        – net_profit_after_all_costs <= 0
  OUTCOME_MICRO_WIN   – net profit > 0 but below minimum meaningful thresholds
                        ("scratch trade"; not a real win for this platform)
  OUTCOME_QUALIFIED_WIN – net profit > 0 AND clears BOTH:
                          • minimum absolute-profit floor (venue/quote-aware)
                          • minimum net ROI floor

A single 1-cent gain must NEVER be counted as a qualified win.

This module is the SINGLE SOURCE OF TRUTH for outcome classification and
MUST be used by all callers that track win statistics.

Depends on ``entry_thresholds.py`` for venue/tier-aware profit minimums
(reuses the same floors applied at trade entry so that only trades that
could have been approved at entry also count as qualified wins at exit).
"""
from __future__ import annotations

from typing import Optional

from .entry_thresholds import (
    ABS_PROFIT_MIN_QUOTE,
    POLICY_VERSION,
    equity_bucket,
    venue_class,
    bot_type_key,
    compute_min_net_profit_required,
)

# ── Outcome class constants ──────────────────────────────────────────────────
OUTCOME_LOSS = "LOSS"
OUTCOME_MICRO_WIN = "MICRO_WIN"
OUTCOME_QUALIFIED_WIN = "QUALIFIED_WIN"

# ── Minimum net ROI floor (%) for a trade to be a QUALIFIED_WIN ──────────────
# A trade must earn at least this return on the deployed notional after all
# costs.  This stops micro-percentage gains from being called "wins".
# Scalpers have a slightly lower bar because their hold windows are short;
# normal / mean-reversion need more because they tie up capital longer.
MIN_NET_ROI_PCT: dict[str, float] = {
    "normal":         0.08,   # 8 bps net ROI (after all costs)
    "trend":          0.08,
    "adaptive":       0.08,
    "mean_reversion": 0.06,
    "scalper":        0.05,   # 5 bps — scalper's edge is in speed, not magnitude
}

# ── Display / ZAR minimum meaningful profit (R) ──────────────────────────────
# For ZAR (Luno) venues only — absolute floor to avoid R0.01 "wins".
# These mirror the "small tier" ABS_PROFIT_MIN_QUOTE values; if the trade
# comes from a micro account we still require at least this much.
_ZAR_MICRO_FLOOR: float = 0.30    # R 0.30 absolute minimum for ZAR venues
_USDT_MICRO_FLOOR: float = 0.04   # $0.04 absolute minimum for USDT venues


def _min_meaningful_profit_quote(
    strategy: str,
    vc: str,
    tier: str,
) -> float:
    """Return the minimum meaningful absolute profit in quote currency."""
    bt = bot_type_key(strategy)
    floor = ABS_PROFIT_MIN_QUOTE.get(
        (bt, tier, vc),
        ABS_PROFIT_MIN_QUOTE.get(("normal", tier, vc), _USDT_MICRO_FLOOR),
    )
    # Ensure an unconditional hard floor even for micro accounts
    hard_floor = _ZAR_MICRO_FLOOR if vc == "zar" else _USDT_MICRO_FLOOR
    return max(floor, hard_floor)


def classify_trade_outcome(
    *,
    gross_pnl: float,
    net_pnl: float,
    notional: float,
    venue: str,
    strategy: str = "normal",
    bot_equity: float = 0.0,
    fees: float = 0.0,
    slippage: float = 0.0,
    all_in_cost_bps: float = 0.0,
    display_currency: Optional[str] = None,
    fx_rate_to_display: float = 1.0,
) -> dict:
    """
    Classify a closed trade into a canonical outcome class.

    Parameters
    ----------
    gross_pnl : float
        Raw PnL before fees/slippage (quote currency).
    net_pnl : float
        PnL after all fees and slippage (quote currency).
    notional : float
        Trade notional in quote currency.
    venue : str
        Exchange name (e.g. "luno", "binance").
    strategy : str
        Bot strategy type ("normal", "scalper", etc.).
    bot_equity : float
        Bot equity at time of trade entry (quote currency).
    fees : float
        Fees charged (quote currency).
    slippage : float
        Slippage cost (quote currency).
    all_in_cost_bps : float
        All-in round-trip cost in basis points (if known).
    display_currency : str or None
        Display currency for human-readable minimum fields.
    fx_rate_to_display : float
        FX rate from quote to display currency.

    Returns
    -------
    dict with the following keys:

      gross_pnl                        – raw PnL (quote currency)
      net_pnl                          – after-all-costs PnL (quote currency)
      fees                             – fees paid
      slippage                         – slippage cost
      gross_green                      – bool: gross_pnl > 0
      net_green                        – bool: net_pnl > 0
      qualified_win                    – bool: QUALIFIED_WIN
      outcome_class                    – LOSS / MICRO_WIN / QUALIFIED_WIN
      net_roi_pct                      – actual net ROI on notional (%)
      min_net_roi_pct                  – required minimum ROI (%)
      minimum_meaningful_profit_quote  – min profit in quote currency
      minimum_meaningful_profit_display– min profit in display currency
      minimum_meaningful_roi_pct       – same as min_net_roi_pct
      capital_tier                     – micro/small/medium/large
      venue_class                      – zar/usdt
      strategy_class                   – normalised strategy key
      policy_version                   – always POLICY_VERSION
    """
    _gross = float(gross_pnl or 0.0)
    _net = float(net_pnl or 0.0)
    _notional = max(float(notional or 0.0), 0.0)
    _equity = max(float(bot_equity or 0.0), 0.0)
    _fees = float(fees or 0.0)
    _slippage = float(slippage or 0.0)

    vc = venue_class(venue)
    bt = bot_type_key(strategy)
    tier = equity_bucket(_equity, vc)

    gross_green = _gross > 0.0
    net_green = _net > 0.0

    # ── Minimum thresholds ────────────────────────────────────────────────
    min_profit_quote = _min_meaningful_profit_quote(strategy, vc, tier)
    min_roi_pct = MIN_NET_ROI_PCT.get(bt, MIN_NET_ROI_PCT["normal"])

    # ── Actual net ROI on deployed notional ───────────────────────────────
    net_roi_pct = (_net / _notional * 100.0) if _notional > 0 else 0.0

    # ── Classify ─────────────────────────────────────────────────────────
    if _net < 0.0:
        outcome_class = OUTCOME_LOSS
        qualified_win = False
    elif _net == 0.0:
        # Exactly break-even: classified as LOSS (no return on capital),
        # but build_outcome_counts() will NOT increment loss_count for flat trades.
        outcome_class = OUTCOME_LOSS
        qualified_win = False
    elif _net < min_profit_quote or net_roi_pct < min_roi_pct:
        # Net positive but too small to be meaningful
        outcome_class = OUTCOME_MICRO_WIN
        qualified_win = False
    else:
        outcome_class = OUTCOME_QUALIFIED_WIN
        qualified_win = True

    # ── Display-currency minimum ──────────────────────────────────────────
    _fx = max(float(fx_rate_to_display or 1.0), 1e-12)
    min_profit_display = round(min_profit_quote * _fx, 4)

    return {
        "gross_pnl":                         round(_gross, 6),
        "net_pnl":                           round(_net, 6),
        "fees":                              round(_fees, 6),
        "slippage":                          round(_slippage, 6),
        "gross_green":                       gross_green,
        "net_green":                         net_green,
        "qualified_win":                     qualified_win,
        "outcome_class":                     outcome_class,
        "net_roi_pct":                       round(net_roi_pct, 4),
        "min_net_roi_pct":                   round(min_roi_pct, 4),
        "minimum_meaningful_profit_quote":   round(min_profit_quote, 4),
        "minimum_meaningful_profit_display": round(min_profit_display, 4),
        "minimum_meaningful_roi_pct":        round(min_roi_pct, 4),
        "capital_tier":                      tier,
        "venue_class":                       vc,
        "strategy_class":                    bt,
        "policy_version":                    POLICY_VERSION,
    }


def build_outcome_counts(outcome: dict) -> dict:
    """
    Return canonical win/loss counter increments from a classified outcome.

    Use this to build ``$inc`` payloads when persisting bot statistics.
    The ``win_count`` field is set only for QUALIFIED_WIN to stop 1-cent
    micro-gains from inflating the win counter.

    Returns
    -------
    dict with:
      gross_green_count  – 1 if gross_pnl > 0
      net_green_count    – 1 if net_pnl > 0
      qualified_win_count– 1 if outcome_class == QUALIFIED_WIN
      win_count          – 1 if outcome_class == QUALIFIED_WIN (backward-compat)
      loss_count         – 1 if outcome_class == LOSS
    """
    is_qw = outcome.get("outcome_class") == OUTCOME_QUALIFIED_WIN
    # Flat trades (net_pnl == 0) are classified as LOSS but don't increment loss_count
    is_loss = outcome.get("outcome_class") == OUTCOME_LOSS and float(outcome.get("net_pnl", 0)) < 0
    return {
        "gross_green_count":   int(outcome.get("gross_green", False)),
        "net_green_count":     int(outcome.get("net_green", False)),
        "qualified_win_count": int(is_qw),
        "win_count":           int(is_qw),   # backward-compat alias
        "loss_count":          int(is_loss),
    }
