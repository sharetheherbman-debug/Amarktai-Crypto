"""
System Settings - Single Source of Truth
Centralized environment variables and feature flags
All modules MUST reference this for configuration
"""

import os
from typing import Optional


def env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Boolean value from environment or default
    """
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Integer value from environment or default
    """
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def env_str(key: str, default: str = '') -> str:
    """Get string environment variable
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        String value from environment or default
    """
    return os.getenv(key, default)


# Database Configuration
MONGO_URL = env_str('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = env_str('DB_NAME', 'amarktai')

# Feature Flags
ENABLE_TRADING = env_bool('ENABLE_TRADING', False)
ENABLE_AUTOPILOT = env_bool('ENABLE_AUTOPILOT', False)
ENABLE_CCXT = env_bool('ENABLE_CCXT', True)
ENABLE_SCHEDULERS = env_bool('ENABLE_SCHEDULERS', False)
ENABLE_LIVE_TRADING = env_bool('ENABLE_LIVE_TRADING', False)

# AI Configuration
OPENAI_API_KEY = env_str('OPENAI_API_KEY', '')
OPENAI_MODEL = env_str('OPENAI_MODEL', 'gpt-4o')  # Can be overridden

# Security
JWT_SECRET = env_str('JWT_SECRET', 'your-secret-key-change-in-production')
ENCRYPTION_KEY = env_str('ENCRYPTION_KEY', '')  # For API key encryption

# Server Configuration
HOST = env_str('HOST', '0.0.0.0')
PORT = env_int('PORT', 8000)
DEBUG = env_bool('DEBUG', False)

# CORS Configuration
CORS_ORIGINS = env_str('CORS_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(',')

# Rate Limiting
RATE_LIMIT_ENABLED = env_bool('RATE_LIMIT_ENABLED', True)
RATE_LIMIT_PER_MINUTE = env_int('RATE_LIMIT_PER_MINUTE', 60)

# Trading Limits
MAX_BOTS_PER_USER = env_int('MAX_BOTS_PER_USER', 45)
MAX_CONCURRENT_TRADES = env_int('MAX_CONCURRENT_TRADES', 10)

# Monitoring
BODYGUARD_INTERVAL_SECONDS = env_int('BODYGUARD_INTERVAL_SECONDS', 300)  # 5 minutes
HEALTH_CHECK_INTERVAL_SECONDS = env_int('HEALTH_CHECK_INTERVAL_SECONDS', 60)

# Email Configuration (if enabled)
SMTP_ENABLED = env_bool('SMTP_ENABLED', False)
SMTP_HOST = env_str('SMTP_HOST', '')
SMTP_PORT = env_int('SMTP_PORT', 587)
SMTP_USER = env_str('SMTP_USER', '')
SMTP_PASSWORD = env_str('SMTP_PASSWORD', '')
SMTP_FROM = env_str('SMTP_FROM', 'noreply@amarktai.io')

# External Services
FLOKX_API_KEY = env_str('FLOKX_API_KEY', '')
FETCHAI_API_KEY = env_str('FETCHAI_API_KEY', '')

# Deployment Configuration
DEPLOYMENT_ENV = env_str('DEPLOYMENT_ENV', 'development')  # development, staging, production
IS_PRODUCTION = DEPLOYMENT_ENV == 'production'
IS_DEVELOPMENT = DEPLOYMENT_ENV == 'development'


def get_feature_flags() -> dict:
    """Get all feature flags as a dictionary
    
    Returns:
        Dict of feature flag names and values
    """
    return {
        'ENABLE_TRADING': ENABLE_TRADING,
        'ENABLE_AUTOPILOT': ENABLE_AUTOPILOT,
        'ENABLE_CCXT': ENABLE_CCXT,
        'ENABLE_SCHEDULERS': ENABLE_SCHEDULERS,
        'ENABLE_LIVE_TRADING': ENABLE_LIVE_TRADING,
        'RATE_LIMIT_ENABLED': RATE_LIMIT_ENABLED,
        'SMTP_ENABLED': SMTP_ENABLED,
    }


def get_system_info() -> dict:
    """Get system configuration info (non-sensitive)
    
    Returns:
        Dict of system configuration
    """
    return {
        'deployment_env': DEPLOYMENT_ENV,
        'is_production': IS_PRODUCTION,
        'debug': DEBUG,
        'database': {
            'url': MONGO_URL.replace(MONGO_URL.split('@')[-1] if '@' in MONGO_URL else '', '***'),
            'name': DB_NAME
        },
        'feature_flags': get_feature_flags(),
        'limits': {
            'max_bots_per_user': MAX_BOTS_PER_USER,
            'max_concurrent_trades': MAX_CONCURRENT_TRADES,
            'rate_limit_per_minute': RATE_LIMIT_PER_MINUTE
        }
    }
