"""
Structured reason codes for Trading Brain V2.

Every skip / approval must produce a machine-readable reason code
and a human-readable reason text. No NaN, no None, no blank.
"""


class ReasonCodes:
    """Canonical reason-code constants for trade decisions."""

    # ── Approval ──
    ENTRY_APPROVED = "ENTRY_APPROVED"

    # ── Cost / Edge ──
    EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
    COST_TOO_HIGH = "COST_TOO_HIGH"
    ABS_PROFIT_TOO_SMALL = "ABS_PROFIT_TOO_SMALL"

    # ── Market quality ──
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    DEPTH_TOO_THIN = "DEPTH_TOO_THIN"
    BOOK_UNSTABLE = "BOOK_UNSTABLE"

    # ── Regime ──
    REGIME_BLOCK = "REGIME_BLOCK"
    REGIME_LOW_VOL = "REGIME_LOW_VOL"
    REGIME_AMBIGUOUS_STANDBY = "REGIME_AMBIGUOUS_STANDBY"

    # ── Risk ──
    CONCENTRATION_LIMIT = "CONCENTRATION_LIMIT"
    RISK_MODE_BLOCK = "RISK_MODE_BLOCK"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"

    # ── Time ──
    TIME_FEASIBILITY_FAIL = "TIME_FEASIBILITY_FAIL"

    # ── Open-trade management exits ──
    NO_PROGRESS_EXIT = "NO_PROGRESS_EXIT"
    EDGE_DECAY_EXIT = "EDGE_DECAY_EXIT"
    MICROSTRUCTURE_BREAK_EXIT = "MICROSTRUCTURE_BREAK_EXIT"
    TIME_BUDGET_EXIT = "TIME_BUDGET_EXIT"
    EARLY_INVALIDATION_EXIT = "EARLY_INVALIDATION_EXIT"

    # ── Scalper-specific ──
    SCALPER_LOSS_STREAK_COOLDOWN = "SCALPER_LOSS_STREAK_COOLDOWN"
    SCALPER_DAILY_BUDGET_EXHAUSTED = "SCALPER_DAILY_BUDGET_EXHAUSTED"
    SCALPER_COVERAGE_THROTTLE = "SCALPER_COVERAGE_THROTTLE"

    # ── System / infra ──
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    VENUE_UNAVAILABLE = "VENUE_UNAVAILABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    ADAPTIVE_STAND_DOWN = "ADAPTIVE_STAND_DOWN"

    # ── Capital ──
    CAPITAL_TOO_SMALL = "CAPITAL_TOO_SMALL"
    POSITION_SIZE_BELOW_MIN = "POSITION_SIZE_BELOW_MIN"


# Human-readable descriptions for UI/diagnostics
REASON_CATALOG = {
    ReasonCodes.ENTRY_APPROVED: "Trade approved – all economics gates passed.",
    ReasonCodes.EDGE_TOO_SMALL: "Net edge after costs is below minimum threshold.",
    ReasonCodes.COST_TOO_HIGH: "All-in round-trip cost exceeds edge capacity.",
    ReasonCodes.ABS_PROFIT_TOO_SMALL: "Projected absolute profit is below minimum for this equity/venue class.",
    ReasonCodes.SPREAD_TOO_WIDE: "Current bid-ask spread exceeds venue/strategy limit.",
    ReasonCodes.DEPTH_TOO_THIN: "Order book depth insufficient for notional size.",
    ReasonCodes.BOOK_UNSTABLE: "Order book instability detected – spread or depth changing too fast.",
    ReasonCodes.REGIME_BLOCK: "Market regime is incompatible with this strategy.",
    ReasonCodes.REGIME_LOW_VOL: "Low volatility regime – insufficient movement expected.",
    ReasonCodes.REGIME_AMBIGUOUS_STANDBY: "Regime is ambiguous – reduced activity, waiting for clarity.",
    ReasonCodes.CONCENTRATION_LIMIT: "Position would exceed symbol/venue concentration cap.",
    ReasonCodes.RISK_MODE_BLOCK: "Risk mode or drawdown limits prevent new entries.",
    ReasonCodes.DRAWDOWN_LIMIT: "Portfolio drawdown limit reached.",
    ReasonCodes.TIME_FEASIBILITY_FAIL: "Predicted time to target exceeds strategy time cap.",
    ReasonCodes.NO_PROGRESS_EXIT: "Trade showed no progress within time budget – exiting.",
    ReasonCodes.EDGE_DECAY_EXIT: "Net edge decayed below cost threshold – exiting.",
    ReasonCodes.MICROSTRUCTURE_BREAK_EXIT: "Microstructure deteriorated sharply – scalper exit.",
    ReasonCodes.TIME_BUDGET_EXIT: "Trade exceeded time budget – exiting.",
    ReasonCodes.EARLY_INVALIDATION_EXIT: "Entry thesis invalidated early – exiting.",
    ReasonCodes.SCALPER_LOSS_STREAK_COOLDOWN: "Scalper loss-streak cooldown active.",
    ReasonCodes.SCALPER_DAILY_BUDGET_EXHAUSTED: "Scalper daily trade budget exhausted.",
    ReasonCodes.SCALPER_COVERAGE_THROTTLE: "Scalper coverage throttle – too many recent entries.",
    ReasonCodes.INSUFFICIENT_BALANCE: "Insufficient wallet balance for trade.",
    ReasonCodes.VENUE_UNAVAILABLE: "Venue API unavailable or degraded.",
    ReasonCodes.MARKET_DATA_STALE: "Market data is stale or unavailable.",
    ReasonCodes.ADAPTIVE_STAND_DOWN: "Adaptive discipline triggered stand-down.",
    ReasonCodes.CAPITAL_TOO_SMALL: "Bot capital too small for meaningful trading.",
    ReasonCodes.POSITION_SIZE_BELOW_MIN: "Calculated position size below exchange minimum.",
}


def safe_reason_text(code: str) -> str:
    """Return human-readable text for a reason code. Never returns None."""
    return REASON_CATALOG.get(code, f"Reason: {code}")


def make_decision_payload(
    reason_code: str,
    approved: bool,
    *,
    confidence: float = 0.0,
    expected_gross_edge_bps: float = 0.0,
    all_in_cost_bps: float = 0.0,
    expected_net_edge_bps: float = 0.0,
    projected_net_profit_quote: float = 0.0,
    trade_profit_target_quote: float = 0.0,
    daily_profit_target_quote: float = 0.0,
    max_hold_seconds: int = 0,
    regime_label: str = "unknown",
    regime_confidence: float = 0.0,
    hold_policy_source: str = "",
    target_source: str = "",
    cost_floor_source: str = "",
    extra: dict = None,
) -> dict:
    """
    Build a render-safe decision payload for UI consumption.
    All numeric fields default to 0.0 (never NaN/None).
    All string fields default to empty string (never None).
    """
    def _sf(v):
        """Safe float – coerce None/NaN/Inf to 0.0."""
        if v is None:
            return 0.0
        try:
            f = float(v)
            if f != f or f == float('inf') or f == float('-inf'):  # NaN/Inf check
                return 0.0
            return round(f, 6)
        except (TypeError, ValueError):
            return 0.0

    def _ss(v):
        """Safe string – coerce None to empty."""
        return str(v) if v is not None else ""

    payload = {
        "decision_reason_code": _ss(reason_code),
        "decision_reason_text": safe_reason_text(reason_code),
        "entry_reason_code": _ss(reason_code),
        "entry_confidence_score": _sf(confidence),
        "approved": bool(approved),
        "regime_label": _ss(regime_label),
        "regime_confidence": _sf(regime_confidence),
        "expected_gross_edge_bps": _sf(expected_gross_edge_bps),
        "all_in_cost_bps": _sf(all_in_cost_bps),
        "expected_net_edge_bps": _sf(expected_net_edge_bps),
        "projected_net_profit_quote": _sf(projected_net_profit_quote),
        "trade_profit_target_quote": _sf(trade_profit_target_quote),
        "daily_profit_target_quote": _sf(daily_profit_target_quote),
        "max_hold_seconds": max(0, int(max_hold_seconds or 0)),
        "hold_policy_source": _ss(hold_policy_source),
        "target_source": _ss(target_source),
        "cost_floor_source": _ss(cost_floor_source),
    }
    if extra:
        payload.update(extra)
    return payload
