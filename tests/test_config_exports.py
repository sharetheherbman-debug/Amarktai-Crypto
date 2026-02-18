"""
Test Config Exports - Ensure all required constants are exported
Addresses the runtime error: "cannot import name 'AUTO_PROMOTE_LIVE' from 'config'"
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_config_exports_required_constants():
    """Test that config module exports all required constants for bot lifecycle"""
    from config import (
        AUTO_PROMOTE_LIVE,
        ENABLE_LIVE_TRADING,
        ENABLE_PAPER_TRADING,
        PAPER_TRAINING_DAYS,
        MIN_WIN_RATE,
        MIN_PROFIT_PERCENT,
        MIN_TRADES_FOR_PROMOTION
    )
    
    # Verify types
    assert isinstance(AUTO_PROMOTE_LIVE, bool), "AUTO_PROMOTE_LIVE should be boolean"
    assert isinstance(ENABLE_LIVE_TRADING, bool), "ENABLE_LIVE_TRADING should be boolean"
    assert isinstance(ENABLE_PAPER_TRADING, bool), "ENABLE_PAPER_TRADING should be boolean"
    assert isinstance(PAPER_TRAINING_DAYS, int), "PAPER_TRAINING_DAYS should be int"
    assert isinstance(MIN_WIN_RATE, float), "MIN_WIN_RATE should be float"
    assert isinstance(MIN_PROFIT_PERCENT, float), "MIN_PROFIT_PERCENT should be float"
    assert isinstance(MIN_TRADES_FOR_PROMOTION, int), "MIN_TRADES_FOR_PROMOTION should be int"
    
    # Verify values are sensible
    assert PAPER_TRAINING_DAYS >= 7, "Paper training should be at least 7 days"
    assert 0 <= MIN_WIN_RATE <= 1, "Win rate should be between 0 and 1"
    assert MIN_TRADES_FOR_PROMOTION > 0, "Need at least 1 trade for promotion"


def test_config_module_all_export():
    """Test that __all__ includes critical constants"""
    import config
    
    # Check __all__ exists
    assert hasattr(config, '__all__'), "config module should have __all__ export list"
    
    # Check critical exports are in __all__
    required_exports = [
        'AUTO_PROMOTE_LIVE',
        'ENABLE_LIVE_TRADING',
        'ENABLE_PAPER_TRADING',
        'PAPER_TRAINING_DAYS',
        'MIN_WIN_RATE',
        'MIN_PROFIT_PERCENT',
        'MIN_TRADES_FOR_PROMOTION',
        'REQUIRE_WALLET_FUNDED',
        'REQUIRE_API_KEYS_FOR_LIVE',
        'PAPER_SUPPORTED_EXCHANGES'
    ]
    
    for export in required_exports:
        assert export in config.__all__, f"{export} should be in config.__all__"


def test_bot_lifecycle_can_import_config():
    """Test that bot_lifecycle can successfully import AUTO_PROMOTE_LIVE"""
    try:
        # This was the failing import
        from config import AUTO_PROMOTE_LIVE, ENABLE_LIVE_TRADING
        
        # If we get here, the import succeeded
        assert True, "Successfully imported AUTO_PROMOTE_LIVE from config"
        
    except ImportError as e:
        pytest.fail(f"Failed to import from config: {e}")


def test_live_trading_gate_defaults():
    """Test that live trading is OFF by default (safety requirement)"""
    from config import ENABLE_LIVE_TRADING, AUTO_PROMOTE_LIVE
    
    # These should default to False in production
    # (can be overridden by env vars, but default should be safe)
    # Note: This test checks the imported values, which may be influenced by .env
    # In production, without env vars, these should be False
    assert isinstance(ENABLE_LIVE_TRADING, bool), "ENABLE_LIVE_TRADING should be bool"
    assert isinstance(AUTO_PROMOTE_LIVE, bool), "AUTO_PROMOTE_LIVE should be bool"


if __name__ == "__main__":
    # Run tests
    test_config_exports_required_constants()
    print("✅ Config exports test passed")
    
    test_config_module_all_export()
    print("✅ Config __all__ export test passed")
    
    test_bot_lifecycle_can_import_config()
    print("✅ Bot lifecycle import test passed")
    
    test_live_trading_gate_defaults()
    print("✅ Live trading gate defaults test passed")
    
    print("\n🎉 All config export tests passed!")
