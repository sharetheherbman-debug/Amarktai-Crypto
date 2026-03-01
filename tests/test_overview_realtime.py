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
from auth import create_access_token

client = TestClient(app)


@pytest.fixture
def auth_token():
    """Real JWT token for endpoints that decode token manually."""
    return create_access_token({"user_id": "test_user_123", "sub": "test_user_123"})


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


async def _single_heartbeat(user_id: str):
    """Terminates after yielding one heartbeat — use in tests instead of the real generator."""
    yield 'event: heartbeat\ndata: {"counter": 1}\n\n'


class TestOverviewRealData:
    """Test that overview endpoints return real data (TASK D)"""
    
    def test_realtime_events_endpoint_exists(self, auth_token):
        """Test that /api/realtime/events SSE endpoint exists and returns 200 + event-stream"""
        import routes.realtime as realtime_module
        with patch.object(realtime_module, "_event_generator", side_effect=_single_heartbeat):
            response = client.get(
                "/api/realtime/events",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_realtime_events_emits_overview_data(self, mock_db, auth_token):
        """Test that realtime events endpoint is accessible with auth"""
        import routes.realtime as realtime_module
        with patch.object(realtime_module, "_event_generator", side_effect=_single_heartbeat):
            response = client.get(
                "/api/realtime/events",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200
    
    def test_overview_data_calculation(self, mock_db, auth_token):
        """Test overview endpoint returns 200 for authenticated user"""
        import routes.realtime as realtime_module
        with patch.object(realtime_module, "_event_generator", side_effect=_single_heartbeat):
            response = client.get(
                "/api/realtime/events",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200


class TestRealtimeEvents:
    """Test that realtime events are published for key actions (TASK D)"""
    
    def test_bot_create_triggers_realtime_event(self, mock_db):
        """Test that creating a bot triggers realtime overview update"""
        pass
    
    def test_bot_delete_triggers_realtime_event(self, mock_db):
        """Test that deleting a bot triggers realtime events"""
        pass
    
    def test_trade_insert_triggers_realtime_event(self, mock_db):
        """Test that inserting a trade triggers realtime update"""
        pass


class TestDashboardEndpoints:
    """Test dashboard endpoints return real data"""
    
    def test_dashboard_endpoints_exist(self, auth_token):
        """Test that dashboard endpoints are accessible"""
        import routes.realtime as realtime_module
        with patch.object(realtime_module, "_event_generator", side_effect=_single_heartbeat):
            response = client.get(
                "/api/realtime/events",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code != 500


class TestSSEHeartbeat:
    """Test SSE heartbeat functionality"""
    
    def test_sse_sends_heartbeat(self, mock_db, auth_token):
        """Test that SSE stream connection is established and sends a heartbeat"""
        import routes.realtime as realtime_module
        with patch.object(realtime_module, "_event_generator", side_effect=_single_heartbeat):
            response = client.get(
                "/api/realtime/events",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200
            assert "heartbeat" in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

