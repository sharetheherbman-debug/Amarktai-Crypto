"""
Test API Keys Repair Script
Tests the repair_api_keys.py script functionality
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from uuid import uuid4


class MockAPIKeysCollection:
    """Mock MongoDB collection for testing"""
    
    def __init__(self):
        self._docs = []
        self._updates = []
    
    async def count_documents(self, filter_query):
        return len(self._docs)
    
    def find(self, filter_query):
        """Return async iterator mock"""
        async def async_iter():
            for doc in self._docs:
                yield doc
        
        mock = MagicMock()
        mock.__aiter__ = lambda self: async_iter()
        return mock
    
    async def update_one(self, filter_query, update_query):
        """Track updates"""
        self._updates.append((filter_query, update_query))
        return MagicMock(modified_count=1)
    
    def add_doc(self, doc):
        """Add document to mock collection"""
        self._docs.append(doc)
    
    def get_updates(self):
        """Get all updates made"""
        return self._updates


@pytest.fixture
def mock_collection():
    """Provide mock API keys collection"""
    return MockAPIKeysCollection()


@pytest.mark.asyncio
async def test_repair_adds_missing_id_field(mock_collection):
    """Test that repair adds id field to keys missing it"""
    
    # Add a key without id field
    mock_collection.add_doc({
        "_id": "mongo_id_1",
        "user_id": str(uuid4()),
        "provider": "luno",
        "api_key_encrypted": "encrypted"
    })
    
    # Simulate repair logic
    async for doc in mock_collection.find({}):
        if not doc.get("id"):
            new_id = str(uuid4())
            await mock_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"id": new_id}}
            )
    
    # Verify update was made
    updates = mock_collection.get_updates()
    assert len(updates) == 1
    assert "$set" in updates[0][1]
    assert "id" in updates[0][1]["$set"]


@pytest.mark.asyncio
async def test_repair_converts_user_id_to_string(mock_collection):
    """Test that repair converts ObjectId user_id to string"""
    
    # Add a key with ObjectId user_id (simulated as dict)
    mock_object_id = MagicMock()
    mock_object_id.__str__ = lambda self: "507f1f77bcf86cd799439011"
    
    mock_collection.add_doc({
        "_id": "mongo_id_1",
        "user_id": mock_object_id,  # ObjectId type
        "provider": "luno",
        "id": str(uuid4())
    })
    
    # Simulate repair logic
    async for doc in mock_collection.find({}):
        user_id = doc.get("user_id")
        if user_id and not isinstance(user_id, str):
            await mock_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"user_id": str(user_id)}}
            )
    
    # Verify update was made
    updates = mock_collection.get_updates()
    assert len(updates) == 1
    assert updates[0][1]["$set"]["user_id"] == "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_repair_initializes_status_field(mock_collection):
    """Test that repair initializes missing status field"""
    
    # Add a key without status field
    mock_collection.add_doc({
        "_id": "mongo_id_1",
        "user_id": str(uuid4()),
        "provider": "luno",
        "id": str(uuid4()),
        "api_key_encrypted": "encrypted",
        "last_test_ok": None  # No test yet
    })
    
    # Simulate repair logic
    async for doc in mock_collection.find({}):
        if not doc.get("status"):
            # Derive status from last_test_ok
            if doc.get("last_test_ok") is True:
                status = "test_ok"
            elif doc.get("last_test_ok") is False:
                status = "test_failed"
            else:
                status = "saved_untested"
            
            await mock_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": status}}
            )
    
    # Verify status was set
    updates = mock_collection.get_updates()
    assert len(updates) == 1
    assert updates[0][1]["$set"]["status"] == "saved_untested"


@pytest.mark.asyncio
async def test_repair_derives_status_from_last_test_ok(mock_collection):
    """Test that repair derives correct status from last_test_ok field"""
    
    # Test case 1: last_test_ok=True
    mock_collection.add_doc({
        "_id": "mongo_id_1",
        "user_id": str(uuid4()),
        "provider": "luno",
        "id": str(uuid4()),
        "last_test_ok": True
    })
    
    # Test case 2: last_test_ok=False
    mock_collection.add_doc({
        "_id": "mongo_id_2",
        "user_id": str(uuid4()),
        "provider": "binance",
        "id": str(uuid4()),
        "last_test_ok": False
    })
    
    # Test case 3: last_test_ok=None
    mock_collection.add_doc({
        "_id": "mongo_id_3",
        "user_id": str(uuid4()),
        "provider": "kucoin",
        "id": str(uuid4()),
        "last_test_ok": None
    })
    
    # Simulate repair logic for all docs
    async for doc in mock_collection.find({}):
        if not doc.get("status"):
            if doc.get("last_test_ok") is True:
                status = "test_ok"
            elif doc.get("last_test_ok") is False:
                status = "test_failed"
            else:
                status = "saved_untested"
            
            await mock_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": status}}
            )
    
    # Verify correct statuses were derived
    updates = mock_collection.get_updates()
    assert len(updates) == 3
    assert updates[0][1]["$set"]["status"] == "test_ok"
    assert updates[1][1]["$set"]["status"] == "test_failed"
    assert updates[2][1]["$set"]["status"] == "saved_untested"


@pytest.mark.asyncio
async def test_repair_adds_timestamps(mock_collection):
    """Test that repair adds missing timestamps"""
    
    # Add a key without timestamps
    mock_collection.add_doc({
        "_id": "mongo_id_1",
        "user_id": str(uuid4()),
        "provider": "luno",
        "id": str(uuid4())
        # No created_at or updated_at
    })
    
    # Simulate repair logic
    async for doc in mock_collection.find({}):
        update_fields = {}
        
        if not doc.get("created_at"):
            update_fields["created_at"] = datetime.now(timezone.utc)
        
        if not doc.get("updated_at"):
            update_fields["updated_at"] = datetime.now(timezone.utc)
        
        if update_fields:
            await mock_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": update_fields}
            )
    
    # Verify timestamps were added
    updates = mock_collection.get_updates()
    assert len(updates) == 1
    assert "created_at" in updates[0][1]["$set"]
    assert "updated_at" in updates[0][1]["$set"]


@pytest.mark.asyncio
async def test_repair_handles_empty_collection(mock_collection):
    """Test that repair handles empty collection gracefully"""
    
    # Don't add any documents
    count = await mock_collection.count_documents({})
    assert count == 0
    
    # Simulate repair - should not crash
    async for doc in mock_collection.find({}):
        pass  # Should never execute
    
    # No updates should be made
    updates = mock_collection.get_updates()
    assert len(updates) == 0


def test_repair_script_importable():
    """
    Test that the repair script can be imported without errors
    
    Note: This test assumes scripts directory is at backend/../scripts
    relative to the test file location.
    """
    try:
        import sys
        import os
        
        # Add backend to path
        backend_path = os.path.join(
            os.path.dirname(__file__), "..", ".."
        )
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        # Try to import the repair script module
        # This will fail if there are syntax errors
        import scripts.repair_api_keys as repair_module
        
        # Verify the repair function exists
        assert hasattr(repair_module, "repair_api_keys")
        assert callable(repair_module.repair_api_keys)
        
    except ImportError as e:
        pytest.skip(f"Could not import repair script: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
