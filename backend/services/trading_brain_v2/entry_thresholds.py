"""
Canonical entry threshold definitions for Trading Brain V2.

This is the SINGLE SOURCE OF TRUTH for all entry gate thresholds.
Both trade_feasibility_gate.py and trade_worth_filter.py import from here.

No duplicate threshold definitions should exist elsewhere.
"""
from __future__ import annotations

import os
from typing import Dict, Tuple

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
# trade worth filter.  Previous discrepancies (e.g. USDT normal/small
# was $0.80 in worth filter vs $0.50 in feasibility gate) are resolved
# in favour of the feasibility gate values.
ABS_PROFIT_MIN_QUOTE: Dict[Tuple[str, str, str], float] = {
    ("normal", "small", "zar"): 3.00,
    ("normal", "small", "usdt"): 0.50,
    ("normal", "medium", "zar"): 12.00,
    ("normal", "medium", "usdt"): 1.50,
    ("normal", "large", "zar"): 40.00,
    ("normal", "large", "usdt"): 5.00,
    ("scalper", "small", "zar"): 1.50,
    ("scalper", "small", "usdt"): 0.20,
    ("scalper", "medium", "zar"): 5.00,
    ("scalper", "medium", "usdt"): 0.50,
    ("scalper", "large", "zar"): 15.00,
    ("scalper", "large", "usdt"): 1.50,
    ("mean_reversion", "small", "zar"): 3.00,
    ("mean_reversion", "small", "usdt"): 0.40,
    ("mean_reversion", "medium", "zar"): 10.00,
    ("mean_reversion", "medium", "usdt"): 1.20,
    ("mean_reversion", "large", "zar"): 30.00,
    ("mean_reversion", "large", "usdt"): 4.00,
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
EQUITY_THRESHOLDS_ZAR: Tuple[int, int] = (5_000, 50_000)
EQUITY_THRESHOLDS_USDT: Tuple[int, int] = (500, 5_000)

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

# ── Minimum projected net profit (flat floor, all strategies) ────────────
# Applied as the final economic gate, AFTER position sizing, edge, and cost
# checks.  Ensures that only trades with meaningful dollar/rand profit are
# approved regardless of BPS edge or notional size.
#   usdt: Binance and all non-Luno USDT-denominated venues
#   zar:  Luno and all ZAR-denominated venues
MIN_PROJECTED_NET_PROFIT: Dict[str, float] = {
    "usdt": 1.5,    # minimum $1.50 net profit per trade
    "zar": 25.0,    # minimum R25.00 net profit per trade
}

# ── Venue-specific round-trip cost estimates (BPS) for exit logic ─────────
# Used by cost-aware no-progress exit to determine whether PnL covers costs.
VENUE_ROUND_TRIP_COST_BPS: Dict[str, float] = {
    "luno": 35.0,       # Luno maker+taker + spread + slippage (ZAR)
    "binance": 20.0,     # Binance taker round-trip (USDT)
    "kucoin": 20.0,
    "bybit": 20.0,
    "kraken": 30.0,
    "default": 25.0,
}


# ── Helper functions ──────────────────────────────────────────────────────

def equity_bucket(equity_quote: float, venue_class: str) -> str:
    """Classify equity into small/medium/large bucket."""
    if venue_class == "zar":
        if equity_quote >= EQUITY_THRESHOLDS_ZAR[1]:
            return "large"
        if equity_quote >= EQUITY_THRESHOLDS_ZAR[0]:
            return "medium"
        return "small"
    else:
        if equity_quote >= EQUITY_THRESHOLDS_USDT[1]:
            return "large"
        if equity_quote >= EQUITY_THRESHOLDS_USDT[0]:
            return "medium"
        return "small"


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
