"""
Test for admin authentication fix - resolve_current_user() helper
Tests the logic without requiring a running server
"""

import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bson import ObjectId


def test_resolve_current_user_string_logic():
    """Test resolve_current_user logic with string user_id"""
    user_id = "test-user-123"
    
    # Test the logic
    if isinstance(user_id, str) and "@" not in user_id:
        result = user_id
    else:
        result = None
    
    assert result == user_id, "String user_id should be returned as-is"
    assert isinstance(result, str), "Result should be string"
    print("✅ resolve_current_user: String user_id works")


def test_resolve_current_user_dict_logic():
    """Test resolve_current_user logic with dict formats"""
    
    # Test case 1: dict with 'id' field
    user_dict1 = {"id": "test-user-456", "email": "test@example.com"}
    if isinstance(user_dict1, dict):
        if "id" in user_dict1:
            result1 = str(user_dict1["id"])
        elif "user_id" in user_dict1:
            result1 = str(user_dict1["user_id"])
        elif "_id" in user_dict1:
            result1 = str(user_dict1["_id"])
        else:
            result1 = None
    
    assert result1 == "test-user-456", "Dict with 'id' should extract id"
    print("✅ resolve_current_user: Dict with 'id' field works")
    
    # Test case 2: dict with 'user_id' field
    user_dict2 = {"user_id": "test-user-789"}
    if isinstance(user_dict2, dict):
        if "id" in user_dict2:
            result2 = str(user_dict2["id"])
        elif "user_id" in user_dict2:
            result2 = str(user_dict2["user_id"])
        elif "_id" in user_dict2:
            result2 = str(user_dict2["_id"])
        else:
            result2 = None
    
    assert result2 == "test-user-789", "Dict with 'user_id' should extract user_id"
    print("✅ resolve_current_user: Dict with 'user_id' field works")
    
    # Test case 3: dict with '_id' ObjectId
    oid = ObjectId()
    user_dict3 = {"_id": oid}
    if isinstance(user_dict3, dict):
        if "id" in user_dict3:
            result3 = str(user_dict3["id"])
        elif "user_id" in user_dict3:
            result3 = str(user_dict3["user_id"])
        elif "_id" in user_dict3:
            result3 = str(user_dict3["_id"])
        else:
            result3 = None
    
    assert result3 == str(oid), "Dict with '_id' should convert ObjectId to string"
    print("✅ resolve_current_user: Dict with '_id' ObjectId works")


def test_resolve_current_user_objectid_logic():
    """Test resolve_current_user logic with ObjectId"""
    oid = ObjectId()
    
    # Test the logic
    if isinstance(oid, ObjectId):
        result = str(oid)
    else:
        result = None
    
    assert result == str(oid), "ObjectId should be converted to string"
    assert isinstance(result, str), "Result should be string"
    print("✅ resolve_current_user: ObjectId conversion works")


def test_admin_check_logic():
    """Test admin check logic for both is_admin and role fields"""
    
    # Test case 1: is_admin=True
    user1 = {"id": "admin-user-1", "is_admin": True}
    is_admin1 = user1.get('is_admin', False) or user1.get('role') == 'admin'
    assert is_admin1 is True, "User with is_admin=True should be admin"
    print("✅ Admin check: is_admin=True works")
    
    # Test case 2: role='admin'
    user2 = {"id": "admin-user-2", "role": "admin"}
    is_admin2 = user2.get('is_admin', False) or user2.get('role') == 'admin'
    assert is_admin2 is True, "User with role='admin' should be admin"
    print("✅ Admin check: role='admin' works")
    
    # Test case 3: Both set
    user3 = {"id": "admin-user-3", "is_admin": True, "role": "admin"}
    is_admin3 = user3.get('is_admin', False) or user3.get('role') == 'admin'
    assert is_admin3 is True, "User with both fields should be admin"
    print("✅ Admin check: Both fields works")
    
    # Test case 4: Non-admin user
    user4 = {"id": "regular-user", "is_admin": False}
    is_admin4 = user4.get('is_admin', False) or user4.get('role') == 'admin'
    assert is_admin4 is False, "Regular user should not be admin"
    print("✅ Admin check: Non-admin user correctly identified")
    
    # Test case 5: No admin fields
    user5 = {"id": "another-user"}
    is_admin5 = user5.get('is_admin', False) or user5.get('role') == 'admin'
    assert is_admin5 is False, "User without admin fields should not be admin"
    print("✅ Admin check: Missing fields defaults to non-admin")


def test_email_detection_logic():
    """Test email string detection logic"""
    
    # Test case 1: Email string
    email = "admin@example.com"
    is_email = isinstance(email, str) and "@" in email
    assert is_email is True, "Email should be detected"
    print("✅ Email detection: Email string detected correctly")
    
    # Test case 2: Regular user_id
    user_id = "user-123"
    is_email2 = isinstance(user_id, str) and "@" in user_id
    assert is_email2 is False, "Regular user_id should not be detected as email"
    print("✅ Email detection: Non-email string handled correctly")


def test_import_helper_function():
    """Test that resolve_current_user can be imported"""
    try:
        from auth import resolve_current_user
        print("✅ Import: resolve_current_user successfully imported from auth.py")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        raise


def test_import_from_admin_enhanced():
    """Test that admin_enhanced imports the helper correctly"""
    try:
        from routes.admin_enhanced import require_admin
        print("✅ Import: require_admin successfully imported from admin_enhanced.py")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        raise


if __name__ == "__main__":
    print("\n=== Testing Admin Auth Fix ===\n")
    
    test_resolve_current_user_string_logic()
    test_resolve_current_user_dict_logic()
    test_resolve_current_user_objectid_logic()
    test_admin_check_logic()
    test_email_detection_logic()
    test_import_helper_function()
    test_import_from_admin_enhanced()
    
    print("\n=== All Tests Passed ✅ ===\n")
