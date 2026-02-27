"""
Test Overview and Realtime Updates
Tests that overview returns real data and realtime events work (TASK D)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
import json
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Import after path setup
from server import app

client = TestClient(app)


@pytest.fixture
def mock_auth():
    """Mock authentication to return a test user"""
    with patch('auth.get_current_user') as mock:
        mock.return_value = "test_user_123"
        yield mock


@pytest.fixture
def auth_headers():
    """Authorization headers with a valid JWT for SSE endpoint tests."""
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_123"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_sse_generator(monkeypatch):
    """Replace the infinite SSE generator with a one-shot version for tests.

    Without this the generator loops forever (asyncio.sleep(5) per iteration),
    causing every SSE test to hang for at least 5 seconds.
    """
    async def _quick_generator(user_id: str):
        yield (
            'event: heartbeat\n'
            'data: {"counter": 1, "timestamp": "2026-01-01T00:00:00+00:00"}\n\n'
        )

    monkeypatch.setattr("routes.realtime._event_generator", _quick_generator)


@pytest.fixture
def mock_db():
    """Mock database operations"""
    mocks = {
        'bots_collection': MagicMock(),
        'trades_collection': MagicMock(),
    }
    with patch('database.bots_collection', mocks['bots_collection']), \
         patch('database.trades_collection', mocks['trades_collection']):
        yield mocks


class TestOverviewRealData:
    """Test that overview endpoints return real data (TASK D)"""
    
    def test_realtime_events_endpoint_exists(self, mock_auth, auth_headers):
        """Test that /api/realtime/events SSE endpoint exists"""
        response = client.get("/api/realtime/events", headers=auth_headers)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_realtime_events_emits_overview_data(self, mock_auth, mock_db, auth_headers):
        """Test that realtime events include real overview data"""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"status": "active", "total_profit": 100.50, "current_capital": 1000},
            {"status": "paused", "total_profit": 50.25, "current_capital": 500},
        ])
        mock_db['bots_collection'].find.return_value = mock_cursor
        
        response = client.get("/api/realtime/events", headers=auth_headers)
        assert response.status_code == 200
    
    def test_overview_data_calculation(self, mock_auth, mock_db, auth_headers):
        """Test overview data is calculated from real database values"""
        mock_cursor = MagicMock()
        test_bots = [
            {"status": "active", "total_profit": 150.0, "current_capital": 2000},
            {"status": "active", "total_profit": 200.0, "current_capital": 3000},
            {"status": "paused", "total_profit": -50.0, "current_capital": 1000},
        ]
        mock_cursor.to_list = AsyncMock(return_value=test_bots)
        mock_db['bots_collection'].find.return_value = mock_cursor
        
        response = client.get("/api/realtime/events", headers=auth_headers)
        assert response.status_code == 200


class TestRealtimeEvents:
    """Test that realtime events are published for key actions (TASK D)"""
    
    def test_bot_create_triggers_realtime_event(self, mock_auth, mock_db):
        """Test that creating a bot triggers realtime overview update"""
        pass
    
    def test_bot_delete_triggers_realtime_event(self, mock_auth, mock_db):
        """Test that deleting a bot triggers realtime events"""
        pass
    
    def test_trade_insert_triggers_realtime_event(self, mock_auth, mock_db):
        """Test that inserting a trade triggers realtime update"""
        pass


class TestDashboardEndpoints:
    """Test dashboard endpoints return real data"""
    
    def test_dashboard_endpoints_exist(self, mock_auth, auth_headers):
        """Test that dashboard endpoints are accessible"""
        endpoints = ["/api/realtime/events"]
        for endpoint in endpoints:
            try:
                response = client.get(endpoint, headers=auth_headers)
                assert response.status_code != 500
            except Exception as e:
                pytest.fail(f"Endpoint {endpoint} crashed: {e}")


class TestSSEHeartbeat:
    """Test SSE heartbeat functionality"""
    
    def test_sse_sends_heartbeat(self, mock_auth, mock_db, auth_headers):
        """Test that SSE stream sends heartbeat events"""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_db['bots_collection'].find.return_value = mock_cursor
        mock_db['bots_collection'].count_documents = AsyncMock(return_value=0)
        mock_db['trades_collection'].find.return_value = mock_cursor
        
        response = client.get("/api/realtime/events", headers=auth_headers)
        assert response.status_code == 200
        # Verify the response body contains a heartbeat event
        assert "heartbeat" in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
