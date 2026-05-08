import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_live_readiness_stays_blocked_when_live_disabled(monkeypatch):
    import database as db
    from routes.diagnostics import live_trading_readiness

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    user_id = "live_block_user"

    mock_modes = MagicMock(find_one=AsyncMock(return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}))
    mock_bots = MagicMock(find=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))))
    mock_trades = MagicMock(find=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))))
    mock_keys = MagicMock(find_one=AsyncMock(return_value=None))

    with patch.object(db, "system_modes_collection", mock_modes), patch.object(db, "bots_collection", mock_bots), patch.object(
        db, "trades_collection", mock_trades
    ), patch.object(db, "api_keys_collection", mock_keys):
        result = await live_trading_readiness(user_id=user_id)

    assert result["status"] == "FAIL"
    assert "enable_live_trading_false" in result["blockers"]

