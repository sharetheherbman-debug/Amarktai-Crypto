"""
Target Policy — Strategy-based target derivation for bots.

Computes reasonable daily and per-trade profit targets based on:
  - bot_type (normal / scalper)
  - risk_mode (safe / balanced / aggressive)
  - capital allocated
  - strategy profile

Avoids hardcoded tiny defaults like "15 rand".
Returns sensible percentage-based targets with source metadata.
"""

from typing import Dict, Optional

# ── Target profiles per risk_mode × bot_type ─────────────────────────────
# daily_pct = expected daily target as fraction of capital
# trade_pct = expected per-trade target as fraction of capital
_TARGET_PROFILES = {
    ("normal", "safe"):       {"daily_pct": 0.005, "trade_pct": 0.003},
    ("normal", "balanced"):   {"daily_pct": 0.010, "trade_pct": 0.005},
    ("normal", "aggressive"): {"daily_pct": 0.020, "trade_pct": 0.010},
    ("scalper", "safe"):      {"daily_pct": 0.008, "trade_pct": 0.002},
    ("scalper", "balanced"):  {"daily_pct": 0.015, "trade_pct": 0.004},
    ("scalper", "aggressive"):{"daily_pct": 0.025, "trade_pct": 0.008},
}

_DEFAULT_PROFILE = {"daily_pct": 0.010, "trade_pct": 0.005}


def derive_targets(bot: Dict) -> Dict:
    """Derive strategy-based targets for a bot.

    Returns dict with:
      daily_profit_target  — absolute ZAR value
      trade_profit_target  — absolute ZAR value
      daily_target_pct     — percentage used
      trade_target_pct     — percentage used
      target_source        — 'configured' | 'strategy_derived'
    """
    bot_type = (bot.get("bot_type") or "normal").lower()
    risk_mode = (bot.get("risk_mode") or bot.get("risk_profile") or "balanced").lower()
    capital = float(bot.get("current_capital", bot.get("initial_capital", 0)) or 0)

    # Check if bot has explicitly configured targets
    configured_daily = _get_configured_pct(bot, "daily_profit_target_pct", "daily_target_pct")
    configured_trade = _get_configured_pct(bot, "trade_profit_target_pct", "per_trade_target_pct")

    if configured_daily is not None or configured_trade is not None:
        daily_pct = configured_daily if configured_daily is not None else _DEFAULT_PROFILE["daily_pct"]
        trade_pct = configured_trade if configured_trade is not None else _DEFAULT_PROFILE["trade_pct"]
        source = "configured"
    else:
        profile = _TARGET_PROFILES.get((bot_type, risk_mode), _DEFAULT_PROFILE)
        daily_pct = profile["daily_pct"]
        trade_pct = profile["trade_pct"]
        source = "strategy_derived"

    return {
        "daily_profit_target": round(capital * daily_pct, 2) if capital > 0 else None,
        "trade_profit_target": round(capital * trade_pct, 2) if capital > 0 else None,
        "daily_target_pct": round(daily_pct * 100, 2),
        "trade_target_pct": round(trade_pct * 100, 2),
        "target_source": source,
        "risk_mode": risk_mode,
        "bot_type": bot_type,
    }


def _get_configured_pct(bot: Dict, *keys: str) -> Optional[float]:
    """Return first configured non-negative percentage from bot payload keys."""
    for key in keys:
        value = bot.get(key)
        if value is None:
            continue
        try:
            pct = float(value)
        except (TypeError, ValueError):
            continue
        if pct > 0:
            return pct
    return None
