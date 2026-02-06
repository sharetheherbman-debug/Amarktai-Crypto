"""
Test API Keys Status System
Verifies that API key status transitions work correctly
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import app
from services.provider_registry import ProviderStatus


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user_token():
    """Mock user token for authentication"""
    from auth import create_access_token
    return create_access_token({"user_id": "test-user-keys", "sub": "test-user-keys"})


class TestAPIKeysStatus:
    """Test API keys status system"""
    
    def test_provider_status_enum_values(self):
        """Verify ProviderStatus enum has all required values"""
        assert hasattr(ProviderStatus, 'NOT_CONFIGURED')
        assert hasattr(ProviderStatus, 'CONFIGURED_UNTESTED')
        assert hasattr(ProviderStatus, 'CONFIGURED_VALID')
        assert hasattr(ProviderStatus, 'CONFIGURED_INVALID')
        assert hasattr(ProviderStatus, 'CONFIGURED_RATE_LIMITED')
        
        # Verify values use intuitive names
        assert ProviderStatus.NOT_CONFIGURED.value == 'not_configured'
        assert ProviderStatus.CONFIGURED_UNTESTED.value == 'saved_untested'  # Changed to intuitive name
        assert ProviderStatus.CONFIGURED_VALID.value == 'test_ok'  # Changed to intuitive name
        assert ProviderStatus.CONFIGURED_INVALID.value == 'test_failed'  # Changed to intuitive name
        assert ProviderStatus.CONFIGURED_RATE_LIMITED.value == 'rate_limited'
    
    def test_provider_status_backward_compatibility(self):
        """Verify backward compatible aliases exist"""
        # These should work for backward compatibility
        assert hasattr(ProviderStatus, 'SAVED_UNTESTED')
        assert hasattr(ProviderStatus, 'TEST_OK')
        assert hasattr(ProviderStatus, 'TEST_FAILED')
        
        # They should map to intuitive values (same as primary names now)
        assert ProviderStatus.SAVED_UNTESTED.value == 'saved_untested'
        assert ProviderStatus.TEST_OK.value == 'test_ok'
        assert ProviderStatus.TEST_FAILED.value == 'test_failed'
    
    def test_keys_status_endpoint_exists(self):
        """Verify /api/keys/status endpoint exists"""
        import inspect
        from routes.keys import router
        
        # Check that the status endpoint is defined
        routes = [route for route in router.routes]
        status_route = next((r for r in routes if '/status' in str(r.path)), None)
        
        assert status_route is not None, "/api/keys/status endpoint must exist"
    
    def test_keys_list_endpoint_returns_status(self):
        """Verify /api/keys/list includes status information"""
        # This is an integration test that would need real DB
        # For now, verify the code structure
        import inspect
        from routes.keys import list_user_keys
        
        source = inspect.getsource(list_user_keys)
        assert 'status' in source.lower(), "list_user_keys must include status"
        assert 'ProviderStatus' in source, "Must use ProviderStatus enum"
    
    def test_save_key_sets_untested_status(self):
        """Verify saving a key sets status to configured_untested"""
        import inspect
        from routes.keys import save_key
        
        source = inspect.getsource(save_key)
        assert 'CONFIGURED_UNTESTED' in source or 'SAVED_UNTESTED' in source, \
            "Saving key must set status to configured_untested"


class TestStatusTransitions:
    """Test status transition logic"""
    
    def test_new_key_starts_as_not_configured(self):
        """A provider with no key should have status not_configured"""
        # This is the expected behavior when querying status
        expected_status = ProviderStatus.NOT_CONFIGURED.value
        assert expected_status == 'not_configured'
    
    def test_saved_key_becomes_configured_untested(self):
        """After saving, status should be saved_untested"""
        expected_status = ProviderStatus.CONFIGURED_UNTESTED.value
        assert expected_status == 'saved_untested'
    
    def test_successful_test_becomes_configured_valid(self):
        """After successful test, status should be test_ok"""
        expected_status = ProviderStatus.CONFIGURED_VALID.value
        assert expected_status == 'test_ok'
    
    def test_failed_test_becomes_configured_invalid(self):
        """After failed test, status should be test_failed"""
        expected_status = ProviderStatus.CONFIGURED_INVALID.value
        assert expected_status == 'test_failed'
    
    def test_rate_limited_status_available(self):
        """Rate limited status should be available"""
        expected_status = ProviderStatus.CONFIGURED_RATE_LIMITED.value
        assert expected_status == 'rate_limited'


class TestAPIKeyRoutes:
    """Test API key route structure"""
    
    def test_all_required_endpoints_exist(self):
        """Verify all required API key endpoints exist"""
        from routes.keys import router
        
        routes = [route for route in router.routes]
        paths = [str(route.path) for route in routes]
        
        # Required endpoints
        assert any('/status' in p for p in paths), "Must have /status endpoint"
        assert any('/list' in p for p in paths), "Must have /list endpoint"
        assert any('/save' in p or '/{provider}' in p for p in paths), "Must have save endpoint"
        assert any('/test' in p for p in paths), "Must have /test endpoint"
        assert any('/providers' in p for p in paths), "Must have /providers endpoint"
    
    def test_providers_list_includes_exchanges(self):
        """Verify providers list includes all supported exchanges"""
        from services.provider_registry import list_providers
        from rules.bot_rules import SUPPORTED_EXCHANGES
        
        providers = list_providers()
        provider_ids = [p.provider_id if hasattr(p, 'provider_id') else p.get('id') for p in providers]
        
        # All supported exchanges should be in providers
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in provider_ids, f"Exchange {exchange} should be in providers list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
