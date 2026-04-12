"""
Bot Rules - Single Source of Truth
All bot-related business rules enforced across the entire system
"""

from typing import Dict, Tuple, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Supported exchanges (8 platforms)
SUPPORTED_EXCHANGES = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate', 'coinbase']

# Bot capacity rules per exchange — NORMAL bots only
# Scalper bots have their own separate caps below.
BOT_CAPS = {
    'luno': 5,      # Luno normal max 5
    'binance': 10,  # All other exchanges normal max 10
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10,
    'coinbase': 10,
}

# Scalper-specific caps per exchange (do NOT share slots with normal bots)
SCALPER_CAPS = {
    'luno': 5,      # Luno scalper max 5
    'binance': 10,  # All other exchanges scalper max 10
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10,
    'coinbase': 10,
}

# Profit thresholds for auto-growth (per exchange, in ZAR)
PROFIT_THRESHOLD_ZAR = 1000  # R1000 realized profit required per exchange

# Reinvestment configuration
DEFAULT_REINVESTMENT_DECIMAL = 0.5  # Default 50% as decimal rate
def _parse_float(value: Optional[str], name: str) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid %s value '%s'; using default", name, value)
        return None

def _resolve_reinvestment_rate() -> float:
    default_rate = DEFAULT_REINVESTMENT_DECIMAL
    percent_value = os.getenv("REINVEST_PERCENTAGE")
    rate_value = os.getenv("REINVESTMENT_RATE")

    if percent_value:
        parsed = _parse_float(percent_value, "REINVEST_PERCENTAGE")
        if parsed is None:
            return default_rate
        if 0 <= parsed <= 100:
            return parsed / 100
        logger.warning("REINVEST_PERCENTAGE should be between 0 and 100; using default")
        return default_rate

    if rate_value:
        parsed = _parse_float(rate_value, "REINVESTMENT_RATE")
        if parsed is None:
            return default_rate
        if parsed < 0:
            logger.warning("REINVESTMENT_RATE must be non-negative; using default")
            return default_rate
        if parsed <= 1:
            # Expected decimal rate (0-1)
            return parsed
        if parsed <= 100:
            logger.warning(
                "REINVESTMENT_RATE value %.2f appears to be a percentage (expected 0-1); converting to rate",
                parsed
            )
            return parsed / 100
        logger.warning("REINVESTMENT_RATE percentage %.2f exceeds 100; using default", parsed)
        return default_rate

    return default_rate

REINVESTMENT_RATE = _resolve_reinvestment_rate()

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
    'scalper_caps': SCALPER_CAPS,
    'profit_threshold_zar': PROFIT_THRESHOLD_ZAR,
    'reinvestment_rate': REINVESTMENT_RATE,
    'reason_codes': REASON_CODES
}


def get_max_bots_for_exchange(exchange: str, bot_type: str = 'normal') -> int:
    """
    Get maximum bot count for a given exchange and bot type.

    Normal bots and scalper bots have separate caps and never share slots.

    Args:
        exchange: Exchange identifier (lowercase)
        bot_type: 'normal' or 'scalper' (default: 'normal')

    Returns:
        Maximum bot count for the given type on this exchange.
    """
    exchange = exchange.lower()
    if exchange not in SUPPORTED_EXCHANGES:
        logger.warning(f"Unknown exchange '{exchange}', returning 0")
        return 0
    if str(bot_type).lower() == 'scalper':
        return SCALPER_CAPS.get(exchange, 5)
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
                        user_id: str = None,
                        bot_type: str = 'normal') -> Tuple[bool, Optional[str]]:
    """
    Check if user can create more bots on this exchange.

    Normal bots and scalper bots each have their own separate caps.
    Scalper bots do NOT consume normal bot slots, and vice versa.

    Args:
        exchange: Exchange identifier
        current_bot_count: Current number of bots of *bot_type* user has on this exchange
        user_id: Optional user ID for logging
        bot_type: 'normal' or 'scalper' (default: 'normal')

    Returns:
        Tuple of (can_create: bool, reason_code: Optional[str])
    """
    exchange = exchange.lower()

    # Validate exchange
    if exchange not in SUPPORTED_EXCHANGES:
        return False, 'INVALID_EXCHANGE'

    max_bots = get_max_bots_for_exchange(exchange, bot_type=bot_type)

    if current_bot_count > max_bots:
        logger.info(
            "Bot cap exceeded for user %s on %s (%s): %d/%d",
            user_id or 'unknown', exchange, bot_type, current_bot_count, max_bots,
        )
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
