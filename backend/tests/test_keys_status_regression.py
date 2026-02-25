"""
Regression tests for /api/keys/status endpoint crash fix
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from server import app

client = TestClient(app)

@pytest.fixture
def mock_auth():
    with patch('auth.get_current_user') as mock:
        mock.return_value = "test_user_123"
        yield mock

@pytest.fixture
def mock_db():
    with patch('database.api_keys_collection') as mock:
        yield mock

@pytest.fixture
def mock_list_providers():
    """Mock list_providers to return dicts (actual format)"""
    with patch('routes.keys.list_providers') as mock:
        mock.return_value = [
            {"id": "openai", "type": "ai", "display_name": "OpenAI", "required_fields": ["api_key"]},
            {"id": "luno", "type": "exchange", "display_name": "Luno", "required_fields": ["api_key", "api_secret"]},
            {"id": "binance", "type": "exchange", "display_name": "Binance", "required_fields": ["api_key", "api_secret"]},
            {"id": "kucoin", "type": "exchange", "display_name": "KuCoin", "required_fields": ["api_key", "api_secret", "passphrase"]},
            {"id": "bybit", "type": "exchange", "display_name": "Bybit", "required_fields": ["api_key", "api_secret"]},
            {"id": "kraken", "type": "exchange", "display_name": "Kraken", "required_fields": ["api_key", "api_secret"]},
            {"id": "bitget", "type": "exchange", "display_name": "Bitget", "required_fields": ["api_key", "api_secret", "passphrase"]},
            {"id": "gate", "type": "exchange", "display_name": "Gate.io", "required_fields": ["api_key", "api_secret"]},
            {"id": "fetchai", "type": "ai", "display_name": "Fetch.ai", "required_fields": ["api_key"]},
        ]
        yield mock

def test_keys_status_returns_all_providers(mock_auth, mock_db, mock_list_providers):
    """Test /api/keys/status returns status for all 10 providers without crashing"""
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.find.return_value = mock_cursor
    
    response = client.get("/api/keys/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "status_map" in data
    
    status_map = data["status_map"]
    assert len(status_map) == 9  # Must have exactly 9 providers
    
    # Check all expected providers
    expected = ["openai", "fetchai", "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
    for provider in expected:
        assert provider in status_map, f"Provider {provider} missing"
        assert status_map[provider]["status"] == "not_configured"

def test_keys_list_not_configured_for_missing_keys(mock_auth, mock_db, mock_list_providers):
    """Test /api/keys/list does NOT show nonexistent keys as configured"""
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.find.return_value = mock_cursor
    
    response = client.get("/api/keys/list")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["keys"]) == 10  # All 10 providers
    
    # ALL should be not_configured
    for key_status in data["keys"]:
        assert key_status["status"] == "not_configured"
