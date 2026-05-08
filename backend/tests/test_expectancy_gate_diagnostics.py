import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_expectancy_gate_blocker_exposes_diagnostics():
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "expectancy_diag_user"

    expectancy_bot = {
        "id": "expectancy_bot",
        "user_id": user_id,
        "name": "Expectancy Bot",
        "status": "active",
        "trading_mode": "paper",
        "exchange": "luno",
        "pair": "BTC/ZAR",
        "last_order_error": "expectancy_gate",
        "last_order_diagnostics": {
            "expected_edge_pct": 0.12,
            "fees_pct_roundtrip": 0.08,
            "spread_pct": 0.02,
            "slippage_pct_roundtrip": 0.01,
            "buffer_pct": 0.05,
            "expectancy_zar": -1.5,
            "required_minimum_zar": 0.0,
        },
    }

    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(return_value={"paperTrading": True, "liveTrading": False})

    bots_cursor = MagicMock()
    bots_cursor.to_list = AsyncMock(return_value=[expectancy_bot])
    mock_bots = MagicMock()
    mock_bots.find = MagicMock(return_value=bots_cursor)

    trades_sort_cursor = MagicMock()
    trades_sort_cursor.to_list = AsyncMock(return_value=[])
    trades_find_cursor = MagicMock()
    trades_find_cursor.sort = MagicMock(return_value=trades_sort_cursor)
    mock_trades = MagicMock()
    mock_trades.count_documents = AsyncMock(return_value=0)
    mock_trades.find = MagicMock(return_value=trades_find_cursor)

    mock_paper_wallet_obj = MagicMock()
    mock_paper_wallet_obj.get_wallet_status = AsyncMock(
        return_value={"available_zar": 30000.0, "balances": {"ZAR": 30000.0}}
    )
    mock_paper_wallet_module = MagicMock()
    mock_paper_wallet_module.paper_wallet_service = mock_paper_wallet_obj

    with (
        patch.object(db, "system_modes_collection", mock_system_modes),
        patch.object(db, "bots_collection", mock_bots),
        patch.object(db, "trades_collection", mock_trades),
        patch.object(db, "api_keys_collection", None),
        patch.object(db, "learning_runs_collection", None),
        patch.object(db, "db", None),
        patch.dict("sys.modules", {"services.paper_wallet_service": mock_paper_wallet_module}),
    ):
        payload = await paper_trading_readiness(user_id=user_id)

    blocker = payload["blocked_bots"][0]
    assert blocker["reason"] == "expectancy_gate"
    assert set(blocker["expectancy_diagnostics"].keys()) == {
        "expected_edge",
        "fees",
        "spread",
        "slippage",
        "buffer",
        "expectancy",
        "required_minimum",
    }
