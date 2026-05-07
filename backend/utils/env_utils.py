"""
Environment utility functions for consistent configuration parsing.
"""
import os


def env_bool(name: str, default: bool = False) -> bool:
    """
    Parse environment variable as boolean.
    
    Returns True for: '1', 'true', 'yes', 'y', 'on' (case-insensitive)
    Returns default when variable is not set or empty.
    
    Args:
        name: Environment variable name
        default: Default value if variable is not set
        
    Returns:
        Boolean value
        
    Examples:
        >>> os.environ['TEST_VAR'] = 'true'
        >>> env_bool('TEST_VAR')
        True
        >>> env_bool('NONEXISTENT', default=False)
        False
    """
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip().lower()
    return value in {'1', 'true', 'yes', 'y', 'on'}


def get_trading_flags() -> dict:
    """
    Canonical trading flag resolver with legacy aliases.

    Canonical flags:
      - ENABLE_TRADING
      - ENABLE_PAPER_TRADING
      - ENABLE_LIVE_TRADING
      - ENABLE_AUTOPILOT

    Legacy aliases:
      - PAPER_TRADING
      - LIVE_TRADING
      - AUTOPILOT_ENABLED
    """
    legacy_paper = env_bool("PAPER_TRADING", False)
    legacy_live = env_bool("LIVE_TRADING", False)
    legacy_autopilot = env_bool("AUTOPILOT_ENABLED", False)

    enable_paper = env_bool("ENABLE_PAPER_TRADING", legacy_paper)
    enable_live = env_bool("ENABLE_LIVE_TRADING", legacy_live)
    enable_autopilot = env_bool("ENABLE_AUTOPILOT", legacy_autopilot)
    enable_trading = env_bool("ENABLE_TRADING", (enable_paper or enable_live))

    return {
        "enable_trading": enable_trading,
        "enable_paper_trading": enable_paper,
        "enable_live_trading": enable_live,
        "enable_autopilot": enable_autopilot,
        "legacy_paper_trading": legacy_paper,
        "legacy_live_trading": legacy_live,
        "legacy_autopilot_enabled": legacy_autopilot,
    }
