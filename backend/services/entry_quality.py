"""
Canonical entry quality scoring, expectancy gating, and adaptive discipline.
"""

from __future__ import annotations

from typing import Dict, List


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
    score = (
        (regime_confidence * 0.35)
        + (ml_confidence * 0.30)
        + ((fetchai_confidence / 100.0) * 0.20)
        + ((coinstats_strength / 100.0) * 0.15)
    )
    score += min(0.08, consensus_strength * 0.04)
    score += min(0.06, consensus_sources * 0.02)
    if direction_conflict:
        score -= 0.28
    if consensus_strength <= 0:
        score -= 0.08

    score = max(0.0, min(1.0, score))
    threshold = 0.78 if str(bot_type).lower() == "scalper" else 0.68
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
    base_required = 0.45 if str(bot_type).lower() == "scalper" else 0.2
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
    """Strategic pre-timeout exit evaluator."""
    if bot_class == "normal" and hold_ratio >= 0.25 and regime_trend == "bearish" and regime_confidence >= 0.6 and pnl_pct <= 0.15:
        return "regime_deterioration_exit"
    if bot_class == "scalper" and hold_ratio >= 0.55 and pnl_pct <= min_progress_pct:
        return "scalper_no_progress_exit"
    if bot_class == "normal" and hold_ratio >= 0.45 and pnl_pct <= min_progress_pct:
        return "normal_no_progress_exit"
    if hold_ratio >= 0.35 and pnl_pct < -0.25:
        return "early_invalidation_exit"
    return None
