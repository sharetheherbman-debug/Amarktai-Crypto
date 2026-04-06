"""
Unit/integration tests for POST /api/admin/bots/{bot_id}/reset-locks

Validates:
- Response contract fields: success, bot_id, status, paused_by_bodyguard, reason
- status == "active" after reset
- paused_by_bodyguard == False after reset
- 404 for missing bot
- 401 for unauthenticated request

Run with: pytest backend/tests/test_reset_locks_contract.py -v
"""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import app
import database as db


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def admin_token():
    """Create an admin user and return a bearer token."""
    # db.connect() is patched by conftest.py mock_database fixture - no real MongoDB needed

    from auth import get_password_hash, create_access_token
    from uuid import uuid4

    user_id = str(uuid4())
    await db.users_collection.insert_one({
        "id": user_id,
        "email": f"reset_locks_test_{user_id[:8]}@example.com",
        "password_hash": get_password_hash("testpass"),
        "first_name": "Admin",
        "last_name": "Test",
        "is_admin": True,
        "created_at": "2026-01-01T00:00:00Z",
    })

    token = create_access_token(data={"user_id": user_id})
    yield token

    await db.users_collection.delete_one({"id": user_id})


@pytest.fixture
async def paused_bot(admin_token):
    """Insert a paused-by-bodyguard bot and clean up after the test."""
    from uuid import uuid4

    bot_id = str(uuid4())
    await db.bots_collection.insert_one({
        "id": bot_id,
        "user_id": "test_user",
        "status": "paused",
        "paused_by_bodyguard": True,
        "current_capital": 10000,
        "initial_capital": 10000,
    })

    yield bot_id

    await db.bots_collection.delete_one({"id": bot_id})


@pytest.mark.asyncio
async def test_reset_locks_response_contract(client, admin_token, paused_bot):
    """reset-locks must return the documented JSON contract."""
    response = await client.post(
        f"/api/admin/bots/{paused_bot}/reset-locks",
        json={"reason": "smoke_test_reset"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Required contract fields
    assert data.get("success") is True
    assert data.get("bot_id") == paused_bot
    assert data.get("status") == "active", f"expected 'active', got {data.get('status')!r}"
    assert data.get("paused_by_bodyguard") is False
    assert "reason" in data


@pytest.mark.asyncio
async def test_reset_locks_clears_bodyguard_flag(client, admin_token, paused_bot):
    """After reset, the DB record must have paused_by_bodyguard=False and status='active'."""
    await client.post(
        f"/api/admin/bots/{paused_bot}/reset-locks",
        json={"reason": "test_clear"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    bot = await db.bots_collection.find_one({"id": paused_bot}, {"_id": 0})
    assert bot is not None
    assert bot.get("status") == "active"
    assert bot.get("paused_by_bodyguard") is False


@pytest.mark.asyncio
async def test_reset_locks_not_found(client, admin_token):
    """reset-locks on a missing bot_id must return 404."""
    response = await client.post(
        "/api/admin/bots/nonexistent-bot-id/reset-locks",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_reset_locks_requires_auth(client, paused_bot):
    """reset-locks must reject unauthenticated requests."""
    response = await client.post(
        f"/api/admin/bots/{paused_bot}/reset-locks",
        json={"reason": "test"},
    )
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )
