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

_REGIME_ALIAS_MAP = {
    "stable_uptrend": "trending_up",
    "volatile_uptrend": "breakout",
    "stable_downtrend": "trending_down",
    "volatile_downtrend": "high_volatility",
    "consolidation": "consolidation",
    "choppy": "mean_reversion",
    "trend": "trending_up",
    "trending": "trending_up",
    "panic": "high_volatility",
    "ranging": "mean_reversion",
    "low_volatility": "low_volatility",
    "volatile": "high_volatility",
    "accumulation": "breakout",
}

_STRATEGY_ALLOWED_REGIMES = {
    "scalper": {"breakout", "high_volatility", "consolidation"},
    "normal": {"trending_up", "trending_down", "consolidation", "mean_reversion", "breakout"},
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

    Unknown or weak-confidence states intentionally bias toward NO_TRADE.
    """
    trend_norm = str(trend or "neutral").lower()
    candidate = _REGIME_ALIAS_MAP.get(str(raw_regime or "").lower(), "unknown")

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

    confidence = 0.35
    confidence += min(0.25, abs(trend_pct) / 10.0)
    confidence += min(0.2, volatility_pct / 10.0)
    confidence -= min(0.25, max(spread_pct, 0) / 3.0)
    if depth_notional is not None and depth_notional > 0:
        confidence += min(0.15, depth_notional / 2_000_000.0)
    confidence = max(0.0, min(1.0, confidence))

    market_quality = max(0.0, min(1.0, confidence - min(0.4, max(spread_pct, 0) / 5.0)))

    if candidate not in CANONICAL_REGIMES:
        candidate = "unknown"
    if confidence < 0.45:
        candidate = "unknown"

    return {
        "regime": candidate,
        "confidence": round(confidence, 4),
        "market_quality": round(market_quality, 4),
        "spread_pct": round(max(spread_pct, 0.0), 4),
        "trend_pct": round(trend_pct, 4),
        "volatility_pct": round(volatility_pct, 4),
    }


def strategy_regime_allowed(bot_type: str, regime: str, confidence: float) -> Dict[str, str | bool]:
    """Determine whether a bot strategy is allowed to trade this regime."""
    normalized_bot_type = "scalper" if str(bot_type or "").lower() == "scalper" else "normal"
    allowed = _STRATEGY_ALLOWED_REGIMES[normalized_bot_type]
    normalized_regime = regime if regime in CANONICAL_REGIMES else "unknown"

    if normalized_regime == "unknown" or confidence < 0.5:
        return {
            "allowed": False,
            "reason_code": "REGIME_UNKNOWN_BLOCK",
            "reason_text": "Regime is unknown or low-confidence; standing down",
        }
    if normalized_regime not in allowed:
        return {
            "allowed": False,
            "reason_code": "REGIME_BLOCK",
            "reason_text": f"Strategy {normalized_bot_type} blocked for regime {normalized_regime}",
        }
    return {
        "allowed": True,
        "reason_code": "REGIME_ALLOWED",
        "reason_text": f"Strategy {normalized_bot_type} allowed for regime {normalized_regime}",
    }
