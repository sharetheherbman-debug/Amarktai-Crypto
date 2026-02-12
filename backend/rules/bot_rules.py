"""
Bot Rules - Single Source of Truth
All bot-related business rules enforced across the entire system
"""

from typing import Dict, Tuple, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Supported exchanges (7 only)
SUPPORTED_EXCHANGES = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']

# Bot capacity rules per exchange
BOT_CAPS = {
    'luno': 5,      # Luno max 5 bots (paper+live combined)
    'binance': 10,  # All other exchanges max 10 bots (paper+live combined)
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10
}

# Profit thresholds for auto-growth (per exchange, in ZAR)
PROFIT_THRESHOLD_ZAR = 1000  # R1000 realized profit required per exchange

# Reinvestment configuration
REINVESTMENT_RATE = float(os.getenv("REINVEST_PERCENTAGE", "80")) / 100  # Default 80%

# Reason codes for rejections
REASON_CODES = {
    'BOT_CAP_EXCEEDED': 'Bot capacity limit exceeded for this exchange',
    'INSUFFICIENT_EXCHANGE_PROFIT': 'Insufficient realized profit on this exchange for auto-growth',
    'INSUFFICIENT_FUNDS_TO_SPAWN': 'Insufficient available funds to spawn new bot',
    'TRADING_MODE_DISABLED': 'Trading mode is disabled (both paper and live are off)',
    'INVALID_EXCHANGE': 'Exchange is not supported',
    'AUTOPILOT_DISABLED': 'Autopilot/auto-growth is disabled'
}

# Complete rules configuration
BOT_RULES = {
    'supported_exchanges': SUPPORTED_EXCHANGES,
    'bot_caps': BOT_CAPS,
    'profit_threshold_zar': PROFIT_THRESHOLD_ZAR,
    'reinvestment_rate': REINVESTMENT_RATE,
    'reason_codes': REASON_CODES
}


def get_max_bots_for_exchange(exchange: str) -> int:
    """
    Get maximum bot count for a given exchange
    
    Args:
        exchange: Exchange identifier (lowercase)
        
    Returns:
        Maximum bot count (5 for luno, 10 for others)
    """
    exchange = exchange.lower()
    if exchange not in SUPPORTED_EXCHANGES:
        logger.warning(f"Unknown exchange '{exchange}', returning 0")
        return 0
    return BOT_CAPS.get(exchange, 10)


def get_profit_threshold_for_exchange(exchange: str) -> float:
    """
    Get profit threshold required for auto-growth on this exchange
    
    Args:
        exchange: Exchange identifier
        
    Returns:
        Profit threshold in ZAR (currently R1000 for all exchanges)
    """
    return PROFIT_THRESHOLD_ZAR


def check_bot_cap_limit(exchange: str, current_bot_count: int, 
                        user_id: str = None) -> Tuple[bool, Optional[str]]:
    """
    Check if user can create more bots on this exchange
    
    Args:
        exchange: Exchange identifier
        current_bot_count: Current number of bots user has on this exchange (paper+live)
        user_id: Optional user ID for logging
        
    Returns:
        Tuple of (can_create: bool, reason_code: Optional[str])
    """
    exchange = exchange.lower()
    
    # Validate exchange
    if exchange not in SUPPORTED_EXCHANGES:
        return False, 'INVALID_EXCHANGE'
    
    max_bots = get_max_bots_for_exchange(exchange)
    
    if current_bot_count >= max_bots:
        logger.info(f"Bot cap exceeded for user {user_id or 'unknown'} on {exchange}: {current_bot_count}/{max_bots}")
        return False, 'BOT_CAP_EXCEEDED'
    
    return True, None


def check_profit_threshold_met(exchange: str, realized_profit_zar: float, 
                                trading_mode: str = 'paper',
                                user_id: str = None) -> Tuple[bool, Optional[str]]:
    """
    Check if exchange has generated enough profit for auto-growth
    
    Args:
        exchange: Exchange identifier
        realized_profit_zar: Total realized profit on this exchange (ZAR)
        trading_mode: 'paper' or 'live' (determines which profit to check)
        user_id: Optional user ID for logging
        
    Returns:
        Tuple of (threshold_met: bool, reason_code: Optional[str])
    """
    threshold = get_profit_threshold_for_exchange(exchange)
    
    if realized_profit_zar < threshold:
        logger.info(
            f"Profit threshold not met for user {user_id or 'unknown'} on {exchange} "
            f"({trading_mode}): R{realized_profit_zar:.2f} < R{threshold:.2f}"
        )
        return False, 'INSUFFICIENT_EXCHANGE_PROFIT'
    
    return True, None


def get_reinvestment_rate() -> float:
    """
    Get the configured reinvestment rate
    
    Returns:
        Reinvestment rate as decimal (e.g., 0.5 = 50%)
    """
    return REINVESTMENT_RATE


def calculate_reinvestment_amount(realized_profit_zar: float, 
                                   available_funds_zar: float) -> float:
    """
    Calculate how much can be reinvested from realized profits
    
    Args:
        realized_profit_zar: Realized profit available
        available_funds_zar: Available funds in wallet
        
    Returns:
        Amount that can be reinvested (ZAR)
    """
    # Can reinvest up to REINVESTMENT_RATE of realized profit
    max_reinvest = realized_profit_zar * REINVESTMENT_RATE
    
    # But never more than available funds
    return min(max_reinvest, available_funds_zar)


def validate_exchange(exchange: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that exchange is supported
    
    Args:
        exchange: Exchange identifier
        
    Returns:
        Tuple of (is_valid: bool, reason_code: Optional[str])
    """
    if exchange.lower() not in SUPPORTED_EXCHANGES:
        return False, 'INVALID_EXCHANGE'
    return True, None


def get_reason_message(reason_code: str) -> str:
    """
    Get human-readable message for reason code
    
    Args:
        reason_code: Reason code key
        
    Returns:
        Human-readable message
    """
    return REASON_CODES.get(reason_code, f"Unknown reason: {reason_code}")
