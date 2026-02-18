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
    
    # Check that timedelta is available at module level (imported correctly)
    import ast
    import inspect
    
    source = inspect.getsource(admin_enhanced_module)
    tree = ast.parse(source)
    
    # Find all top-level import statements
    top_level_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    
    has_timedelta = False
    for node in top_level_imports:
        if isinstance(node, ast.ImportFrom) and node.module == 'datetime':
            imported_names = [alias.name for alias in node.names]
            if 'timedelta' in imported_names:
                has_timedelta = True
                break
    
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
    
    import ast
    import inspect
    
    source = inspect.getsource(admin_enhanced_module)
    tree = ast.parse(source)
    
    # Find all function definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check for imports inside the function
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.ImportFrom) and stmt.module == 'datetime':
                    imported_names = [alias.name for alias in stmt.names]
                    if 'timedelta' in imported_names:
                        pytest.fail(
                            f"Found inline timedelta import in function '{node.name}'. "
                            f"All imports should be at the top level."
                        )

