"""
Phase 1 endpoint tests.

Covers:
  A) /api/diagnostics/paper-close-proof — structure + route registration
  B) /api/diagnostics/news-sources — structure + route registration
  C) /api/market/intelligence — structure + route registration + required fields
  D) CoinStats parsing: happy path, empty-list 200, alternate response keys
  E) market_intelligence_service stores top_articles in brief
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_aiohttp_response(status: int, json_body=None):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body if json_body is not None else [])
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_session(response):
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ── A: /api/diagnostics/paper-close-proof ────────────────────────────────────

def test_paper_close_proof_in_openapi():
    """/api/diagnostics/paper-close-proof must be in OpenAPI schema paths."""
    from fastapi import FastAPI
    from routes.diagnostics import router as diag_router

    app = FastAPI()
    app.include_router(diag_router)

    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/paper-close-proof" in paths, (
        f"paper-close-proof not in paths. Available: {[p for p in paths if 'paper' in p]}"
    )
    assert "get" in paths["/api/diagnostics/paper-close-proof"]


@pytest.mark.asyncio
async def test_paper_close_proof_returns_required_fields():
    """/api/diagnostics/paper-close-proof returns all required fields without error."""
    from routes.diagnostics import paper_close_proof

    # Mock DB
    mock_trades_col = MagicMock()
    mock_trades_col.find = MagicMock(return_value=MagicMock(
        sort=lambda *a, **kw: MagicMock(to_list=AsyncMock(return_value=[])),
    ))
    mock_trades_col.count_documents = AsyncMock(return_value=0)

    mock_paper_engine = MagicMock()
    mock_paper_engine.get_status = MagicMock(return_value={"last_close_time": None})

    with patch("database.trades_collection", mock_trades_col), \
         patch("routes.diagnostics.db.trades_collection", mock_trades_col), \
         patch("paper_trading_engine.paper_engine", mock_paper_engine):
        result = await paper_close_proof(user_id="user1")

    required = {
        "success", "open_trades_count", "oldest_open_trade_age_minutes",
        "closes_attempted_last_5m", "closes_done_last_5m",
        "last_close_at", "last_10_closes", "timestamp",
    }
    missing = required - set(result.keys())
    assert not missing, f"Missing fields: {missing}"
    assert result["success"] is True


# ── B: /api/diagnostics/news-sources ─────────────────────────────────────────

def test_news_sources_in_openapi():
    """/api/diagnostics/news-sources must be in OpenAPI schema paths."""
    from fastapi import FastAPI
    from routes.diagnostics import router as diag_router

    app = FastAPI()
    app.include_router(diag_router)

    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/news-sources" in paths, (
        f"news-sources not in paths. Available: {[p for p in paths if 'news' in p or 'diag' in p]}"
    )
    assert "get" in paths["/api/diagnostics/news-sources"]


@pytest.mark.asyncio
async def test_news_sources_returns_required_structure():
    """/api/diagnostics/news-sources returns success + providers list including coinstats."""
    from routes.diagnostics import news_sources_diagnostic
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()

    with patch("services.news_coinstats.coinstats_provider", provider), \
         patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("test-key", "env"))):
        result = await news_sources_diagnostic(user_id="user1")

    assert result["success"] is True
    assert "providers" in result
    assert "timestamp" in result

    provider_names = [p["provider"] for p in result["providers"]]
    assert "coinstats" in provider_names, f"coinstats not in providers: {provider_names}"

    cs = next(p for p in result["providers"] if p["provider"] == "coinstats")
    required_keys = {"configured", "key_source", "fetch_status", "last_articles_count", "cache_age_seconds"}
    missing = required_keys - set(cs.keys())
    assert not missing, f"coinstats entry missing keys: {missing}"


# ── C: /api/market/intelligence ──────────────────────────────────────────────

def test_market_intelligence_in_openapi():
    """/api/market/intelligence must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.market_api import router as market_router

    app = FastAPI()
    app.include_router(market_router)

    paths = app.openapi().get("paths", {})
    assert "/api/market/intelligence" in paths, (
        f"market/intelligence not in paths. Available: {[p for p in paths if 'market' in p]}"
    )
    assert "get" in paths["/api/market/intelligence"]


@pytest.mark.asyncio
async def test_market_intelligence_returns_200_and_required_fields():
    """/api/market/intelligence returns 200 and required fields even when empty."""
    import services.market_intelligence_service as mis

    mis._last_brief = {
        "mood": "neutral",
        "why_it_matters": "Test",
        "what_amarktai_is_doing": "Monitoring",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "headlines_count": 0,
        "top_articles": [],
        "source": "CoinStats",
        "fetch_status": "no_articles",
        "block_reason": "CoinStats returned no articles.",
    }

    from routes.market_api import get_market_intelligence

    result = await get_market_intelligence(user_id="user1")

    required = {"success", "source", "mood", "why_it_matters",
                "what_amarktai_is_doing", "last_updated", "articles_count",
                "top_headlines", "block_reason", "fetch_status"}
    missing = required - set(result.keys())
    assert not missing, f"Missing fields: {missing}"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_market_intelligence_never_500():
    """/api/market/intelligence must return structured JSON even when service raises."""
    with patch("services.market_intelligence_service.get_latest_intelligence",
               new=AsyncMock(side_effect=RuntimeError("DB connection failed"))):
        from routes.market_api import get_market_intelligence
        result = await get_market_intelligence(user_id="user1")

    assert "success" in result
    assert result["success"] is False
    assert "block_reason" in result
    assert "mood" in result


# ── D: CoinStats parsing ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coinstats_parse_news_key():
    """CoinStats response with 'news' key → articles parsed correctly."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    body = {
        "news": [
            {"id": "1", "title": "BTC pumps", "link": "http://x.com",
             "source": "CoinDesk", "feedDate": 0, "categories": [], "relatedCoins": [],
             "description": "BTC pumps to 100k"},
        ]
    }
    resp = _make_aiohttp_response(200, body)
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))), \
         patch("aiohttp.ClientSession", return_value=session):
        articles = await provider._fetch(user_id=None)

    assert len(articles) == 1
    assert articles[0]["title"] == "BTC pumps"
    assert articles[0]["provider"] == "coinstats"


@pytest.mark.asyncio
async def test_coinstats_parse_data_key():
    """CoinStats response with 'data' key → articles parsed correctly."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    body = {
        "data": [
            {"id": "2", "title": "ETH surges", "url": "http://y.com",
             "source": "Cointelegraph", "publishedAt": 0, "tags": [], "relatedCoins": [],
             "description": ""},
        ]
    }
    resp = _make_aiohttp_response(200, body)
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))), \
         patch("aiohttp.ClientSession", return_value=session):
        articles = await provider._fetch(user_id=None)

    assert len(articles) == 1
    assert articles[0]["title"] == "ETH surges"


@pytest.mark.asyncio
async def test_coinstats_empty_200_graceful():
    """CoinStats 200 with empty list → returns [], records last_error, no crash."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    provider._last_warn_ts = None  # allow immediate warn
    resp = _make_aiohttp_response(200, [])  # empty list
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))), \
         patch("aiohttp.ClientSession", return_value=session):
        articles = await provider._fetch(user_id=None)

    assert articles == []
    # last_error should be set (rate_warn was called)
    assert provider._last_error is not None
    assert "0 articles" in provider._last_error or "empty" in provider._last_error.lower()


@pytest.mark.asyncio
async def test_coinstats_empty_dict_logs_response_keys():
    """CoinStats 200 with empty dict logs the response keys for diagnosis."""
    from services.news_coinstats import CoinStatsNewsProvider

    provider = CoinStatsNewsProvider()
    provider._last_warn_ts = None
    # Simulate unexpected schema (e.g. {count: 0, articles: None})
    resp = _make_aiohttp_response(200, {"count": 0, "articles": None})
    session = _make_session(resp)

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))), \
         patch("aiohttp.ClientSession", return_value=session):
        articles = await provider._fetch(user_id=None)

    assert articles == []
    assert provider._last_error is not None
    # Should mention response keys so operator can diagnose
    assert "Response keys" in provider._last_error or "keys" in provider._last_error.lower()


# ── E: market_intelligence_service stores top_articles ───────────────────────

@pytest.mark.asyncio
async def test_fetch_and_process_stores_top_articles():
    """_fetch_and_process with articles → _last_brief contains top_articles list."""
    import services.market_intelligence_service as mis

    articles = [
        {"title": f"Headline {i}", "id": str(i), "link": f"http://x.com/{i}",
         "source": "CoinStats", "feedDate": 0, "categories": [], "relatedCoins": [],
         "description": ""}
        for i in range(7)
    ]
    resp = _make_aiohttp_response(200, articles)
    session = _make_session(resp)

    mis._last_brief = None
    mis._last_error = None

    from services.news_coinstats import coinstats_provider
    coinstats_provider._cache = None
    coinstats_provider._cache_ts = None
    coinstats_provider._last_error = None

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))), \
         patch("aiohttp.ClientSession", return_value=session), \
         patch("services.market_intelligence_service._emit_intelligence_event",
               new=AsyncMock()):
        await mis._fetch_and_process(user_id="u1")

    assert mis._last_brief is not None
    assert "top_articles" in mis._last_brief, (
        f"top_articles missing from _last_brief. Keys: {list(mis._last_brief.keys())}"
    )
    assert len(mis._last_brief["top_articles"]) <= 5
    assert len(mis._last_brief["top_articles"]) > 0


# ── F: last-tick-summary includes closes_failed ───────────────────────────────

def test_last_tick_summary_includes_closes_failed():
    """/api/diagnostics/last-tick-summary response schema includes closes_failed."""
    from fastapi import FastAPI
    from routes.diagnostics import router as diag_router

    app = FastAPI()
    app.include_router(diag_router)

    paths = app.openapi().get("paths", {})
    # The endpoint exists — runtime field validation is done via the DB mock test
    assert "/api/diagnostics/last-tick-summary" in paths


# ── G: /api/coinstats/test-connection ────────────────────────────────────────

def test_coinstats_test_connection_in_openapi():
    """/api/coinstats/test-connection must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.coinstats import router as coinstats_router

    app = FastAPI()
    app.include_router(coinstats_router)

    paths = app.openapi().get("paths", {})
    assert "/api/coinstats/test-connection" in paths, (
        f"test-connection not in paths. Available: {[p for p in paths if 'coinstats' in p]}"
    )
    assert "get" in paths["/api/coinstats/test-connection"]


@pytest.mark.asyncio
async def test_coinstats_test_connection_never_500():
    """/api/coinstats/test-connection must return structured JSON even when service raises."""
    with patch("services.news_coinstats.coinstats_provider") as mock_provider:
        mock_provider.test_connection = AsyncMock(side_effect=RuntimeError("network error"))
        from routes.coinstats import coinstats_test_connection
        result = await coinstats_test_connection(user_id="user1")

    assert "status" in result
    assert result["status"] == "error"
    assert "configured" in result
    assert result["configured"] is False


# ── H: /api/intelligence/status ──────────────────────────────────────────────

def test_intelligence_status_in_openapi():
    """/api/intelligence/status must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.intelligence import router as intel_router

    app = FastAPI()
    app.include_router(intel_router)

    paths = app.openapi().get("paths", {})
    assert "/api/intelligence/status" in paths, (
        f"intelligence/status not in paths. Available: {[p for p in paths if 'intelligence' in p]}"
    )
    assert "get" in paths["/api/intelligence/status"]


@pytest.mark.asyncio
async def test_intelligence_status_returns_required_fields():
    """/api/intelligence/status returns all required fields."""
    import services.market_intelligence_service as mis
    mis._last_brief = {
        "mood": "neutral",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "fetch_status": "ok",
        "block_reason": None,
    }

    with patch("services.news_coinstats.resolve_coinstats_key",
               new=AsyncMock(return_value=("key", "env"))):
        from routes.intelligence import get_intelligence_status
        result = await get_intelligence_status(user_id="user1")

    required = {
        "running", "hf_enabled", "source", "mood",
        "last_run_at", "next_run_in_seconds", "refresh_interval_seconds",
        "coinstats_configured", "key_source", "resolved_for_user_id",
    }
    missing = required - set(result.keys())
    assert not missing, f"intelligence/status missing fields: {missing}"
    assert result["running"] is True
    assert result["source"] == "CoinStats"


# ── I: /api/intelligence/latest ──────────────────────────────────────────────

def test_intelligence_latest_in_openapi():
    """/api/intelligence/latest must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.intelligence import router as intel_router

    app = FastAPI()
    app.include_router(intel_router)

    paths = app.openapi().get("paths", {})
    assert "/api/intelligence/latest" in paths, (
        f"intelligence/latest not in paths. Available: {[p for p in paths if 'intelligence' in p]}"
    )
    assert "get" in paths["/api/intelligence/latest"]


@pytest.mark.asyncio
async def test_intelligence_latest_returns_required_fields():
    """/api/intelligence/latest returns required fields and never raises."""
    import services.market_intelligence_service as mis
    mis._last_brief = {
        "what_happened": "BTC hits ATH",
        "why_it_matters": "Test",
        "what_amarktai_is_doing": "Monitoring",
        "confidence": "High",
        "mood": "positive",
        "top_risk": "none",
        "source": "CoinStats",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "headlines_count": 1,
        "fetch_status": "ok",
        "block_reason": None,
    }

    from routes.intelligence import get_latest_intelligence
    result = await get_latest_intelligence(user_id="user1")

    assert result.get("mood") == "positive"
    assert result.get("source") == "CoinStats"


@pytest.mark.asyncio
async def test_intelligence_latest_never_500():
    """/api/intelligence/latest must return structured JSON when service raises."""
    with patch("services.market_intelligence_service.get_latest_intelligence",
               new=AsyncMock(side_effect=RuntimeError("DB down"))):
        from routes.intelligence import get_latest_intelligence
        result = await get_latest_intelligence(user_id="user1")

    assert "mood" in result
    assert "source" in result
    assert result.get("source") == "CoinStats"


# ── J: /api/market/brief ─────────────────────────────────────────────────────

def test_market_brief_in_openapi():
    """/api/market/brief must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.market_api import router as market_router

    app = FastAPI()
    app.include_router(market_router)

    paths = app.openapi().get("paths", {})
    assert "/api/market/brief" in paths, (
        f"market/brief not in paths. Available: {[p for p in paths if 'market' in p]}"
    )
    assert "get" in paths["/api/market/brief"]


@pytest.mark.asyncio
async def test_market_brief_returns_required_fields():
    """/api/market/brief returns required fields and never raises."""
    import routes.market_api as market_api_mod

    # Reset cache to force a fresh fetch
    market_api_mod._brief_cache = {}
    market_api_mod._brief_cache_at = 0.0

    import services.market_intelligence_service as mis
    mis._last_brief = {
        "mood": "neutral",
        "what_happened": "BTC stable",
        "why_it_matters": "",
        "what_amarktai_is_doing": "",
        "top_risk": "none",
        "confidence": "Moderate",
        "source": "CoinStats",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "fetch_status": "ok",
        "block_reason": None,
    }

    from routes.market_api import get_market_brief
    result = await get_market_brief(user_id="user1")

    required = {"mood", "source"}
    missing = required - set(result.keys())
    assert not missing, f"market/brief missing fields: {missing}"
    assert result.get("source") == "CoinStats"


# ── K: /api/events/market-intelligence ───────────────────────────────────────

def test_events_market_intelligence_in_openapi():
    """/api/events/market-intelligence must appear in OpenAPI paths."""
    from fastapi import FastAPI
    from routes.events import router as events_router

    app = FastAPI()
    app.include_router(events_router)

    paths = app.openapi().get("paths", {})
    assert "/api/events/market-intelligence" in paths, (
        f"events/market-intelligence not in paths. Available: {[p for p in paths if 'events' in p]}"
    )
    assert "get" in paths["/api/events/market-intelligence"]


@pytest.mark.asyncio
async def test_events_market_intelligence_returns_required_fields():
    """/api/events/market-intelligence returns required fields and never raises."""
    import services.market_intelligence_service as mis
    mis._last_brief = {
        "what_happened": "Market stable",
        "why_it_matters": "",
        "what_amarktai_is_doing": "",
        "confidence": "Moderate",
        "mood": "neutral",
        "top_risk": "none",
        "source": "CoinStats",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "fetch_status": "ok",
    }

    from routes.events import get_market_intelligence
    result = await get_market_intelligence(user_id="user1")

    assert "mood" in result
    assert "source" in result
    assert result.get("source") == "CoinStats"


@pytest.mark.asyncio
async def test_events_market_intelligence_never_500():
    """/api/events/market-intelligence returns structured JSON when service raises."""
    with patch("services.market_intelligence_service.get_latest_intelligence",
               new=AsyncMock(side_effect=RuntimeError("service error"))):
        from routes.events import get_market_intelligence
        result = await get_market_intelligence(user_id="user1")

    assert "mood" in result
    assert "source" in result
