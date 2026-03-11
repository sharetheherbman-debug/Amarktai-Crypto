"""
Test API Keys Contract Unification
Tests backward compatibility for API key payloads and endpoint behavior
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Import after path setup
from server import app
import auth as _auth_module
from auth import create_access_token

client = TestClient(app)

TEST_USER_ID = "test_user_123"
AUTH_TOKEN = create_access_token({"user_id": TEST_USER_ID, "sub": TEST_USER_ID})
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}


@pytest.fixture(autouse=True)
def override_auth():
    """Override get_current_user dependency for the entire test session."""
    app.dependency_overrides[_auth_module.get_current_user] = lambda: TEST_USER_ID
    yield
    app.dependency_overrides.pop(_auth_module.get_current_user, None)


@pytest.fixture
def mock_db():
    """Mock database operations"""
    with patch('database.api_keys_collection') as mock:
        yield mock


class TestAPIKeyContractUnification:
    """Test suite for API key contract unification (TASK B)"""
    
    def test_save_api_key_canonical_format(self, mock_db):
        """Test saving API key with canonical format (provider, api_key, api_secret)"""
        mock_db.find_one = AsyncMock(side_effect=[None, {"provider": "binance", "api_key_encrypted": "encrypted"}])
        mock_db.insert_one = AsyncMock(return_value=MagicMock(inserted_id="key-id"))
        
        payload = {
            "provider": "binance",
            "api_key": "test_key_12345",
            "api_secret": "test_secret_67890"
        }
        
        response = client.post("/api/keys/save", json=payload)
        
        # Should accept canonical format
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("success") is True
        assert "binance" in data.get("message", "").lower()
    
    def test_save_api_key_legacy_exchange_field(self, mock_db):
        """Legacy payloads should be rejected for canonical /api/keys/save"""
        mock_db.find_one = AsyncMock(return_value=None)
        mock_db.insert_one = AsyncMock(return_value=MagicMock(inserted_id="key-id"))
        
        # Legacy format: uses 'exchange' instead of 'provider'
        payload = {
            "exchange": "kucoin",
            "api_key": "test_key_12345",
            "api_secret": "test_secret_67890"
        }
        
        # Legacy payload should be rejected for canonical endpoint
        response = client.post("/api/keys/save", json=payload)
        
        # Legacy payload should be rejected
        assert response.status_code == 422
    
    def test_save_api_key_legacy_camelcase(self, mock_db):
        """Legacy camelCase fields should be rejected for canonical /api/keys/save"""
        mock_db.find_one = AsyncMock(return_value=None)
        mock_db.insert_one = AsyncMock(return_value=MagicMock(inserted_id="key-id"))
        
        # Legacy format: camelCase
        payload = {
            "provider": "luno",
            "apiKey": "test_key_12345",
            "apiSecret": "test_secret_67890"
        }
        
        response = client.post("/api/keys/save", json=payload)
        
        # Legacy camelCase should be rejected
        assert response.status_code == 422
    
    def test_test_api_key_with_api_key_field(self, mock_db):
        """Test API key test endpoint with 'api_key' field"""
        mock_db.find_one = AsyncMock(return_value={"provider": "binance"})
        mock_db.update_one = AsyncMock(return_value=MagicMock())
        
        payload = {
            "provider": "binance",
            "api_key": "test_key_12345",
            "api_secret": "test_secret_67890"
        }
        
        with patch('routes.keys.test_provider', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = (True, None)
            
            response = client.post("/api/keys/test", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert data.get("success") is True or data.get("ok") is True
    
    def test_test_api_key_with_key_field(self, mock_db):
        """Legacy key fields should be rejected for canonical /api/keys/test"""
        payload = {
            "key": "test_key_12345",
            "secret": "test_secret_67890"
        }
        
        response = client.post("/api/keys/test", json=payload)
        
        assert response.status_code == 422
    
    def test_test_api_key_missing_key_returns_error(self, mock_db):
        """Test that test endpoint returns clear error when api_key is missing"""
        mock_db.find_one = AsyncMock(return_value=None)
        payload = {
            "provider": "binance"
            # Missing api_key intentionally
        }
        
        response = client.post("/api/keys/test", json=payload)
        
        assert response.status_code == 404
        data = response.json()
        assert "no saved key" in str(data).lower() or "provide api_key" in str(data).lower()
    
    def test_list_api_keys_returns_masked(self, mock_db):
        """Test that list endpoint returns masked keys, never plaintext"""
        mock_db.find = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {
                "provider": "binance",
                "api_key": "full_key_should_be_masked",
                "last_test_ok": True
            }
        ])
        mock_db.find.return_value = mock_cursor
        
        response = client.get("/api/keys/list")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        keys = data.get("keys", [])
        
        if keys:
            # Should not contain full api_key
            for key in keys:
                assert "full_key_should_be_masked" not in str(key)
                # Should have masked version
                assert "api_key_masked" in key or "api_key" not in key


class TestOpenAPIEndpoint:
    """Test OpenAPI endpoint exists and is accessible"""
    
    def test_openapi_json_exists(self):
        """Test that /api/openapi.json returns 200"""
        response = client.get("/api/openapi.json")
        
        # Should return OpenAPI schema
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data or "swagger" in data or "paths" in data
    
    def test_docs_endpoint_exists(self):
        """Test that /docs endpoint exists"""
        response = client.get("/api/docs")
        
        # FastAPI automatically creates /docs
        assert response.status_code == 200


class TestKeysRouteOrder:
    """Test that routes in keys.py are ordered correctly to prevent shadowing"""
    
    def test_keys_test_endpoint_exists_in_openapi(self):
        """Test that POST /api/keys/test is registered in OpenAPI schema"""
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        
        openapi = response.json()
        paths = openapi.get("paths", {})
        
        # Verify /api/keys/test exists
        assert "/api/keys/test" in paths, "/api/keys/test should be in OpenAPI schema"
        assert "post" in paths["/api/keys/test"], "POST method should exist for /api/keys/test"
    
    def test_keys_test_not_shadowed_by_provider(self):
        """Test that POST /api/keys/test is NOT caught by /{provider} route"""
        with patch('database.api_keys_collection') as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)
            
            # Attempt to POST to /api/keys/test with invalid provider
            payload = {
                "provider": "notarealexchange",
                "api_key": "test_key"
            }
            
            response = client.post("/api/keys/test", json=payload)
            
            # Should return 400 with "Unknown provider: notarealexchange"
            # NOT 422 or error about "test" being an unknown provider
            assert response.status_code == 400
            data = response.json()
            detail = data.get("detail", "")
            
            # Should mention the actual invalid provider name
            assert "notarealexchange" in detail.lower(), f"Error should mention 'notarealexchange', got: {detail}"
            # Should NOT mention "test" as the provider
            assert "unknown provider: test" not in detail.lower(), f"Should not say 'Unknown provider: test', got: {detail}"
    
    def test_provider_list_includes_all_10_providers(self):
        """Test that provider validation includes all core supported providers"""
        response = client.get("/api/keys/providers")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") is True
        
        providers = data.get("providers", [])
        provider_ids = {p["id"] for p in providers}
        
        # Must include all 11 core providers (exchanges + AI)
        expected_providers = {
            "openai", "fetchai", "coinstats", "huggingface",  # AI
            "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"  # Exchanges
        }
        
        missing = expected_providers - provider_ids
        assert not missing, f"Missing core providers: {missing} (got {provider_ids})"
        assert data.get("total", 0) >= 11, f"Should have at least 11 providers, got {data.get('total', 0)}"
    
    def test_unknown_provider_error_includes_all_providers(self):
        """Test that unknown provider error message includes kraken and gate"""
        with patch('database.api_keys_collection') as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)
            
            payload = {
                "provider": "invalid_exchange",
                "api_key": "test_key"
            }
            
            response = client.post("/api/keys/test", json=payload)
            assert response.status_code == 400
            
            data = response.json()
            detail = data.get("detail", "")
            
            # Error message should include kraken and gate
            assert "kraken" in detail.lower(), f"Error should mention 'kraken', got: {detail}"
            assert "gate" in detail.lower(), f"Error should mention 'gate', got: {detail}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
