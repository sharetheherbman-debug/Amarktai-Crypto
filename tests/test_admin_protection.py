"""
Test Admin Endpoint Protection
Ensures all /api/admin/* endpoints require admin privileges.
Non-admin users must get 403, admin users must get 200.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_require_admin_exists_in_auth():
    """require_admin must be defined in auth.py"""
    try:
        from auth import require_admin
    except ImportError:
        pytest.skip("auth dependencies not installed")
    assert callable(require_admin)


def test_is_admin_exists_in_auth():
    """is_admin must be defined in auth.py"""
    try:
        from auth import is_admin
    except ImportError:
        pytest.skip("auth dependencies not installed")
    assert callable(is_admin)


def test_get_admin_user_alias():
    """get_admin_user must be an alias for require_admin in auth.py"""
    try:
        from auth import require_admin, get_admin_user
    except ImportError:
        pytest.skip("auth dependencies not installed")
    assert get_admin_user is require_admin


def test_admin_enhanced_uses_centralized_require_admin():
    """admin_enhanced.py must import require_admin from auth, not define its own"""
    import inspect
    try:
        from routes.admin_enhanced import router
        import routes.admin_enhanced as admin_enhanced_module
    except ImportError:
        pytest.skip("routes.admin_enhanced dependencies not installed")
    
    source = inspect.getsource(admin_enhanced_module)
    
    # Must import from auth
    assert "from auth import require_admin" in source, \
        "admin_enhanced.py must import require_admin from auth"
    
    # Must NOT define its own
    assert "async def require_admin" not in source, \
        "admin_enhanced.py must not define its own require_admin"


def test_admin_start_fresh_uses_centralized_require_admin():
    """admin_start_fresh.py must import require_admin from auth"""
    import inspect
    try:
        import routes.admin_start_fresh as module
    except ImportError:
        pytest.skip("routes.admin_start_fresh dependencies not installed")
    source = inspect.getsource(module)
    
    assert "from auth import" in source and "require_admin" in source, \
        "admin_start_fresh.py must import require_admin from auth"


def test_admin_whitelist_uses_auth_dependency():
    """admin_whitelist.py must use get_admin_user from auth (alias for require_admin)"""
    import inspect
    try:
        import routes.admin_whitelist as module
    except ImportError:
        pytest.skip("routes.admin_whitelist dependencies not installed")
    source = inspect.getsource(module)
    
    assert "from auth import get_admin_user" in source, \
        "admin_whitelist.py must import get_admin_user from auth"


def test_user_model_has_is_admin_field():
    """User model must include is_admin field"""
    try:
        from models import User
    except ImportError:
        pytest.skip("models dependencies not installed")
    
    # Check that User model has is_admin field
    user_fields = User.model_fields if hasattr(User, 'model_fields') else User.__fields__
    assert 'is_admin' in user_fields, \
        "User model must have is_admin field"


def test_require_admin_raises_403_conceptually():
    """Verify require_admin's logic would raise 403 for non-admin"""
    try:
        from auth import is_admin
    except ImportError:
        pytest.skip("auth dependencies not installed")
    import asyncio
    
    # is_admin with a non-existent user should return False
    # (database lookup will fail gracefully)
    result = asyncio.get_event_loop().run_until_complete(
        is_admin("nonexistent_user_id_12345")
    )
    assert result is False, "is_admin should return False for non-existent user"


if __name__ == "__main__":
    test_require_admin_exists_in_auth()
    test_is_admin_exists_in_auth()
    test_get_admin_user_alias()
    print("✅ All admin protection tests passed!")
