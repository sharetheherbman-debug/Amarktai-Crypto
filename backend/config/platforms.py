"""
Platform Configuration - Single Source of Truth
Defines all 5 supported trading platforms/exchanges
All platform-related logic MUST reference this module
"""

from typing import Dict, List, Optional

# All supported platforms (canonical list) - EXACTLY 5 PLATFORMS
SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'bybit', 'bitget']

# Platform configuration with complete metadata
PLATFORM_CONFIG: Dict[str, Dict] = {
    'luno': {
        'id': 'luno',
        'name': 'Luno',
        'display_name': 'Luno',
        'icon': '🇿🇦',
        'color': '#3861FB',
        'max_bots': 5,
        'region': 'ZA',
        'requires_passphrase': False,
        'enabled': True,
        'supports_paper': True,
        'supports_live': True,
        'required_key_fields': ['api_key', 'api_secret'],
        'ccxt_id': 'luno',
        'description': 'South African cryptocurrency exchange'
    },
    'binance': {
        'id': 'binance',
        'name': 'Binance',
        'display_name': 'Binance',
        'icon': '🟡',
        'color': '#F3BA2F',
        'max_bots': 10,
        'region': 'Global',
        'requires_passphrase': False,
        'enabled': True,
        'supports_paper': True,
        'supports_live': True,
        'required_key_fields': ['api_key', 'api_secret'],
        'ccxt_id': 'binance',
        'description': 'Global cryptocurrency exchange'
    },
    'kucoin': {
        'id': 'kucoin',
        'name': 'KuCoin',
        'display_name': 'KuCoin',
        'icon': '🟢',
        'color': '#23AF91',
        'max_bots': 10,
        'region': 'Global',
        'requires_passphrase': True,
        'enabled': True,
        'supports_paper': True,
        'supports_live': True,
        'required_key_fields': ['api_key', 'api_secret', 'passphrase'],
        'ccxt_id': 'kucoin',
        'description': 'Global cryptocurrency exchange'
    },
    'bybit': {
        'id': 'bybit',
        'name': 'Bybit',
        'display_name': 'Bybit',
        'icon': '🟠',
        'color': '#F7A600',
        'max_bots': 10,
        'region': 'Global',
        'requires_passphrase': False,
        'enabled': True,
        'supports_paper': True,
        'supports_live': True,
        'required_key_fields': ['api_key', 'api_secret'],
        'ccxt_id': 'bybit',
        'description': 'Global derivatives and cryptocurrency exchange'
    },
    'bitget': {
        'id': 'bitget',
        'name': 'Bitget',
        'display_name': 'Bitget',
        'icon': '🔵',
        'color': '#00F0FF',
        'max_bots': 10,
        'region': 'Global',
        'requires_passphrase': True,
        'enabled': True,
        'supports_paper': True,
        'supports_live': True,
        'required_key_fields': ['api_key', 'api_secret', 'passphrase'],
        'ccxt_id': 'bitget',
        'description': 'Global cryptocurrency and derivatives exchange'
    }
}

# Total bot capacity across all platforms
TOTAL_BOT_CAPACITY = sum(p['max_bots'] for p in PLATFORM_CONFIG.values())


def get_platform_config(platform_id: str) -> Optional[Dict]:
    """Get configuration for a specific platform
    
    Args:
        platform_id: Platform identifier (case-insensitive)
        
    Returns:
        Platform config dict or None if not found
    """
    return PLATFORM_CONFIG.get(platform_id.lower())


def is_valid_platform(platform_id: str) -> bool:
    """Check if platform ID is valid
    
    Args:
        platform_id: Platform identifier to validate
        
    Returns:
        True if platform is supported, False otherwise
    """
    return platform_id.lower() in SUPPORTED_PLATFORMS


def get_enabled_platforms() -> List[str]:
    """Get list of enabled platform IDs
    
    Returns:
        List of enabled platform IDs
    """
    return [p for p in SUPPORTED_PLATFORMS if PLATFORM_CONFIG[p]['enabled']]


def get_all_platforms() -> List[Dict]:
    """Get all platform configs as a list
    
    Returns:
        List of all platform configuration dicts
    """
    return [PLATFORM_CONFIG[pid] for pid in SUPPORTED_PLATFORMS]


def get_platform_display_name(platform_id: str) -> str:
    """Get display name for platform
    
    Args:
        platform_id: Platform identifier
        
    Returns:
        Display name or uppercase platform_id if not found
    """
    config = get_platform_config(platform_id)
    return config.get('display_name', platform_id.upper()) if config else platform_id.upper()


def get_max_bots(platform_id: str) -> int:
    """Get maximum bots allowed for platform
    
    Args:
        platform_id: Platform identifier
        
    Returns:
        Max bot count or 0 if platform not found
    """
    config = get_platform_config(platform_id)
    return config.get('max_bots', 0) if config else 0


def validate_platform_for_mode(platform_id: str, mode: str) -> tuple[bool, Optional[str]]:
    """Validate if platform supports the requested trading mode
    
    Args:
        platform_id: Platform identifier
        mode: Trading mode ('paper' or 'live')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    config = get_platform_config(platform_id)
    
    if not config:
        return False, f"Platform '{platform_id}' is not supported"
    
    if mode == 'paper' and not config.get('supports_paper'):
        return False, f"Platform '{platform_id}' does not support paper trading"
    
    if mode == 'live' and not config.get('supports_live'):
        return False, f"Platform '{platform_id}' does not support live trading yet"
    
    return True, None


def get_required_key_fields(platform_id: str) -> List[str]:
    """Get required API key fields for platform
    
    Args:
        platform_id: Platform identifier
        
    Returns:
        List of required field names
    """
    config = get_platform_config(platform_id)
    return config.get('required_key_fields', []) if config else []


def normalize_platform_id(platform_id: str) -> str:
    """Normalize platform ID to canonical lowercase form
    
    Args:
        platform_id: Platform identifier (any case)
        
    Returns:
        Normalized lowercase platform ID
    """
    return platform_id.lower().strip()
