"""
Canonical entry quality scoring, expectancy gating, and adaptive discipline.
"""

from __future__ import annotations

from typing import Dict, List

SCALPER_CONFIDENCE_THRESHOLD = 0.78
NORMAL_CONFIDENCE_THRESHOLD = 0.68
SCALPER_BASE_EDGE_PCT = 0.60   # raised from 0.45 — scalpers require stronger projected edge
NORMAL_BASE_EDGE_PCT = 0.2

# Entry quality classification thresholds
HIGH_QUALITY_MIN_CONFIDENCE = 0.75
HIGH_QUALITY_MIN_EDGE_PCT = 0.5
HIGH_QUALITY_MIN_SOURCES = 2
MEDIUM_QUALITY_MIN_CONFIDENCE = 0.60
MEDIUM_QUALITY_MIN_EDGE_PCT = 0.2
MEDIUM_QUALITY_MIN_SOURCES = 1


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
    """Compute canonical entry confidence score with conflict penalties."""
    _rc = float(regime_confidence or 0)
    _ml = float(ml_confidence or 0)
    score = (
        (_rc * 0.35)
        + (_ml * 0.30)
        + ((float(fetchai_confidence or 0) / 100.0) * 0.20)
        + ((float(coinstats_strength or 0) / 100.0) * 0.15)
    )
    score += min(0.08, consensus_strength * 0.04)
    score += min(0.06, consensus_sources * 0.02)
    if direction_conflict:
        score -= 0.28
    if consensus_strength <= 0:
        score -= 0.08

    score = max(0.0, min(1.0, score))
    threshold = SCALPER_CONFIDENCE_THRESHOLD if str(bot_type).lower() == "scalper" else NORMAL_CONFIDENCE_THRESHOLD
    accepted = score >= threshold
    return {
        "entry_confidence_score": round(score, 4),
        "minimum_required": threshold,
        "accepted": accepted,
        "reason_code": "ENTRY_CONFIDENCE_OK" if accepted else "LOW_ENTRY_CONFIDENCE",
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

    if max_consecutive_losses >= 3 or (loss_ratio >= 0.75 and timeout_loss_ratio >= 0.6 and sample >= 6):
        return {
            "stand_down": True,
            "confidence_uplift": 0.15,
            "edge_uplift_pct": 0.35,
            "reason_code": "ADAPTIVE_STAND_DOWN",
        }
    if max_consecutive_losses >= 1 or timeout_loss_ratio >= 0.5:
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


def classify_entry_quality(
    *,
    entry_confidence_score: float,
    net_edge_pct: float,
    consensus_sources: int,
    bot_type: str = "normal",
) -> Dict:
    """Classify an entry setup into high / medium / low quality.

    Rules
    -----
    High:   confidence >= 0.75 AND net_edge >= 0.5% AND sources >= 2
    Medium: confidence >= 0.60 AND net_edge >= 0.2% AND sources >= 1
    Low:    everything else → should_trade = False

    Returns
    -------
    dict with quality, priority, should_trade, reason.
    """
    conf = float(entry_confidence_score or 0)
    edge = float(net_edge_pct or 0)
    sources = int(consensus_sources or 0)

    if (conf >= HIGH_QUALITY_MIN_CONFIDENCE
            and edge >= HIGH_QUALITY_MIN_EDGE_PCT
            and sources >= HIGH_QUALITY_MIN_SOURCES):
        return {
            "quality": "high",
            "priority": 1,
            "should_trade": True,
            "reason": (
                f"High quality entry: confidence={conf:.2f}, "
                f"net_edge={edge:.2f}%, sources={sources}"
            ),
        }

    if (conf >= MEDIUM_QUALITY_MIN_CONFIDENCE
            and edge >= MEDIUM_QUALITY_MIN_EDGE_PCT
            and sources >= MEDIUM_QUALITY_MIN_SOURCES):
        return {
            "quality": "medium",
            "priority": 2,
            "should_trade": True,
            "reason": (
                f"Medium quality entry: confidence={conf:.2f}, "
                f"net_edge={edge:.2f}%, sources={sources}"
            ),
        }

    return {
        "quality": "low",
        "priority": 3,
        "should_trade": False,
        "reason": (
            f"Low quality entry rejected: confidence={conf:.2f}, "
            f"net_edge={edge:.2f}%, sources={sources} — "
            "does not meet minimum thresholds"
        ),
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
      1.  regime_decay_exit          — bearish regime with significant confidence
      1a. regime_deterioration_exit — regime confidence collapsed to zero AND adverse trend
      2.  profit_protection_exit — small gain appeared then stalled
      3.  stagnation_exit        — price flat near zero for extended period
      4.  scalper_no_progress_exit
      5.  normal_no_progress_exit
      6.  early_invalidation_exit

    Scalper no-progress exit fires at 60% of hold window (fast recycle).
    Normal no-progress exit fires at 45% of hold window.
    Early-invalidation threshold is -0.40% to avoid exiting slightly-red
    trades still inside normal price noise.
    """
    # 1. Regime decay: strong bearish with high confidence.
    # 1a. Regime deterioration: confidence has collapsed AND trend is clearly adverse.
    if hold_ratio >= 0.20:
        bearish_with_confidence = (regime_trend == "bearish" and regime_confidence >= 0.55)
        strong_bearish = (regime_trend == "bearish" and regime_confidence >= 0.80)
        if bot_class == "normal":
            if strong_bearish and pnl_pct <= 0.25:
                return "regime_decay_exit"
            if bearish_with_confidence and hold_ratio >= 0.25 and pnl_pct <= 0.15:
                return "regime_decay_exit"
        # Regime deterioration: confidence has collapsed AND trend is clearly adverse
        is_adverse_trend = regime_trend in ("bearish", "trending_down", "high_volatility", "breakout")
        if regime_confidence <= 0.0 and hold_ratio >= 0.30 and is_adverse_trend:
            return "regime_deterioration_exit"

    # 2. Profit protection: trade made small progress but gain is stalling at hold midpoint
    if bot_class == "normal" and hold_ratio >= 0.55 and 0.0 < pnl_pct < min_progress_pct * 2.0:
        return "profit_protection_exit"

    # 3. Stagnation: price has gone nowhere for extended period (worse than no-progress floor)
    if bot_class == "normal" and hold_ratio >= 0.40 and -0.05 <= pnl_pct <= 0.02:
        return "stagnation_exit"

    # 4. Scalper: no progress at 60% of hold window (fast recycle, no dead waiting)
    if bot_class == "scalper" and hold_ratio >= 0.60 and pnl_pct <= min_progress_pct:
        return "scalper_no_progress_exit"

    # 5. Normal: no progress at 45% of hold window
    if bot_class == "normal" and hold_ratio >= 0.45 and pnl_pct <= min_progress_pct:
        return "normal_no_progress_exit"

    # 6. Early invalidation: sharp adverse move in first 35% of hold window
    if hold_ratio >= 0.35 and pnl_pct < -0.40:
        return "early_invalidation_exit"

    return None
