import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_live_readiness_remains_blocked_without_live_proof(monkeypatch):
    import database as db
    from routes.diagnostics import live_trading_readiness

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    user_id = "live_readiness_blocked_user"
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "liveTrading": True, "autopilot": False, "emergencyStop": False}
    )
    await db.bots_collection.insert_one(
        {"id": "live_bot_1", "user_id": user_id, "trading_mode": "live", "status": "active", "exchange": "binance"}
    )

    result = await live_trading_readiness(user_id=user_id)
    assert result["status"] == "FAIL"
    assert any("enable_live_trading_false" in blocker for blocker in result["blockers"])
