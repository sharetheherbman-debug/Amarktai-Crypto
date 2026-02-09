"""
Test Route Collision Detection
Ensures no duplicate routes exist in the FastAPI application

This test prevents route collisions that would cause server boot failures
"""

import pytest
import sys
import os
from collections import defaultdict

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_no_route_collisions():
    """
    Verify that the FastAPI application has no duplicate routes
    
    This test ensures each method+path combination is registered exactly once
    Duplicate routes cause unpredictable behavior and server boot failures
    """
    # Import server module (this builds the app)
    import server
    app = server.app
    
    # Extract routes and check for duplicates
    routes_map = defaultdict(list)
    
    for route in app.routes:
        # Skip non-route objects (like mounts)
        if not hasattr(route, 'methods'):
            continue
            
        # Get methods (filter out HEAD and OPTIONS as they're auto-generated)
        methods = route.methods or set()
        methods = {m for m in methods if m not in ('HEAD', 'OPTIONS')}
        
        if not methods:
            continue
            
        # Get path
        path = route.path.rstrip('/')
        if not path.startswith('/'):
            path = '/' + path
        
        # Get endpoint name
        endpoint_name = "unknown"
        if hasattr(route, 'endpoint'):
            endpoint = route.endpoint
            if hasattr(endpoint, '__module__') and hasattr(endpoint, '__name__'):
                endpoint_name = f"{endpoint.__module__}:{endpoint.__name__}"
            elif hasattr(endpoint, '__name__'):
                endpoint_name = endpoint.__name__
        
        # Record each method+path combination
        for method in methods:
            route_key = (method, path)
            routes_map[route_key].append(endpoint_name)
    
    # Find duplicates
    duplicates = {
        route_key: endpoints 
        for route_key, endpoints in routes_map.items() 
        if len(endpoints) > 1
    }
    
    # Assert no duplicates
    if duplicates:
        error_msg = "\n\nROUTE COLLISIONS DETECTED:\n"
        error_msg += "="*80 + "\n"
        
        for (method, path), endpoints in sorted(duplicates.items()):
            error_msg += f"\n❌ {method:6s} {path}\n"
            error_msg += f"   Defined {len(endpoints)} times:\n"
            for endpoint in endpoints:
                error_msg += f"      - {endpoint}\n"
        
        error_msg += "\n" + "="*80
        error_msg += "\n⚠️  Fix by keeping only one handler per route (method + path)"
        error_msg += "\n" + "="*80 + "\n"
        
        pytest.fail(error_msg)
    
    # If we get here, no duplicates were found
    print(f"\n✅ No route collisions detected ({len(routes_map)} unique routes)")


def test_api_prices_live_exactly_once():
    """
    Verify that GET /api/prices/live appears exactly once
    
    This was a critical issue (route collision) that prevented server boot.
    This test ensures the fix persists and we never regress.
    """
    import server
    app = server.app
    
    # Find all GET /api/prices/live routes
    prices_live_routes = []
    
    for route in app.routes:
        if not hasattr(route, 'methods'):
            continue
        
        methods = route.methods or set()
        if 'GET' not in methods:
            continue
        
        path = route.path.rstrip('/')
        if not path.startswith('/'):
            path = '/' + path
            
        if path == '/api/prices/live':
            endpoint_name = "unknown"
            if hasattr(route, 'endpoint'):
                endpoint = route.endpoint
                if hasattr(endpoint, '__module__') and hasattr(endpoint, '__name__'):
                    endpoint_name = f"{endpoint.__module__}:{endpoint.__name__}"
                elif hasattr(endpoint, '__name__'):
                    endpoint_name = endpoint.__name__
            prices_live_routes.append(endpoint_name)
    
    # Assert exactly one route
    if len(prices_live_routes) == 0:
        pytest.fail(
            "\n\n❌ CRITICAL: GET /api/prices/live route not found!\n"
            "This endpoint is required for dashboard price display.\n"
            "Expected location: routes.prices:get_live_prices\n"
        )
    elif len(prices_live_routes) > 1:
        pytest.fail(
            f"\n\n❌ CRITICAL: GET /api/prices/live defined {len(prices_live_routes)} times!\n"
            f"This causes route collision and prevents server boot.\n"
            f"Locations:\n" + 
            "\n".join(f"  - {loc}" for loc in prices_live_routes) +
            "\n\nKeep only ONE definition (should be routes.prices:get_live_prices)\n"
        )
    
    # Success - exactly one route
    print(f"\n✅ GET /api/prices/live registered exactly once: {prices_live_routes[0]}")


def test_critical_routes_exist():
    """
    Verify that critical routes are properly registered
    
    Tests that essential endpoints needed for production are available
    """
    import server
    app = server.app
    
    # Extract all routes as (method, path) tuples
    registered_routes = set()
    for route in app.routes:
        if not hasattr(route, 'methods'):
            continue
        methods = route.methods or set()
        methods = {m for m in methods if m not in ('HEAD', 'OPTIONS')}
        if not methods:
            continue
        path = route.path.rstrip('/')
        if not path.startswith('/'):
            path = '/' + path
        for method in methods:
            registered_routes.add((method, path))
    
    # Critical routes that must exist
    critical_routes = [
        ('GET', '/api/health/ping'),
        ('GET', '/api/metrics'),  # Prometheus metrics
        ('GET', '/api/system/mode'),
        ('GET', '/api/system/status'),
        ('POST', '/api/system/emergency-stop'),
        ('GET', '/api/trades/recent'),
        ('GET', '/api/portfolio/summary'),
        ('GET', '/api/countdown/status'),
        ('DELETE', '/api/bots/{bot_id}'),
        ('GET', '/api/admin/users'),
        ('GET', '/api/admin/system-stats'),
    ]
    
    missing_routes = []
    for method, path in critical_routes:
        if (method, path) not in registered_routes:
            missing_routes.append(f"{method} {path}")
    
    if missing_routes:
        error_msg = "\n\nCRITICAL ROUTES MISSING:\n"
        error_msg += "="*80 + "\n"
        for route in missing_routes:
            error_msg += f"❌ {route}\n"
        error_msg += "="*80 + "\n"
        pytest.fail(error_msg)
    
    print(f"\n✅ All {len(critical_routes)} critical routes are registered")


def test_route_count_reasonable():
    """
    Sanity check that we have a reasonable number of routes
    
    Too few routes might indicate a mounting failure
    Too many routes might indicate duplicate registrations
    """
    import server
    app = server.app
    
    # Count unique routes
    unique_routes = set()
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = route.methods or set()
            methods = {m for m in methods if m not in ('HEAD', 'OPTIONS')}
            for method in methods:
                unique_routes.add((method, route.path))
    
    route_count = len(unique_routes)
    
    # We expect between 200-400 routes in this app
    # Adjust these bounds if the app legitimately grows/shrinks
    MIN_EXPECTED = 200
    MAX_EXPECTED = 400
    
    assert route_count >= MIN_EXPECTED, (
        f"Too few routes registered ({route_count}). "
        f"Expected at least {MIN_EXPECTED}. "
        f"Some routers may have failed to mount."
    )
    
    assert route_count <= MAX_EXPECTED, (
        f"Too many routes registered ({route_count}). "
        f"Expected at most {MAX_EXPECTED}. "
        f"This might indicate duplicate route registrations."
    )
    
    print(f"\n✅ Route count is reasonable: {route_count} routes")


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
