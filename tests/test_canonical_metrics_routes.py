import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_metrics_summary_uses_canonical_snapshot():
    from routes.dashboard_aliases import get_metrics_summary

    bot_cursor = MagicMock()
    bot_cursor.to_list = AsyncMock(return_value=[{"id": "b1", "status": "active"}])
    bots_collection = MagicMock()
    bots_collection.find.return_value = bot_cursor

    trade_cursor = MagicMock()
    trade_cursor.to_list = AsyncMock(return_value=[])
    trades_collection = MagicMock()
    trades_collection.find.return_value = trade_cursor
    trades_collection.count_documents = AsyncMock(return_value=2)

    with patch('database.bots_collection', bots_collection), \
         patch('database.trades_collection', trades_collection), \
         patch('services.canonical_metrics.get_canonical_metrics_snapshot', new=AsyncMock(return_value={
             "summary": {
                 "profit_realized": 123.45,
                 "winning_trades": 3,
                 "losing_trades": 1,
                 "trade_count": 4,
                 "win_rate_pct": 75.0,
             }
         })), \
         patch('services.canonical.get_canonical_bot_counts', new=AsyncMock(return_value={
             "total": 1,
             "active": 1,
             "paused": 0,
         })):
        payload = asyncio.run(get_metrics_summary("test-user"))

    assert payload["metrics"]["performance"]["total_profit"] == 123.45
    assert payload["metrics"]["performance"]["win_rate"] == 75.0
    assert payload["metrics"]["trades"]["total"] == 4


def test_analytics_capital_breakdown_uses_canonical_metrics():
    from routes.analytics_api import get_capital_breakdown

    bot_cursor = MagicMock()
    bot_cursor.to_list = AsyncMock(return_value=[{"id": "b1", "name": "Bot One", "initial_capital": 1000, "current_capital": 1100}])
    bots_collection = MagicMock()
    bots_collection.find.return_value = bot_cursor

    with patch('routes.analytics_api.db.bots_collection', bots_collection), \
         patch('routes.analytics_api.get_canonical_metrics_snapshot', new=AsyncMock(return_value={
             "summary": {
                 "capital_initial": 1000.0,
                 "capital_current": 1100.0,
                 "profit_realized": 100.0,
             },
             "by_bot_id": {
                 "b1": {
                     "capital_initial": 1000.0,
                     "capital_current": 1100.0,
                     "profit_realized": 100.0,
                 }
             }
         })):
        payload = asyncio.run(get_capital_breakdown("test-user"))

    assert payload["funded_capital"] == 1000.0
    assert payload["current_capital"] == 1100.0
    assert payload["realized_pnl"] == 100.0
    assert payload["breakdown_by_bot"][0]["realized_pnl"] == 100.0
