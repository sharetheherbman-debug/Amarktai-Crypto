"""
Exchange Configuration for Wallet Requirements
Defines required fields and deposit requirements for each supported exchange
"""

# Required fields per exchange
EXCHANGE_REQUIRED_FIELDS = {
    "luno": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Luno requires ZAR wallet for deposits"
    },
    "binance": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Binance may require KYC verification"
    },
    "kucoin": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "KuCoin supports multiple trading pairs"
    },
    "bybit": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Bybit supports derivatives and spot trading"
    },
    "kraken": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Kraken is a trusted exchange with strong security"
    },
    "bitget": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Bitget supports copy trading and futures"
    },
    "gate": {
        "api_key": "API Key (public)",
        "api_secret": "API Secret (private)",
        "note": "Gate.io supports a wide range of altcoins"
    }
}

# Default fields for unknown exchanges
DEFAULT_REQUIRED_FIELDS = {
    "api_key": "API Key (public)",
    "api_secret": "API Secret (private)"
}

# Deposit requirements per exchange
EXCHANGE_DEPOSIT_REQUIREMENTS = {
    "luno": {
        "min_deposit_zar": 100,
        "deposit_methods": ["EFT", "Card"],
        "processing_time": "Instant to 2 hours"
    },
    "binance": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto", "Card", "P2P"],
        "processing_time": "Instant to 30 minutes"
    },
    "kucoin": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto"],
        "processing_time": "Network dependent"
    },
    "bybit": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto", "Card"],
        "processing_time": "Instant to 30 minutes"
    },
    "kraken": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto", "Wire Transfer"],
        "processing_time": "Varies by method"
    },
    "bitget": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto", "Card"],
        "processing_time": "Instant to 30 minutes"
    },
    "gate": {
        "min_deposit_zar": 0,
        "deposit_methods": ["Crypto"],
        "processing_time": "Network dependent"
    }
}

# Default deposit requirements for unknown exchanges
DEFAULT_DEPOSIT_REQUIREMENTS = {
    "min_deposit_zar": 0,
    "deposit_methods": ["Various"],
    "processing_time": "Varies"
}


def get_required_fields(exchange: str) -> dict:
    """Get required fields for an exchange
    
    Args:
        exchange: Exchange name (lowercase)
        
    Returns:
        Dictionary of required fields with descriptions
    """
    return EXCHANGE_REQUIRED_FIELDS.get(exchange, DEFAULT_REQUIRED_FIELDS.copy())


def get_deposit_requirements(exchange: str) -> dict:
    """Get deposit requirements for an exchange
    
    Args:
        exchange: Exchange name (lowercase)
        
    Returns:
        Dictionary with deposit requirements
    """
    return EXCHANGE_DEPOSIT_REQUIREMENTS.get(exchange, DEFAULT_DEPOSIT_REQUIREMENTS.copy())
