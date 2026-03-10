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


def test_bots_status_returns_error_when_collection_missing():
    with patch.object(bot_lifecycle.db, "bots_collection", None):
        response = client.get("/api/bots/status")

    assert response.status_code == 503
    payload = response.json()

    assert payload.get("detail")


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


def test_bots_status_exposes_trade_truth_fields_for_cards():
    token = create_access_token({"user_id": "test-user", "sub": "test-user"})

    bot_doc = {
        "id": "bot-1",
        "user_id": "test-user",
        "name": "Radar Bot",
        "exchange": "luno",
        "status": "active",
        "bot_type": "normal",
        "initial_capital": 1000,
        "current_capital": 1180,
        "open_position_value": 80,
        "created_at": "2026-01-01T00:00:00Z",
    }

    mock_bot_cursor = MagicMock()
    mock_bot_cursor.to_list = AsyncMock(return_value=[bot_doc])
    mock_bots_collection = MagicMock()
    mock_bots_collection.find.return_value = mock_bot_cursor

    mock_trade_cursor = MagicMock()
    mock_trade_cursor.to_list = AsyncMock(return_value=[{
        "_id": "bot-1",
        "total_trades": 5,
        "wins": 3,
        "losses": 2,
        "realized_pnl": 180.0,
    }])
    mock_trades_collection = MagicMock()
    mock_trades_collection.aggregate.return_value = mock_trade_cursor

    with patch.object(bot_lifecycle.db, "bots_collection", mock_bots_collection), \
         patch.object(bot_lifecycle.db, "trades_collection", mock_trades_collection), \
         patch.object(bot_lifecycle.bot_runtime_state, "list_states", AsyncMock(return_value=[])):
        response = client.get(
            "/api/bots/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("success") is True
    assert len(payload.get("bots", [])) == 1
    bot = payload["bots"][0]
    assert bot["profit"] == 180.0
    assert bot["total_profit"] == 180.0
    assert bot["total_trades"] == 5
    assert bot["trades_count"] == 5
    assert bot["win_rate"] == 60.0
    assert bot["available_capital"] == 1100.0
