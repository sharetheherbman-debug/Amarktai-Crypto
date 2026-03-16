"""
OpenTradeManager – dead-capital exit rules for open positions.

Implements time-budget exits, edge-decay exits, microstructure breaks,
cost-aware no-progress exits, stop-loss, take-profit, trailing-stop,
and regime-deterioration exits.

All exits produce structured reason codes that are used by the calibration
system to track exit reason distributions.
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

# ── Regime deterioration exit ──
# For normal bots: exit when regime confidence drops sharply after entry
# AND the current regime is no longer in the bot's allowed set.
REGIME_DETERIORATION_CONF_DROP = 0.25    # confidence dropped by 25+ points
REGIME_DETERIORATION_MIN_CONF = 0.30     # confidence now below 30%
# Time fractions after which regime deterioration is evaluated
REGIME_DETERIORATION_MIN_HOLD_FRACTION = 0.20   # don't fire in first 20% of hold
REGIME_LEFT_ALLOWLIST_MIN_FRACTION = 0.30        # don't fire on allowlist exit in first 30%

# ── Scalper early recycle ──
# Scalpers exit at 50% of time budget if no meaningful progress.
SCALPER_EARLY_RECYCLE_FRACTION = 0.50


class OpenTradeManager:
    """
    Evaluate whether an open trade should be closed early
    based on economic and time-budget rules.

    Also classifies exit reasons for calibration tracking:
      STOP_LOSS_EXIT
      TAKE_PROFIT_EXIT
      TRAILING_STOP_EXIT
      REGIME_DETERIORATION_EXIT
      NO_PROGRESS_EXIT (cost-aware)
      EDGE_DECAY_EXIT
      MICROSTRUCTURE_BREAK_EXIT
      TIME_BUDGET_EXIT
      EARLY_INVALIDATION_EXIT
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
        # Stop/take-profit/trailing parameters (from policy pack)
        stop_loss_pct: float = 0.0,
        take_profit_pct: float = 0.0,
        trailing_stop_pct: float = 0.0,
        # Regime deterioration parameters (for normal bots)
        regime_confidence_at_entry: float = None,
        allowed_regimes: list = None,
    ) -> dict:
        """
        Evaluate whether an open trade should exit early.

        New parameters (policy pack support):
          stop_loss_pct          — close if PnL drops below –stop_loss_pct (0 = disabled)
          take_profit_pct        — close if PnL exceeds +take_profit_pct (0 = disabled)
          trailing_stop_pct      — trailing stop distance (0 = disabled)
          regime_confidence_at_entry — regime confidence recorded at entry for comparison
          allowed_regimes        — list of regimes valid for this bot type

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

        # ── Policy pack stop-loss / take-profit / trailing stop ──

        _sl = float(stop_loss_pct or 0.0)
        _tp = float(take_profit_pct or 0.0)
        _ts = float(trailing_stop_pct or 0.0)

        # Stop-loss
        if _sl > 0 and pnl_pct <= -(_sl * 100):
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.STOP_LOSS_EXIT,
                "reason_text": f"Stop-loss triggered: PnL {pnl_pct:.3f}% ≤ -{_sl*100:.2f}%.",
                "details": {
                    "pnl_pct": pnl_pct, "stop_loss_pct": _sl * 100,
                    "elapsed": elapsed, "policy_driven": True,
                },
            }

        # Take-profit
        if _tp > 0 and pnl_pct >= _tp * 100:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.TAKE_PROFIT_EXIT,
                "reason_text": f"Take-profit triggered: PnL {pnl_pct:.3f}% ≥ {_tp*100:.2f}%.",
                "details": {
                    "pnl_pct": pnl_pct, "take_profit_pct": _tp * 100,
                    "elapsed": elapsed, "policy_driven": True,
                },
            }

        # Trailing stop: track high-water mark in trade dict, exit on drop
        if _ts > 0:
            hw_key = "_high_water_pct"
            hwm = float(trade.get(hw_key) or pnl_pct)
            if pnl_pct > hwm:
                trade[hw_key] = pnl_pct
                hwm = pnl_pct
            trail_trigger = hwm - _ts * 100
            if pnl_pct < trail_trigger:
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.TRAILING_STOP_EXIT,
                    "reason_text": (
                        f"Trailing stop: PnL {pnl_pct:.3f}% dropped from high {hwm:.3f}% "
                        f"by more than {_ts*100:.2f}%."
                    ),
                    "details": {
                        "pnl_pct": pnl_pct, "high_water_pct": hwm,
                        "trailing_stop_pct": _ts * 100,
                        "trigger_pct": trail_trigger,
                        "elapsed": elapsed, "policy_driven": True,
                    },
                }

        # ── Regime deterioration exit (normal + mean_reversion bots) ──
        # Exit when regime has shifted away from allowed set AND confidence
        # has dropped significantly since entry.
        if bt != "scalper" and regime_confidence_at_entry is not None:
            conf_drop = float(regime_confidence_at_entry) - float(regime_confidence or 0.0)
            regime_left_allowlist = (
                allowed_regimes is not None
                and str(regime_label or "unknown").lower() not in [r.lower() for r in allowed_regimes]
            )
            if (
                conf_drop >= REGIME_DETERIORATION_CONF_DROP
                or (float(regime_confidence or 0.0) < REGIME_DETERIORATION_MIN_CONF and time_fraction > REGIME_DETERIORATION_MIN_HOLD_FRACTION)
                or (regime_left_allowlist and time_fraction > REGIME_LEFT_ALLOWLIST_MIN_FRACTION)
            ):
                return {
                    "should_exit": True,
                    "reason_code": ReasonCodes.REGIME_DETERIORATION_EXIT,
                    "reason_text": (
                        f"Regime deterioration: confidence dropped from "
                        f"{regime_confidence_at_entry:.2f} to {regime_confidence:.2f} "
                        f"(drop={conf_drop:.2f}). Current regime: '{regime_label}'."
                    ),
                    "details": {
                        "regime_confidence_at_entry": regime_confidence_at_entry,
                        "regime_confidence_now": regime_confidence,
                        "conf_drop": conf_drop,
                        "current_regime": regime_label,
                        "regime_left_allowlist": regime_left_allowlist,
                        "elapsed": elapsed,
                    },
                }

        # ── Scalper early recycle ──
        _venue = (exchange or trade.get("exchange", "")).lower()
        _rt_cost_bps = venue_round_trip_cost_bps(_venue)
        _no_progress_pct = _rt_cost_bps / 100.0
        _vc = venue_class(_venue)

        if bt == "scalper" and time_fraction >= SCALPER_EARLY_RECYCLE_FRACTION and pnl_pct <= _no_progress_pct:
            return {
                "should_exit": True,
                "reason_code": ReasonCodes.NO_PROGRESS_EXIT,
                "reason_text": (
                    f"Scalper early recycle at {time_fraction:.0%} time budget "
                    f"({elapsed:.0f}s/{safe_max_hold}s). "
                    f"PnL {pnl_pct:.3f}% ≤ venue cost {_no_progress_pct:.2f}%."
                ),
                "details": {
                    "elapsed": elapsed, "max_hold": safe_max_hold,
                    "pnl_pct": pnl_pct, "no_progress_threshold_pct": _no_progress_pct,
                    "venue_round_trip_cost_bps": _rt_cost_bps,
                    "venue_class": _vc,
                    "scalper_early_recycle": True,
                },
            }

        # ── Cost-Aware No-Progress Exit ──
        # Determine venue-specific round-trip cost to use as the no-progress
        # threshold.  A trade that hasn't covered its round-trip costs by the
        # time-budget point is effectively "no progress" because closing it
        # would not cover the fees already incurred.

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
