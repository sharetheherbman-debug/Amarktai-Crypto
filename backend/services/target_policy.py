"""
Target Policy — Strategy-based target derivation for bots.

Computes reasonable daily and per-trade profit targets based on:
  - bot_type (normal / scalper)
  - risk_mode (safe / balanced / aggressive)
  - exchange (Luno/ZAR vs USDT exchanges)
  - capital allocated
  - strategy profile

Targets are exchange-cost-aware:
  - Luno (ZAR) bots face higher round-trip costs (~1-2%) and require
    higher minimum targets to be above the cost floor.
  - USDT exchanges (Binance, KuCoin, Bybit, etc.) have lower costs
    (~0.2%) and use standard profiles.

Avoids targets that are below the exchange cost floor and therefore
economically meaningless (e.g. "8 ZAR on 1000 ZAR capital" for Luno).
Returns sensible percentage-based targets with source metadata.
"""

from typing import Dict, Optional

# ── Round-trip cost floor per exchange ────────────────────────────────────
# Approximate total round-trip cost as fraction of notional:
#   fees (taker × 2 sides) + spread
# Luno: taker fee 0.5% × 2 = 1.0% + spread 0.5% = 1.5% total
# Default: taker fee 0.1% × 2 = 0.2% + spread 0.1% = 0.3% total
# Targets must meaningfully exceed these floors to be non-trivial.
_EXCHANGE_COST_FLOOR: Dict[str, float] = {
    "luno":    0.015,   # 1.5% round-trip: 0.5% taker×2 + 0.5% spread
    "default": 0.003,   # 0.3% round-trip: 0.1% taker×2 + 0.1% spread
}

# Luno minimum daily target percentage — always at least this fraction of
# capital, regardless of risk_mode.
# Set at 2.0%: meaningfully above Luno's 1.5% round-trip cost floor,
# ensuring targets are non-trivial (not below breakeven).
_LUNO_MIN_DAILY_PCT = 0.020   # 2.0% of capital/day — above Luno's cost floor
_LUNO_MIN_TRADE_PCT = 0.008   # 0.8% of capital per trade

# ── Target profiles per risk_mode × bot_type ─────────────────────────────
# For USDT exchanges (Binance, KuCoin, Bybit, etc.) — low cost floor.
# daily_pct = expected daily target as fraction of capital
# trade_pct = expected per-trade target as fraction of capital
_TARGET_PROFILES = {
    ("normal", "safe"):       {"daily_pct": 0.010, "trade_pct": 0.005},
    ("normal", "balanced"):   {"daily_pct": 0.020, "trade_pct": 0.008},
    ("normal", "aggressive"): {"daily_pct": 0.035, "trade_pct": 0.015},
    ("scalper", "safe"):      {"daily_pct": 0.015, "trade_pct": 0.004},
    ("scalper", "balanced"):  {"daily_pct": 0.025, "trade_pct": 0.007},
    ("scalper", "aggressive"):{"daily_pct": 0.040, "trade_pct": 0.012},
}

# ── Luno-specific profiles ────────────────────────────────────────────────
# Higher percentages required because Luno's ZAR spreads and fees are
# significantly wider than USDT exchanges (1.5% round-trip vs 0.3%).
# Minimum daily target is enforced via _LUNO_MIN_DAILY_PCT (2.0%) so
# profiles below that floor are automatically raised.
_LUNO_TARGET_PROFILES = {
    ("normal", "safe"):       {"daily_pct": 0.020, "trade_pct": 0.010},
    ("normal", "balanced"):   {"daily_pct": 0.035, "trade_pct": 0.015},
    ("normal", "aggressive"): {"daily_pct": 0.060, "trade_pct": 0.025},
    ("scalper", "safe"):      {"daily_pct": 0.025, "trade_pct": 0.008},
    ("scalper", "balanced"):  {"daily_pct": 0.040, "trade_pct": 0.012},
    ("scalper", "aggressive"):{"daily_pct": 0.070, "trade_pct": 0.020},
}

_DEFAULT_PROFILE = {"daily_pct": 0.020, "trade_pct": 0.008}


def derive_targets(bot: Dict) -> Dict:
    """Derive exchange-aware, strategy-based targets for a bot.

    Returns dict with:
      daily_profit_target  — absolute value in quote currency
      trade_profit_target  — absolute value in quote currency
      daily_target_pct     — percentage used
      trade_target_pct     — percentage used
      target_source        — 'configured' | 'strategy_derived'
      exchange             — exchange name (for audit)

    Exchange economics are factored in:
      Luno/ZAR bots use higher minimum percentages due to wider spreads
      and higher trading fees vs USDT exchanges.
    """
    bot_type = (bot.get("bot_type") or "normal").lower()
    risk_mode = (bot.get("risk_mode") or bot.get("risk_profile") or "balanced").lower()
    exchange = (bot.get("exchange") or "").lower()
    capital = float(bot.get("current_capital", bot.get("initial_capital", 0)) or 0)

    # Check if bot has explicitly configured targets
    configured_daily = _get_configured_pct(bot, "daily_profit_target_pct", "daily_target_pct")
    configured_trade = _get_configured_pct(bot, "trade_profit_target_pct", "per_trade_target_pct")

    if configured_daily is not None or configured_trade is not None:
        daily_pct = configured_daily if configured_daily is not None else _DEFAULT_PROFILE["daily_pct"]
        trade_pct = configured_trade if configured_trade is not None else _DEFAULT_PROFILE["trade_pct"]
        source = "configured"
    else:
        # Select profile table — Luno has higher cost floor so uses Luno profiles
        is_luno = (exchange == "luno")
        profile_table = _LUNO_TARGET_PROFILES if is_luno else _TARGET_PROFILES
        profile = profile_table.get((bot_type, risk_mode), _DEFAULT_PROFILE)
        daily_pct = profile["daily_pct"]
        trade_pct = profile["trade_pct"]

        # For Luno bots apply an absolute minimum floor so targets are never
        # below the exchange cost floor (meaningless targets).
        if is_luno:
            daily_pct = max(daily_pct, _LUNO_MIN_DAILY_PCT)
            trade_pct = max(trade_pct, _LUNO_MIN_TRADE_PCT)

        source = "strategy_derived"

    return {
        "daily_profit_target": round(capital * daily_pct, 2) if capital > 0 else None,
        "trade_profit_target": round(capital * trade_pct, 2) if capital > 0 else None,
        "daily_target_pct": round(daily_pct * 100, 2),
        "trade_target_pct": round(trade_pct * 100, 2),
        "target_source": source,
        "risk_mode": risk_mode,
        "bot_type": bot_type,
        "exchange": exchange,
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
