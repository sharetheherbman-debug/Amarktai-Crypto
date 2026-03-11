"""
Canonical hold-policy resolver shared by engine and API routes.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exchange_limits import SCALPER_MAX_HOLD_SECONDS


NORMAL_MAX_HOLD_SECONDS = {
    "safe": int(os.getenv("NORMAL_SAFE_MAX_HOLD_SECONDS", "21600")),       # 6 hours
    "balanced": int(os.getenv("NORMAL_BALANCED_MAX_HOLD_SECONDS", "10800")),  # 3 hours
    "aggressive": int(os.getenv("NORMAL_AGGRESSIVE_MAX_HOLD_SECONDS", "5400")),  # 90 minutes
}


def resolve_hold_policy(bot: Dict[str, Any], open_trade: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve canonical hold policy for a bot/trade."""
    source_trade = open_trade or {}
    bot_type = str(bot.get("bot_type") or source_trade.get("bot_type") or "normal").lower()
    risk_mode = str(bot.get("risk_mode") or bot.get("risk_profile") or "balanced").lower()
    if risk_mode not in NORMAL_MAX_HOLD_SECONDS:
        risk_mode = "balanced"

    explicit_max_hold = source_trade.get("max_hold_seconds", bot.get("max_hold_seconds"))
    try:
        # Explicit values may be stored as numeric strings in historical docs.
        # float(...) handles values like "300.5"; int(...) normalizes to whole seconds.
        # Canonical policy resolves to integer-second hold durations.
        explicit_max_hold = int(float(explicit_max_hold)) if explicit_max_hold is not None else None
    except (TypeError, ValueError):
        explicit_max_hold = None

    if explicit_max_hold and explicit_max_hold > 0:
        max_hold_seconds = explicit_max_hold
    elif bot_type == "scalper":
        max_hold_seconds = int(SCALPER_MAX_HOLD_SECONDS)
    else:
        max_hold_seconds = int(NORMAL_MAX_HOLD_SECONDS[risk_mode])

    return {
        "bot_type": bot_type,
        "risk_mode": risk_mode,
        "max_hold_seconds": max_hold_seconds,
        "source": "explicit" if explicit_max_hold else ("scalper_default" if bot_type == "scalper" else "normal_risk_mode_default"),
    }
