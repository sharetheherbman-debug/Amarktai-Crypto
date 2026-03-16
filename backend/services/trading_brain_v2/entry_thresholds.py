"""
Canonical entry threshold definitions for Trading Brain V2.

This is the SINGLE SOURCE OF TRUTH for all entry gate thresholds.
Both trade_feasibility_gate.py and trade_worth_filter.py import from here.

No duplicate threshold definitions should exist elsewhere.

Policy version: v2
  - Added micro capital tier (< R1 000 ZAR / < $100 USDT)
  - Added bitget and gate exchange cost profiles
  - compute_min_net_profit_required() replaces the flat MIN_PROJECTED_NET_PROFIT
    floor and unifies ABS_PROFIT_MIN_QUOTE + cost-coverage into a single
    canonical policy function that scales with capital tier.
  - Paper and live modes share the same policy — no fake paper relaxations.
"""
from __future__ import annotations

import os
from typing import Dict, Tuple

# ── Policy version ────────────────────────────────────────────────────────
POLICY_VERSION: str = "v2"

# ── Meaningful-win threshold multiplier ───────────────────────────────────
# A trade is only a "meaningful win" if net_pnl >= min_profit_required × this multiplier.
# This ensures small positive net profits that barely exceed costs are classified
# as MICRO_WIN rather than QUALIFIED_WIN, preventing fake-win inflation in reports.
MEANINGFUL_WIN_THRESHOLD_MULTIPLE: float = float(
    __import__("os").getenv("MEANINGFUL_WIN_THRESHOLD_MULTIPLE", "1.5")
)

# ── Minimum net edge (BPS) after round-trip costs ─────────────────────────
# Per-strategy: the minimum post-cost edge required for any entry.
# Scalpers use a meaningful 20 BPS floor (not the old 8 BPS) because
# tight hold windows demand real edge to overcome costs.
MIN_NET_EDGE_BPS: Dict[str, float] = {
    "normal": 15.0,
    "trend": 15.0,
    "adaptive": 15.0,
    "mean_reversion": 12.0,
    "scalper": 20.0,
}

# ── Cost multiplier: edge must be >= K * all_in_cost ──────────────────────
K_COST: Dict[str, float] = {
    "normal": 1.5,
    "trend": 1.5,
    "adaptive": 1.5,
    "mean_reversion": 1.3,
    "scalper": 1.5,
}

# ── Maximum acceptable cost as percentage of gross edge ───────────────────
MAX_COST_TO_EDGE_RATIO: float = 0.55

# ── Minimum entry confidence score ────────────────────────────────────────
MIN_ENTRY_CONFIDENCE: float = float(os.getenv("MIN_ENTRY_CONFIDENCE", "0.40"))

# ── Absolute profit minimums by (strategy, equity_bucket, venue_class) ────
# venue_class: "zar" for Luno, "usdt" for others
# These are the canonical minimums used by BOTH feasibility gate and
# trade worth filter.  Four capital tiers: micro / small / medium / large.
# Scalpers require less absolute profit than normal bots (shorter holds)
# but must still clear round-trip costs + a meaningful safety margin.
ABS_PROFIT_MIN_QUOTE: Dict[Tuple[str, str, str], float] = {
    # ── micro tier (< R1 000 ZAR / < $100 USDT) ───────────────────────────
    ("normal",        "micro", "zar"):  0.75,
    ("normal",        "micro", "usdt"): 0.10,
    ("scalper",       "micro", "zar"):  0.30,
    ("scalper",       "micro", "usdt"): 0.04,
    ("mean_reversion","micro", "zar"):  0.60,
    ("mean_reversion","micro", "usdt"): 0.08,
    # ── small tier ────────────────────────────────────────────────────────
    ("normal",        "small", "zar"):  1.50,
    ("normal",        "small", "usdt"): 0.50,
    ("scalper",       "small", "zar"):  1.50,
    ("scalper",       "small", "usdt"): 0.20,
    ("mean_reversion","small", "zar"):  3.00,
    ("mean_reversion","small", "usdt"): 0.40,
    # ── medium tier ───────────────────────────────────────────────────────
    ("normal",        "medium", "zar"):  12.00,
    ("normal",        "medium", "usdt"):  1.50,
    ("scalper",       "medium", "zar"):   5.00,
    ("scalper",       "medium", "usdt"):  0.50,
    ("mean_reversion","medium", "zar"):  10.00,
    ("mean_reversion","medium", "usdt"):  1.20,
    # ── large tier ────────────────────────────────────────────────────────
    ("normal",        "large", "zar"):  40.00,
    ("normal",        "large", "usdt"):  5.00,
    ("scalper",       "large", "zar"):  15.00,
    ("scalper",       "large", "usdt"):  1.50,
    ("mean_reversion","large", "zar"):  30.00,
    ("mean_reversion","large", "usdt"):  4.00,
}

# ── Minimum reward-per-second floor ───────────────────────────────────────
# Units: quote currency per second
MIN_REWARD_PER_SECOND: Dict[str, Dict[str, float]] = {
    "zar": {
        "normal": 0.005,
        "scalper": 0.010,
    },
    "usdt": {
        "normal": 0.0005,
        "scalper": 0.0010,
    },
}

# ── Equity bucket thresholds ──────────────────────────────────────────────
# 3-value tuples → 4 tiers: micro / small / medium / large
# micro:  equity < thresholds[0]
# small:  thresholds[0] <= equity < thresholds[1]
# medium: thresholds[1] <= equity < thresholds[2]
# large:  equity >= thresholds[2]
EQUITY_THRESHOLDS_ZAR: Tuple[int, int, int] = (1_000, 5_000, 50_000)
EQUITY_THRESHOLDS_USDT: Tuple[int, int, int] = (100, 500, 5_000)

# ── Spread caps (% of mid) ───────────────────────────────────────────────
SPREAD_CAP_PCT: Dict[str, float] = {
    "normal": 0.35,
    "scalper": 0.20,
    "mean_reversion": 0.30,
}

# ── Depth minimum (quote notional) ───────────────────────────────────────
DEPTH_MIN_NOTIONAL: Dict[str, float] = {
    "normal": 50000,
    "scalper": 30000,
    "mean_reversion": 40000,
}

# ── Strategy time caps (seconds) ─────────────────────────────────────────
STRATEGY_TIME_CAP: Dict[str, int] = {
    "normal": 21600,
    "trend": 21600,
    "adaptive": 21600,
    "mean_reversion": 10800,
    "scalper": 300,
}

# ── Minimum projected net profit (legacy flat floor reference) ────────────
# NOTE: This dict is retained for backward-compatibility. The authoritative
# minimum-profit computation is now done by compute_min_net_profit_required()
# which uses ABS_PROFIT_MIN_QUOTE per capital tier.  These values represent
# the minimum for the "large" capital tier and serve only as a hard outer cap.
MIN_PROJECTED_NET_PROFIT: Dict[str, float] = {
    "usdt": 1.5,    # $1.50 — applies only to medium/large tier fallback
    "zar": 25.0,    # R25.00 — applies only to medium/large tier fallback
}

# ── Venue safety buffer (BPS added above round-trip cost) ────────────────
# Ensures projected profit clears not just costs but also a small margin.
VENUE_SAFETY_BUFFER_BPS: Dict[str, float] = {
    "luno":    10.0,
    "binance":  8.0,
    "kucoin":   8.0,
    "bybit":    8.0,
    "kraken":  10.0,
    "bitget":   8.0,
    "gate":    10.0,
    "default":  8.0,
}

# ── Venue-specific round-trip cost estimates (BPS) for exit logic ─────────
# Used by cost-aware no-progress exit to determine whether PnL covers costs.
VENUE_ROUND_TRIP_COST_BPS: Dict[str, float] = {
    "luno":    35.0,    # Luno maker+taker + spread + slippage (ZAR)
    "binance": 20.0,    # Binance taker round-trip (USDT)
    "kucoin":  20.0,
    "bybit":   20.0,
    "kraken":  30.0,
    "bitget":  20.0,
    "gate":    22.0,
    "default": 25.0,
}


# ── Helper functions ──────────────────────────────────────────────────────

def equity_bucket(equity_quote: float, venue_class: str) -> str:
    """Classify equity into micro/small/medium/large bucket."""
    if venue_class == "zar":
        micro_max, small_max, medium_max = EQUITY_THRESHOLDS_ZAR
        if equity_quote >= medium_max:
            return "large"
        if equity_quote >= small_max:
            return "medium"
        if equity_quote >= micro_max:
            return "small"
        return "micro"
    else:
        micro_max, small_max, medium_max = EQUITY_THRESHOLDS_USDT
        if equity_quote >= medium_max:
            return "large"
        if equity_quote >= small_max:
            return "medium"
        if equity_quote >= micro_max:
            return "small"
        return "micro"


def venue_class(venue: str) -> str:
    """Classify venue into 'zar' or 'usdt'."""
    return "zar" if venue and venue.lower() == "luno" else "usdt"


def bot_type_key(bot_type: str) -> str:
    """Normalize bot type for threshold lookups."""
    bt = (bot_type or "normal").lower()
    if bt in ("scalper",):
        return "scalper"
    if bt in ("mean_reversion",):
        return "mean_reversion"
    return "normal"


def venue_round_trip_cost_bps(exchange: str) -> float:
    """Return estimated round-trip cost in BPS for a venue."""
    return VENUE_ROUND_TRIP_COST_BPS.get(
        (exchange or "").lower(),
        VENUE_ROUND_TRIP_COST_BPS["default"],
    )


def compute_min_net_profit_required(
    strategy: str,
    venue: str,
    notional: float,
    bot_equity: float,
    all_in_cost_bps: float,
    exchange: str = None,
) -> dict:
    """
    Canonical policy function: compute the minimum net profit required for a
    trade to be approved.

    Replaces the old flat MIN_PROJECTED_NET_PROFIT check with a tier-aware,
    venue-aware, cost-inclusive policy.

    min_required = max(
        cost_coverage_floor,   # notional × (all_in_cost_bps + safety_buffer_bps) / 10 000
        strategy_floor,        # ABS_PROFIT_MIN_QUOTE[strategy, tier, venue_class]
    )

    Both paper and live modes use this same function — no fake paper relaxation.

    Returns
    -------
    dict with keys:
      min_net_profit_quote     – the required minimum
      cost_floor_quote         – component: cost coverage floor
      safety_buffer_quote      – component: safety buffer above costs
      strategy_floor_quote     – component: tier/strategy/venue floor
      capital_tier             – micro / small / medium / large
      venue_class              – zar / usdt
      strategy_class           – normal / scalper / mean_reversion
      policy_version           – always POLICY_VERSION
    """
    exch = (exchange or venue or "").lower()
    vc = venue_class(venue)
    bt = bot_type_key(strategy)
    tier = equity_bucket(max(float(bot_equity or 0.0), 0.0), vc)

    safe_notional = max(float(notional or 0.0), 0.0)

    # ── Cost coverage floor ───────────────────────────────────────────────
    # Trade must earn back round-trip costs plus a safety buffer.
    safety_bps = VENUE_SAFETY_BUFFER_BPS.get(exch, VENUE_SAFETY_BUFFER_BPS["default"])
    cost_floor = safe_notional * (float(all_in_cost_bps or 0.0) + safety_bps) / 10_000.0
    safety_component = safe_notional * safety_bps / 10_000.0

    # ── Strategy / tier floor ────────────────────────────────────────────
    # Per-tier, per-strategy minimum that scales with account size.
    strategy_floor = ABS_PROFIT_MIN_QUOTE.get(
        (bt, tier, vc),
        ABS_PROFIT_MIN_QUOTE.get(("normal", tier, vc), 0.10),
    )

    min_required = max(cost_floor, strategy_floor)

    return {
        "min_net_profit_quote":  round(min_required, 6),
        "cost_floor_quote":      round(cost_floor, 6),
        "safety_buffer_quote":   round(safety_component, 6),
        "strategy_floor_quote":  round(strategy_floor, 6),
        "capital_tier":          tier,
        "venue_class":           vc,
        "strategy_class":        bt,
        "policy_version":        POLICY_VERSION,
        "policy_source":         "entry_thresholds.compute_min_net_profit_required",
    }
