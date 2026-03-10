import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_canonical_metrics_aggregates_closed_trade_truth():
    from services.canonical_metrics import get_canonical_metrics_snapshot

    bots = [
        {"id": "b1", "initial_capital": 1000, "current_capital": 1150, "open_position_value": 50},
        {"id": "b2", "initial_capital": 500, "current_capital": 450, "open_position_value": 0},
    ]

    trade_cursor = MagicMock()
    trade_cursor.to_list = AsyncMock(return_value=[
        {"_id": "b1", "trade_count": 3, "winning_trades": 2, "losing_trades": 1, "profit_realized": 120.0},
        {"_id": "b2", "trade_count": 2, "winning_trades": 0, "losing_trades": 2, "profit_realized": -50.0},
    ])
    trades_collection = MagicMock()
    trades_collection.aggregate.return_value = trade_cursor

    with patch('services.canonical_metrics.db.trades_collection', trades_collection), \
         patch('services.canonical_metrics.backfill_missing_current_capital', new=AsyncMock(return_value=0)):
        snapshot = asyncio.run(get_canonical_metrics_snapshot("u1", bots=bots))

    summary = snapshot["summary"]
    by_bot = snapshot["by_bot_id"]
    assert summary["capital_initial"] == 1500.0
    assert summary["capital_current"] == 1600.0
    assert summary["profit_realized"] == 70.0
    assert summary["trade_count"] == 5
    assert summary["winning_trades"] == 2
    assert summary["win_rate_pct"] == 40.0
    assert by_bot["b1"]["capital_available"] == 1100.0
    assert by_bot["b1"]["win_rate_pct"] == pytest.approx(66.67, abs=0.01)
    assert by_bot["b2"]["win_rate_pct"] == 0.0


def test_backfill_current_capital_uses_initial_capital():
    from services.canonical_metrics import backfill_missing_current_capital

    result = MagicMock()
    result.modified_count = 3
    bots_collection = MagicMock()
    bots_collection.update_many = AsyncMock(return_value=result)

    with patch('services.canonical_metrics.db.bots_collection', bots_collection):
        modified = asyncio.run(backfill_missing_current_capital("u1"))

    assert modified == 3
    assert bots_collection.update_many.await_count == 1
