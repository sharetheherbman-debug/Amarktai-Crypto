"""
Test Rules Package Imports
Ensures all required symbols are importable from the rules package.
If this test fails, bot spawn and reinvest are broken.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_calculate_reinvestment_amount_importable():
    """calculate_reinvestment_amount must be importable from rules"""
    from rules import calculate_reinvestment_amount
    assert callable(calculate_reinvestment_amount)


def test_get_reason_message_importable():
    """get_reason_message must be importable from rules"""
    from rules import get_reason_message
    assert callable(get_reason_message)


def test_profit_threshold_importable():
    """PROFIT_THRESHOLD_ZAR must be importable from rules"""
    from rules import PROFIT_THRESHOLD_ZAR
    assert isinstance(PROFIT_THRESHOLD_ZAR, (int, float))
    assert PROFIT_THRESHOLD_ZAR > 0


def test_validate_exchange_importable():
    """validate_exchange must be importable from rules"""
    from rules import validate_exchange
    assert callable(validate_exchange)


def test_supported_exchanges_importable():
    """SUPPORTED_EXCHANGES must be importable from rules"""
    from rules import SUPPORTED_EXCHANGES
    assert isinstance(SUPPORTED_EXCHANGES, list)
    assert len(SUPPORTED_EXCHANGES) == 7


def test_core_rules_importable():
    """Core rules symbols must be importable"""
    from rules import (
        BOT_RULES,
        get_max_bots_for_exchange,
        get_profit_threshold_for_exchange,
        check_bot_cap_limit,
        check_profit_threshold_met,
        get_reinvestment_rate,
        REASON_CODES
    )
    assert BOT_RULES is not None
    assert callable(get_max_bots_for_exchange)
    assert callable(get_profit_threshold_for_exchange)
    assert callable(check_bot_cap_limit)
    assert callable(check_profit_threshold_met)
    assert callable(get_reinvestment_rate)
    assert isinstance(REASON_CODES, dict)


def test_calculate_reinvestment_amount_logic():
    """Verify calculate_reinvestment_amount returns correct values"""
    from rules import calculate_reinvestment_amount
    
    # Default reinvestment rate is 80% (DEFAULT_REINVESTMENT_DECIMAL = 0.8)
    result = calculate_reinvestment_amount(1000.0, 5000.0)
    assert result == 800.0  # 80% of 1000
    
    # Limited by available funds
    result = calculate_reinvestment_amount(1000.0, 200.0)
    assert result == 200.0  # min(800, 200)


def test_get_reason_message_logic():
    """Verify get_reason_message returns messages for known codes"""
    from rules import get_reason_message, REASON_CODES
    
    for code in REASON_CODES:
        msg = get_reason_message(code)
        assert isinstance(msg, str)
        assert len(msg) > 0
    
    # Unknown code should return a fallback message
    msg = get_reason_message("UNKNOWN_CODE_XYZ")
    assert "Unknown reason" in msg


def test_validate_exchange_logic():
    """Verify validate_exchange accepts valid and rejects invalid exchanges"""
    from rules import validate_exchange
    
    # Valid exchanges
    for exchange in ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']:
        is_valid, reason = validate_exchange(exchange)
        assert is_valid is True, f"{exchange} should be valid"
        assert reason is None
    
    # Invalid exchanges
    for exchange in ['valr', 'ovex', 'nonexistent']:
        is_valid, reason = validate_exchange(exchange)
        assert is_valid is False, f"{exchange} should be invalid"
        assert reason == 'INVALID_EXCHANGE'


if __name__ == "__main__":
    test_calculate_reinvestment_amount_importable()
    test_get_reason_message_importable()
    test_profit_threshold_importable()
    test_validate_exchange_importable()
    test_supported_exchanges_importable()
    test_core_rules_importable()
    test_calculate_reinvestment_amount_logic()
    test_get_reason_message_logic()
    test_validate_exchange_logic()
    print("✅ All rules import tests passed!")
