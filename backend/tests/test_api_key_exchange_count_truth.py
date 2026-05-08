import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_api_key_exchange_count_truth_matches_records():
    from routes.wallet_hub import _build_platform_wallet_payload
    import database as db

    fake_records = [
        {"provider": "luno", "last_test_ok": True, "last_tested_at": "2026-05-01T00:00:00+00:00"},
        {"provider": "binance", "last_test_ok": True, "last_tested_at": "2026-05-02T00:00:00+00:00"},
    ]
    mock_keys_collection = MagicMock()
    mock_keys_collection.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=fake_records)))

    with patch.object(db, "api_keys_collection", mock_keys_collection), patch(
        "routes.wallet_hub.system_mode_service.get_current_mode", new=AsyncMock(return_value="paper")
    ), patch("routes.wallet_hub.wallet_summary_service.get_summary", new=AsyncMock(return_value={
        "available_wallet_zar": 30000.0, "allocated_funds_zar": 0.0
    })), patch("routes.wallet_hub.paper_wallet_service.get_balances", new=AsyncMock(return_value={
        "balances": {"ZAR": 30000.0}
    })), patch("routes.wallet_hub.wallet_manager.get_master_balance", new=AsyncMock(return_value={"error": "no"})), patch(
        "routes.wallet_hub.wallet_manager.get_all_balances", new=AsyncMock(return_value={})
    ), patch("routes.wallet_hub.get_paper_wallet_allocated_balances", AsyncMock(return_value={"ZAR": 0.0})):
        payload = await _build_platform_wallet_payload("key_count_truth_user")

    assert payload["connectedExchangesCount"] == 2
    assert payload["validApiKeysCount"] == 2

