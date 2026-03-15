"""
OpenTradeManager – dead-capital exit rules for open positions.

Implements time-budget exits, edge-decay exits, microstructure breaks,
cost-aware no-progress exits, break-even protection, and adaptive trailing.
Prevents dead-capital holding and improves real net results.
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

# ── Break-even protection thresholds ──────────────────────────────────────────
# Once a trade has reached this gain, move stop to break-even (cover costs).
# Defined in multiples of round-trip cost so it's venue-aware.
BREAKEVEN_TRIGGER_COST_MULTIPLES = 2.5   # e.g. Luno: 2.5 * 0.35% = 0.875% gain triggers BE

# ── Adaptive trailing stop ────────────────────────────────────────────────────
# After break-even is set, trail at this fraction of the peak gain.
# e.g. 0.40 → trail keeps 40% of peak gain (stop = peak * 0.60)
TRAILING_LOCK_FRACTION = 0.40

# ── No-progress early exit ────────────────────────────────────────────────────
# Early abort when loss exceeds round-trip cost at this time fraction of budget.
NO_PROGRESS_EARLY_TIME_FRACTION = 0.50   # check at 50% of time budget


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
        peak_pnl_pct: float = None,
    ) -> dict:
        """
        Evaluate whether an open trade should exit early.

        Enhanced exit stack (in priority order):
          1. Break-even protection: if trade reached BE trigger, exit if PnL falls back below cost
          2. Adaptive trailing stop: trail peak gain at TRAILING_LOCK_FRACTION
          3. Cost-aware time budget exit: no progress by 75% of budget
          4. Full time budget exit (backstop)
          5. Edge decay exit
          6. No-progress early exit at 50% of budget (cost-dominant)
          7. Microstructure break (scalper-specific)
          8. Early invalidation

        ``peak_pnl_pct`` may be tracked externally and passed in so the trailing
        logic can work across multiple evaluation calls.

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

        # ── Venue cost parameters ──────────────────────────────────────────
        _venue = (exchange or trade.get("exchange", "")).lower()
        _rt_cost_bps = venue_round_trip_cost_bps(_venue)
        # Convert BPS to pct for comparison with pnl_pct
        _no_progress_pct = _rt_cost_bps / 100.0  # e.g. 35 bps → 0.35%
        _vc = venue_class(_venue)

        # ── Break-even trigger level ───────────────────────────────────────
        _be_trigger_pct = BREAKEVEN_TRIGGER_COST_MULTIPLES * _no_progress_pct

        # ── Peak gain tracking ─────────────────────────────────────────────
        _peak = float(peak_pnl_pct) if peak_pnl_pct is not None else pnl_pct
        _peak = max(_peak, pnl_pct)  # peak can only increase

        # ── 1. Break-even protection ───────────────────────────────────────
        # If trade reached the break-even trigger gain but has now fallen back
        # below break-even (round-trip cost level), exit to avoid a loss.
        if _peak >= _be_trigger_pct and pnl_pct < _no_progress_pct:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.NO_PROGRESS_EXIT,
                "reason_text": (
                    f"Break-even protection triggered: peak gain {_peak:.2f}% but "
                    f"current PnL {pnl_pct:.2f}% fell below cost coverage "
                    f"{_no_progress_pct:.2f}%."
                ),
                "details": {
                    "exit_type": "breakeven_protection",
                    "peak_pnl_pct": _peak,
                    "pnl_pct": pnl_pct,
                    "breakeven_trigger_pct": _be_trigger_pct,
                    "no_progress_threshold_pct": _no_progress_pct,
                    "venue_round_trip_cost_bps": _rt_cost_bps,
                    "venue_class": _vc,
                },
            }

        # ── 2. Adaptive trailing stop ──────────────────────────────────────
        # After break-even trigger is reached, protect a fraction of peak gain.
        # Trail = keep at least TRAILING_LOCK_FRACTION of the peak gain.
        if _peak >= _be_trigger_pct:
            trail_stop_pct = _peak * (1.0 - TRAILING_LOCK_FRACTION)
            if pnl_pct < trail_stop_pct and pnl_pct > 0:
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.PROFIT_PROTECTION_EXIT,
                    "reason_text": (
                        f"Adaptive trailing stop: locked {TRAILING_LOCK_FRACTION:.0%} of "
                        f"peak {_peak:.2f}%. Trail floor {trail_stop_pct:.2f}%, "
                        f"current {pnl_pct:.2f}%."
                    ),
                    "details": {
                        "exit_type": "adaptive_trailing",
                        "peak_pnl_pct": _peak,
                        "trail_stop_pct": trail_stop_pct,
                        "pnl_pct": pnl_pct,
                        "trailing_lock_fraction": TRAILING_LOCK_FRACTION,
                        "venue_round_trip_cost_bps": _rt_cost_bps,
                    },
                }

        # ── 3. No-progress early exit (50% of budget) ─────────────────────
        # If at the halfway mark the trade has lost more than the round-trip
        # cost, the edge has likely not materialised — early abandon.
        if time_fraction >= NO_PROGRESS_EARLY_TIME_FRACTION and pnl_pct < -_no_progress_pct:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.NO_PROGRESS_EXIT,
                "reason_text": (
                    f"Early no-progress exit at {time_fraction:.0%} of budget "
                    f"({elapsed:.0f}s/{safe_max_hold}s). PnL: {pnl_pct:.2f}% "
                    f"is deeply negative (below -{_no_progress_pct:.2f}%) — "
                    f"edge has not materialised."
                ),
                "details": {
                    "exit_type": "early_no_progress",
                    "elapsed": elapsed,
                    "max_hold": safe_max_hold,
                    "pnl_pct": pnl_pct,
                    "no_progress_threshold_pct": _no_progress_pct,
                    "venue_round_trip_cost_bps": _rt_cost_bps,
                    "venue_class": _vc,
                },
            }

        # ── 4. Cost-aware time budget exit ────────────────────────────────
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
                    "exit_type": "cost_aware_time_budget",
                    "elapsed": elapsed,
                    "max_hold": safe_max_hold,
                    "pnl_pct": pnl_pct,
                    "no_progress_threshold_pct": _no_progress_pct,
                    "venue_round_trip_cost_bps": _rt_cost_bps,
                    "venue_class": _vc,
                },
            }

        # ── 5. Full time budget exit (backstop) ───────────────────────────
        if time_fraction >= 1.0:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.TIME_BUDGET_EXIT,
                "reason_text": f"Time budget expired ({elapsed:.0f}s/{safe_max_hold}s).",
                "details": {"elapsed": elapsed, "max_hold": safe_max_hold, "pnl_pct": pnl_pct},
            }

        # ── 6. Edge decay exit ────────────────────────────────────────────
        if current_edge_bps > 0 and all_in_cost_bps > 0:
            net_edge = current_edge_bps - all_in_cost_bps
            if net_edge < 0 and time_fraction > 0.3:
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.EDGE_DECAY_EXIT,
                    "reason_text": f"Edge decayed below cost ({net_edge:.1f} bps net). Exiting.",
                    "details": {"current_edge_bps": current_edge_bps, "cost_bps": all_in_cost_bps},
                }

        # ── 7. Microstructure break (scalper-specific) ────────────────────
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

        # ── 8. Early invalidation ─────────────────────────────────────────
        if time_fraction < EARLY_INVALIDATION_TIME_FRACTION and pnl_pct < EARLY_INVALIDATION_LOSS_PCT:
            # Quick large adverse move → thesis likely wrong
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.EARLY_INVALIDATION_EXIT,
                "reason_text": f"Early invalidation: {pnl_pct:.2f}% loss within {time_fraction:.0%} of time budget.",
                "details": {"pnl_pct": pnl_pct, "elapsed": elapsed},
            }

        return {"should_exit": False, "reason_code": None, "reason_text": "", "details": {}}
