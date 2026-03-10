import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_ai_system_state_uses_overview_canonical_capital():
    from routes.ai_chat import AIActionRouter

    bots_cursor = MagicMock()
    bots_cursor.to_list = AsyncMock(return_value=[
        {"id": "b1", "status": "active", "current_capital": 100, "total_profit": 0},
        {"id": "b2", "status": "paused", "current_capital": 100, "total_profit": 0},
    ])

    trades_cursor = MagicMock()
    trades_cursor.sort.return_value = trades_cursor
    trades_cursor.limit.return_value = trades_cursor
    trades_cursor.to_list = AsyncMock(return_value=[])

    mock_bots_collection = MagicMock()
    mock_bots_collection.find.return_value = bots_cursor
    mock_modes_collection = MagicMock()
    mock_modes_collection.find_one = AsyncMock(return_value={})
    mock_trades_collection = MagicMock()
    mock_trades_collection.find.return_value = trades_cursor

    with patch('routes.ai_chat.db.bots_collection', mock_bots_collection), \
         patch('routes.ai_chat.db.system_modes_collection', mock_modes_collection), \
         patch('routes.ai_chat.db.trades_collection', mock_trades_collection), \
         patch('routes.ai_chat.trade_budget_manager.get_all_exchanges_budget_report', new=AsyncMock(return_value={})), \
         patch('services.overview_service.overview_service.get_snapshot', new=AsyncMock(return_value={
             "equity": 9876.54,
             "total_profit": 432.1,
         })):
        state = asyncio.run(AIActionRouter.get_system_state("user-1"))

    assert state["capital"]["total"] == 9876.54
    assert state["capital"]["total_profit"] == 432.1
