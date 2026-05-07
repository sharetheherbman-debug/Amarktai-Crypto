import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_trading_readiness_contract_fields():
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "paper_readiness_user"
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )
    await db.bots_collection.insert_many(
        [
            {"id": "paper_eligible", "user_id": user_id, "status": "active", "trading_mode": "paper"},
            {"id": "paper_blocked", "user_id": user_id, "status": "paused", "trading_mode": "paper", "paused_by_user": True},
        ]
    )
    await db.trades_collection.insert_many(
        [
            {"id": "paper_open", "user_id": user_id, "status": "open", "is_paper": True},
            {"id": "paper_closed", "user_id": user_id, "status": "closed", "is_paper": True, "net_pnl": 12.5},
        ]
    )
    await db.wallets_collection.insert_one(
        {"user_id": user_id, "type": "paper", "balances": {"ZAR": 30000.0}}
    )

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
