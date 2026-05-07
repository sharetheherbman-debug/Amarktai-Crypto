"""
Verify that paper reset clears wallet, trades, fills, and runtime state.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_reset_resets_wallet_trades_fills_runtime():
    """perform_paper_reset must return proof that wallet, trades, fills, and runtime were cleared."""
    from routes.system_mode import perform_paper_reset
    import database as db

    mock_system_modes = MagicMock()
    mock_system_modes.update_one = AsyncMock()
    mock_audit_logs = MagicMock()
    mock_audit_logs.insert_one = AsyncMock()

    orchestrator_result = {
        "bots_soft_deleted": 3,
        "open_trades_deleted": 5,
        "fills_deleted": 12,
        "trades_deleted": 8,
        "runtime_deleted": 2,
        "risk_locks_reset": 1,
        "wallet_reset": True,
        "wallet_available": 30000.0,
        "paper_balance": 30000.0,
        "remaining_paper_bots": 0,
        "remaining_open_paper_trades": 0,
        "remaining_paper_fills": 0,
        "post_reset": {},
        "warnings": [],
    }

    with patch(
        "services.paper_reset_orchestrator.run",
        new=AsyncMock(return_value=orchestrator_result),
    ), patch.object(db, "system_modes_collection", mock_system_modes), patch.object(
        db, "audit_logs_collection", mock_audit_logs
    ), patch("routes.system_mode.manager.send_message", new=AsyncMock()), patch(
        "routes.system_mode.rt_events.force_refresh", new=AsyncMock()
    ):
        payload = await perform_paper_reset("reset_wallet_fills_user")

    # Wallet reset proof
    assert payload["wallet_reset"] is True
    assert payload["paper_balance"] == 30000.0
    assert payload["wallet_available"] == 30000.0

    # Trades cleared proof
    assert payload["open_trades_deleted"] == 5
    assert payload["trades_deleted"] == 8
    assert payload["remaining_open_paper_trades"] == 0

    # Fills cleared proof
    assert payload["fills_deleted"] == 12
    assert payload["remaining_paper_fills"] == 0

    # Runtime/risk cleared proof
    assert payload["runtime_deleted"] == 2
    assert payload["risk_locks_cleared"] == 1

    # Bots cleared proof
    assert payload["bots_deleted"] == 3
    assert payload["remaining_paper_bots"] == 0


@pytest.mark.asyncio
async def test_paper_reset_response_includes_all_required_proof_fields():
    """Reset response must include every proof field listed in the contract."""
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
            }
        ),
    ), patch.object(db, "system_modes_collection", mock_system_modes), patch.object(
        db, "audit_logs_collection", mock_audit_logs
    ), patch("routes.system_mode.manager.send_message", new=AsyncMock()), patch(
        "routes.system_mode.rt_events.force_refresh", new=AsyncMock()
    ):
        payload = await perform_paper_reset("proof_fields_user")

    required_fields = {
        "bots_deleted",
        "open_trades_deleted",
        "fills_deleted",
        "trades_deleted",
        "runtime_deleted",
        "risk_locks_cleared",
        "wallet_reset",
        "wallet_available",
        "paper_balance",
        "remaining_paper_bots",
        "remaining_open_paper_trades",
        "remaining_paper_fills",
    }
    missing = required_fields - set(payload.keys())
    assert not missing, f"Missing proof fields in reset response: {missing}"
