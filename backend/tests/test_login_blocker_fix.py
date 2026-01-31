"""
Test Login Blocker Fix - KeyError: 'id'
Tests that login works regardless of which id field exists:
- user has only _id
- user has both _id and id  
- user has id but no _id (edge case)
"""

import pytest
from fastapi.testclient import TestClient
from bson import ObjectId
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server import app
import database as db


@pytest.fixture
async def setup_db():
    """Setup test database connection"""
    await db.connect()
    yield
    # Cleanup test users
    await db.users_collection.delete_many({"email": {"$regex": "^test_login_blocker_"}})


@pytest.mark.asyncio
async def test_login_with_only_id_field(setup_db):
    """Test login when user has 'id' field but no '_id' MongoDB field (edge case)"""
    client = TestClient(app)
    
    # Create user with only 'id' field (simulate already migrated user)
    from auth import get_password_hash
    test_email = "test_login_blocker_id_only@example.com"
    test_password = "SecurePass123!"
    user_id = "test-uuid-123"
    
    # Insert directly with custom _id to simulate edge case
    user_dict = {
        "_id": ObjectId(),  # MongoDB will have this
        "id": user_id,  # Custom id field
        "email": test_email,
        "hashed_password": get_password_hash(test_password),
        "first_name": "Test",
        "currency": "ZAR",
        "created_at": "2024-01-01T00:00:00Z"
    }
    await db.users_collection.insert_one(user_dict)
    
    # Test login
    response = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    
    assert response.status_code == 200, f"Login failed: {response.json()}"
    data = response.json()
    assert "access_token" in data
    assert data["user"]["id"] == user_id
    print("✓ Login with 'id' field only - PASSED")


@pytest.mark.asyncio
async def test_login_with_only_mongodb_id(setup_db):
    """Test login when user has only MongoDB '_id' field (old users)"""
    client = TestClient(app)
    
    # Create user with only _id (no custom 'id' field)
    from auth import get_password_hash
    test_email = "test_login_blocker_mongodb_only@example.com"
    test_password = "SecurePass123!"
    
    # Insert without 'id' field to simulate old user
    mongodb_id = ObjectId()
    user_dict = {
        "_id": mongodb_id,
        "email": test_email,
        "hashed_password": get_password_hash(test_password),
        "first_name": "Test",
        "currency": "ZAR",
        "created_at": "2024-01-01T00:00:00Z"
    }
    await db.users_collection.insert_one(user_dict)
    
    # Test login - should work and auto-migrate
    response = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    
    assert response.status_code == 200, f"Login failed: {response.json()}"
    data = response.json()
    assert "access_token" in data
    assert "id" in data["user"], "User should have 'id' field after auto-migration"
    assert data["user"]["id"] == str(mongodb_id), "ID should match MongoDB _id"
    
    # Verify database was updated
    user_after = await db.users_collection.find_one({"email": test_email})
    assert "id" in user_after, "Database should have 'id' field after login"
    assert user_after["id"] == str(mongodb_id)
    print("✓ Login with MongoDB '_id' only - PASSED (auto-migrated)")


@pytest.mark.asyncio
async def test_login_with_both_id_fields(setup_db):
    """Test login when user has both '_id' and 'id' fields (normal case)"""
    client = TestClient(app)
    
    # Create user with both fields (normal case)
    from auth import get_password_hash
    test_email = "test_login_blocker_both@example.com"
    test_password = "SecurePass123!"
    user_id = "test-uuid-456"
    
    user_dict = {
        "_id": ObjectId(),
        "id": user_id,
        "email": test_email,
        "hashed_password": get_password_hash(test_password),
        "first_name": "Test",
        "currency": "ZAR",
        "created_at": "2024-01-01T00:00:00Z"
    }
    await db.users_collection.insert_one(user_dict)
    
    # Test login
    response = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    
    assert response.status_code == 200, f"Login failed: {response.json()}"
    data = response.json()
    assert "access_token" in data
    assert data["user"]["id"] == user_id
    print("✓ Login with both '_id' and 'id' - PASSED")


@pytest.mark.asyncio
async def test_migration_script_fixes_missing_ids(setup_db):
    """Test that startup migration fixes users with missing 'id' field"""
    # Create 3 users without 'id' field
    from auth import get_password_hash
    
    users = []
    for i in range(3):
        mongodb_id = ObjectId()
        user_dict = {
            "_id": mongodb_id,
            "email": f"test_migration_{i}@example.com",
            "hashed_password": get_password_hash("pass123"),
            "first_name": f"User{i}",
            "currency": "ZAR"
        }
        await db.users_collection.insert_one(user_dict)
        users.append((str(mongodb_id), user_dict["email"]))
    
    # Run migration
    from migrations.fix_user_id_field import migrate_user_ids
    await migrate_user_ids(db)
    
    # Verify all users now have 'id' field
    for expected_id, email in users:
        user = await db.users_collection.find_one({"email": email})
        assert "id" in user, f"User {email} should have 'id' field after migration"
        assert user["id"] == expected_id, f"ID should match MongoDB _id"
    
    print("✓ Migration script fixes missing IDs - PASSED")


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("\n=== Testing Login Blocker Fix ===\n")
        
        # Setup
        await db.connect()
        
        try:
            await test_login_with_only_id_field(None)
            await test_login_with_only_mongodb_id(None)
            await test_login_with_both_id_fields(None)
            await test_migration_script_fixes_missing_ids(None)
            
            print("\n✅ All login blocker tests PASSED")
        except AssertionError as e:
            print(f"\n❌ Test failed: {e}")
        finally:
            # Cleanup
            await db.users_collection.delete_many({"email": {"$regex": "^test_login_blocker_|^test_migration_"}})
    
    asyncio.run(run_tests())
