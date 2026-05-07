import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_perform_paper_reset_reports_deleted_old_paper_bots():
    from routes.system_mode import perform_paper_reset
    import database as db

    mock_system_modes = MagicMock()
    mock_system_modes.update_one = AsyncMock()
    mock_audit_logs = MagicMock()
    mock_audit_logs.insert_one = AsyncMock()

    with patch(
        "services.paper_reset_orchestrator.run",
        new=AsyncMock(
            return_value={
                "bots_soft_deleted": 4,
                "open_trades_deleted": 0,
                "fills_deleted": 0,
                "trades_deleted": 0,
                "runtime_deleted": 0,
                "risk_locks_reset": 1,
                "wallet_reset": True,
                "wallet_available": 30000.0,
                "paper_balance": 30000.0,
                "remaining_paper_bots": 0,
                "remaining_open_paper_trades": 0,
                "remaining_paper_fills": 0,
                "post_reset": {},
                "warnings": [],
            },
        ),
    ), patch.object(db, "system_modes_collection", mock_system_modes), patch.object(
        db, "audit_logs_collection", mock_audit_logs
    ), patch("routes.system_mode.manager.send_message", new=AsyncMock()), patch(
        "routes.system_mode.rt_events.force_refresh", new=AsyncMock()
    ):
        payload = await perform_paper_reset("paper_reset_old_bots_user")

    assert payload["bots_deleted"] == 4
    assert payload["remaining_paper_bots"] == 0
