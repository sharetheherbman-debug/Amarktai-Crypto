import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_paper_reset_resets_wallet_to_30000():
    from routes.system_mode import perform_paper_reset
    import database as db

    mock_system_modes = MagicMock(update_one=AsyncMock())
    mock_audit_logs = MagicMock(insert_one=AsyncMock())

    with patch("services.paper_reset_orchestrator.run", new=AsyncMock(return_value={
        "bots_soft_deleted": 0,
        "open_trades_deleted": 0,
        "fills_deleted": 0,
        "trades_deleted": 0,
        "runtime_deleted": 0,
        "risk_locks_reset": 0,
        "wallet_reset": True,
        "wallet_available": 30000.0,
        "paper_balance": 30000.0,
        "remaining_paper_bots": 0,
        "remaining_open_paper_trades": 0,
        "remaining_paper_fills": 0,
        "post_reset": {},
        "warnings": [],
    })), patch.object(db, "system_modes_collection", mock_system_modes), patch.object(
        db, "audit_logs_collection", mock_audit_logs
    ), patch("routes.system_mode.manager.send_message", new=AsyncMock()), patch(
        "routes.system_mode.rt_events.force_refresh", new=AsyncMock()
    ):
        result = await perform_paper_reset("wallet_reset_30000_user")

    assert result["wallet_reset"] is True
    assert result["paper_balance"] == 30000.0
    assert result["wallet_available"] == 30000.0
    assert result["invariants_passed"] is True

