import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_wallet_auto_init_on_platform_read():
    import database as db
    from routes.wallet_hub import get_wallet_platform
    from services.paper_wallet_service import paper_wallet_service

    user_id = "paper_wallet_init_user"
    paper_wallet_service.collection = None
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    response = await get_wallet_platform(user_id=user_id)
    wallet_doc = await db.wallets_collection.find_one({"user_id": user_id, "type": "paper"}, {"_id": 0})

    assert response["success"] is True
    assert wallet_doc is not None
    assert wallet_doc["balances"]["ZAR"] == 0.0
