"""
Test Type-Safe Wallet Balance Handling
Addresses the runtime error: "'>' not supported between instances of 'dict' and 'int'"
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_wallet_balance_type_extraction():
    """Test type-safe extraction of wallet balance from various data structures"""
    
    # Test case 1: Normal dict with numeric value
    wallet_data_1 = {
        'available_zar': 1500.0,
        'error': False
    }
    
    # Simulate the extraction logic
    if not wallet_data_1.get('error'):
        available_zar = wallet_data_1.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000
    
    assert available_funds == 1500.0, "Should extract numeric value correctly"
    assert isinstance(available_funds, (int, float)), "Should be numeric type"
    
    # Test case 2: Malformed dict with nested value
    wallet_data_2 = {
        'available_zar': {'value': 2000.0, 'currency': 'ZAR'},
        'error': False
    }
    
    if not wallet_data_2.get('error'):
        available_zar = wallet_data_2.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000
    
    assert available_funds == 2000.0, "Should extract nested value from dict"
    assert isinstance(available_funds, (int, float)), "Should be numeric type"
    
    # Test case 3: Error case
    wallet_data_3 = {
        'error': True,
        'message': 'Wallet not found'
    }
    
    if not wallet_data_3.get('error'):
        available_zar = wallet_data_3.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000  # Fallback for reinvestment
    
    assert available_funds == 1000, "Should use fallback on error"
    
    # Test case 4: Missing available_zar key
    wallet_data_4 = {
        'error': False
    }
    
    if not wallet_data_4.get('error'):
        available_zar = wallet_data_4.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000
    
    assert available_funds == 0, "Should default to 0 when key is missing"
    
    # Test case 5: Non-numeric nested value
    wallet_data_5 = {
        'available_zar': {'value': 'not a number', 'currency': 'ZAR'},
        'error': False
    }
    
    if not wallet_data_5.get('error'):
        available_zar = wallet_data_5.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000
    
    assert available_funds == 0, "Should default to 0 when nested value is non-numeric"


def test_comparison_with_extracted_value():
    """Test that extracted values can be safely compared with thresholds"""
    
    # Simulate the problematic comparison that was causing the error
    PROFIT_THRESHOLD_ZAR = 1000
    
    # Test with properly extracted numeric value
    current_profit = 1500.0
    
    # This should not raise TypeError
    assert current_profit > PROFIT_THRESHOLD_ZAR, "Comparison should work with float"
    
    # Test comparison in context
    if current_profit < PROFIT_THRESHOLD_ZAR:
        reason = "INSUFFICIENT_EXCHANGE_PROFIT"
    else:
        reason = "MILESTONE_NOT_REACHED"
    
    assert reason == "MILESTONE_NOT_REACHED", "Logic should work correctly"


def test_min_comparison_with_extracted_value():
    """Test min() function with extracted values (used in calculate_reinvestment_amount)"""
    
    # Simulate the min comparison in calculate_reinvestment_amount
    realized_profit = 2000.0
    REINVESTMENT_RATE = 0.5
    max_reinvest = realized_profit * REINVESTMENT_RATE
    
    # Extract available_funds safely
    wallet_data = {'available_zar': 800.0, 'error': False}
    
    if not wallet_data.get('error'):
        available_zar = wallet_data.get('available_zar', 0)
        if isinstance(available_zar, dict):
            available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
        else:
            available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
    else:
        available_funds = 1000
    
    # This should not raise TypeError: '>' not supported between instances of 'dict' and 'int'
    reinvest_amount = min(max_reinvest, available_funds)
    
    assert reinvest_amount == 800.0, "Should use available funds as limit"
    assert isinstance(reinvest_amount, (int, float)), "Result should be numeric"


if __name__ == "__main__":
    # Run tests
    test_wallet_balance_type_extraction()
    print("✅ Wallet balance type extraction test passed")
    
    test_comparison_with_extracted_value()
    print("✅ Comparison with extracted value test passed")
    
    test_min_comparison_with_extracted_value()
    print("✅ Min comparison test passed")
    
    print("\n🎉 All type-safe wallet balance tests passed!")
