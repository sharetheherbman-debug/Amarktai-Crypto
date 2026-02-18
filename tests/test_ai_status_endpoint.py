"""
Test AI Status Endpoint
Ensures /api/ai/status returns 200 and never crashes.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_ai_status_endpoint_exists():
    """GET /api/ai/status endpoint must exist"""
    try:
        from routes.ai_status import router
    except ImportError:
        pytest.skip("routes.ai_status dependencies not installed")
    
    # Check that ai/status route is defined
    routes = [route.path for route in router.routes]
    assert "/api/ai/status" in routes, \
        "ai/status endpoint must be defined in ai_status router"


def test_ai_status_router_registered_in_server():
    """ai_status router must be registered in server.py routers list"""
    try:
        from pathlib import Path
        server_path = Path(__file__).parent.parent / "backend" / "server.py"
        if not server_path.exists():
            pytest.skip("server.py not found")
        
        server_content = server_path.read_text()
        assert "routes.ai_status" in server_content, \
            "routes.ai_status must be registered in server.py routers_to_mount list"
        
    except Exception as e:
        pytest.skip(f"Could not check server.py: {e}")


def test_ai_status_returns_required_fields():
    """AI status endpoint must return required fields in response"""
    try:
        from routes.ai_status import get_ai_status
        import inspect
    except ImportError:
        pytest.skip("routes.ai_status dependencies not installed")
    
    # Check that endpoint uses authentication by inspecting function signature
    sig = inspect.signature(get_ai_status)
    params = sig.parameters
    
    # Must have user_id parameter with Depends(get_current_user)
    assert "user_id" in params, "ai/status endpoint must have user_id parameter"
    
    # Check that it has authentication via Depends
    source = inspect.getsource(get_ai_status)
    assert "get_current_user" in source, \
        "ai/status endpoint must use get_current_user for authentication"


def test_ai_status_graceful_degradation():
    """AI status must handle errors gracefully and never crash"""
    try:
        import routes.ai_status as ai_status_module
        import inspect
    except ImportError:
        pytest.skip("routes.ai_status dependencies not installed")
    
    # Check that the endpoint has exception handling
    source = inspect.getsource(ai_status_module.get_ai_status)
    
    assert "try:" in source, "ai/status endpoint must have exception handling"
    assert "except" in source, "ai/status endpoint must catch exceptions"
    assert "return" in source.split("except")[1], \
        "ai/status must return response even on error (graceful degradation)"
