import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_dashboard_snapshot_excludes_deleted_bots_and_trades():
    import database as db
    from routes.dashboard_overview import get_dashboard_snapshot

    user_id = "dashboard_deleted_filter_user"
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    await db.bots_collection.insert_many(
        [
            {"id": "bot_live", "user_id": user_id, "status": "active", "trading_mode": "paper"},
            {"id": "bot_deleted", "user_id": user_id, "status": "deleted", "trading_mode": "paper"},
            {"id": "bot_soft_deleted", "user_id": user_id, "status": "active", "deleted": True, "trading_mode": "paper"},
        ]
    )

    await db.trades_collection.insert_many(
        [
            {"id": "trade_kept", "user_id": user_id, "status": "closed", "profit": 10, "closed_at": "2026-01-01T00:00:00+00:00"},
            {"id": "trade_deleted", "user_id": user_id, "status": "closed", "profit": 20, "deleted": True, "closed_at": "2026-01-02T00:00:00+00:00"},
        ]
    )

    snapshot = await get_dashboard_snapshot(user_id=user_id)
    assert snapshot["bots_summary"]["active"] == 1
    assert snapshot["trades_summary"]["closed"] == 1
