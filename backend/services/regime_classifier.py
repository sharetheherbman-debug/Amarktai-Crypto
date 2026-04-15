"""
Canonical market regime classifier for strategy admission decisions.
"""

from __future__ import annotations

from typing import Dict, Optional, Set


CANONICAL_REGIMES: Set[str] = {
    "trending_up",
    "trending_down",
    "consolidation",
    "mean_reversion",
    "breakout",
    "high_volatility",
    "low_volatility",
    "unknown",
}
# Regime used as fallback when insufficient data or low confidence.
# "consolidation" is chosen because it is a valid regime for both scalpers and
# normal bots, and represents a neutral/uncertain market state.
_FALLBACK_REGIME = "consolidation"
# Minimum confidence floor — never emit 0.0 so the confidence gate always has
# something to work with.
_MIN_CONFIDENCE = 0.20

BASE_REGIME_CONFIDENCE = 0.35
DEPTH_NOTIONAL_NORMALIZATION_FACTOR = 2_000_000.0

_REGIME_ALIAS_MAP = {
    "stable_uptrend": "trending_up",
    "volatile_uptrend": "breakout",
    "stable_downtrend": "trending_down",
    "volatile_downtrend": "high_volatility",
    "consolidation": "consolidation",
    "choppy": "mean_reversion",
    "range": "consolidation",
    "ranging": "mean_reversion",
    "trend": "trending_up",
    "trending": "trending_up",
    "trend_up": "trending_up",
    "trend_down": "trending_down",
    "volatile": "high_volatility",
    "panic": "high_volatility",
    "low_volatility": "low_volatility",
    "accumulation": "breakout",
}

_STRATEGY_ALLOWED_REGIMES = {
    # Scalpers operate on short-term micro-volatility and momentum; they work in
    # consolidating/ranging markets AND in moderate-volatility regimes where
    # micro-momentum signals are present.  Only hard-trending breakout regimes
    # (where momentum overwhelms the tight scalper spread) are excluded.
    "scalper": {"consolidation", "mean_reversion", "high_volatility", "low_volatility"},
    "normal": {"trending_up", "trending_down", "consolidation", "mean_reversion", "breakout", "high_volatility", "low_volatility"},
}


def classify_regime(
    *,
    raw_regime: Optional[str],
    trend: Optional[str],
    trend_pct: float,
    volatility_pct: float,
    spread_pct: float,
    depth_notional: Optional[float] = None,
) -> Dict[str, float | str | bool]:
    """Classify market regime into canonical labels with confidence.

    Regime NEVER returns "unknown" — insufficient data falls back to
    _FALLBACK_REGIME ("consolidation") so the trading pipeline always has a
    usable regime to work with.
    """
    trend_norm = str(trend or "neutral").lower()
    candidate = _REGIME_ALIAS_MAP.get(str(raw_regime or "").lower(), _FALLBACK_REGIME)

    # Feature-driven overrides (prefer measured quality over raw aliases)
    if volatility_pct >= 4.5:
        candidate = "high_volatility"
    elif volatility_pct <= 1.0 and abs(trend_pct) < 0.5:
        candidate = "low_volatility"
    elif abs(trend_pct) >= 2.0 and trend_norm in {"bullish", "bearish"}:
        candidate = "trending_up" if trend_norm == "bullish" else "trending_down"
    elif abs(trend_pct) < 0.6 and volatility_pct < 2.2:
        candidate = "consolidation"
    elif abs(trend_pct) < 1.2 and volatility_pct >= 2.2:
        candidate = "mean_reversion"

    confidence = BASE_REGIME_CONFIDENCE
    confidence += min(0.25, abs(trend_pct) / 10.0)
    confidence += min(0.2, volatility_pct / 10.0)
    confidence -= min(0.25, max(spread_pct, 0) / 3.0)
    if depth_notional is not None and depth_notional > 0:
        confidence += min(0.15, depth_notional / DEPTH_NOTIONAL_NORMALIZATION_FACTOR)
    # Enforce minimum confidence floor so downstream gates always have a signal.
    confidence = max(_MIN_CONFIDENCE, min(1.0, confidence))

    market_quality = max(0.0, min(1.0, confidence - min(0.4, max(spread_pct, 0) / 5.0)))

    # Guard: if the candidate is somehow not in the canonical set, use the fallback.
    if candidate not in CANONICAL_REGIMES or candidate == "unknown":
        candidate = _FALLBACK_REGIME

    # Previously low-confidence states were forced to "unknown", which blocked all
    # trades.  Now we keep the detected regime label and just report the actual
    # (possibly low) confidence — callers can decide how to interpret it.

    return {
        "regime": candidate,
        "confidence": round(confidence, 4),
        "market_quality": round(market_quality, 4),
        "spread_pct": round(max(spread_pct, 0.0), 4),
        "trend_pct": round(trend_pct, 4),
        "volatility_pct": round(volatility_pct, 4),
    }


def strategy_regime_allowed(bot_type: str, regime: str, confidence: float) -> Dict[str, str | bool]:
    """Determine whether a bot strategy is allowed to trade this regime.

    Returns a dict with:
        allowed             — bool
        reason_code         — machine-readable reason code
        reason_text         — human-readable reason
        bot_type_specific   — True (always — decisions are bot-type specific)
        allowed_regimes     — list of regimes allowed for this bot type
    """
    normalized_bot_type = "scalper" if str(bot_type or "").lower() == "scalper" else "normal"
    allowed = _STRATEGY_ALLOWED_REGIMES[normalized_bot_type]
    normalized_regime = regime if regime in CANONICAL_REGIMES else _FALLBACK_REGIME
    allowed_list = sorted(allowed)

    # Lower confidence gate: 0.30 is sufficient for a valid regime signal.
    # The old 0.40 threshold blocked most paper-mode bot cycles where regime
    # confidence is 0.30–0.38 (calm/consolidating market with small spread).
    if normalized_regime == "unknown" or confidence < 0.30:
        return {
            "allowed": False,
            "reason_code": "REGIME_UNKNOWN_BLOCK",
            "reason_text": (
                f"{normalized_bot_type} blocked: regime unknown or low-confidence "
                f"({confidence:.0%}); allowed regimes: {allowed_list}"
            ),
            "bot_type_specific": True,
            "allowed_regimes": allowed_list,
        }
    if normalized_regime not in allowed:
        return {
            "allowed": False,
            "reason_code": "REGIME_BLOCK",
            "reason_text": (
                f"{normalized_bot_type} blocked for regime '{normalized_regime}'; "
                f"allowed regimes: {allowed_list}"
            ),
            "bot_type_specific": True,
            "allowed_regimes": allowed_list,
        }
    return {
        "allowed": True,
        "reason_code": "REGIME_ALLOWED",
        "reason_text": (
            f"{normalized_bot_type} allowed for regime '{normalized_regime}' "
            f"(confidence {confidence:.0%})"
        ),
        "bot_type_specific": True,
        "allowed_regimes": allowed_list,
    }
