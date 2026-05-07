"""
Verify /api/diagnostics/paper-trading-readiness is mounted and returns all required fields.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_paper_trading_readiness_route_declared_in_diagnostics():
    """Route must be declared in routes/diagnostics.py."""
    diag_path = os.path.join(backend_dir, "routes", "diagnostics.py")
    with open(diag_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert 'prefix="/api/diagnostics"' in src
    assert '@router.get("/paper-trading-readiness")' in src


def test_paper_trading_readiness_route_mounted_in_openapi():
    """Route must appear in app OpenAPI paths (i.e., router is mounted)."""
    from server import app

    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/paper-trading-readiness" in paths, (
        "GET /api/diagnostics/paper-trading-readiness not found in OpenAPI — diagnostics router not mounted"
    )


@pytest.mark.asyncio
async def test_paper_trading_readiness_returns_required_contract_fields():
    """Response must include every field specified in the Phase 4 contract."""
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "readiness_mount_user"

    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )
    mock_bots = MagicMock()
    mock_bots.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_trades = MagicMock()
    mock_trades.count_documents = AsyncMock(return_value=0)
    mock_trades.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    ))

    mock_paper_wallet_obj = MagicMock()
    mock_paper_wallet_obj.get_wallet_status = AsyncMock(
        return_value={"balances": {"ZAR": 30000.0}, "available_zar": 30000.0}
    )
    mock_paper_wallet_module = MagicMock()
    mock_paper_wallet_module.paper_wallet_service = mock_paper_wallet_obj

    with patch.object(db, "system_modes_collection", mock_system_modes), \
         patch.object(db, "bots_collection", mock_bots), \
         patch.object(db, "trades_collection", mock_trades), \
         patch.dict("sys.modules", {"services.paper_wallet_service": mock_paper_wallet_module}):
        result = await paper_trading_readiness(user_id=user_id)

    required_fields = {
        "success",
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
    missing = required_fields - set(result.keys())
    assert not missing, f"Missing contract fields in paper-trading-readiness: {missing}"
    assert result["success"] is True
    assert result["status"] in ("PASS", "FAIL")
    assert isinstance(result["blocked_bots"], list)
    assert isinstance(result["paper_performance"], dict)


@pytest.mark.asyncio
async def test_paper_trading_readiness_reports_blockers_for_blocked_bots():
    """Blocked bots must appear in blocked_bots list with a reason."""
    import database as db
    from routes.diagnostics import paper_trading_readiness

    user_id = "readiness_blockers_user"

    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    blocked_bot = {
        "id": "blocked_bot_1",
        "user_id": user_id,
        "name": "Blocked Bot",
        "status": "active",
        "trading_mode": "paper",
        "exchange": "luno",
        "pair": "XBTTZAR",
        "last_order_error": "expectancy_gate",
        "last_order_diagnostics": {
            "expected_edge_pct": 0.05,
            "fees_pct_roundtrip": 0.08,
            "expectancy_zar": -3.0,
            "required_minimum_zar": 5.0,
        },
        "training_complete": True,
        "paper_test_ready": True,
    }

    mock_bots = MagicMock()
    mock_bots.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[blocked_bot])))
    mock_trades = MagicMock()
    mock_trades.count_documents = AsyncMock(return_value=0)
    mock_trades.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    ))
    mock_paper_wallet_obj2 = MagicMock()
    mock_paper_wallet_obj2.get_wallet_status = AsyncMock(
        return_value={"balances": {"ZAR": 30000.0}, "available_zar": 30000.0}
    )
    mock_paper_wallet_module2 = MagicMock()
    mock_paper_wallet_module2.paper_wallet_service = mock_paper_wallet_obj2

    with patch.object(db, "system_modes_collection", mock_system_modes), \
         patch.object(db, "bots_collection", mock_bots), \
         patch.object(db, "trades_collection", mock_trades), \
         patch.dict("sys.modules", {"services.paper_wallet_service": mock_paper_wallet_module2}):
        result = await paper_trading_readiness(user_id=user_id)

    assert result["blocked_bots"], "Expected at least one blocked bot"
    blocked = result["blocked_bots"][0]
    assert blocked["reason"] == "expectancy_gate"
    assert "expectancy_diagnostics" in blocked
