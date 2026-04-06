"""
Basic integration tests for dashboard critical endpoints
Run with: pytest backend/tests/test_dashboard_auth.py -v
"""

import pytest
from httpx import AsyncClient
from fastapi import status
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server import app
import database as db


@pytest.fixture(scope="module")
async def client():
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="module")
async def test_user_token():
    """Create a test user and return auth token"""
    # Connect to database
    await db.connect()
    
    # Create test user
    from auth import get_password_hash
    from uuid import uuid4
    from datetime import datetime, timezone
    
    test_user_id = str(uuid4())
    test_email = f"test_{test_user_id[:8]}@example.com"
    
    user_data = {
        "id": test_user_id,
        "email": test_email,
        "password_hash": get_password_hash("testpassword123"),
        "first_name": "Test",
        "last_name": "User",
        "is_admin": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users_collection.insert_one(user_data)
    
    # Generate token
    token = create_access_token({"user_id": test_user_id})
    
    yield {"token": token, "user_id": test_user_id}
    
    # Cleanup
    await db.users_collection.delete_one({"id": test_user_id})
    await db.close_db()


@pytest.mark.asyncio
async def test_health_ping(client):
    """Test health check endpoint (no auth required)"""
    response = await client.get("/api/health/ping")
    assert response.status_code == 200
    assert "status" in response.json()


@pytest.mark.asyncio
async def test_auth_me_with_valid_token(client, test_user_token):
    """Test /api/auth/me with valid token"""
    token = test_user_token["token"]
    
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert "email" in data
    assert "id" in data
    assert data["id"] == test_user_token["user_id"]
    assert "password_hash" not in data  # Should be filtered out


@pytest.mark.asyncio
async def test_auth_me_without_token(client):
    """Test /api/auth/me without token returns 401"""
    response = await client.get("/api/auth/me")
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_bots_endpoint_requires_auth(client, test_user_token):
    """Test /api/bots requires authentication"""
    token = test_user_token["token"]
    
    # Without auth
    response = await client.get("/api/bots")
    assert response.status_code in [401, 403]
    
    # With auth
    response = await client.get(
        "/api/bots",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_portfolio_summary_endpoint(client, test_user_token):
    """Test /api/portfolio/summary endpoint"""
    token = test_user_token["token"]
    
    response = await client.get(
        "/api/portfolio/summary",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should return 200 even if user has no data
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_whale_summary_endpoint(client, test_user_token):
    """Test /api/advanced/whale/summary endpoint"""
    token = test_user_token["token"]
    
    response = await client.get(
        "/api/advanced/whale/summary",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # May return 503 if whale monitoring not available, but should not 404
    assert response.status_code in [200, 503]


@pytest.mark.asyncio
async def test_realtime_events_sse(client, test_user_token):
    """Test /api/realtime/events SSE endpoint exists"""
    token = test_user_token["token"]
    
    response = await client.get(
        "/api/realtime/events",
        headers={"Authorization": f"Bearer {token}"},
        timeout=2.0  # Short timeout since SSE streams
    )
    
    # Should start streaming (200) or not be found if disabled
    # We don't wait for full stream, just check it starts
    assert response.status_code in [200, 404, 503]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
