from typing import Any, Mapping


def normalize_trading_mode(value: Any, default: str = "paper") -> str:
    """Normalize trading mode values from legacy fields."""
    raw = str(value or "").strip().lower()
    if raw.startswith("live"):
        return "live"
    if raw.startswith("paper"):
        return "paper"
    if raw.startswith("auto"):
        return "autopilot"
    return default


def resolve_bot_trading_mode(bot: Mapping[str, Any], default: str = "paper") -> str:
    """Resolve trading mode from bot document aliases."""
    if not bot:
        return default
    return normalize_trading_mode(bot.get("trading_mode") or bot.get("mode"), default=default)

