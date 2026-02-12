"""
Test bots status defaults
Ensures /api/bots/status always returns safe defaults without auth.
"""

from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import app

client = TestClient(app)


def test_bots_status_returns_defaults_without_auth():
    response = client.get("/api/bots/status")

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("success") is True
    assert payload.get("active_bots") == 0
    assert payload.get("bots") == []
    assert isinstance(payload.get("platforms"), dict)
    assert isinstance(payload.get("timestamp"), str)
    assert payload.get("exchange_counts") == payload.get("platforms")
    assert payload.get("total") == 0
    assert payload.get("all_exchanges") == ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
