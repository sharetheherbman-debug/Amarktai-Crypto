import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_live_readiness_blocks_without_keys():
    import database as db
    from routes.diagnostics import live_trading_readiness

    user_id = "user_no_keys"
    await db.system_modes_collection.insert_one({
        "user_id": user_id,
        "liveTrading": True,
        "autopilot": True,
        "emergencyStop": False,
    })
    await db.bots_collection.insert_one({
        "id": "live_no_keys_bot",
        "user_id": user_id,
        "trading_mode": "live",
        "status": "active",
        "exchange": "binance",
        "pair": "BTC/USDT",
    })

    result = await live_trading_readiness(user_id=user_id)
    assert result["status"] == "FAIL"
    assert any("exchange_keys" in blocker for blocker in result["blockers"])
