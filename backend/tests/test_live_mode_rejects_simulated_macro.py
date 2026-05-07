import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_live_mode_rejects_simulated_macro(monkeypatch):
    monkeypatch.setenv("MACRO_SIGNAL_WEIGHT", "0.2")
    monkeypatch.setenv("ENABLE_TRADING", "true")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    import database as db
    from services.live_gate_service import live_gate_service

    user_id = "user_live_macro"
    bot_id = "bot_live_macro"
    exchange = "binance"

    await db.system_modes_collection.insert_one({
        "user_id": user_id,
        "liveTrading": True,
        "autopilot": True,
        "emergencyStop": False,
    })
    await db.bots_collection.insert_one({
        "id": bot_id,
        "user_id": user_id,
        "name": "Live Bot",
        "status": "active",
        "trading_mode": "live",
        "exchange": exchange,
    })
    await db.api_keys_collection.insert_one({
        "user_id": user_id,
        "exchange": exchange,
        "api_key": "k",
        "api_secret": "s",
        "last_test_ok": True,
        "tested": True,
        "valid": True,
        "last_balance_check": "2026-01-01T00:00:00+00:00",
    })

    can_place, violations = await live_gate_service.can_place_order(user_id, bot_id, exchange)
    assert not can_place
    assert any("MACRO_SIGNAL_WEIGHT" in v for v in violations)
