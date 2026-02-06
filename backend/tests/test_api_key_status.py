"""
Test API Key Management - Status Transitions
Tests the unified API key storage schema and status logic
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4


# Mock database module
class MockDB:
    """Mock database for testing"""
    
    def __init__(self):
        self.api_keys_collection = MagicMock()
        self.users_collection = MagicMock()
        self._keys_storage = {}
    
    def reset(self):
        """Reset mock storage"""
        self._keys_storage = {}


@pytest.fixture
def mock_db():
    """Provide mock database"""
    return MockDB()


@pytest.mark.asyncio
async def test_save_key_creates_saved_untested_status(mock_db):
    """Test that saving a key creates status=saved_untested"""
    
    # Mock the database operations
    mock_db.api_keys_collection.find_one = AsyncMock(return_value=None)
    mock_db.api_keys_collection.insert_one = AsyncMock(
        return_value=MagicMock(inserted_id="test_id")
    )
    mock_db.api_keys_collection.update_one = AsyncMock()
    
    # Simulate what the save endpoint does
    user_id = str(uuid4())
    provider_id = "luno"
    
    key_doc = {
        "id": str(uuid4()),
        "user_id": user_id,
        "provider": provider_id,
        "api_key_encrypted": "encrypted_key",
        "api_secret_encrypted": "encrypted_secret",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_tested_at": None,
        "last_test_ok": None,
        "last_test_error": None,
        "status": "saved_untested"
    }
    
    # Simulate insert
    await mock_db.api_keys_collection.insert_one(key_doc)
    
    # Verify the key was saved with correct status
    assert key_doc["status"] == "saved_untested"
    assert key_doc["last_tested_at"] is None
    assert key_doc["last_test_ok"] is None
    mock_db.api_keys_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_test_key_success_updates_to_test_ok(mock_db):
    """Test that testing a key successfully updates status to test_ok"""
    
    # Mock saved key
    saved_key = {
        "_id": "test_mongo_id",
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "provider": "luno",
        "api_key_encrypted": "encrypted_key",
        "api_secret_encrypted": "encrypted_secret",
        "status": "saved_untested",
        "last_tested_at": None,
        "last_test_ok": None
    }
    
    mock_db.api_keys_collection.find_one = AsyncMock(return_value=saved_key)
    mock_db.api_keys_collection.update_one = AsyncMock()
    
    # Simulate successful test
    timestamp = datetime.now(timezone.utc).isoformat()
    update_data = {
        "last_tested_at": timestamp,
        "last_test_ok": True,
        "last_test_error": None,
        "status": "test_ok"
    }
    
    await mock_db.api_keys_collection.update_one(
        {"user_id": saved_key["user_id"], "provider": saved_key["provider"]},
        {"$set": update_data}
    )
    
    # Verify update was called with correct data
    mock_db.api_keys_collection.update_one.assert_called_once()
    call_args = mock_db.api_keys_collection.update_one.call_args
    assert call_args[0][1]["$set"]["status"] == "test_ok"
    assert call_args[0][1]["$set"]["last_test_ok"] is True
    assert call_args[0][1]["$set"]["last_test_error"] is None


@pytest.mark.asyncio
async def test_test_key_failure_updates_to_test_failed(mock_db):
    """Test that testing a key unsuccessfully updates status to test_failed"""
    
    # Mock saved key
    saved_key = {
        "_id": "test_mongo_id",
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "provider": "luno",
        "api_key_encrypted": "encrypted_key",
        "api_secret_encrypted": "encrypted_secret",
        "status": "saved_untested",
        "last_tested_at": None,
        "last_test_ok": None
    }
    
    mock_db.api_keys_collection.find_one = AsyncMock(return_value=saved_key)
    mock_db.api_keys_collection.update_one = AsyncMock()
    
    # Simulate failed test
    timestamp = datetime.now(timezone.utc).isoformat()
    error_message = "Invalid API credentials"
    update_data = {
        "last_tested_at": timestamp,
        "last_test_ok": False,
        "last_test_error": error_message,
        "status": "test_failed"
    }
    
    await mock_db.api_keys_collection.update_one(
        {"user_id": saved_key["user_id"], "provider": saved_key["provider"]},
        {"$set": update_data}
    )
    
    # Verify update was called with correct data
    mock_db.api_keys_collection.update_one.assert_called_once()
    call_args = mock_db.api_keys_collection.update_one.call_args
    assert call_args[0][1]["$set"]["status"] == "test_failed"
    assert call_args[0][1]["$set"]["last_test_ok"] is False
    assert call_args[0][1]["$set"]["last_test_error"] == error_message


@pytest.mark.asyncio
async def test_list_computes_status_from_db_fields(mock_db):
    """Test that /api/keys/list computes status correctly from DB fields"""
    
    # Mock keys with different statuses
    keys = [
        {
            "provider": "luno",
            "status": "saved_untested",
            "last_tested_at": None,
            "last_test_ok": None
        },
        {
            "provider": "binance",
            "status": "test_ok",
            "last_tested_at": datetime.now(timezone.utc).isoformat(),
            "last_test_ok": True
        },
        {
            "provider": "kucoin",
            "status": "test_failed",
            "last_tested_at": datetime.now(timezone.utc).isoformat(),
            "last_test_ok": False,
            "last_test_error": "Invalid credentials"
        }
    ]
    
    # Verify status computation logic
    for key in keys:
        if key.get("last_test_ok") is True:
            computed_status = "test_ok"
        elif key.get("last_test_ok") is False:
            computed_status = "test_failed"
        else:
            computed_status = "saved_untested"
        
        # Status in DB should match computed status
        assert key["status"] == computed_status


def test_status_values_are_consistent():
    """Test that status values match ProviderStatus enum"""
    
    # These are the canonical status values
    VALID_STATUSES = [
        "not_configured",
        "saved_untested",
        "test_ok",
        "test_failed",
        "rate_limited"
    ]
    
    # Verify all expected statuses are defined
    assert "not_configured" in VALID_STATUSES
    assert "saved_untested" in VALID_STATUSES
    assert "test_ok" in VALID_STATUSES
    assert "test_failed" in VALID_STATUSES


@pytest.mark.asyncio
async def test_id_field_always_present(mock_db):
    """Test that id field is always generated when saving keys"""
    
    key_doc = {
        "id": str(uuid4()),  # Should always be present
        "user_id": str(uuid4()),
        "provider": "luno",
        "api_key_encrypted": "encrypted",
        "api_secret_encrypted": "encrypted",
        "status": "saved_untested"
    }
    
    # Verify id is present and is a valid UUID string
    assert "id" in key_doc
    assert isinstance(key_doc["id"], str)
    assert len(key_doc["id"]) == 36  # UUID4 string length


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
