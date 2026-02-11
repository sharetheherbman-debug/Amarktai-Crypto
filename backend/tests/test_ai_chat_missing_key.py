"""
Test AI chat behavior when OpenAI key not configured
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
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
def mock_no_openai_key():
    with patch('routes.api_key_management.get_decrypted_key') as mock:
        mock.return_value = None
        yield mock

def test_ai_chat_missing_openai_key_returns_clear_error(mock_auth, mock_no_openai_key):
    """Test /api/ai/chat returns clear error when OpenAI key not configured"""
    with patch('routes.ai_chat.db.chat_messages_collection') as mock_chat:
        with patch('routes.ai_chat.action_router.get_system_state') as mock_state:
            mock_chat.insert_one = AsyncMock()
            mock_chat.find = AsyncMock(return_value=AsyncMock(
                sort=AsyncMock(return_value=AsyncMock(
                    limit=AsyncMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[])))
                ))
            ))
            mock_state.return_value = {"bots": {"total": 0}, "capital": {}, "recent_performance": {}}
            
            with patch('os.getenv', return_value=None):
                response = client.post("/api/ai/chat", json={"content": "Hello"})
    
    assert response.status_code in (400, 409)
    data = response.json()
    assert "not configured" in data["content"].lower() or "api key" in data["content"].lower()
    assert data.get("code") == "no_api_key"
    assert data.get("success") is False
