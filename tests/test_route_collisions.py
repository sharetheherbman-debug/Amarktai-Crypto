"""
Test Route Collision Detection
Ensures no duplicate routes exist in the FastAPI application.
This test MUST fail if any duplicate (method, path) combinations are registered.
"""

import pytest
import sys
import os
from collections import defaultdict

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_no_route_collisions():
    """
    Test that no duplicate routes exist in the application.
    
    This test imports the FastAPI app and verifies that each (method, path) 
    combination is registered exactly once (excluding auto-generated HEAD/OPTIONS).
    
    MUST fail if any collisions are detected.
    """
    # Import app after path setup
    from server import app
    
    route_registry = defaultdict(list)
    collisions = []
    
    # Collect all routes
    for route in app.routes:
        # Skip non-API routes (like root, docs, openapi, etc.)
        if not hasattr(route, 'methods') or not hasattr(route, 'path'):
            continue
        
        for method in route.methods:
            # Skip auto-generated methods
            if method in ['HEAD', 'OPTIONS']:
                continue
            
            route_key = f"{method} {route.path}"
            route_name = getattr(route, 'name', 'unknown')
            
            # Store route info
            route_registry[route_key].append(route_name)
    
    # Check for duplicates
    for route_key, route_names in route_registry.items():
        if len(route_names) > 1:
            collisions.append({
                'route': route_key,
                'count': len(route_names),
                'handlers': route_names
            })
    
    # Generate detailed error message if collisions found
    if collisions:
        error_msg = "\n" + "="*80 + "\n"
        error_msg += "ROUTE COLLISIONS DETECTED!\n"
        error_msg += "="*80 + "\n"
        for collision in collisions:
            error_msg += f"\n❌ {collision['route']}\n"
            error_msg += f"   Registered {collision['count']} times:\n"
            for handler in collision['handlers']:
                error_msg += f"   - {handler}\n"
        error_msg += "\n" + "="*80 + "\n"
        error_msg += "Multiple routers are registering the same endpoint.\n"
        error_msg += "This WILL cause unpredictable behavior in production.\n"
        error_msg += "Fix by removing duplicate route definitions.\n"
        error_msg += "="*80 + "\n"
        
        pytest.fail(error_msg)
    
    # Test passes - no collisions found
    print(f"✅ Route collision check passed - {len(route_registry)} unique routes registered")
    assert len(collisions) == 0, "No route collisions should exist"


def test_critical_endpoints_exist():
    """
    Test that critical endpoints exist in the application.
    
    Verifies that the 4 endpoints mentioned in the problem statement are registered.
    """
    from server import app
    
    critical_endpoints = {
        'GET /api/system/status',
        'GET /api/diagnostics/wallet-status',
        'GET /api/diagnostics/transfers',
        'GET /api/analytics/profit-history'
    }
    
    registered_routes = set()
    
    for route in app.routes:
        if not hasattr(route, 'methods') or not hasattr(route, 'path'):
            continue
        
        for method in route.methods:
            if method in ['HEAD', 'OPTIONS']:
                continue
            route_key = f"{method} {route.path}"
            registered_routes.add(route_key)
    
    missing = critical_endpoints - registered_routes
    
    if missing:
        error_msg = "\n" + "="*80 + "\n"
        error_msg += "CRITICAL ENDPOINTS MISSING!\n"
        error_msg += "="*80 + "\n"
        for endpoint in missing:
            error_msg += f"❌ {endpoint}\n"
        error_msg += "="*80 + "\n"
        pytest.fail(error_msg)
    
    print(f"✅ All {len(critical_endpoints)} critical endpoints exist")
    assert len(missing) == 0, "All critical endpoints should be registered"


if __name__ == "__main__":
    # Allow running directly for quick testing
    print("Testing route collisions...")
    test_no_route_collisions()
    print("\nTesting critical endpoints...")
    test_critical_endpoints_exist()
    print("\n✅ All route tests passed!")
