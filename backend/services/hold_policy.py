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

# Paper-mode validation cap for normal bots.
# In paper mode, normal bots should not hold for hours — fast turnover is
# required for validation.  This cap overrides the risk-mode default when
# paper mode is active and the bot has no explicit max_hold_seconds set.
PAPER_NORMAL_MAX_HOLD_SECONDS = int(os.getenv("PAPER_NORMAL_MAX_HOLD_SECONDS", "1200"))  # 20 min (spec: 8–20 min range)


def resolve_hold_policy(
    bot: Dict[str, Any],
    open_trade: Optional[Dict[str, Any]] = None,
    *,
    is_paper_mode: bool = False,
) -> Dict[str, Any]:
    """Resolve canonical hold policy for a bot/trade.

    Parameters
    ----------
    bot : dict
        Bot document.
    open_trade : dict or None
        Open trade document (may carry explicit max_hold_seconds).
    is_paper_mode : bool
        When True the paper-mode hold cap is applied for normal bots so that
        paper validation completes in minutes rather than hours.
    """
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
        source = "explicit"
    elif bot_type == "scalper":
        max_hold_seconds = int(SCALPER_MAX_HOLD_SECONDS)
        source = "scalper_default"
    else:
        max_hold_seconds = int(NORMAL_MAX_HOLD_SECONDS[risk_mode])
        source = "normal_risk_mode_default"

    # Paper-mode adaptive cap: keep normal bot holds short for fast validation.
    # Explicit per-trade/per-bot values take precedence.
    if is_paper_mode and bot_type == "normal" and source != "explicit":
        if max_hold_seconds > PAPER_NORMAL_MAX_HOLD_SECONDS:
            max_hold_seconds = PAPER_NORMAL_MAX_HOLD_SECONDS
            source = "paper_normal_cap"

    return {
        "bot_type": bot_type,
        "risk_mode": risk_mode,
        "max_hold_seconds": max_hold_seconds,
        "source": source,
    }
