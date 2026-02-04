"""
Test to verify no route collisions exist in server.py
This test validates that the server can start without RuntimeError due to duplicate routes.
"""
import sys
import os
import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_no_route_collision_on_import():
    """Test that server module imports without route collision errors"""
    try:
        # Import will trigger route collision detection in server.py
        import server
        
        # If we get here, no collision was detected
        assert True, "Server imported successfully without route collision"
        
    except RuntimeError as e:
        if 'collision' in str(e).lower():
            pytest.fail(f"Route collision detected: {e}")
        else:
            # Some other RuntimeError
            raise
    except ImportError as e:
        # Missing dependencies - skip test in CI
        pytest.skip(f"Missing dependencies for full server import: {e}")


def test_resume_all_routes_are_unique():
    """Test that resume-all endpoints are not duplicated"""
    from routes import risk_management, bot_lifecycle
    
    # Get routes from risk_management
    risk_routes = []
    for route in risk_management.router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            for method in route.methods:
                risk_routes.append(f"{method} {route.path}")
    
    # Get routes from bot_lifecycle
    lifecycle_routes = []
    for route in bot_lifecycle.router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            # Account for prefix
            prefix = getattr(bot_lifecycle.router, 'prefix', '')
            for method in route.methods:
                lifecycle_routes.append(f"{method} {prefix}{route.path}")
    
    # Check for resume-all collision
    resume_all_routes = [r for r in risk_routes + lifecycle_routes if 'resume-all' in r]
    
    # Should not have duplicate POST /api/bots/resume-all
    bots_resume_all = [r for r in resume_all_routes if r == "POST /api/bots/resume-all"]
    
    assert len(bots_resume_all) <= 1, \
        f"Duplicate resume-all route found: {bots_resume_all}. " \
        f"All resume-all routes: {resume_all_routes}"


if __name__ == "__main__":
    # Run tests directly
    print("Testing for route collisions...")
    try:
        test_no_route_collision_on_import()
        print("✅ No route collision on import")
    except Exception as e:
        print(f"❌ Route collision test failed: {e}")
        sys.exit(1)
    
    try:
        test_resume_all_routes_are_unique()
        print("✅ Resume-all routes are unique")
    except Exception as e:
        print(f"❌ Resume-all uniqueness test failed: {e}")
        sys.exit(1)
    
    print("\n✅ All route collision tests passed!")
