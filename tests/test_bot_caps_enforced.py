"""
Test Bot Caps Enforcement
Verifies that bot capacity limits are enforced correctly:
- Luno: max 5 bots per user
- All other exchanges: max 10 bots per user
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import app
from rules.bot_rules import BOT_CAPS, SUPPORTED_EXCHANGES


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user_token():
    """Mock user token for authentication"""
    from auth import create_access_token
    return create_access_token({"user_id": "test-user-123", "sub": "test-user-123"})


class TestBotCaps:
    """Test bot capacity enforcement"""
    
    def test_bot_caps_constants(self):
        """Verify bot caps are properly defined"""
        assert BOT_CAPS['luno'] == 5, "Luno should have max 5 bots"
        assert BOT_CAPS['binance'] == 10, "Binance should have max 10 bots"
        assert BOT_CAPS['kucoin'] == 10, "KuCoin should have max 10 bots"
        assert BOT_CAPS['bybit'] == 10, "Bybit should have max 10 bots"
        assert BOT_CAPS['kraken'] == 10, "Kraken should have max 10 bots"
        assert BOT_CAPS['bitget'] == 10, "Bitget should have max 10 bots"
        assert BOT_CAPS['gate'] == 10, "Gate.io should have max 10 bots"
    
    def test_supported_exchanges_list(self):
        """Verify exactly 7 supported exchanges"""
        assert len(SUPPORTED_EXCHANGES) == 7, "Must have exactly 7 supported exchanges"
        assert 'luno' in SUPPORTED_EXCHANGES
        assert 'binance' in SUPPORTED_EXCHANGES
        assert 'kucoin' in SUPPORTED_EXCHANGES
        assert 'bybit' in SUPPORTED_EXCHANGES
        assert 'kraken' in SUPPORTED_EXCHANGES
        assert 'bitget' in SUPPORTED_EXCHANGES
        assert 'gate' in SUPPORTED_EXCHANGES
        
        # Verify unsupported exchanges are NOT in list
        assert 'valr' not in [e.lower() for e in SUPPORTED_EXCHANGES], "VALR should not be supported"
        assert 'ovex' not in [e.lower() for e in SUPPORTED_EXCHANGES], "OVEX should not be supported"
    
    def test_check_bot_cap_limit_function(self):
        """Test the check_bot_cap_limit function directly"""
        from rules.bot_rules import check_bot_cap_limit
        
        # Test Luno cap (5 bots)
        can_create, reason = check_bot_cap_limit('luno', 4, 'test-user')
        assert can_create is True, "Should allow bot when under cap"
        
        can_create, reason = check_bot_cap_limit('luno', 5, 'test-user')
        assert can_create is False, "Should block bot when at cap"
        assert reason == 'BOT_CAP_EXCEEDED'
        
        # Test other exchange cap (10 bots)
        can_create, reason = check_bot_cap_limit('binance', 9, 'test-user')
        assert can_create is True, "Should allow bot when under cap"
        
        can_create, reason = check_bot_cap_limit('binance', 10, 'test-user')
        assert can_create is False, "Should block bot when at cap"
        assert reason == 'BOT_CAP_EXCEEDED'
    
    def test_invalid_exchange_rejected(self):
        """Test that invalid exchanges are rejected"""
        from rules.bot_rules import validate_exchange
        
        is_valid, reason = validate_exchange('invalid_exchange')
        assert is_valid is False
        assert reason == 'INVALID_EXCHANGE'
        
        is_valid, reason = validate_exchange('valr')
        assert is_valid is False, "VALR should be invalid"
        
        is_valid, reason = validate_exchange('ovex')
        assert is_valid is False, "OVEX should be invalid"
    
    def test_batch_create_respects_caps(self):
        """Test that batch create endpoint respects bot caps (integration test)"""
        # This would need a real database and auth setup
        # For now, just verify the logic exists in batch_create_bots
        import inspect
        from server import batch_create_bots
        
        source = inspect.getsource(batch_create_bots)
        assert 'check_bot_cap_limit' in source, "batch_create_bots must check bot caps"
        assert 'BOT_CAP_EXCEEDED' in source or 'get_reason_message' in source, "Must handle cap exceeded"


class TestExchangeConfiguration:
    """Test exchange configuration consistency"""
    
    def test_exchange_limits_match_supported_list(self):
        """Verify exchange limits are defined for all supported exchanges"""
        from exchange_limits import EXCHANGE_LIMITS
        
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in EXCHANGE_LIMITS, f"Exchange {exchange} missing from EXCHANGE_LIMITS"
    
    def test_bot_caps_match_supported_list(self):
        """Verify bot caps are defined for all supported exchanges"""
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in BOT_CAPS, f"Exchange {exchange} missing from BOT_CAPS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
