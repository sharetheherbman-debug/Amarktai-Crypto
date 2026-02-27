"""
Regime Playbooks — lightweight mapper from market regime to trading playbook.

Playbooks:
  momentum       — trade breakouts / pullbacks with trailing-stop logic
  mean_reversion — fade extremes, tight TP/SL, fast timeouts
  stand_down     — no new entries; wide spreads / high volatility / risk event

Interface
---------
  from engines.regime_playbooks import select_playbook, get_playbook_params

  playbook_info = select_playbook(regime_dict)
  # Returns: {
  #   "playbook": "momentum" | "mean_reversion" | "stand_down",
  #   "regime":   <original regime str>,
  #   "strength": float (0-1),
  #   "confidence": float (0-1),
  # }

  params = get_playbook_params(risk_mode="safe", playbook="momentum")
  # Returns per-playbook overrides: take_profit_pct, stop_loss_pct, etc.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regime → playbook mapping
# ---------------------------------------------------------------------------

# Each regime string maps to one of the three playbooks.
# The "strength" heuristic is a rough confidence proxy from the regime label.
_REGIME_PLAYBOOK_MAP: Dict[str, str] = {
    # Trending / momentum-friendly
    "stable_uptrend": "momentum",
    "volatile_uptrend": "momentum",
    "BULLISH_CALM": "momentum",
    "bullish": "momentum",
    # Mean-reversion / choppy
    "consolidation": "mean_reversion",
    "SQUEEZE": "mean_reversion",
    "sideways": "mean_reversion",
    "choppy": "stand_down",
    # Bearish / downside — stand-down for safe, mean-rev for aggressive
    "stable_downtrend": "mean_reversion",
    "volatile_downtrend": "stand_down",
    "BEARISH_VOLATILE": "stand_down",
    "bearish": "mean_reversion",
    # Unknown / error
    "unknown": "stand_down",
    "UNKNOWN": "stand_down",
    "error": "stand_down",
}

# Regime-label to "strength" (trend strength proxy, 0–1)
_REGIME_STRENGTH: Dict[str, float] = {
    "stable_uptrend": 0.8,
    "volatile_uptrend": 0.6,
    "BULLISH_CALM": 0.75,
    "bullish": 0.65,
    "consolidation": 0.5,
    "SQUEEZE": 0.4,
    "sideways": 0.45,
    "choppy": 0.2,
    "stable_downtrend": 0.6,
    "volatile_downtrend": 0.3,
    "BEARISH_VOLATILE": 0.3,
    "bearish": 0.5,
    "unknown": 0.1,
    "UNKNOWN": 0.1,
    "error": 0.0,
}

# ---------------------------------------------------------------------------
# Per-playbook parameter overrides  (applied on top of risk-mode defaults)
# ---------------------------------------------------------------------------

# Structure: playbook -> risk_mode -> param_overrides
_PLAYBOOK_PARAMS: Dict[str, Dict[str, Dict[str, float]]] = {
    "momentum": {
        "safe": {
            "take_profit_pct": 0.020,
            "stop_loss_pct": 0.012,
            "max_hold_minutes": 60,
            "safety_exit_minutes": 35,
            "position_size_multiplier": 1.0,
        },
        "balanced": {
            "take_profit_pct": 0.030,
            "stop_loss_pct": 0.018,
            "max_hold_minutes": 90,
            "safety_exit_minutes": 50,
            "position_size_multiplier": 1.1,
        },
        "aggressive": {
            "take_profit_pct": 0.050,
            "stop_loss_pct": 0.030,
            "max_hold_minutes": 120,
            "safety_exit_minutes": 65,
            "position_size_multiplier": 1.25,
        },
    },
    "mean_reversion": {
        "safe": {
            "take_profit_pct": 0.012,
            "stop_loss_pct": 0.010,
            "max_hold_minutes": 40,
            "safety_exit_minutes": 20,
            "position_size_multiplier": 0.85,
        },
        "balanced": {
            "take_profit_pct": 0.018,
            "stop_loss_pct": 0.014,
            "max_hold_minutes": 60,
            "safety_exit_minutes": 30,
            "position_size_multiplier": 0.90,
        },
        "aggressive": {
            "take_profit_pct": 0.030,
            "stop_loss_pct": 0.022,
            "max_hold_minutes": 80,
            "safety_exit_minutes": 45,
            "position_size_multiplier": 1.0,
        },
    },
    "stand_down": {
        # Stand-down params are not used for entry (entry is blocked);
        # kept here for completeness / future use by the exit controller.
        "safe": {
            "take_profit_pct": 0.010,
            "stop_loss_pct": 0.008,
            "max_hold_minutes": 30,
            "safety_exit_minutes": 15,
            "position_size_multiplier": 0.5,
        },
        "balanced": {
            "take_profit_pct": 0.012,
            "stop_loss_pct": 0.010,
            "max_hold_minutes": 35,
            "safety_exit_minutes": 18,
            "position_size_multiplier": 0.5,
        },
        "aggressive": {
            "take_profit_pct": 0.015,
            "stop_loss_pct": 0.012,
            "max_hold_minutes": 40,
            "safety_exit_minutes": 20,
            "position_size_multiplier": 0.5,
        },
    },
}

_DEFAULT_RISK_MODE = "balanced"


def select_playbook(regime_dict: Optional[Dict]) -> Dict:
    """
    Map a regime dict (from market_regime_detector.detect_regime) to a playbook.

    Parameters
    ----------
    regime_dict : dict | None
        Output of MarketRegimeDetector.detect_regime, containing at least
        ``regime`` and ``confidence`` keys.  May be None or empty.

    Returns
    -------
    dict with keys:
        playbook   : "momentum" | "mean_reversion" | "stand_down"
        regime     : original regime string
        strength   : float 0–1 (trend / signal strength heuristic)
        confidence : float 0–1 (from detector or default 0)
    """
    if not regime_dict:
        return {"playbook": "stand_down", "regime": "unknown", "strength": 0.1, "confidence": 0.0}

    regime = str(regime_dict.get("regime") or "unknown")
    confidence = float(regime_dict.get("confidence") or 0.0)
    playbook = _REGIME_PLAYBOOK_MAP.get(regime, "stand_down")
    strength = _REGIME_STRENGTH.get(regime, 0.2)

    # Extra stand-down trigger: very low confidence regardless of regime label
    if confidence < 0.15:
        playbook = "stand_down"
        strength = min(strength, 0.2)

    return {
        "playbook": playbook,
        "regime": regime,
        "strength": round(strength, 3),
        "confidence": round(confidence, 3),
    }


def get_playbook_params(risk_mode: str, playbook: str) -> Dict:
    """
    Return per-playbook parameter overrides for *risk_mode*.

    Falls back to *balanced* if *risk_mode* is unknown.  Always returns a
    fully-populated dict; callers should treat these as *suggestions* applied
    on top of the bot's base configuration.
    """
    mode = risk_mode if risk_mode in _PLAYBOOK_PARAMS.get(playbook, {}) else _DEFAULT_RISK_MODE
    return dict(_PLAYBOOK_PARAMS.get(playbook, {}).get(mode, {}))
