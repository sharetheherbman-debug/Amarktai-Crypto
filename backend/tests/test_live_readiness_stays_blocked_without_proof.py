import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_live_readiness_remains_blocked_without_live_proof(monkeypatch):
    import database as db
    from routes.diagnostics import live_trading_readiness

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    user_id = "live_readiness_blocked_user"

    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "liveTrading": True, "autopilot": False, "emergencyStop": False}
    )
    mock_bots = MagicMock()
    live_bot = {"id": "live_bot_1", "user_id": user_id, "trading_mode": "live", "status": "active", "exchange": "binance"}
    mock_bots.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[live_bot])))
    mock_api_keys = MagicMock()
    mock_api_keys.find_one = AsyncMock(return_value=None)
    mock_trades = MagicMock()
    mock_trades.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    with patch.object(db, "system_modes_collection", mock_system_modes), \
         patch.object(db, "bots_collection", mock_bots), \
         patch.object(db, "api_keys_collection", mock_api_keys), \
         patch.object(db, "trades_collection", mock_trades):
        result = await live_trading_readiness(user_id=user_id)

    assert result["status"] == "FAIL"
    assert any("enable_live_trading_false" in blocker for blocker in result["blockers"])
