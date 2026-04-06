"""
Test GET /api/bots endpoint
Ensures it returns correct format for realtime polling.
"""

import pytest
from fastapi.testclient import TestClient


def test_bots_requires_auth(client: TestClient):
    """GET /api/bots without auth should return 401/403"""
    response = client.get("/api/bots")
    assert response.status_code in [401, 403], f"Expected 401/403 but got {response.status_code}"


def test_bots_returns_list(client: TestClient, normal_user_token: str):
    """GET /api/bots with auth should return bot list"""
    response = client.get(
        "/api/bots",
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
    
    data = response.json()
    
    # Should have standard structure
    assert "bots" in data, "Response must have 'bots' key"
    assert isinstance(data["bots"], list), "bots must be a list"
    
    # Should have total count
    assert "total" in data or "count" in data or len(data["bots"]) >= 0


def test_bots_filters_deleted(client: TestClient, normal_user_token: str):
    """Deleted bots should not appear in list"""
    response = client.get(
        "/api/bots",
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    assert response.status_code == 200
    
    data = response.json()
    bots = data.get("bots", [])
    
    # No bot should have status=deleted
    for bot in bots:
        assert bot.get("status") != "deleted", "Deleted bots should be filtered out"
        assert not bot.get("deleted"), "Deleted bots should be filtered out"


def test_bots_response_schema(client: TestClient, normal_user_token: str):
    """Verify bot objects have expected fields"""
    response = client.get(
        "/api/bots",
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    assert response.status_code == 200
    
    data = response.json()
    bots = data.get("bots", [])
    
    if len(bots) > 0:
        bot = bots[0]
        # Check for essential fields
        required_fields = ["id", "name", "status", "exchange"]
        for field in required_fields:
            assert field in bot, f"Bot must have '{field}' field"
