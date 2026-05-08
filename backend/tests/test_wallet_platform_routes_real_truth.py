import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_wallet_platform_routes_return_real_truth_fields():
    from routes.wallet_hub import _build_platform_wallet_payload

    mock_mode_service = MagicMock(get_current_mode=AsyncMock(return_value="paper"))
    mock_summary_service = MagicMock(get_summary=AsyncMock(return_value={
        "available_wallet_zar": 30000.0,
        "allocated_funds_zar": 0.0,
    }))
    mock_paper_wallet = MagicMock(get_balances=AsyncMock(return_value={"balances": {"ZAR": 30000.0}}))
    mock_wallet_manager = MagicMock(
        get_master_balance=AsyncMock(return_value={"error": "not_configured"}),
        get_all_balances=AsyncMock(return_value={}),
    )

    with patch("routes.wallet_hub.system_mode_service", mock_mode_service), patch(
        "routes.wallet_hub.wallet_summary_service", mock_summary_service
    ), patch("routes.wallet_hub.paper_wallet_service", mock_paper_wallet), patch(
        "routes.wallet_hub.wallet_manager", mock_wallet_manager
    ), patch("routes.wallet_hub.get_paper_wallet_allocated_balances", AsyncMock(return_value={"ZAR": 0.0})):
        payload = await _build_platform_wallet_payload("wallet_truth_user")

    for field in (
        "success", "currency", "totalBalance", "availableBalance", "allocatedBalance",
        "paperBalance", "liveBalance", "platforms", "byExchange", "exchanges",
        "configuredExchanges", "connectedExchangesCount", "validApiKeysCount", "perExchange"
    ):
        assert field in payload, f"Missing field: {field}"
    assert payload["paperBalance"] == 30000.0

