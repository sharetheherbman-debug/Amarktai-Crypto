"""
OpenTradeManager – dead-capital exit rules for open positions.

Implements time-budget exits, edge-decay exits, microstructure breaks,
and cost-aware no-progress exits. Prevents dead-capital holding.
"""
import logging
import time

from .reason_codes import ReasonCodes
from .entry_thresholds import venue_round_trip_cost_bps, venue_class

logger = logging.getLogger(__name__)

# ── Early-invalidation thresholds ──
# If a trade loses more than this percentage within the first portion of
# its time budget, the entry thesis is likely wrong — exit immediately.
EARLY_INVALIDATION_TIME_FRACTION = 0.3   # first 30% of time budget
EARLY_INVALIDATION_LOSS_PCT = -0.5       # -0.5% loss triggers exit


class OpenTradeManager:
    """
    Evaluate whether an open trade should be closed early
    based on economic and time-budget rules.
    """

    def evaluate(
        self,
        trade: dict,
        bot_type: str,
        max_hold_seconds: int,
        current_price: float,
        entry_price: float,
        current_spread_pct: float = 0.0,
        current_depth_notional: float = 0.0,
        current_edge_bps: float = 0.0,
        all_in_cost_bps: float = 0.0,
        regime_label: str = "unknown",
        regime_confidence: float = 0.5,
        exchange: str = "",
    ) -> dict:
        """
        Evaluate whether an open trade should exit early.

        Returns: {should_exit: bool, reason_code, reason_text, details}
        """
        opened_at = trade.get("opened_at") or trade.get("entry_time")
        if not opened_at:
            return {"should_exit": False, "reason_code": None, "reason_text": "", "details": {}}

        # Parse time
        if isinstance(opened_at, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                elapsed = time.time() - dt.timestamp()
            except (ValueError, TypeError):
                elapsed = 0
        elif isinstance(opened_at, (int, float)):
            elapsed = time.time() - opened_at
        else:
            elapsed = 0

        bt = (bot_type or "normal").lower()
        safe_max_hold = max(max_hold_seconds, 60)
        time_fraction = elapsed / safe_max_hold

        # PnL progress
        if entry_price > 0 and current_price > 0:
            side = trade.get("side", "buy")
            if side == "buy":
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100
        else:
            pnl_pct = 0.0

        # ── Repair 5: Cost-Aware No-Progress Exit ──
        # Determine venue-specific round-trip cost to use as the no-progress
        # threshold.  A trade that hasn't covered its round-trip costs by the
        # time-budget point is effectively "no progress" because closing it
        # would not cover the fees already incurred.
        _venue = (exchange or trade.get("exchange", "")).lower()
        _rt_cost_bps = venue_round_trip_cost_bps(_venue)
        # Convert BPS to pct for comparison with pnl_pct
        _no_progress_pct = _rt_cost_bps / 100.0  # e.g. 35 bps → 0.35%
        _vc = venue_class(_venue)

        # ── 1. Cost-aware time budget exit ──
        time_budget_pct = 0.6 if bt == "scalper" else 0.75
        if time_fraction >= time_budget_pct and pnl_pct <= _no_progress_pct:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.NO_PROGRESS_EXIT,
                "reason_text": (
                    f"No progress at {time_fraction:.0%} of time budget "
                    f"({elapsed:.0f}s/{safe_max_hold}s). PnL: {pnl_pct:.2f}% "
                    f"below venue cost threshold {_no_progress_pct:.2f}% "
                    f"({_venue or 'default'}: {_rt_cost_bps:.0f} bps round-trip)."
                ),
                "details": {
                    "elapsed": elapsed,
                    "max_hold": safe_max_hold,
                    "pnl_pct": pnl_pct,
                    "no_progress_threshold_pct": _no_progress_pct,
                    "venue_round_trip_cost_bps": _rt_cost_bps,
                    "venue_class": _vc,
                },
            }

        # ── 2. Full time budget exit ──
        if time_fraction >= 1.0:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.TIME_BUDGET_EXIT,
                "reason_text": f"Time budget expired ({elapsed:.0f}s/{safe_max_hold}s).",
                "details": {"elapsed": elapsed, "max_hold": safe_max_hold, "pnl_pct": pnl_pct},
            }

        # ── 3. Edge decay exit ──
        if current_edge_bps > 0 and all_in_cost_bps > 0:
            net_edge = current_edge_bps - all_in_cost_bps
            if net_edge < 0 and time_fraction > 0.3:
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.EDGE_DECAY_EXIT,
                    "reason_text": f"Edge decayed below cost ({net_edge:.1f} bps net). Exiting.",
                    "details": {"current_edge_bps": current_edge_bps, "cost_bps": all_in_cost_bps},
                }

        # ── 4. Microstructure break (scalper-specific) ──
        if bt == "scalper":
            if current_spread_pct > 0.20:  # 20 bps
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.MICROSTRUCTURE_BREAK_EXIT,
                    "reason_text": f"Spread widened to {current_spread_pct:.2f}% – scalper microstructure break.",
                    "details": {"spread_pct": current_spread_pct},
                }
            if current_depth_notional > 0 and current_depth_notional < 20000:
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.MICROSTRUCTURE_BREAK_EXIT,
                    "reason_text": f"Depth dropped to {current_depth_notional:.0f} – scalper exit.",
                    "details": {"depth_notional": current_depth_notional},
                }

        # ── 5. Early invalidation ──
        if time_fraction < EARLY_INVALIDATION_TIME_FRACTION and pnl_pct < EARLY_INVALIDATION_LOSS_PCT:
            # Quick large adverse move → thesis likely wrong
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.EARLY_INVALIDATION_EXIT,
                "reason_text": f"Early invalidation: {pnl_pct:.2f}% loss within {time_fraction:.0%} of time budget.",
                "details": {"pnl_pct": pnl_pct, "elapsed": elapsed},
            }

        return {"should_exit": False, "reason_code": None, "reason_text": "", "details": {}}
