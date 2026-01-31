"""
Backend Authoritative Platform Registry

This module is the SINGLE SOURCE OF TRUTH for supported platforms.
All other parts of the application should consume from here.

Supported platforms: luno, binance, kucoin, bybit, kraken, bitget, gate (exactly 7)

This module re-exports from config.platforms to provide a consistent import path.
"""

# Re-export everything from config.platforms (the true source of truth)
from config.platforms import (
    SUPPORTED_PLATFORMS,
    PLATFORM_CONFIG as PLATFORM_REGISTRY,
    TOTAL_BOT_CAPACITY,
    get_all_platforms,
    get_platform_config,
    is_valid_platform,
    get_enabled_platforms,
    get_platform_display_name,
    get_max_bots,
    get_required_key_fields,
    normalize_platform_id,
    validate_platform_for_mode
)

# For backward compatibility
__all__ = [
    'SUPPORTED_PLATFORMS',
    'PLATFORM_REGISTRY',
    'TOTAL_BOT_CAPACITY',
    'get_all_platforms',
    'get_platform_config',
    'is_valid_platform',
    'get_enabled_platforms',
    'get_platform_display_name',
    'get_max_bots',
    'get_required_key_fields',
    'normalize_platform_id',
    'validate_platform_for_mode',
]
