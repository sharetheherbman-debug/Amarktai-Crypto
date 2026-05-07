"""
Verify /api/wallet/platform/summary returns the same data as /api/wallet/platform
and includes all Phase 3 contract fields including API key truth.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

_MOCK_PATCHES = [
    ("routes.wallet_hub.system_mode_service", lambda: MagicMock(
        get_current_mode=AsyncMock(return_value="paper")
    )),
    ("routes.wallet_hub.wallet_summary_service", lambda: MagicMock(
        get_summary=AsyncMock(return_value={"available_wallet_zar": 30000.0, "allocated_funds_zar": 0.0})
    )),
    ("routes.wallet_hub.paper_wallet_service", lambda: MagicMock(
        get_balances=AsyncMock(return_value={"balances": {"ZAR": 30000.0}})
    )),
    ("routes.wallet_hub.wallet_manager", lambda: MagicMock(
        get_master_balance=AsyncMock(return_value={"error": "not_configured"}),
        get_all_balances=AsyncMock(return_value={}),
    )),
    ("routes.wallet_hub.get_paper_wallet_allocated_balances", lambda: AsyncMock(return_value={"ZAR": 0.0})),
]


def _make_mock_db_with_keys(key_docs):
    """Build a mock db.api_keys_collection that returns key_docs."""
    import database as db
    mock_api_keys = MagicMock()
    cursor_mock = MagicMock()
    cursor_mock.to_list = AsyncMock(return_value=key_docs)
    mock_api_keys.find = MagicMock(return_value=cursor_mock)
    return mock_api_keys


def _apply_patches(extra=None):
    """Context manager stack for wallet_hub patches."""
    from contextlib import ExitStack
    stack = ExitStack()
    for target, factory in _MOCK_PATCHES:
        obj = factory()
        if callable(obj) and not isinstance(obj, MagicMock):
            stack.enter_context(patch(target, new=obj))
        else:
            stack.enter_context(patch(target, obj))
    if extra:
        for ctx in extra:
            stack.enter_context(ctx)
    return stack


@pytest.mark.asyncio
async def test_wallet_platform_summary_matches_wallet_hub():
    """/api/wallet/platform/summary must return the same data as /api/wallet/platform."""
    from routes.wallet_hub import get_wallet_platform, get_wallet_platform_summary
    import database as db

    mock_api_keys = _make_mock_db_with_keys([])

    with _apply_patches(extra=[patch.object(db, "api_keys_collection", mock_api_keys)]):
        platform = await get_wallet_platform(user_id="summary_test_user")

    with _apply_patches(extra=[patch.object(db, "api_keys_collection", mock_api_keys)]):
        summary = await get_wallet_platform_summary(user_id="summary_test_user")

    # Both endpoints share the same builder so all fields must match
    for field in ("success", "currency", "totalBalance", "availableBalance", "paperBalance",
                  "liveBalance", "liveWalletMissing", "configuredExchanges", "validApiKeysCount",
                  "connectedExchangesCount"):
        assert platform[field] == summary[field], (
            f"Field '{field}' differs: platform={platform[field]!r} summary={summary[field]!r}"
        )


@pytest.mark.asyncio
async def test_wallet_platform_includes_phase3_api_key_fields():
    """Platform payload must include all Phase 3 API key truth fields."""
    from routes.wallet_hub import _build_platform_wallet_payload
    import database as db

    two_key_docs = [
        {"exchange": "luno", "last_test_ok": True, "last_tested_at": "2026-05-01T12:00:00+00:00"},
        {"exchange": "binance", "last_test_ok": True, "last_tested_at": "2026-05-02T08:00:00+00:00"},
    ]
    mock_api_keys = _make_mock_db_with_keys(two_key_docs)

    with _apply_patches(extra=[patch.object(db, "api_keys_collection", mock_api_keys)]):
        payload = await _build_platform_wallet_payload("api_key_fields_user")

    required = {
        "configuredExchanges",
        "validApiKeysCount",
        "connectedExchangesCount",
        "missingKeys",
        "lastKeyTestAt",
        "lastTestOk",
    }
    missing = required - set(payload.keys())
    assert not missing, f"Missing Phase 3 fields: {missing}"


@pytest.mark.asyncio
async def test_wallet_platform_reflects_two_configured_exchanges():
    """When 2 exchanges have valid keys, validApiKeysCount and connectedExchangesCount must be 2."""
    from routes.wallet_hub import _build_platform_wallet_payload
    import database as db

    two_key_docs = [
        {"exchange": "luno", "last_test_ok": True, "last_tested_at": "2026-05-01T12:00:00+00:00"},
        {"exchange": "binance", "last_test_ok": True, "last_tested_at": "2026-05-02T08:00:00+00:00"},
    ]
    mock_api_keys = _make_mock_db_with_keys(two_key_docs)

    with _apply_patches(extra=[patch.object(db, "api_keys_collection", mock_api_keys)]):
        payload = await _build_platform_wallet_payload("two_exchanges_user")

    assert payload["validApiKeysCount"] == 2, (
        f"Expected validApiKeysCount=2 but got {payload['validApiKeysCount']}"
    )
    assert payload["connectedExchangesCount"] == 2, (
        f"Expected connectedExchangesCount=2 but got {payload['connectedExchangesCount']}"
    )
    assert "luno" in payload["configuredExchanges"]
    assert "binance" in payload["configuredExchanges"]
    assert payload["lastTestOk"].get("luno") is True
    assert payload["lastTestOk"].get("binance") is True


@pytest.mark.asyncio
async def test_wallet_platform_no_keys_returns_zero_counts():
    """When no API keys are stored, validApiKeysCount must be 0."""
    from routes.wallet_hub import _build_platform_wallet_payload
    import database as db

    mock_api_keys = _make_mock_db_with_keys([])

    with _apply_patches(extra=[patch.object(db, "api_keys_collection", mock_api_keys)]):
        payload = await _build_platform_wallet_payload("no_keys_user")

    assert payload["validApiKeysCount"] == 0
    assert payload["connectedExchangesCount"] == 0
    assert payload["configuredExchanges"] == []
