import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_perform_paper_reset_reports_deleted_old_paper_bots():
    from routes.system_mode import perform_paper_reset

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
    ), patch("routes.system_mode.db.system_modes_collection.update_one", new=AsyncMock()), patch(
        "routes.system_mode.db.audit_logs_collection.insert_one", new=AsyncMock()
    ), patch("routes.system_mode.manager.send_message", new=AsyncMock()), patch(
        "routes.system_mode.rt_events.force_refresh", new=AsyncMock()
    ):
        payload = await perform_paper_reset("paper_reset_old_bots_user")

    assert payload["bots_deleted"] == 4
    assert payload["remaining_paper_bots"] == 0
