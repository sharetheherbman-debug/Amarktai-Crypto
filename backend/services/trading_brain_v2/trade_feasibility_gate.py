"""
TradeFeasibilityGate – hard pre-trade gate for Trading Brain V2.

Every candidate trade must pass ALL checks before any order is sent.
Every rejection produces a structured reason code + diagnostics payload.

All thresholds are imported from the canonical entry_thresholds module.
"""
import logging
from .reason_codes import ReasonCodes, make_decision_payload
from .entry_thresholds import (
    MAX_COST_TO_EDGE_RATIO,
    MIN_ENTRY_CONFIDENCE,
    MIN_NET_EDGE_BPS,
    K_COST,
    ABS_PROFIT_MIN_QUOTE,
    MIN_PROJECTED_NET_PROFIT,
    SPREAD_CAP_PCT,
    DEPTH_MIN_NOTIONAL,
    STRATEGY_TIME_CAP,
    equity_bucket as _equity_bucket,
    venue_class as _venue_class,
)

logger = logging.getLogger(__name__)


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
        # Repair 1: Edge floor transparency
        raw_gross_edge_bps: float = None,
        paper_edge_floor_applied: bool = False,
        # Repair 4: Confidence gate truth
        confidence_sources: dict = None,
    ) -> dict:
        """
        Run all feasibility checks. Returns decision payload.

        Additional transparency parameters (Repairs 1 & 4):
        - raw_gross_edge_bps: the original edge BEFORE paper floor was applied
        - paper_edge_floor_applied: True if paper edge floor inflated the edge
        - confidence_sources: breakdown of individual signal contributions
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

        # ── Edge floor truth (Repair 1) ──
        _raw_edge = raw_gross_edge_bps if raw_gross_edge_bps is not None else expected_gross_edge_bps
        _floor_applied = paper_edge_floor_applied

        # ── Confidence truth (Repair 4) ──
        _conf_sources = confidence_sources or {}

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
            extra={
                # Repair 1: Edge floor transparency
                "raw_gross_edge_bps": round(_raw_edge, 2),
                "paper_edge_floor_applied": _floor_applied,
                # Repair 3: Threshold truth
                "threshold_source": "entry_thresholds",
                "min_net_edge_bps_used": MIN_NET_EDGE_BPS.get(strat_key, 15.0),
                "k_cost_used": K_COST.get(strat_key, 1.5),
                "min_entry_confidence_used": MIN_ENTRY_CONFIDENCE,
                # Repair 4: Confidence truth
                "confidence_sources": _conf_sources,
            },
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

        # ── 4. Entry confidence floor ──
        # Reject trades where signal agreement is below the minimum threshold.
        if entry_confidence < MIN_ENTRY_CONFIDENCE:
            return make_decision_payload(ReasonCodes.LOW_CONFIDENCE_ENTRY, False, **common)

        # ── 5. Spread cap ──
        spread_cap = SPREAD_CAP_PCT.get(strat_key, 0.35)
        if spread_pct > spread_cap:
            return make_decision_payload(ReasonCodes.SPREAD_TOO_WIDE, False, **common)

        # ── 6. Depth ──
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

        # ── 7. Cost cap: if all-in cost > MAX_COST_TO_EDGE_RATIO of gross edge, block ──
        if all_in_cost_bps > 0 and expected_gross_edge_bps > 0:
            cost_ratio = all_in_cost_bps / expected_gross_edge_bps
            if cost_ratio > MAX_COST_TO_EDGE_RATIO:
                return make_decision_payload(ReasonCodes.COST_TOO_HIGH, False, **common)

        # ── 8. Absolute profit rule ──
        lookup = (strat_key if strat_key in ("scalper", "mean_reversion") else "normal",
                  eq_bucket, vc)
        abs_min = ABS_PROFIT_MIN_QUOTE.get(lookup, 2.0)
        if projected_net_profit_quote < abs_min:
            return make_decision_payload(ReasonCodes.ABS_PROFIT_TOO_SMALL, False, **common)

        # ── 8b. Flat minimum projected net profit ──
        # A final flat floor applied after the per-strategy abs-profit check (step 8
        # above).  Ensures every approved trade produces at least $1.50 USDT or
        # R25.00 ZAR in net profit, regardless of strategy type or equity bucket.
        min_profit_floor = MIN_PROJECTED_NET_PROFIT.get(vc, 0.0)
        if min_profit_floor > 0 and projected_net_profit_quote < min_profit_floor:
            return make_decision_payload(ReasonCodes.ENTRY_REJECTED_MIN_PROFIT, False, **common)

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
