import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_wallet_platform_compat_shape_and_alias():
    import database as db
    from routes.wallet_hub import get_wallet_platform, get_wallet_platform_summary
    from services.paper_wallet_service import paper_wallet_service

    user_id = "wallet_platform_user"
    paper_wallet_service.collection = None
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    payload = await get_wallet_platform(user_id=user_id)
    summary_payload = await get_wallet_platform_summary(user_id=user_id)

    required_keys = {
        "success",
        "totalBalance",
        "availableBalance",
        "allocatedBalance",
        "paperBalance",
        "liveBalance",
        "platforms",
        "byExchange",
        "exchanges",
        "currency",
    }
    assert required_keys.issubset(payload.keys())
    assert required_keys.issubset(summary_payload.keys())
    assert payload["currency"] == "ZAR"


@pytest.mark.asyncio
async def test_wallet_platform_initializes_paper_wallet():
    import database as db
    from routes.wallet_hub import get_wallet_platform
    from services.paper_wallet_service import paper_wallet_service

    user_id = "wallet_platform_init_user"
    paper_wallet_service.collection = None
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    await get_wallet_platform(user_id=user_id)
    wallet = await db.wallets_collection.find_one(
        {"user_id": user_id, "type": "paper"},
        {"_id": 0},
    )
    assert wallet is not None
