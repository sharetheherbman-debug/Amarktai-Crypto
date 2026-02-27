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
    # 32-byte URL-safe base64 Fernet key (valid format for cryptography.Fernet)
    "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmNoYXJz"
)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

# Make the backend package importable from every test module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

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
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


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

    with patch("database.bots_collection", _make_collection()), \
         patch("database.trades_collection", _make_collection()), \
         patch("database.users_collection", users_col), \
         patch("database.orders_collection", _make_collection()), \
         patch("database.audit_logs_collection", _make_collection()), \
         patch("database.bot_metrics_collection", _make_collection()):

        from server import app
        tc = TestClient(app, raise_server_exceptions=False)
        yield tc
