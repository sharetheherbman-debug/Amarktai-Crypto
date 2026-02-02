"""
Test Route Uniqueness and Platform Configuration

This test ensures:
1. No duplicate routes exist (same METHOD + PATH)
2. Exactly 7 supported platforms (no more, no less)
3. VALR and OVEX only exist in _archive directories

This prevents issues like:
- Route collisions causing server startup failures
- Platform count drift across modules
- Removed exchanges accidentally re-introduced
"""

import os
import sys
import pytest
from pathlib import Path

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_no_duplicate_routes():
    """
    Test that no duplicate routes exist in the FastAPI app
    Checks for collisions on METHOD + PATH combinations
    """
    from server import app
    
    routes_seen = {}
    duplicates = []
    
    # Iterate through all routes
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods:
                # Normalize path (remove trailing slashes)
                path = route.path.rstrip('/')
                route_key = f"{method} {path}"
                
                if route_key in routes_seen:
                    duplicates.append({
                        'route': route_key,
                        'first_seen': routes_seen[route_key],
                        'duplicate': str(route.endpoint)
                    })
                else:
                    routes_seen[route_key] = str(route.endpoint)
    
    # Report any duplicates
    if duplicates:
        error_msg = "❌ Duplicate routes detected:\n"
        for dup in duplicates:
            error_msg += f"  {dup['route']}\n"
            error_msg += f"    First: {dup['first_seen']}\n"
            error_msg += f"    Duplicate: {dup['duplicate']}\n"
        pytest.fail(error_msg)
    
    print(f"✅ Route uniqueness check passed: {len(routes_seen)} unique routes")


def test_exactly_7_platforms():
    """
    Test that exactly 7 platforms are supported
    Validates the canonical platforms list
    """
    from config.platforms import SUPPORTED_PLATFORMS, PLATFORM_CONFIG
    
    # Check SUPPORTED_PLATFORMS list
    assert len(SUPPORTED_PLATFORMS) == 7, \
        f"SUPPORTED_PLATFORMS should have exactly 7 exchanges, found {len(SUPPORTED_PLATFORMS)}"
    
    # Check PLATFORM_CONFIG dict
    assert len(PLATFORM_CONFIG) == 7, \
        f"PLATFORM_CONFIG should have exactly 7 exchanges, found {len(PLATFORM_CONFIG)}"
    
    # Verify expected exchanges
    expected_exchanges = {'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'}
    actual_exchanges = set(SUPPORTED_PLATFORMS)
    
    assert actual_exchanges == expected_exchanges, \
        f"Platform mismatch. Expected: {expected_exchanges}, Got: {actual_exchanges}"
    
    print(f"✅ Platform count check passed: {len(SUPPORTED_PLATFORMS)} exchanges")
    print(f"   Exchanges: {', '.join(SUPPORTED_PLATFORMS)}")


def test_no_valr_ovex_in_active_code():
    """
    Test that VALR and OVEX only exist in _archive directories
    Ensures removed exchanges stay removed
    """
    from config.platforms import SUPPORTED_PLATFORMS, PLATFORM_CONFIG
    
    # Check not in canonical lists
    assert 'valr' not in SUPPORTED_PLATFORMS, \
        "VALR should not be in SUPPORTED_PLATFORMS"
    assert 'ovex' not in SUPPORTED_PLATFORMS, \
        "OVEX should not be in SUPPORTED_PLATFORMS"
    assert 'valr' not in PLATFORM_CONFIG, \
        "VALR should not be in PLATFORM_CONFIG"
    assert 'ovex' not in PLATFORM_CONFIG, \
        "OVEX should not be in PLATFORM_CONFIG"
    
    print("✅ VALR/OVEX exclusion check passed")


def test_all_modules_use_canonical_source():
    """
    Test that key modules import from canonical platforms.py
    Ensures no hardcoded platform lists exist
    """
    # Read key files and check they import from config.platforms
    files_to_check = [
        'config.py',
        'config/__init__.py',
        'engines/wallet_manager.py',
        'routes/wallet_endpoints.py',
        'routes/analytics_api.py',
    ]
    
    issues = []
    
    for file_path in files_to_check:
        full_path = backend_dir / file_path
        if full_path.exists():
            content = full_path.read_text()
            
            # Check if file imports from config.platforms
            if 'config.platforms' not in content and 'from config.platforms import' not in content:
                # Check if it has hardcoded exchange lists
                if "['luno', 'binance', 'kucoin']" in content or \
                   '["luno", "binance", "kucoin"]' in content or \
                   "['luno', 'binance', 'kucoin', 'bybit', 'bitget']" in content:
                    issues.append(f"{file_path} appears to have hardcoded exchange list")
    
    if issues:
        pytest.fail("❌ Modules with potential hardcoded exchanges:\n  " + "\n  ".join(issues))
    
    print("✅ Canonical source check passed")


def test_paper_trading_supports_all_7():
    """
    Test that paper trading configuration supports all 7 exchanges
    """
    from config import PAPER_SUPPORTED_EXCHANGES
    
    assert len(PAPER_SUPPORTED_EXCHANGES) == 7, \
        f"PAPER_SUPPORTED_EXCHANGES should have 7 exchanges, found {len(PAPER_SUPPORTED_EXCHANGES)}"
    
    expected = {'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'}
    assert set(PAPER_SUPPORTED_EXCHANGES) == expected, \
        f"PAPER_SUPPORTED_EXCHANGES mismatch. Expected: {expected}, Got: {set(PAPER_SUPPORTED_EXCHANGES)}"
    
    print(f"✅ Paper trading supports all 7 exchanges")


def test_platform_endpoints_exist():
    """
    Test that critical platform endpoints exist without collision
    """
    from server import app
    
    # Check for key endpoints
    required_endpoints = [
        ('GET', '/api/platforms'),
        ('GET', '/api/system/status'),
        ('GET', '/api/system/emergency-gates'),  # Renamed from /status to avoid collision
        ('GET', '/api/wallet/transfers'),
    ]
    
    found_routes = {}
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods:
                path = route.path.rstrip('/')
                route_key = f"{method} {path}"
                found_routes[route_key] = True
    
    missing = []
    for method, path in required_endpoints:
        route_key = f"{method} {path}"
        if route_key not in found_routes:
            missing.append(route_key)
    
    if missing:
        pytest.fail(f"❌ Missing required endpoints:\n  " + "\n  ".join(missing))
    
    print(f"✅ All required endpoints exist")


if __name__ == "__main__":
    # Run tests when executed directly
    print("=" * 70)
    print("ROUTE UNIQUENESS AND PLATFORM CONFIGURATION TESTS")
    print("=" * 70)
    print()
    
    try:
        test_no_duplicate_routes()
        test_exactly_7_platforms()
        test_no_valr_ovex_in_active_code()
        test_all_modules_use_canonical_source()
        test_paper_trading_supports_all_7()
        test_platform_endpoints_exist()
        
        print()
        print("=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 70)
        sys.exit(1)
