"""
Canonical entry quality scoring, expectancy gating, and adaptive discipline.
"""

from __future__ import annotations

from typing import Dict, List

SCALPER_CONFIDENCE_THRESHOLD = 0.78
NORMAL_CONFIDENCE_THRESHOLD = 0.68
SCALPER_BASE_EDGE_PCT = 0.60   # raised from 0.45 — scalpers require stronger projected edge
NORMAL_BASE_EDGE_PCT = 0.2

# Minimum non-zero value to treat a signal as "available"
_SIGNAL_AVAILABLE_THRESHOLD = 0.01


def compute_entry_confidence(
    *,
    bot_type: str,
    regime_confidence: float,
    ml_confidence: float,
    fetchai_confidence: float,
    coinstats_strength: float,
    consensus_strength: int,
    consensus_sources: int,
    direction_conflict: bool,
) -> Dict[str, float | bool | str]:
    """Compute canonical entry confidence score with conflict penalties.

    Uses adaptive weight normalization: when FetchAI or CoinStats signals are
    unavailable (zero), their weight is redistributed proportionally to the
    available primary signals (regime + ML).  This prevents strong 2-signal
    alignment from being artificially blocked purely because a third-party
    data source is unavailable.

    The score structure is:
      - regime_confidence    base weight 0.35 (primary)
      - ml_confidence        base weight 0.30 (primary)
      - fetchai_confidence   base weight 0.20 (secondary, redistributed if absent)
      - coinstats_strength   base weight 0.15 (secondary, redistributed if absent)
      - consensus bonus      up to +0.14
      - direction_conflict   penalty -0.28
      - no_consensus         penalty -0.05 (reduced from 0.08 – still meaningful)
    """
    _rc = float(regime_confidence or 0)
    _ml = float(ml_confidence or 0)
    _fa = float(fetchai_confidence or 0)
    _cs = float(coinstats_strength or 0)

    # ── Adaptive weight normalization ────────────────────────────────────
    # If secondary signals are unavailable, their weight flows to primary signals
    # in proportion so that strong regime+ML can reach the threshold on their own.
    fa_available = _fa >= _SIGNAL_AVAILABLE_THRESHOLD
    cs_available = _cs >= _SIGNAL_AVAILABLE_THRESHOLD

    w_regime = 0.35
    w_ml = 0.30
    w_fa = 0.20
    w_cs = 0.15

    if not fa_available and not cs_available:
        # Both secondary signals absent: full redistribution to primary
        # weights proportional to base regime/ml ratio
        _extra = w_fa + w_cs
        _sum_primary = w_regime + w_ml
        w_regime += _extra * (w_regime / _sum_primary)
        w_ml += _extra * (w_ml / _sum_primary)
        w_fa = 0.0
        w_cs = 0.0
    elif not fa_available:
        # FetchAI absent: distribute its weight proportionally to regime/ml
        _sum_primary = w_regime + w_ml
        w_regime += w_fa * (w_regime / _sum_primary)
        w_ml += w_fa * (w_ml / _sum_primary)
        w_fa = 0.0
    elif not cs_available:
        # CoinStats absent: distribute its weight proportionally to regime/ml
        _sum_primary = w_regime + w_ml
        w_regime += w_cs * (w_regime / _sum_primary)
        w_ml += w_cs * (w_ml / _sum_primary)
        w_cs = 0.0

    score = (
        (_rc * w_regime)
        + (_ml * w_ml)
        + ((_fa / 100.0) * w_fa)
        + ((_cs / 100.0) * w_cs)
    )

    # ── Consensus bonus ──────────────────────────────────────────────────
    score += min(0.08, int(consensus_strength) * 0.04)
    score += min(0.06, int(consensus_sources) * 0.02)

    # ── Penalties ────────────────────────────────────────────────────────
    if direction_conflict:
        score -= 0.28
    if int(consensus_strength) <= 0:
        score -= 0.05   # reduced from 0.08 — still a meaningful deterrent

    score = max(0.0, min(1.0, score))

    # ── Threshold ────────────────────────────────────────────────────────
    threshold = (
        SCALPER_CONFIDENCE_THRESHOLD
        if str(bot_type).lower() == "scalper"
        else NORMAL_CONFIDENCE_THRESHOLD
    )
    accepted = score >= threshold

    return {
        "entry_confidence_score": round(score, 4),
        "minimum_required": threshold,
        "accepted": accepted,
        "reason_code": "ENTRY_CONFIDENCE_OK" if accepted else "LOW_ENTRY_CONFIDENCE",
        # Transparency: per-signal contributions
        "confidence_sources": {
            "regime_confidence":  round(_rc, 4),
            "ml_confidence":      round(_ml, 4),
            "fetchai_confidence": round(_fa / 100.0, 4),
            "coinstats_strength": round(_cs / 100.0, 4),
            "fetchai_available":  fa_available,
            "coinstats_available": cs_available,
            "weights_normalized": not (fa_available and cs_available),
            "w_regime": round(w_regime, 4),
            "w_ml":     round(w_ml, 4),
            "w_fa":     round(w_fa, 4),
            "w_cs":     round(w_cs, 4),
            "consensus_strength": int(consensus_strength),
            "consensus_sources":  int(consensus_sources),
            "direction_conflict": direction_conflict,
        },
    }


def evaluate_expectancy_gate(
    *,
    bot_type: str,
    expected_move_pct: float,
    estimated_cost_pct: float,
    market_quality: float,
    entry_confidence_score: float,
    timeout_risk_pct: float,
    adaptive_edge_uplift_pct: float = 0.0,
) -> Dict[str, float | bool | str]:
    """Expectancy-first gate: block when post-cost edge is weak."""
    quality_multiplier = max(0.45, min(1.25, (market_quality * 0.7) + (entry_confidence_score * 0.55)))
    effective_move = expected_move_pct * quality_multiplier
    net_edge_pct = effective_move - estimated_cost_pct - timeout_risk_pct
    base_required = SCALPER_BASE_EDGE_PCT if str(bot_type).lower() == "scalper" else NORMAL_BASE_EDGE_PCT
    required_net_edge_pct = base_required + max(0.0, adaptive_edge_uplift_pct)
    accepted = net_edge_pct >= required_net_edge_pct
    return {
        "accepted": accepted,
        "net_edge_pct": round(net_edge_pct, 4),
        "required_net_edge_pct": round(required_net_edge_pct, 4),
        "effective_move_pct": round(effective_move, 4),
        "quality_multiplier": round(quality_multiplier, 4),
        "reason_code": "EXPECTANCY_OK" if accepted else "INSUFFICIENT_NET_EXPECTANCY",
    }


def derive_adaptive_discipline(recent_closed_trades: List[Dict]) -> Dict[str, float | bool | str]:
    """Lightweight bot-level adaptive discipline from recent outcomes."""
    if not recent_closed_trades:
        return {
            "stand_down": False,
            "confidence_uplift": 0.0,
            "edge_uplift_pct": 0.0,
            "reason_code": "ADAPTIVE_NEUTRAL",
        }

    losses = 0
    timeout_losses = 0
    consecutive_losses = 0
    max_consecutive_losses = 0
    for trade in recent_closed_trades:
        pnl = float(trade.get("net_pnl", trade.get("profit_loss", 0)) or 0)
        close_reason = str(trade.get("trade_close_reason", "")).lower()
        if pnl <= 0:
            losses += 1
            consecutive_losses += 1
            if "max_hold_exceeded" in close_reason or "time" in close_reason:
                timeout_losses += 1
        else:
            consecutive_losses = 0
        max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)

    sample = len(recent_closed_trades)
    loss_ratio = losses / max(sample, 1)
    timeout_loss_ratio = timeout_losses / max(losses, 1) if losses else 0.0

    if max_consecutive_losses >= 4 or (loss_ratio >= 0.75 and timeout_loss_ratio >= 0.6 and sample >= 6):
        return {
            "stand_down": True,
            "confidence_uplift": 0.15,
            "edge_uplift_pct": 0.35,
            "reason_code": "ADAPTIVE_STAND_DOWN",
        }
    if max_consecutive_losses >= 2 or timeout_loss_ratio >= 0.5:
        return {
            "stand_down": False,
            "confidence_uplift": 0.08,
            "edge_uplift_pct": 0.18,
            "reason_code": "ADAPTIVE_TIGHTENED",
        }
    return {
        "stand_down": False,
        "confidence_uplift": 0.0,
        "edge_uplift_pct": 0.0,
        "reason_code": "ADAPTIVE_NEUTRAL",
    }


def evaluate_pre_timeout_exit(
    *,
    bot_class: str,
    hold_ratio: float,
    pnl_pct: float,
    min_progress_pct: float,
    regime_trend: str,
    regime_confidence: float,
) -> str | None:
    """Strategic pre-timeout exit evaluator.

    Exit priority (first match wins):
      1. regime_decay_exit     — regime confidence deteriorated significantly
      2. profit_protection_exit — small gain appeared then stalled
      3. stagnation_exit        — price flat near zero for extended period
      4. scalper_no_progress_exit
      5. normal_no_progress_exit
      6. early_invalidation_exit

    Scalper no-progress exit fires at 70% of hold window.
    Normal no-progress exit fires at 45% of hold window.
    Early-invalidation threshold is -0.40% to avoid exiting slightly-red
    trades still inside normal price noise.
    """
    # 1. Regime decay: bearish AND low confidence OR any strong bearish signal
    if bot_class == "normal" and hold_ratio >= 0.20:
        bearish_with_confidence = (regime_trend == "bearish" and regime_confidence >= 0.55)
        regime_collapsed = (regime_trend == "bearish" and regime_confidence >= 0.80)
        if regime_collapsed and pnl_pct <= 0.25:
            return "regime_decay_exit"
        if bearish_with_confidence and hold_ratio >= 0.25 and pnl_pct <= 0.15:
            return "regime_decay_exit"

    # 2. Profit protection: trade made small progress but gain is stalling at hold midpoint
    if bot_class == "normal" and hold_ratio >= 0.55 and 0.0 < pnl_pct < min_progress_pct * 2.0:
        return "profit_protection_exit"

    # 3. Stagnation: price has gone nowhere for extended period (worse than no-progress floor)
    if bot_class == "normal" and hold_ratio >= 0.40 and -0.05 <= pnl_pct <= 0.02:
        return "stagnation_exit"

    # 4. Scalper: no progress at 70% of hold window
    if bot_class == "scalper" and hold_ratio >= 0.70 and pnl_pct <= min_progress_pct:
        return "scalper_no_progress_exit"

    # 5. Normal: no progress at 45% of hold window
    if bot_class == "normal" and hold_ratio >= 0.45 and pnl_pct <= min_progress_pct:
        return "normal_no_progress_exit"

    # 6. Early invalidation: sharp adverse move in first 35% of hold window
    if hold_ratio >= 0.35 and pnl_pct < -0.40:
        return "early_invalidation_exit"

    return None
