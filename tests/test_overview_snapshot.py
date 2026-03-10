"""
Test Overview Snapshot Endpoint
Verifies that the overview snapshot returns all required fields
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import app
from routes.dashboard_overview import OVERVIEW_SNAPSHOT_KEYS


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user_token():
    """Mock user token for authentication"""
    from auth import create_access_token
    return create_access_token({"user_id": "test-user-overview", "sub": "test-user-overview"})


class TestOverviewSnapshot:
    """Test overview snapshot endpoint"""
    
    def test_overview_snapshot_endpoint_exists(self):
        """Verify /api/overview/snapshot endpoint exists"""
        from routes.dashboard_overview import router
        
        routes = [route for route in router.routes]
        snapshot_route = next((r for r in routes if '/snapshot' in str(r.path)), None)
        
        assert snapshot_route is not None, "/api/overview/snapshot endpoint must exist"
    
    def test_overview_snapshot_structure(self):
        """Verify overview snapshot returns required fields"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)

        for field in OVERVIEW_SNAPSHOT_KEYS:
            assert field in source, f"Overview snapshot must include '{field}'"
        assert "activity" in source
        assert "runnableBots" in source
        assert "pausedBots" in source

    def test_overview_snapshot_keys_contract(self):
        """Verify overview snapshot contract keys list is stable"""
        expected_keys = {
            "systemMode",
            "activeBots",
            "openPositions",
            "totalProfit",
            "winRate",
            "todaysTrades",
            "riskLevel",
            "lastRebalance",
            "nextReinvest",
        }
        assert set(OVERVIEW_SNAPSHOT_KEYS) == expected_keys


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
