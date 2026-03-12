"""
Minimum Worthwhile Trade Filter

A focused, bot-type-aware pre-trade gate that blocks entries whose projected
absolute profit is too small relative to round-trip costs, slippage, and hold
time. This is the single source of truth for the "is this trade worth doing?"
check used outside Trading Brain V2.

All public functions return structured results with machine-readable reason
codes. No NaN, no None on numeric fields.

Reason codes:
  INSUFFICIENT_COST_EDGE         — net edge after fees/slippage is below floor
  INSUFFICIENT_ABSOLUTE_EDGE     — projected absolute profit is below minimum
  REWARD_TOO_SMALL_FOR_HOLD      — reward/time ratio is below acceptable floor
  TRADE_WORTH_FILTER_OK          — trade passes all checks
"""
from __future__ import annotations

import math
from typing import Dict, Optional


# ── Minimum net edge (BPS) after round-trip costs ─────────────────────────
# Scalpers accept a tighter floor because they trade more frequently.
MIN_NET_EDGE_BPS: Dict[str, float] = {
    "normal": 15.0,
    "trend": 15.0,
    "adaptive": 15.0,
    "mean_reversion": 12.0,
    "scalper": 8.0,
}

# ── Minimum absolute reward (quote currency) ──────────────────────────────
# Bucket: small / medium / large equity in ZAR and USDT.
#
# Calibrated for realistic minimum Luno trade economics:
#   - Small ZAR account (< 5000 ZAR): 3% notional proxy ≈ 150 ZAR max
#   - At 50 bps net edge on 150 ZAR: 0.75 ZAR profit
#   - Floor set to be achievable with ~100-300 ZAR notional at good edge.
#
# USDT accounts retain their existing floors (Binance fees are lower and
# USDT liquidity is higher, so these are still meaningful).
_ABS_MIN_QUOTE: Dict[tuple, float] = {
    # (bot_type, equity_bucket, venue_class) -> min profit in quote
    ("normal",  "small",  "zar"):  1.50,
    ("normal",  "medium", "zar"):  6.00,
    ("normal",  "large",  "zar"): 20.00,
    ("normal",  "small",  "usdt"): 0.80,
    ("normal",  "medium", "usdt"): 2.00,
    ("normal",  "large",  "usdt"): 6.00,
    ("scalper", "small",  "zar"):  0.50,
    ("scalper", "medium", "zar"):  2.00,
    ("scalper", "large",  "zar"):  8.00,
    ("scalper", "small",  "usdt"): 0.20,
    ("scalper", "medium", "usdt"): 0.50,
    ("scalper", "large",  "usdt"): 1.50,
}

# ── Minimum reward-per-second floor ───────────────────────────────────────
# Guards against trades that lock capital too long for negligible reward.
# Units: quote currency per second
_MIN_REWARD_PER_SECOND: Dict[str, Dict[str, float]] = {
    "zar": {
        "normal":  0.005,   # R0.005/s → R18/h minimum acceptable
        "scalper": 0.010,   # R0.01/s  → scalpers must earn faster
    },
    "usdt": {
        "normal":  0.0005,
        "scalper": 0.0010,
    },
}

# ── Equity bucket thresholds ───────────────────────────────────────────────
_EQUITY_THRESHOLDS_ZAR = (5_000, 50_000)   # small < 5k, medium 5k-50k, large >50k
_EQUITY_THRESHOLDS_USDT = (500, 5_000)


def _safe_float(v, default: float = 0.0) -> float:
    """Coerce value to float; return default for None/NaN/Inf."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _equity_bucket(equity: float, venue_class: str) -> str:
    thresholds = (
        _EQUITY_THRESHOLDS_ZAR if venue_class == "zar" else _EQUITY_THRESHOLDS_USDT
    )
    if equity >= thresholds[1]:
        return "large"
    if equity >= thresholds[0]:
        return "medium"
    return "small"


def _venue_class(exchange: str) -> str:
    return "zar" if (exchange or "").lower() == "luno" else "usdt"


def _bot_type_key(bot_type: str) -> str:
    bt = (bot_type or "normal").lower()
    if bt in ("scalper",):
        return "scalper"
    return "normal"


def evaluate_minimum_worthwhile_trade(
    *,
    bot_type: str,
    exchange: str,
    bot_equity: float,
    notional: float,
    expected_gross_edge_bps: float,
    all_in_cost_bps: float,
    predicted_hold_seconds: Optional[float] = None,
) -> Dict:
    """
    Evaluate whether a proposed trade meets the minimum worthwhile threshold.

    Parameters
    ----------
    bot_type : str
        "normal" | "scalper" | "trend" | "adaptive" | "mean_reversion"
    exchange : str
        Exchange name (e.g. "luno", "binance")
    bot_equity : float
        Bot's current capital in quote currency
    notional : float
        Proposed trade notional in quote currency
    expected_gross_edge_bps : float
        Expected gross edge in basis points (before costs)
    all_in_cost_bps : float
        Round-trip cost estimate in basis points (fees + slippage)
    predicted_hold_seconds : float or None
        Expected hold duration in seconds (used for reward-rate check)

    Returns
    -------
    dict with fields:
      approved : bool
      reason_code : str
      reason_text : str
      expected_net_edge_bps : float
      projected_net_profit_quote : float
      min_net_edge_required_bps : float
      min_abs_profit_required : float
      diagnostics : dict
    """
    vc = _venue_class(exchange)
    bt = _bot_type_key(bot_type)

    safe_equity = _safe_float(bot_equity)
    safe_notional = _safe_float(notional)
    gross_bps = _safe_float(expected_gross_edge_bps)
    cost_bps = _safe_float(all_in_cost_bps)

    net_edge_bps = gross_bps - cost_bps
    projected_net_profit = safe_notional * (max(net_edge_bps, 0.0) / 10_000.0)

    min_edge = MIN_NET_EDGE_BPS.get(bt, MIN_NET_EDGE_BPS["normal"])
    eq_bucket = _equity_bucket(safe_equity, vc)
    abs_min = _ABS_MIN_QUOTE.get((bt, eq_bucket, vc), _ABS_MIN_QUOTE.get(("normal", eq_bucket, vc), 5.0))

    diagnostics = {
        "bot_type": bt,
        "venue_class": vc,
        "equity_bucket": eq_bucket,
        "net_edge_bps": round(net_edge_bps, 4),
        "gross_edge_bps": round(gross_bps, 4),
        "cost_bps": round(cost_bps, 4),
        "projected_net_profit": round(projected_net_profit, 4),
        "min_edge_required_bps": min_edge,
        "min_abs_profit_required": abs_min,
    }

    # ── Check 1: net edge floor ───────────────────────────────────────────
    if net_edge_bps < min_edge:
        return {
            "approved": False,
            "reason_code": "INSUFFICIENT_COST_EDGE",
            "reason_text": (
                f"Net edge {net_edge_bps:.1f} BPS is below the {min_edge:.1f} BPS "
                f"floor required for {bt} bots."
            ),
            "expected_net_edge_bps": round(net_edge_bps, 4),
            "projected_net_profit_quote": round(projected_net_profit, 4),
            "min_net_edge_required_bps": min_edge,
            "min_abs_profit_required": abs_min,
            "diagnostics": diagnostics,
        }

    # ── Check 2: absolute profit floor ────────────────────────────────────
    if projected_net_profit < abs_min:
        return {
            "approved": False,
            "reason_code": "INSUFFICIENT_ABSOLUTE_EDGE",
            "reason_text": (
                f"Projected net profit {projected_net_profit:.2f} is below the "
                f"{abs_min:.2f} minimum for {bt}/{eq_bucket}/{vc}."
            ),
            "expected_net_edge_bps": round(net_edge_bps, 4),
            "projected_net_profit_quote": round(projected_net_profit, 4),
            "min_net_edge_required_bps": min_edge,
            "min_abs_profit_required": abs_min,
            "diagnostics": diagnostics,
        }

    # ── Check 3: reward-rate floor (when hold duration is known) ──────────
    if predicted_hold_seconds and predicted_hold_seconds > 0:
        reward_per_sec = projected_net_profit / predicted_hold_seconds
        floor_per_sec = _MIN_REWARD_PER_SECOND.get(vc, {}).get(bt, 0.005)
        if reward_per_sec < floor_per_sec:
            return {
                "approved": False,
                "reason_code": "REWARD_TOO_SMALL_FOR_HOLD",
                "reason_text": (
                    f"Reward rate {reward_per_sec:.6f}/s is below floor "
                    f"{floor_per_sec:.6f}/s for {bt} hold of {predicted_hold_seconds:.0f}s."
                ),
                "expected_net_edge_bps": round(net_edge_bps, 4),
                "projected_net_profit_quote": round(projected_net_profit, 4),
                "min_net_edge_required_bps": min_edge,
                "min_abs_profit_required": abs_min,
                "diagnostics": {**diagnostics, "reward_per_sec": round(reward_per_sec, 6), "floor_per_sec": floor_per_sec},
            }

    # ── All checks passed ─────────────────────────────────────────────────
    return {
        "approved": True,
        "reason_code": "TRADE_WORTH_FILTER_OK",
        "reason_text": "Trade meets all minimum worthwhile thresholds.",
        "expected_net_edge_bps": round(net_edge_bps, 4),
        "projected_net_profit_quote": round(projected_net_profit, 4),
        "min_net_edge_required_bps": min_edge,
        "min_abs_profit_required": abs_min,
        "diagnostics": diagnostics,
    }
