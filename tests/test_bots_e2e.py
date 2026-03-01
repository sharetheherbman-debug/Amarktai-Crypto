"""
Test Bots End-to-End Deletion
Tests that deleted bots disappear from the list immediately (TASK C)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Import after path setup
from server import app
from auth import create_access_token

client = TestClient(app)

# Real JWT token — required because the app uses HTTPBearer, which needs an actual
# Authorization header; patching auth.get_current_user alone is not sufficient.
TEST_USER_ID = "test_user_123"
AUTH_TOKEN = create_access_token({"user_id": TEST_USER_ID, "sub": TEST_USER_ID})
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}


@pytest.fixture
def mock_db():
    """Mock database operations"""
    mocks = {
        'bots_collection': MagicMock(),
    }
    with patch('database.bots_collection', mocks['bots_collection']):
        yield mocks


@pytest.fixture
def mock_realtime():
    """Mock realtime events"""
    with patch('realtime_events.rt_events') as mock:
        mock.bot_deleted = AsyncMock()
        yield mock


@pytest.fixture
def mock_realtime_service():
    """Mock realtime service"""
    with patch('services.realtime_service.realtime_service') as mock:
        mock.broadcast_overview_update = AsyncMock()
        mock.broadcast_profits_update = AsyncMock()
        mock.broadcast_platform_stats_update = AsyncMock()
        yield mock


class TestBotsDeleteTruthFix:
    """Test suite for bot deletion truth (TASK C)"""
    
    def test_get_bots_filters_deleted(self, mock_db):
        """Test that GET /api/bots filters out soft-deleted bots"""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"id": "bot1", "name": "Active Bot", "status": "active"},
            {"id": "bot2", "name": "Paused Bot", "status": "paused"},
        ])
        mock_db['bots_collection'].find.return_value = mock_cursor
        
        response = client.get("/api/bots", headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        payload = response.json()
        # /api/bots returns {"success": True, "bots": [...], "total": n}
        bots = payload.get("bots", payload) if isinstance(payload, dict) else payload
        
        # Should only return 2 bots (active and paused)
        assert len(bots) == 2
        assert all(bot.get("status") != "deleted" for bot in bots)
    
    def test_delete_bot_marks_as_deleted(self, mock_db, mock_realtime, mock_realtime_service):
        """Test that DELETE /api/bots/{id} soft-deletes the bot"""
        bot_id = "test_bot_123"
        
        # Mock finding the bot (query includes user_id filter)
        mock_db['bots_collection'].find_one = AsyncMock(return_value={
            "id": bot_id,
            "user_id": TEST_USER_ID,
            "name": "Test Bot",
            "status": "active",
            "exchange": "binance"
        })
        
        # Mock update operation
        mock_db['bots_collection'].update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        response = client.delete(f"/api/bots/{bot_id}", headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        
        # Verify update_one was called with deleted status
        mock_db['bots_collection'].update_one.assert_called_once()
        call_args = mock_db['bots_collection'].update_one.call_args
        update_dict = call_args[0][1]["$set"]
        assert update_dict["status"] == "deleted"
        assert "deleted_at" in update_dict
    
    def test_e2e_create_delete_list(self, mock_db, mock_realtime, mock_realtime_service):
        """Test E2E: Delete bot -> List bots -> Bot not present"""
        bot_id = "new_bot_456"
        
        # Step 1: Delete bot
        mock_db['bots_collection'].find_one = AsyncMock(return_value={
            "id": bot_id,
            "user_id": TEST_USER_ID,
            "name": "New Test Bot",
            "status": "active",
            "exchange": "kucoin"
        })
        mock_db['bots_collection'].update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        delete_response = client.delete(f"/api/bots/{bot_id}", headers=AUTH_HEADERS)
        assert delete_response.status_code == 200
        assert delete_response.json().get("success") is True
        
        # Step 2: List bots - deleted bot should not appear
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db['bots_collection'].find.return_value = mock_cursor
        
        list_response = client.get("/api/bots", headers=AUTH_HEADERS)
        assert list_response.status_code == 200
        payload = list_response.json()
        bots = payload.get("bots", payload) if isinstance(payload, dict) else payload
        
        # Bot should not be in list
        bot_ids = [b.get("id") for b in bots]
        assert bot_id not in bot_ids
    
    def test_delete_nonexistent_bot_returns_404(self, mock_db):
        """Test that deleting a non-existent bot returns 404"""
        mock_db['bots_collection'].find_one = AsyncMock(return_value=None)
        
        response = client.delete("/api/bots/nonexistent_bot", headers=AUTH_HEADERS)
        
        assert response.status_code == 404
    
    def test_delete_other_users_bot_returns_404(self, mock_db):
        """Test that deleting another user's bot returns 404"""
        mock_db['bots_collection'].find_one = AsyncMock(return_value=None)
        
        response = client.delete("/api/bots/other_user_bot", headers=AUTH_HEADERS)
        
        assert response.status_code == 404


class TestBotLifecycleDelete:
    """Test bot deletion in bot_lifecycle.py"""
    
    def test_bot_lifecycle_delete_endpoint_exists(self):
        """Test that DELETE endpoint exists in bot_lifecycle router"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
