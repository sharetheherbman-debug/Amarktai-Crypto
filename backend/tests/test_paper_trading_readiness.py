import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_trading_readiness_contract_fields():
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "paper_readiness_user"

    # Two bots: one eligible (active), one blocked (paused by user)
    paper_bots_data = [
        {"id": "paper_eligible", "user_id": user_id, "status": "active", "trading_mode": "paper"},
        {"id": "paper_blocked", "user_id": user_id, "status": "paused", "trading_mode": "paper", "paused_by_user": True},
    ]
    # One closed trade with PnL
    closed_trades_data = [
        {"id": "paper_closed", "user_id": user_id, "status": "closed", "is_paper": True, "net_pnl": 12.5},
    ]

    # Build mock collections
    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(return_value={"paperTrading": True, "liveTrading": False})

    bots_cursor = MagicMock()
    bots_cursor.to_list = AsyncMock(return_value=paper_bots_data)
    mock_bots = MagicMock()
    mock_bots.find = MagicMock(return_value=bots_cursor)

    trades_sort_cursor = MagicMock()
    trades_sort_cursor.to_list = AsyncMock(return_value=closed_trades_data)
    trades_find_cursor = MagicMock()
    trades_find_cursor.sort = MagicMock(return_value=trades_sort_cursor)
    mock_trades = MagicMock()
    mock_trades.count_documents = AsyncMock(return_value=1)  # one open trade
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
        result = await paper_trading_readiness(user_id=user_id)

    expected = {
        "status",
        "scheduler_running",
        "paper_enabled",
        "paper_wallet_ready",
        "paper_wallet_balance",
        "paper_bots_count",
        "eligible_bots_count",
        "blocked_bots",
        "last_scheduler_tick",
        "last_trade_attempt",
        "last_order_error",
        "open_paper_trades",
        "recent_paper_fills",
        "paper_performance",
    }
    assert expected.issubset(result.keys())
    assert result["status"] in {"PASS", "FAIL"}
    assert result["paper_bots_count"] == 2
    assert result["eligible_bots_count"] == 1
