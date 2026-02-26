"""
Tests for Market Intelligence CoinStats integration (B3).

Validates:
 - Mock HTTP 200 → test_connection returns status=success + configured=True
 - Mock HTTP 200 → _fetch_and_process results in fetch_status=ok
 - Mock HTTP 401 → _fetch_and_process results in fetch_status=invalid_key
 - _resolve_scheduler_user_id finds users with encrypted key fields
"""
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_aiohttp_response(status: int, json_body=None):
    """Build a minimal aiohttp response mock."""
    import json as _json

    resp = MagicMock()
    resp.status = status
    if json_body is not None:
        resp.json = AsyncMock(return_value=json_body)
    else:
        resp.json = AsyncMock(return_value=[])

    # Context-manager support
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_session(response):
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ── test_connection tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_200_returns_success():
    """test_connection() with HTTP 200 must return status=success and configured=True."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    resp = _make_aiohttp_response(200, [{"title": "BTC pumps", "id": "1"}])
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("test-api-key-abc", "user"))), \
         patch("aiohttp.ClientSession", return_value=session):
        result = await provider.test_connection(user_id="u1")

    assert result["status"] == "success"
    assert result["configured"] is True
    assert result["http_status"] == 200


@pytest.mark.asyncio
async def test_connection_401_returns_error():
    """test_connection() with HTTP 401 must return status=error."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    resp = _make_aiohttp_response(401)
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("bad-key", "user"))), \
         patch("aiohttp.ClientSession", return_value=session):
        result = await provider.test_connection(user_id="u1")

    assert result["status"] == "error"
    assert result["http_status"] == 401


# ── _fetch_and_process tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_and_process_200_sets_ok():
    """_fetch_and_process with HTTP 200 and articles → fetch_status=ok."""
    import services.market_intelligence_service as mis

    articles = [
        {"title": "BTC hits ATH", "id": "a1", "link": "http://example.com",
         "source": "CoinStats", "feedDate": 0, "categories": [], "relatedCoins": [],
         "description": ""},
    ]

    resp = _make_aiohttp_response(200, articles)
    session = _make_session(resp)

    # Reset module state
    mis._last_brief = None
    mis._last_error = None

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("valid-key", "user"))), \
         patch("aiohttp.ClientSession", return_value=session):
        await mis._fetch_and_process(user_id="u1")

    assert mis._last_brief is not None
    assert mis._last_brief.get("fetch_status") == "ok", (
        f"Expected fetch_status=ok, got: {mis._last_brief.get('fetch_status')}"
    )
    # _last_error must be cleared
    assert mis._last_error is None


@pytest.mark.asyncio
async def test_fetch_and_process_401_sets_invalid_key():
    """_fetch_and_process with HTTP 401 → fetch_status=invalid_key."""
    import services.market_intelligence_service as mis
    from services.news_coinstats import coinstats_provider

    resp = _make_aiohttp_response(401)
    session = _make_session(resp)

    mis._last_brief = None
    mis._last_error = None
    # Clear provider cache so it re-fetches (not using cached 200 response)
    coinstats_provider._cache = None
    coinstats_provider._cache_ts = None
    coinstats_provider._last_error = None

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("bad-key", "user"))), \
         patch("aiohttp.ClientSession", return_value=session):
        await mis._fetch_and_process(user_id="u1")

    assert mis._last_brief is not None
    assert mis._last_brief.get("fetch_status") == "invalid_key", (
        f"Expected fetch_status=invalid_key, got: {mis._last_brief.get('fetch_status')}"
    )


# ── _resolve_scheduler_user_id tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_scheduler_user_id_encrypted_field():
    """_resolve_scheduler_user_id finds users with api_key_encrypted field."""
    import services.market_intelligence_service as mis

    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value={"user_id": "user_xyz"})

    with patch("database.api_keys_collection", mock_col):
        result = await mis._resolve_scheduler_user_id()

    assert result == "user_xyz"
    # Verify it was called with an $or query containing encrypted fields
    call_args = mock_col.find_one.call_args
    query = call_args[0][0]
    assert "$or" in query, "Query should use $or for multiple encrypted field variants"
    field_names = [list(cond.keys())[0] for cond in query["$or"]]
    assert "api_key_encrypted" in field_names, "Query must check api_key_encrypted"
    assert "api_key" in field_names, "Query must check legacy api_key"


@pytest.mark.asyncio
async def test_resolve_scheduler_user_id_returns_none_when_missing():
    """_resolve_scheduler_user_id returns None if no matching document."""
    import services.market_intelligence_service as mis

    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value=None)

    with patch("database.api_keys_collection", mock_col):
        result = await mis._resolve_scheduler_user_id()

    assert result is None


# ── Stale invalid_key is replaced on user-context fetch ──────────────────────

@pytest.mark.asyncio
async def test_stale_invalid_key_replaced_by_user_fetch():
    """get_latest_intelligence with stale invalid_key triggers re-fetch for valid user."""
    import services.market_intelligence_service as mis

    # Pre-populate a stale brief with invalid_key status
    mis._last_brief = {
        "fetch_status": "invalid_key",
        "mood": "neutral",
        "source": "CoinStats",
        "updated_at": "2020-01-01T00:00:00+00:00",
    }

    articles = [
        {"title": "ETH surges", "id": "b1", "link": "http://example.com",
         "source": "CoinStats", "feedDate": 0, "categories": [], "relatedCoins": [],
         "description": ""},
    ]
    resp = _make_aiohttp_response(200, articles)
    session = _make_session(resp)

    from services.news_coinstats import coinstats_provider
    coinstats_provider._cache = None
    coinstats_provider._cache_ts = None
    coinstats_provider._last_error = None

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("valid-key", "user"))), \
         patch("aiohttp.ClientSession", return_value=session), \
         patch("services.market_intelligence_service._emit_intelligence_event",
               new=AsyncMock()):
        brief = await mis.get_latest_intelligence(user_id="u1")

    # After re-fetch the brief should be ok
    assert brief.get("fetch_status") == "ok", (
        f"Expected fetch_status=ok after user-context re-fetch, got: {brief.get('fetch_status')}"
    )
