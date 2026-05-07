import os
import sys

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_expectancy_gate_blocker_exposes_diagnostics():
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "expectancy_diag_user"
    await db.system_modes_collection.insert_one({"user_id": user_id, "paperTrading": True, "liveTrading": False})
    await db.wallets_collection.insert_one({"user_id": user_id, "type": "paper", "balances": {"ZAR": 30000.0}})
    await db.bots_collection.insert_one(
        {
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
    )

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
