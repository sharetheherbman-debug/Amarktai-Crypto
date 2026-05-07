"""
Verify /api/wallet/platform and /api/wallet/platform/summary routes exist
and return real key/wallet truth from the canonical services.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_wallet_platform_route_declared_in_wallet_hub():
    """Both platform routes must be declared in wallet_hub.py."""
    hub_path = os.path.join(backend_dir, "routes", "wallet_hub.py")
    with open(hub_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert 'prefix="/api/wallet"' in src
    assert '@router.get("/platform")' in src
    assert '@router.get("/platform/summary")' in src


def test_wallet_platform_route_mounted_in_openapi():
    """Both platform routes must appear in the app's OpenAPI paths."""
    from server import app

    paths = app.openapi().get("paths", {})
    assert "/api/wallet/platform" in paths, "Missing /api/wallet/platform in OpenAPI"
    assert "/api/wallet/platform/summary" in paths, "Missing /api/wallet/platform/summary in OpenAPI"


@pytest.mark.asyncio
async def test_wallet_platform_returns_required_fields():
    """/api/wallet/platform must return all required contract fields."""
    from routes.wallet_hub import _build_platform_wallet_payload

    mock_mode_service = MagicMock()
    mock_mode_service.get_current_mode = AsyncMock(return_value="paper")

    mock_summary_service = MagicMock()
    mock_summary_service.get_summary = AsyncMock(return_value={
        "available_wallet_zar": 30000.0,
        "allocated_funds_zar": 0.0,
    })

    mock_paper_wallet_service = MagicMock()
    mock_paper_wallet_service.get_balances = AsyncMock(return_value={
        "balances": {"ZAR": 30000.0}
    })

    mock_wallet_manager = MagicMock()
    mock_wallet_manager.get_master_balance = AsyncMock(return_value={"error": "not_configured"})
    mock_wallet_manager.get_all_balances = AsyncMock(return_value={})

    with patch("routes.wallet_hub.system_mode_service", mock_mode_service), \
         patch("routes.wallet_hub.wallet_summary_service", mock_summary_service), \
         patch("routes.wallet_hub.paper_wallet_service", mock_paper_wallet_service), \
         patch("routes.wallet_hub.wallet_manager", mock_wallet_manager), \
         patch("routes.wallet_hub.get_paper_wallet_allocated_balances", AsyncMock(return_value={"ZAR": 0.0})):
        payload = await _build_platform_wallet_payload("wallet_platform_user")

    required_fields = {
        "success",
        "currency",
        "totalBalance",
        "availableBalance",
        "allocatedBalance",
        "paperBalance",
        "liveBalance",
        "platforms",
        "byExchange",
        "exchanges",
    }
    missing = required_fields - set(payload.keys())
    assert not missing, f"Missing fields in wallet/platform response: {missing}"
    assert payload["success"] is True
    assert payload["currency"] == "ZAR"
    assert payload["paperBalance"] == 30000.0
    assert isinstance(payload["platforms"], list)


@pytest.mark.asyncio
async def test_wallet_platform_summary_returns_same_as_platform():
    """platform/summary must return the same data as /api/wallet/platform."""
    from routes.wallet_hub import get_wallet_platform, get_wallet_platform_summary

    mock_mode_service = MagicMock()
    mock_mode_service.get_current_mode = AsyncMock(return_value="paper")
    mock_summary_service = MagicMock()
    mock_summary_service.get_summary = AsyncMock(return_value={
        "available_wallet_zar": 30000.0, "allocated_funds_zar": 0.0
    })
    mock_paper_wallet_service = MagicMock()
    mock_paper_wallet_service.get_balances = AsyncMock(return_value={"balances": {"ZAR": 30000.0}})
    mock_wallet_manager = MagicMock()
    mock_wallet_manager.get_master_balance = AsyncMock(return_value={"error": "not_configured"})
    mock_wallet_manager.get_all_balances = AsyncMock(return_value={})

    patches = [
        patch("routes.wallet_hub.system_mode_service", mock_mode_service),
        patch("routes.wallet_hub.wallet_summary_service", mock_summary_service),
        patch("routes.wallet_hub.paper_wallet_service", mock_paper_wallet_service),
        patch("routes.wallet_hub.wallet_manager", mock_wallet_manager),
        patch("routes.wallet_hub.get_paper_wallet_allocated_balances", AsyncMock(return_value={"ZAR": 0.0})),
    ]

    user_id = "summary_match_user"
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        platform_result = await get_wallet_platform(user_id=user_id)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        summary_result = await get_wallet_platform_summary(user_id=user_id)

    # Both endpoints share the same builder so core fields must match
    assert platform_result["paperBalance"] == summary_result["paperBalance"]
    assert platform_result["currency"] == summary_result["currency"]
    assert platform_result["success"] == summary_result["success"]
