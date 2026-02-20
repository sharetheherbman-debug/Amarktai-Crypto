"""
Test bots status defaults
Ensures /api/bots/status returns safe defaults for empty DB and missing collection.
"""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from auth import create_access_token
from server import app
import routes.bot_lifecycle as bot_lifecycle

client = TestClient(app)


def test_bots_status_returns_empty_when_no_bots():
    token = create_access_token({"user_id": "test-user", "sub": "test-user"})
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    with patch.object(bot_lifecycle.db, "bots_collection", mock_collection):
        response = client.get(
            "/api/bots/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("success") is True
    assert payload.get("active_bots") == 0
    assert payload.get("bots") == []
    exchange_counts = payload.get("exchange_counts")
    assert exchange_counts
    assert payload.get("platforms") == exchange_counts
    assert payload.get("all_exchanges")
    assert set(exchange_counts.keys()) == set(payload.get("all_exchanges"))


def test_bots_status_requires_auth_when_collection_missing():
    with patch.object(bot_lifecycle.db, "bots_collection", None):
        response = client.get("/api/bots/status")

    assert response.status_code == 401


def test_bots_status_returns_401_without_token():
    """GET /api/bots/status without Authorization header must return 401."""
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    with patch.object(bot_lifecycle.db, "bots_collection", mock_collection):
        response = client.get("/api/bots/status")

    assert response.status_code == 401


def test_bots_status_returns_error_with_auth_when_collection_missing():
    token = create_access_token({"user_id": "test-user", "sub": "test-user"})

    with patch.object(bot_lifecycle.db, "bots_collection", None):
        response = client.get(
            "/api/bots/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    payload = response.json()

    assert payload.get("detail")


def test_bots_status_meta_returns_exchange_counts():
    token = create_access_token({"user_id": "test-user", "sub": "test-user"})
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor

    with patch.object(bot_lifecycle.db, "bots_collection", mock_collection):
        response = client.get(
            "/api/bots/status?meta=1",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("exchange_counts")
    assert payload.get("all_exchanges")
    assert set(payload["exchange_counts"].keys()) == set(payload["all_exchanges"])
