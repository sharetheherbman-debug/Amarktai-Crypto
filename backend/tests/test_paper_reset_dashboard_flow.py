import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_paper_reset_dashboard_flow_accepts_frontend_payload_aliases(monkeypatch):
    import database as db
    from routes.system_mode import PaperResetRequest, paper_reset

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "START FRESH")
    user_id = "dashboard_reset_user"
    mock_system_modes = MagicMock()
    mock_system_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    with patch.object(db, "system_modes_collection", mock_system_modes), patch(
        "routes.system_mode.perform_paper_reset",
        new=AsyncMock(
            return_value={
                "bots_deleted": 5,
                "remaining_paper_bots": 0,
                "remaining_open_paper_trades": 0,
                "remaining_paper_fills": 0,
                "wallet_reset": True,
                "paper_balance": 30000.0,
                "wallet_available": 30000.0,
                "invariants_passed": True,
                "failed_invariants": [],
            }
        ),
    ):
        payload = PaperResetRequest(
            password="START FRESH",
            resetPassword="START FRESH",
            reset_password="START FRESH",
            confirmation="START FRESH",
            confirmation_phrase="START FRESH",
            confirm="START FRESH",
        )
        result = await paper_reset(request=payload, user_id=user_id)

    assert result["success"] is True
    assert result["wallet_reset"] is True
    assert result["paper_balance"] == 30000.0

