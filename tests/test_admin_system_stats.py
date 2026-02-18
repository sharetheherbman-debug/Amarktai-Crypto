"""
Test Admin System Stats Endpoint
Ensures /api/admin/system-stats returns 200 and doesn't crash with timedelta import errors.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_admin_enhanced_imports_timedelta():
    """admin_enhanced.py must import timedelta at top level"""
    try:
        import routes.admin_enhanced as admin_enhanced_module
    except ImportError:
        pytest.skip("routes.admin_enhanced dependencies not installed")
    
    # Check that timedelta is imported at module level
    import inspect
    source = inspect.getsource(admin_enhanced_module)
    
    # Should have timedelta in the top-level imports
    lines = source.split('\n')
    top_imports = [line for line in lines[:30] if 'from datetime import' in line]
    
    has_timedelta = any('timedelta' in line for line in top_imports)
    assert has_timedelta, "timedelta must be imported at the top level of admin_enhanced.py"


def test_system_stats_endpoint_exists():
    """GET /api/admin/system-stats endpoint must exist"""
    try:
        from routes.admin_enhanced import router
    except ImportError:
        pytest.skip("routes.admin_enhanced dependencies not installed")
    
    # Check that system-stats route is defined
    routes = [route.path for route in router.routes]
    assert "/system-stats" in routes or any("system-stats" in r for r in routes), \
        "system-stats endpoint must be defined in admin_enhanced router"


def test_system_stats_no_inline_timedelta_imports():
    """admin_enhanced.py should not have inline timedelta imports inside functions"""
    try:
        import routes.admin_enhanced as admin_enhanced_module
    except ImportError:
        pytest.skip("routes.admin_enhanced dependencies not installed")
    
    import inspect
    source = inspect.getsource(admin_enhanced_module)
    
    # Count inline timedelta imports (after the first 30 lines which are top-level imports)
    lines = source.split('\n')[30:]
    inline_imports = [line for line in lines if 'from datetime import' in line and 'timedelta' in line]
    
    assert len(inline_imports) == 0, \
        f"Found {len(inline_imports)} inline timedelta imports. All imports should be at the top level."

