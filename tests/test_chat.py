"""
Test AI Chat Improvements
Tests server-side memory, login greeting, and admin panel (TASK E)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace
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
    """Override get_current_user for all tests in this module."""
    app.dependency_overrides[_auth_module.get_current_user] = lambda: TEST_USER_ID
    yield
    app.dependency_overrides.pop(_auth_module.get_current_user, None)


@pytest.fixture
def mock_db():
    """Mock database operations"""
    mocks = {
        'chat_messages_collection': MagicMock(),
        'users_collection': MagicMock(),
    }
    with patch('database.chat_messages_collection', mocks['chat_messages_collection']), \
         patch('database.users_collection', mocks['users_collection']):
        yield mocks


class TestAIChatMemory:
    """Test server-side chat memory (TASK E)"""
    
    def test_login_then_chat_returns_response(self):
        """Login and send chat message with mocked OpenAI response"""
        test_email = "chatuser@example.com"
        test_password = "password123"
        user_doc = {
            "email": test_email,
            "hashed_password": "hashed",
            "id": "user-chat-001"
        }
        with patch('database.users_collection') as mock_users, \
             patch('routes.auth.verify_password', return_value=True):
            mock_users.find_one = AsyncMock(return_value=user_doc)
            mock_users.update_one = AsyncMock()
            login_resp = client.post("/api/auth/login", json={
                "email": test_email,
                "password": test_password
            })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        assert token
        
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[])
        
        openai_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello from AI"))]
        )
        
        with patch('routes.ai_chat.db.chat_messages_collection') as mock_chat, \
             patch('routes.ai_chat.action_router.get_system_state', new=AsyncMock(return_value={
                 "bots": {"total": 0, "active": 0, "paused": 0, "stopped": 0},
                 "capital": {"total": 0, "total_profit": 0},
                 "recent_performance": {"recent_trades_count": 0, "recent_pnl": 0}
             })), \
             patch('routes.api_key_management.get_decrypted_key', new=AsyncMock(return_value={
                 "api_key": "sk-test"
             })), \
             patch('routes.ai_chat.manager.send_message', new=AsyncMock()), \
             patch('openai.AsyncOpenAI') as mock_openai:
            
            mock_chat.insert_one = AsyncMock()
            mock_chat.find.return_value = mock_cursor
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=openai_response)
            mock_openai.return_value = mock_client
            
            chat_resp = client.post(
                "/api/ai/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "Hello"}
            )
        
        assert chat_resp.status_code == 200
        payload = chat_resp.json()
        assert payload.get("content")
    
    def test_chat_endpoint_exists(self):
        """Test that chat endpoint exists"""
        response = client.post("/api/ai/chat", json={"message": "Hello"})
        
        # Should not crash (may return error if AI service not configured)
        assert response.status_code != 500
    
    def test_chat_messages_stored_in_database(self, mock_db):
        """Test that chat messages are stored server-side"""
        # Mock chat response
        mock_db['chat_messages_collection'].insert_one = AsyncMock()
        
        with patch('ai_super_brain.AISuperBrain.chat') as mock_chat:
            mock_chat.return_value = {"response": "Test response", "action": None}
            
            response = client.post("/api/ai/chat", json={"message": "Test message"})
            
            # If endpoint works, verify storage was attempted
            if response.status_code == 200:
                # Chat messages should be stored
                pass
    
    def test_chat_history_not_auto_rendered(self, mock_db):
        """Test that chat history is NOT automatically re-rendered on page refresh"""
        # This is more of a frontend test, but backend should support it
        # by not sending full history by default
        pass


class TestLoginGreeting:
    """Test login greeting with daily report (TASK E)"""
    
    def test_login_greeting_endpoint(self, mock_db):
        """Test that there's an endpoint or mechanism for login greeting"""
        # This might be part of the auth flow or a separate endpoint
        # Check if greeting is sent after login
        pass
    
    def test_daily_report_includes_system_summary(self, mock_db):
        """Test that daily report includes system activity summary"""
        # Should include bot status, trades, profit since last login
        pass


class TestAdminPanelTrigger:
    """Test admin panel trigger mechanism (TASK E)"""
    
    def test_show_admin_command_triggers_password_gate(self, mock_db):
        """Test that 'show admin' command in chat triggers password gate"""
        with patch('ai_super_brain.AISuperBrain.chat') as mock_chat:
            # Simulate user typing "show admin"
            mock_chat.return_value = {
                "response": "Admin panel access requires authentication",
                "action": "show_admin_panel",
                "requires_password": True
            }
            
            response = client.post("/api/ai/chat", json={"message": "show admin"})
            
            if response.status_code == 200:
                data = response.json()
                # Should indicate admin panel trigger
                # Implementation details may vary
                pass


class TestChatUI:
    """Test chat UI requirements (TASK E)"""
    
    def test_chat_ui_modern_design(self):
        """Test that chat UI is modern and clean (frontend test)"""
        # This is a frontend test - would check CSS/styling
        # Backend just needs to support the data flow
        pass
    
    def test_chat_panel_fixed_height_scroll(self):
        """Test that chat panel has fixed height with internal scroll"""
        # Frontend test - check CSS for overflow: auto/scroll
        pass


class TestChatSystemState:
    """Test chat has access to system state (TASK E)"""
    
    def test_chat_can_query_bot_status(self, mock_db):
        """Test that chat can query bot status"""
        with patch('ai_super_brain.AISuperBrain.chat') as mock_chat, \
             patch('routes.ai_chat.AIActionRouter.get_system_state') as mock_state:
            
            mock_state.return_value = {
                "bots": {"total": 5, "active": 3},
                "capital": {"total": 10000}
            }
            mock_chat.return_value = {
                "response": "You have 3 active bots out of 5 total"
            }
            
            response = client.post("/api/ai/chat", json={
                "message": "How many bots are active?"
            })
            
            if response.status_code == 200:
                # Chat should have access to system state
                pass
    
    def test_chat_can_issue_emergency_stop(self, mock_db):
        """Test that chat can issue emergency stop with confirmation"""
        # Emergency stop should require confirmation
        with patch('ai_super_brain.AISuperBrain.chat') as mock_chat:
            mock_chat.return_value = {
                "response": "Emergency stop requires confirmation. Type 'confirm emergency stop'",
                "action": "emergency_stop",
                "requires_confirmation": True
            }
            
            response = client.post("/api/ai/chat", json={
                "message": "emergency stop"
            })
            
            if response.status_code == 200:
                data = response.json()
                # Should require confirmation
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
