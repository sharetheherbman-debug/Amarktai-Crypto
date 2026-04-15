"""
Regime Playbooks — lightweight mapper from market regime to trading playbook.

Playbooks:
  momentum       — trade breakouts / pullbacks with trailing-stop logic
  mean_reversion — fade extremes, tight TP/SL, fast timeouts; also used as
                   cautious fallback when regime is unknown/uncertain
  stand_down     — no new entries; ONLY for extreme conditions: extreme
                   volatility spike, confirmed bearish volatile regime, or
                   explicit news-risk event

Stand-down policy
-----------------
  stand_down is reserved for CLEARLY DANGEROUS conditions only:
    - volatile_downtrend  (strong downtrend + high volatility)
    - BEARISH_VOLATILE    (legacy label for same condition)
  All other regimes — including unknown, error, choppy, consolidation —
  fall back to mean_reversion with a reduced position size.  This ensures
  the system can ALWAYS trade cautiously rather than permanently blocking.

Interface
---------
  from engines.regime_playbooks import select_playbook, get_playbook_params

  playbook_info = select_playbook(regime_dict)
  # Returns: {
  #   "playbook": "momentum" | "mean_reversion" | "stand_down",
  #   "regime":   <original regime str>,
  #   "strength": float (0-1),
  #   "confidence": float (0-1),
  #   "caution":  bool  (True when using fallback / reduced size),
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
#
# IMPORTANT: stand_down is ONLY for extreme downside volatile conditions.
# choppy / unknown / error use mean_reversion (cautious) so trading is never
# permanently blocked by regime alone.
_REGIME_PLAYBOOK_MAP: Dict[str, str] = {
    # Trending / momentum-friendly
    "stable_uptrend": "momentum",
    "volatile_uptrend": "momentum",
    "BULLISH_CALM": "momentum",
    "bullish": "momentum",
    # Mean-reversion / range / choppy / consolidation
    "consolidation": "mean_reversion",
    "SQUEEZE": "mean_reversion",
    "sideways": "mean_reversion",
    "choppy": "mean_reversion",      # was stand_down — choppy ≠ dangerous
    # Bearish / downside
    "stable_downtrend": "mean_reversion",
    "volatile_downtrend": "stand_down",   # extreme: strong downtrend + high vol
    "BEARISH_VOLATILE": "stand_down",     # extreme: legacy label
    "bearish": "mean_reversion",
    # Unknown / error — use mean_reversion (cautious) not stand_down
    "unknown": "mean_reversion",
    "UNKNOWN": "mean_reversion",
    "error": "mean_reversion",
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
# TP/SL calibration rationale
# ────────────────────────────
# Luno charges 0.25% per side (taker), plus ~0.06% spread + ~0.08% slippage
# = 0.64% total round-trip cost.  For a trade to have positive expected value
# at a 50% win rate (worst case), we need:
#   net_TP  > net_SL
#   TP - costs > SL + costs
#   TP > SL + 2 × 0.64%  →  TP > SL + 1.28%   (minimum viability on Luno)
#
# Previous values violated this (e.g. mean_reversion safe TP=1.2%, SL=1.0%
# gave R:R = 0.34 — guaranteed to lose on Luno).  Every row below satisfies
# TP ≥ SL + 1.5% to give a comfortable buffer above break-even.
_PLAYBOOK_PARAMS: Dict[str, Dict[str, Dict[str, float]]] = {
    "momentum": {
        # Trending market — wide TP to ride the move, moderate SL.
        "safe": {
            "take_profit_pct": 0.040,   # net after 0.64% cost: +3.36%
            "stop_loss_pct":   0.018,   # net after 0.64% cost: -2.44%  R:R≈1.38
            "max_hold_minutes": 90,
            "safety_exit_minutes": 45,
            "position_size_multiplier": 1.0,
        },
        "balanced": {
            "take_profit_pct": 0.055,   # net: +4.91%
            "stop_loss_pct":   0.025,   # net: -3.14%  R:R≈1.56
            "max_hold_minutes": 120,
            "safety_exit_minutes": 60,
            "position_size_multiplier": 1.1,
        },
        "risky": {
            "take_profit_pct": 0.065,
            "stop_loss_pct":   0.030,
            "max_hold_minutes": 120,
            "safety_exit_minutes": 65,
            "position_size_multiplier": 1.15,
        },
        "aggressive": {
            "take_profit_pct": 0.080,   # net: +7.36%
            "stop_loss_pct":   0.035,   # net: -4.14%  R:R≈1.78
            "max_hold_minutes": 150,
            "safety_exit_minutes": 75,
            "position_size_multiplier": 1.25,
        },
    },
    "mean_reversion": {
        # Range / consolidation market — moderate TP, tight SL.
        # TP must clear round-trip cost by a meaningful margin.
        "safe": {
            "take_profit_pct": 0.030,   # net: +2.36%
            "stop_loss_pct":   0.015,   # net: -2.14%  R:R≈1.10
            "max_hold_minutes": 60,
            "safety_exit_minutes": 30,
            "position_size_multiplier": 0.85,
        },
        "balanced": {
            "take_profit_pct": 0.040,   # net: +3.36%
            "stop_loss_pct":   0.020,   # net: -2.64%  R:R≈1.27
            "max_hold_minutes": 80,
            "safety_exit_minutes": 40,
            "position_size_multiplier": 0.90,
        },
        "risky": {
            "take_profit_pct": 0.050,
            "stop_loss_pct":   0.025,
            "max_hold_minutes": 90,
            "safety_exit_minutes": 45,
            "position_size_multiplier": 0.95,
        },
        "aggressive": {
            "take_profit_pct": 0.060,   # net: +5.36%
            "stop_loss_pct":   0.030,   # net: -3.64%  R:R≈1.47
            "max_hold_minutes": 100,
            "safety_exit_minutes": 50,
            "position_size_multiplier": 1.0,
        },
    },
    "stand_down": {
        # Stand-down params are not used for entry (entry is blocked);
        # kept here for completeness / future use by the exit controller.
        "safe": {
            "take_profit_pct": 0.025,
            "stop_loss_pct":   0.015,
            "max_hold_minutes": 30,
            "safety_exit_minutes": 15,
            "position_size_multiplier": 0.5,
        },
        "balanced": {
            "take_profit_pct": 0.030,
            "stop_loss_pct":   0.018,
            "max_hold_minutes": 35,
            "safety_exit_minutes": 18,
            "position_size_multiplier": 0.5,
        },
        "risky": {
            "take_profit_pct": 0.035,
            "stop_loss_pct":   0.020,
            "max_hold_minutes": 40,
            "safety_exit_minutes": 20,
            "position_size_multiplier": 0.5,
        },
        "aggressive": {
            "take_profit_pct": 0.040,
            "stop_loss_pct":   0.022,
            "max_hold_minutes": 40,
            "safety_exit_minutes": 20,
            "position_size_multiplier": 0.5,
        },
    },
}

_DEFAULT_RISK_MODE = "balanced"

# Caution-mode scaling factors applied when caution=True (unknown/low-confidence regime).
# Exposed as constants so they are easy to tune without touching logic.
_CAUTION_POSITION_MULTIPLIER: float = 0.5   # fraction of normal position_size_multiplier
_CAUTION_HOLD_FRACTION: float = 0.75         # fraction of normal hold/exit times
_CAUTION_MIN_HOLD_MINUTES: int = 15          # floor for max_hold_minutes after reduction
_CAUTION_MIN_EXIT_MINUTES: int = 10          # floor for safety_exit_minutes after reduction
_CAUTION_CONFIDENCE_THRESHOLD: float = 0.15  # below this → caution even for known regimes


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
        caution    : bool — True when using a reduced-size cautious fallback
                     (low confidence or unknown/error regime)
    """
    if not regime_dict:
        # Regime detector unavailable — trade cautiously with mean_reversion,
        # do NOT stand down permanently.
        return {
            "playbook": "mean_reversion",
            "regime": "unknown",
            "strength": 0.1,
            "confidence": 0.0,
            "caution": True,
        }

    regime = str(regime_dict.get("regime") or "unknown")
    confidence = float(regime_dict.get("confidence") or 0.0)
    playbook = _REGIME_PLAYBOOK_MAP.get(regime, "mean_reversion")
    strength = _REGIME_STRENGTH.get(regime, 0.2)

    # Low-confidence regime: trade cautiously (mean_reversion with reduced size)
    # rather than standing down completely.  Only truly dangerous regimes
    # (volatile_downtrend / BEARISH_VOLATILE) still stand down.
    caution = False
    if confidence < _CAUTION_CONFIDENCE_THRESHOLD and playbook != "stand_down":
        playbook = "mean_reversion"
        strength = min(strength, 0.2)
        caution = True
    elif regime in ("unknown", "UNKNOWN", "error"):
        caution = True

    return {
        "playbook": playbook,
        "regime": regime,
        "strength": round(strength, 3),
        "confidence": round(confidence, 3),
        "caution": caution,
    }


def get_playbook_params(risk_mode: str, playbook: str, caution: bool = False) -> Dict:
    """
    Return per-playbook parameter overrides for *risk_mode*.

    Falls back to *balanced* if *risk_mode* is unknown.  Always returns a
    fully-populated dict; callers should treat these as *suggestions* applied
    on top of the bot's base configuration.

    When *caution* is True (unknown/low-confidence regime), position_size_multiplier
    is halved and hold times are reduced to limit exposure.
    """
    mode = risk_mode if risk_mode in _PLAYBOOK_PARAMS.get(playbook, {}) else _DEFAULT_RISK_MODE
    params = dict(_PLAYBOOK_PARAMS.get(playbook, {}).get(mode, {}))
    if caution and params:
        params["position_size_multiplier"] = round(
            params.get("position_size_multiplier", 1.0) * _CAUTION_POSITION_MULTIPLIER, 3
        )
        params["max_hold_minutes"] = max(
            int(params.get("max_hold_minutes", 40) * _CAUTION_HOLD_FRACTION),
            _CAUTION_MIN_HOLD_MINUTES,
        )
        params["safety_exit_minutes"] = max(
            int(params.get("safety_exit_minutes", 20) * _CAUTION_HOLD_FRACTION),
            _CAUTION_MIN_EXIT_MINUTES,
        )
    return params
