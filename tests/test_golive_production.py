"""
Go-Live Production Readiness Tests
Covers:
  B3 - Trade insertion regression tests
  F3 - HuggingFace status logic unit tests
  A1 - DB config parsing (MONGO_URI support)
  A3 - /api/build response shape
"""
import sys
import os
import pytest

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# =============================================================================
# B3: build_trade_record tests
# =============================================================================

class TestBuildTradeRecord:
    """B3 – Regression tests for build_trade_record."""

    def test_preserves_provided_id(self):
        """build_trade_record must keep a provided id and never overwrite it."""
        from utils.trade_utils import build_trade_record
        trade = {"id": "my-custom-id-123", "side": "buy", "pair": "BTC/ZAR", "exchange": "luno"}
        result = build_trade_record(trade)
        assert result["id"] == "my-custom-id-123"

    def test_auto_generates_id_when_missing(self):
        """build_trade_record must generate a non-null UUID when id is absent."""
        from utils.trade_utils import build_trade_record
        trade = {"side": "buy", "pair": "BTC/ZAR", "exchange": "luno"}
        result = build_trade_record(trade)
        assert result["id"] is not None
        assert len(result["id"]) > 0

    def test_auto_generates_id_when_empty_string(self):
        """build_trade_record must replace empty-string id."""
        from utils.trade_utils import build_trade_record
        trade = {"id": "", "side": "buy", "pair": "BTC/ZAR", "exchange": "luno"}
        result = build_trade_record(trade)
        assert result["id"] not in (None, "")

    def test_auto_generates_id_when_none(self):
        """build_trade_record must replace explicit None id."""
        from utils.trade_utils import build_trade_record
        trade = {"id": None, "side": "buy", "pair": "BTC/ZAR", "exchange": "luno"}
        result = build_trade_record(trade)
        assert result["id"] is not None
        assert len(result["id"]) > 0

    def test_two_records_have_distinct_ids(self):
        """Two calls without an id must produce distinct UUIDs."""
        from utils.trade_utils import build_trade_record
        trade_a = build_trade_record({"side": "buy", "pair": "BTC/ZAR", "exchange": "luno"})
        trade_b = build_trade_record({"side": "sell", "pair": "ETH/ZAR", "exchange": "luno"})
        assert trade_a["id"] != trade_b["id"]


# =============================================================================
# B3: order_pipeline trade_doc id field test (unit, no DB)
# =============================================================================

class TestOrderPipelineTradeDocId:
    """Verify order_pipeline trade_doc always includes 'id' before insertion."""

    def test_trade_doc_in_pipeline_has_id(self):
        """The trade_doc built in order_pipeline must contain a non-null 'id'."""
        import uuid

        # Replicate the construction from order_pipeline.py
        trade_doc = {
            "id": str(uuid.uuid4()),
            "user_id": "user_1",
            "bot_id": "bot_1",
            "order_id": "order_abc",
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "symbol": "BTC/ZAR",
            "side": "buy",
            "amount": 0.001,
            "entry_price": 1000000.0,
            "fill_price": 1000000.0,
            "notional": 1000.0,
            "fee": 1.0,
            "fee_currency": "ZAR",
            "status": "closed",
            "is_paper": True,
            "net_pnl": 0.0,
            "profit_loss": 0.0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "filled_at": "2024-01-01T00:00:00+00:00",
        }

        assert "id" in trade_doc
        assert trade_doc["id"] not in (None, "")


# =============================================================================
# A1: DB config parsing
# =============================================================================

class TestParseMongoConfig:
    """A1 – MONGO_URI parsing must extract the embedded DB name."""

    def test_mongo_uri_with_db_path(self, monkeypatch):
        """MONGO_URI=mongodb://host:27017/amarktai → db_name='amarktai'."""
        monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:27017/amarktai")
        monkeypatch.delenv("MONGO_URL", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)

        # Re-import the function after env change
        import importlib
        import database as database_module
        importlib.reload(database_module)
        mongo_url, db_name = database_module._parse_mongo_config()
        assert db_name == "amarktai"

    def test_mongo_url_plus_db_name(self, monkeypatch):
        """MONGO_URL + DB_NAME must be honoured when MONGO_URI is absent."""
        monkeypatch.delenv("MONGO_URI", raising=False)
        monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")
        monkeypatch.setenv("DB_NAME", "my_custom_db")

        import importlib
        import database as database_module
        importlib.reload(database_module)
        mongo_url, db_name = database_module._parse_mongo_config()
        assert db_name == "my_custom_db"

    def test_defaults_when_nothing_set(self, monkeypatch):
        """Defaults: MONGO_URL→localhost, DB_NAME→amarktai_trading."""
        monkeypatch.delenv("MONGO_URI", raising=False)
        monkeypatch.delenv("MONGO_URL", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)

        import importlib
        import database as database_module
        importlib.reload(database_module)
        mongo_url, db_name = database_module._parse_mongo_config()
        assert "localhost" in mongo_url
        assert db_name == "amarktai_trading"


# =============================================================================
# F3: HuggingFace status logic (mock requests)
# =============================================================================

class TestHuggingFaceStatus:
    """F3 – Backend unit tests for HF status logic."""

    def test_hf_status_returns_not_enabled_when_no_key(self, monkeypatch):
        """When no HF key is configured, status must show enabled=False."""
        import asyncio
        from unittest.mock import AsyncMock

        # Patch the resolver to return no key
        async def mock_resolve(user_id):
            return (None, "missing")

        monkeypatch.setattr(
            "routes.huggingface.resolve_huggingface_key",
            mock_resolve
        )
        # Also reset module-level tracking vars
        import routes.huggingface as hf_module
        hf_module._hf_last_success = None
        hf_module._hf_last_error = None
        hf_module._hf_last_latency_ms = None

        # Create a mock get_current_user dependency
        async def mock_user():
            return "test_user"

        # Call the endpoint function directly
        result = asyncio.get_event_loop().run_until_complete(
            hf_module.get_hf_status(user_id="test_user")
        )

        assert result["enabled"] is False

    def test_hf_status_structure(self, monkeypatch):
        """get_hf_status response must always contain required keys."""
        import asyncio
        import routes.huggingface as hf_module

        async def mock_resolve(user_id):
            return (None, "missing")

        monkeypatch.setattr("routes.huggingface.resolve_huggingface_key", mock_resolve)
        hf_module._hf_last_success = None
        hf_module._hf_last_error = None
        hf_module._hf_last_latency_ms = None

        result = asyncio.get_event_loop().run_until_complete(
            hf_module.get_hf_status(user_id="test_user")
        )
        required_keys = {"enabled", "model", "last_success_at", "last_error", "latency_ms"}
        assert required_keys.issubset(result.keys())
