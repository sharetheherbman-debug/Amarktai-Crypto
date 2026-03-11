"""
TradeFeasibilityGate – hard pre-trade gate for Trading Brain V2.

Every candidate trade must pass ALL checks before any order is sent.
Every rejection produces a structured reason code + diagnostics payload.
"""
import logging
from .reason_codes import ReasonCodes, make_decision_payload

logger = logging.getLogger(__name__)

# ── Per-strategy minimum net edge (BPS after all costs) ──
MIN_NET_EDGE_BPS = {
    "normal": 15.0,       # 0.15% net
    "trend": 15.0,
    "adaptive": 15.0,
    "mean_reversion": 12.0,
    "scalper": 8.0,       # tighter but still meaningful
}

# ── Cost multiplier: edge must be >= k * all_in_cost ──
K_COST = {
    "normal": 1.5,
    "trend": 1.5,
    "adaptive": 1.5,
    "mean_reversion": 1.3,
    "scalper": 1.2,
}

# ── Absolute profit minimums by (strategy, equity_bucket, venue_class) ──
# venue_class: "zar" for Luno, "usdt" for others
ABS_PROFIT_MIN_QUOTE = {
    ("normal", "small", "zar"): 5.0,      # R5 minimum
    ("normal", "small", "usdt"): 0.50,     # $0.50
    ("normal", "medium", "zar"): 15.0,     # R15
    ("normal", "medium", "usdt"): 1.50,    # $1.50
    ("normal", "large", "zar"): 50.0,      # R50
    ("normal", "large", "usdt"): 5.00,     # $5
    ("scalper", "small", "zar"): 2.0,      # R2
    ("scalper", "small", "usdt"): 0.20,    # $0.20
    ("scalper", "medium", "zar"): 5.0,     # R5
    ("scalper", "medium", "usdt"): 0.50,
    ("scalper", "large", "zar"): 15.0,     # R15
    ("scalper", "large", "usdt"): 1.50,
    ("mean_reversion", "small", "zar"): 4.0,
    ("mean_reversion", "small", "usdt"): 0.40,
    ("mean_reversion", "medium", "zar"): 12.0,
    ("mean_reversion", "medium", "usdt"): 1.20,
    ("mean_reversion", "large", "zar"): 40.0,
    ("mean_reversion", "large", "usdt"): 4.00,
}

# ── Spread caps (% of mid) ──
SPREAD_CAP_PCT = {
    "normal": 0.35,
    "scalper": 0.20,
    "mean_reversion": 0.30,
}

# ── Depth minimum (quote notional) ──
DEPTH_MIN_NOTIONAL = {
    "normal": 50000,
    "scalper": 30000,
    "mean_reversion": 40000,
}

# ── Strategy time caps (seconds) ──
STRATEGY_TIME_CAP = {
    "normal": 21600,       # 6 hours
    "trend": 21600,
    "adaptive": 21600,
    "mean_reversion": 10800,  # 3 hours
    "scalper": 300,           # 5 minutes
}


def _equity_bucket(equity_quote: float, venue_class: str) -> str:
    if venue_class == "zar":
        if equity_quote >= 50000:
            return "large"
        if equity_quote >= 5000:
            return "medium"
        return "small"
    else:
        if equity_quote >= 5000:
            return "large"
        if equity_quote >= 500:
            return "medium"
        return "small"


def _venue_class(venue: str) -> str:
    return "zar" if venue and venue.lower() == "luno" else "usdt"


class TradeFeasibilityGate:
    """
    Hard pre-trade gate. Returns an ENTRY_APPROVED decision payload
    or a structured rejection with reason code + diagnostics.
    """

    def evaluate(
        self,
        strategy: str,
        venue: str,
        symbol: str,
        bot_equity: float,
        notional: float,
        expected_gross_edge_bps: float,
        all_in_cost_bps: float,
        spread_pct: float,
        depth_notional: float,
        predicted_time_to_target: float = None,
        regime_result: dict = None,
        regime_eligibility: dict = None,
        concentration_ok: bool = True,
        risk_mode_ok: bool = True,
        drawdown_ok: bool = True,
        entry_confidence: float = 0.0,
        mid_price: float = 0.0,
    ) -> dict:
        """
        Run all feasibility checks. Returns decision payload.
        """
        vc = _venue_class(venue)
        strat = (strategy or "normal").lower()
        if strat in ("trend", "adaptive"):
            strat_key = strat
        elif strat == "mean_reversion":
            strat_key = "mean_reversion"
        elif strat == "scalper":
            strat_key = "scalper"
        else:
            strat_key = "normal"

        eq_bucket = _equity_bucket(bot_equity, vc)

        # ── Net edge ──
        expected_net_edge_bps = expected_gross_edge_bps - all_in_cost_bps

        # ── Projected absolute profit ──
        safe_notional = max(notional, 0.0)
        projected_net_profit_quote = safe_notional * (max(expected_net_edge_bps, 0.0) / 10000.0)

        # Common payload kwargs
        common = dict(
            confidence=entry_confidence,
            expected_gross_edge_bps=expected_gross_edge_bps,
            all_in_cost_bps=all_in_cost_bps,
            expected_net_edge_bps=expected_net_edge_bps,
            projected_net_profit_quote=projected_net_profit_quote,
            regime_label=(regime_result or {}).get("regime_label", "unknown"),
            regime_confidence=(regime_result or {}).get("regime_confidence", 0.0),
            cost_floor_source="all_in_cost_model",
        )

        # ── 1. Risk / drawdown blocks ──
        if not risk_mode_ok:
            return make_decision_payload(ReasonCodes.RISK_MODE_BLOCK, False, **common)
        if not drawdown_ok:
            return make_decision_payload(ReasonCodes.DRAWDOWN_LIMIT, False, **common)

        # ── 2. Concentration ──
        if not concentration_ok:
            return make_decision_payload(ReasonCodes.CONCENTRATION_LIMIT, False, **common)

        # ── 3. Regime eligibility ──
        if regime_eligibility and not regime_eligibility.get("eligible", True):
            action = regime_eligibility.get("action", "blocked")
            if action == "blocked":
                return make_decision_payload(ReasonCodes.REGIME_BLOCK, False, **common)
            if action == "standby":
                return make_decision_payload(ReasonCodes.REGIME_AMBIGUOUS_STANDBY, False, **common)

        # ── 4. Spread cap ──
        spread_cap = SPREAD_CAP_PCT.get(strat_key, 0.35)
        if spread_pct > spread_cap:
            return make_decision_payload(ReasonCodes.SPREAD_TOO_WIDE, False, **common)

        # ── 5. Depth ──
        depth_min = DEPTH_MIN_NOTIONAL.get(strat_key, 50000)
        if depth_notional < depth_min:
            return make_decision_payload(ReasonCodes.DEPTH_TOO_THIN, False, **common)

        # ── 6. Edge rule ──
        min_edge = MIN_NET_EDGE_BPS.get(strat_key, 15.0)
        k = K_COST.get(strat_key, 1.5)
        required_edge = max(min_edge, k * all_in_cost_bps)

        # Regime eligibility may require stricter edge
        if regime_eligibility:
            edge_mult = regime_eligibility.get("edge_multiplier", 1.0)
            required_edge *= edge_mult

        if expected_net_edge_bps < required_edge:
            return make_decision_payload(ReasonCodes.EDGE_TOO_SMALL, False, **common)

        # ── 7. Cost cap: if all-in cost > 50% of gross edge, block ──
        if all_in_cost_bps > 0 and expected_gross_edge_bps > 0:
            cost_ratio = all_in_cost_bps / expected_gross_edge_bps
            if cost_ratio > 0.65:
                return make_decision_payload(ReasonCodes.COST_TOO_HIGH, False, **common)

        # ── 8. Absolute profit rule ──
        lookup = (strat_key if strat_key in ("scalper", "mean_reversion") else "normal",
                  eq_bucket, vc)
        abs_min = ABS_PROFIT_MIN_QUOTE.get(lookup, 2.0)
        if projected_net_profit_quote < abs_min:
            return make_decision_payload(ReasonCodes.ABS_PROFIT_TOO_SMALL, False, **common)

        # ── 9. Time feasibility ──
        time_cap = STRATEGY_TIME_CAP.get(strat_key, 21600)
        if predicted_time_to_target is not None and predicted_time_to_target > time_cap:
            return make_decision_payload(ReasonCodes.TIME_FEASIBILITY_FAIL, False, **common)

        # ── All passed ──
        return make_decision_payload(
            ReasonCodes.ENTRY_APPROVED,
            True,
            max_hold_seconds=time_cap,
            hold_policy_source="trade_feasibility_gate",
            **common,
        )
