"""
Bot Rules Module
Single source of truth for all bot-related business rules
"""

from .bot_rules import (
    BOT_RULES,
    PROFIT_THRESHOLD_ZAR,
    SUPPORTED_EXCHANGES,
    get_max_bots_for_exchange,
    get_profit_threshold_for_exchange,
    check_bot_cap_limit,
    check_profit_threshold_met,
    get_reinvestment_rate,
    calculate_reinvestment_amount,
    validate_exchange,
    get_reason_message,
    REASON_CODES
)

__all__ = [
    'BOT_RULES',
    'PROFIT_THRESHOLD_ZAR',
    'SUPPORTED_EXCHANGES',
    'get_max_bots_for_exchange',
    'get_profit_threshold_for_exchange',
    'check_bot_cap_limit',
    'check_profit_threshold_met',
    'get_reinvestment_rate',
    'calculate_reinvestment_amount',
    'validate_exchange',
    'get_reason_message',
    'REASON_CODES'
]
