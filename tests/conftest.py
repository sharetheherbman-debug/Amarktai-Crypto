"""
Shared pytest fixtures for the Amarktai Network test suite.

Provides:
  - client:            FastAPI TestClient backed by a mocked database
  - admin_token:       JWT for an admin user (is_admin=True)
  - normal_user_token: JWT for a regular (non-admin) user
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Set required environment variables BEFORE any backend module is imported.
# The settings validation runs at import time and requires these to be present.
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-32chars!!")
os.environ.setdefault(
    "ENCRYPTION_KEY",
    # A valid URL-safe base64-encoded 32-byte Fernet key for tests.
    "PxKPmauGholCa7qHkY1IPALzJiSHm9aVfdW2je0TLQw="
)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

# Make the backend package importable from every test module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# ---------------------------------------------------------------------------
# Pre-import packages that MUST remain as real modules throughout the test
# session.  Some test files (e.g. test_strategy_upgrade.py) run module-level
# code like ``if "fastapi.middleware.cors" not in sys.modules: sys.modules[...] = MagicMock()``
# at *collection* time (before any fixture runs).  Pre-importing here ensures
# the real packages are already in sys.modules before collection scans those
# test files, preventing them from being replaced with a plain MagicMock.
# ---------------------------------------------------------------------------
import fastapi                        # noqa: E402
import fastapi.security               # noqa: E402
import fastapi.responses              # noqa: E402
import fastapi.middleware             # noqa: E402
import fastapi.middleware.cors        # noqa: E402
import pydantic                       # noqa: E402
import starlette                      # noqa: E402
import starlette.responses            # noqa: E402
import starlette.requests             # noqa: E402
import starlette.middleware           # noqa: E402
try:
    import aiohttp                    # noqa: E402
except ImportError:
    pass
try:
    import jose                       # noqa: E402
except ImportError:
    pass
try:
    import passlib                    # noqa: E402
except ImportError:
    pass
try:
    import cryptography               # noqa: E402
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Minimal stubs for heavy optional dependencies that are not installed in CI.
# ---------------------------------------------------------------------------
for _mod in (
    "ccxt",
    "ccxt.async_support",
    "ccxt_service",
    "tenacity",
    "huggingface_hub",
    "redis",
    "aioredis",
    "openai",
    "numpy",
    "pandas",
    "sklearn",
    "sklearn.preprocessing",
    "sklearn.model_selection",
    "sklearn.linear_model",
    "psutil",
    "pyotp",
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.asyncio",
    "apscheduler.triggers",
    "apscheduler.triggers.interval",
    "apscheduler.triggers.cron",
    # Also stub the packages test_strategy_upgrade.py stubs at module-level so
    # they are already in sys.modules before that file is collected/imported
    # and therefore don't get replaced with a bare MagicMock (which would break
    # aiohttp/dotenv usage inside server.py at fixture time).
    "scipy",
    "scipy.stats",
    "dotenv",
    "rapidfuzz",
    "rapidfuzz.fuzz",
    "rapidfuzz.process",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# aiohttp is used by real server code — stub it with an AsyncMock-capable
# object so that ``await aiohttp.ClientSession().get(...)`` does not crash.
if "aiohttp" not in sys.modules:
    _aiohttp_stub = MagicMock()
    _aiohttp_session = MagicMock()
    _aiohttp_session.__aenter__ = AsyncMock(return_value=_aiohttp_session)
    _aiohttp_session.__aexit__ = AsyncMock(return_value=False)
    _aiohttp_session.get = AsyncMock(return_value=MagicMock(
        status=200,
        json=AsyncMock(return_value={}),
        text=AsyncMock(return_value=""),
    ))
    _aiohttp_stub.ClientSession = MagicMock(return_value=_aiohttp_session)
    sys.modules["aiohttp"] = _aiohttp_stub


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _make_token(user_id: str, is_admin: bool = False) -> str:
    """Create a signed JWT for the given user_id."""
    from auth import create_access_token
    return create_access_token({"sub": user_id, "is_admin": is_admin})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def admin_token() -> str:
    """JWT that authenticates an admin user."""
    return _make_token("admin_user_test", is_admin=True)


@pytest.fixture(scope="session")
def normal_user_token() -> str:
    """JWT that authenticates a regular (non-admin) user."""
    return _make_token("normal_user_test", is_admin=False)


@pytest.fixture()
def client():
    """
    FastAPI TestClient with the database layer stubbed out so tests never
    need a real MongoDB connection.

    The fixture patches the most commonly accessed collections in the
    ``database`` module.  Auth is left intact — tests that need a logged-in
    user should pass an ``admin_token`` / ``normal_user_token`` header.
    """
    from fastapi.testclient import TestClient

    # Build a generic async-mock collection that satisfies common call patterns.
    def _make_collection():
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _cursor = MagicMock()
        _cursor.to_list = AsyncMock(return_value=[])
        _cursor.sort = MagicMock(return_value=_cursor)
        _cursor.limit = MagicMock(return_value=_cursor)
        col.find = MagicMock(return_value=_cursor)
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
        col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        col.count_documents = AsyncMock(return_value=0)
        return col

    # The users collection must return different documents depending on who is asking.
    # admin_user_test → admin doc (is_admin=True)
    # any other user  → regular user doc (is_admin=False)
    _admin_doc = {
        "id": "admin_user_test",
        "email": "admin@test.com",
        "is_admin": True,
        "role": "admin",
        "daily_loss_lock_active": False,
        "emergency_stop": False,
    }
    _normal_doc = {
        "id": "normal_user_test",
        "email": "normal@test.com",
        "is_admin": False,
        "role": "user",
        "daily_loss_lock_active": False,
        "emergency_stop": False,
    }

    async def _user_lookup(query, *args, **kwargs):
        uid = query.get("id", "") if isinstance(query, dict) else ""
        if uid == "admin_user_test":
            return _admin_doc
        if uid == "normal_user_test":
            return _normal_doc
        # force_logout check uses {"_id": ...} — return a no-force doc
        return {"force_logout": False}

    users_col = _make_collection()
    users_col.find_one = _user_lookup

    # Stub database.connect so the lifespan startup never actually tries to
    # connect to MongoDB.  Without this, the lifespan would overwrite our
    # collection patches via ``global db; db = client[db_name]`` and all
    # subsequent collection accesses would return un-awaitable MagicMocks.
    async def _noop_connect():
        pass

    with patch("database.bots_collection", _make_collection()), \
         patch("database.trades_collection", _make_collection()), \
         patch("database.users_collection", users_col), \
         patch("database.orders_collection", _make_collection()), \
         patch("database.audit_logs_collection", _make_collection()), \
         patch("database.bot_metrics_collection", _make_collection()), \
         patch("database.db", None), \
         patch("database.connect", _noop_connect), \
         patch("database.connect_db", _noop_connect):

        from server import app
        tc = TestClient(app, raise_server_exceptions=False)
        yield tc
