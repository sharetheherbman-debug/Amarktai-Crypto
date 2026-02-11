"""
Test admin storage endpoint serialization.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import os
import sys

backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    try:
        from server import app, get_current_user
    except ImportError as exc:
        pytest.skip(f"Server dependencies not available: {exc}")

    app.dependency_overrides[get_current_user] = lambda: "admin-user"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def make_collection(return_list):
    collection = MagicMock()
    find_result = MagicMock()
    find_result.to_list = AsyncMock(return_value=return_list)
    collection.find.return_value = find_result
    return collection


def test_admin_storage_returns_json(client):
    now = datetime.now(timezone.utc)
    users_collection = MagicMock()
    users_collection.find_one = AsyncMock(return_value={"_id": "admin-user", "id": "admin-user", "email": "admin@example.com"})
    users_find = MagicMock()
    users_find.to_list = AsyncMock(return_value=[
        {"_id": "user-1", "id": "user-1", "email": "user@example.com", "first_name": "Test", "created_at": now}
    ])
    users_collection.find.return_value = users_find

    chat_collection = make_collection([{"user_id": "user-1", "timestamp": now}])
    trades_collection = make_collection([{"user_id": "user-1", "timestamp": now}])
    bots_collection = make_collection([{"user_id": "user-1", "timestamp": now, "status": "active"}])
    alerts_collection = make_collection([{"user_id": "user-1", "timestamp": now}])

    with patch('database.users_collection', users_collection), \
         patch('database.chat_messages_collection', chat_collection), \
         patch('database.trades_collection', trades_collection), \
         patch('database.bots_collection', bots_collection), \
         patch('database.alerts_collection', alerts_collection):
        response = client.get("/api/admin/storage")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "timestamp" in data
        assert isinstance(data["users"], list)
