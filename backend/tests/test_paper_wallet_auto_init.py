import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_wallet_auto_init_only_for_paper_mode():
    import database as db
    from services.paper_wallet_ledger import paper_wallet_ledger
    from services.paper_wallet_service import paper_wallet_service

    user_id = "user_wallet_auto"
    paper_bot_id = "paper_bot_auto"
    live_bot_id = "live_bot_auto"

    await db.bots_collection.insert_one({
        "id": paper_bot_id,
        "user_id": user_id,
        "initial_capital": 1000.0,
        "trading_mode": "paper",
        "exchange": "luno",
        "pair": "BTC/ZAR",
    })
    await db.bots_collection.insert_one({
        "id": live_bot_id,
        "user_id": user_id,
        "initial_capital": 1000.0,
        "trading_mode": "live",
        "exchange": "binance",
        "pair": "BTC/USDT",
    })

    await paper_wallet_service.deposit(user_id, 5000.0, "ZAR")

    ok_paper, _, _ = await paper_wallet_ledger.get_balance(paper_bot_id)
    ok_live, _, _ = await paper_wallet_ledger.get_balance(live_bot_id)
    paper_ledger = await db.paper_ledger_collection.find_one({"bot_id": paper_bot_id})
    live_ledger = await db.paper_ledger_collection.find_one({"bot_id": live_bot_id})

    assert ok_paper is True
    assert ok_live is False
    assert paper_ledger is not None
    assert live_ledger is None
