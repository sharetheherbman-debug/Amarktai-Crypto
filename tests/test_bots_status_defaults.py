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

    with patch.object(bot_lifecycle, "bots_collection", mock_collection):
        response = client.get(
            "/api/bots/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("success") is True
    assert payload.get("active_bots") == 0
    assert payload.get("bots") == []
    assert payload.get("platforms") == {}


def test_bots_status_returns_error_when_collection_missing():
    with patch.object(bot_lifecycle, "bots_collection", None):
        response = client.get("/api/bots/status")

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("success") is False
    assert payload.get("active_bots") == 0
    assert payload.get("bots") == []
    assert payload.get("platforms") == {}
    assert payload.get("error")
