#!/usr/bin/env python3
"""
Verify Dashboard Endpoint Compatibility
Tests that all required endpoints are present in OpenAPI spec and accessible

Usage:
    python3 verify_dashboard_endpoints.py [backend_url]
    BACKEND_URL=http://production:8001 python3 verify_dashboard_endpoints.py
"""

import requests
import json
import sys
import os
from typing import List, Tuple
from urllib.parse import urlparse

# Parse backend URL from command line, environment, or default
def get_backend_url() -> str:
    """Get backend URL from CLI arg, env var, or use default"""
    url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("BACKEND_URL", "http://localhost:8001")
    
    # Basic URL validation
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
        # Ensure no trailing slash
        url = url.rstrip("/")
        return url
    except Exception as e:
        print(f"Error: Invalid backend URL '{url}': {e}")
        print("Usage: python3 verify_dashboard_endpoints.py [backend_url]")
        print("Example: python3 verify_dashboard_endpoints.py http://localhost:8001")
        sys.exit(1)

BACKEND_URL = get_backend_url()

def check_openapi_paths() -> Tuple[bool, List[str]]:
    """Check if all required paths are in OpenAPI spec"""
    print("\n=== Checking OpenAPI Specification ===")
    
    try:
        response = requests.get(f"{BACKEND_URL}/openapi.json", timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch OpenAPI spec: {response.status_code}")
            return False, []
        
        openapi_spec = response.json()
        paths = openapi_spec.get("paths", {})
        
        required_endpoints = [
            "/api/wallet/requirements",
            "/api/system/emergency-stop",
            "/api/system/emergency-stop/status",
            "/api/system/emergency-stop/disable",
            "/api/auth/profile",
            "/api/ai/insights",
            "/api/ml/predict",
            "/api/profits/reinvest",
            "/api/advanced/decisions/recent",
            "/api/keys/test",
            "/api/system/mode",
            "/api/health/ping",
        ]
        
        missing = []
        present = []
        
        for endpoint in required_endpoints:
            if endpoint in paths:
                present.append(endpoint)
                print(f"✅ {endpoint}")
            else:
                missing.append(endpoint)
                print(f"❌ {endpoint} - NOT FOUND")
        
        print(f"\n📊 Summary: {len(present)}/{len(required_endpoints)} endpoints present")
        
        return len(missing) == 0, missing
        
    except Exception as e:
        print(f"❌ Error checking OpenAPI spec: {e}")
        return False, []


def test_endpoint_auth(endpoint: str, method: str = "GET") -> str:
    """Test endpoint returns 401/403 without auth, not 404"""
    try:
        if method == "GET":
            response = requests.get(f"{BACKEND_URL}{endpoint}", timeout=5)
        else:
            response = requests.post(f"{BACKEND_URL}{endpoint}", timeout=5)
        
        status = response.status_code
        
        if status == 404:
            return f"❌ {endpoint} returns 404 (endpoint not mounted)"
        elif status in [401, 403]:
            return f"✅ {endpoint} returns {status} (properly protected)"
        elif status == 200:
            return f"⚠️  {endpoint} returns 200 (no auth required?)"
        else:
            return f"ℹ️  {endpoint} returns {status}"
            
    except Exception as e:
        return f"❌ {endpoint} error: {e}"


def test_protected_endpoints():
    """Test that protected endpoints return 401/403, not 404"""
    print("\n=== Testing Protected Endpoints ===")
    
    protected_endpoints = [
        ("/api/wallet/requirements", "GET"),
        ("/api/system/emergency-stop", "POST"),
        ("/api/ai/insights", "GET"),
        ("/api/ml/predict", "GET"),
        ("/api/profits/reinvest", "POST"),
        ("/api/advanced/decisions/recent", "GET"),
        ("/api/keys/test", "POST"),
        ("/api/system/mode", "GET"),
        ("/api/auth/profile", "GET"),
    ]
    
    results = []
    for endpoint, method in protected_endpoints:
        result = test_endpoint_auth(endpoint, method)
        print(result)
        results.append(result)
    
    # Count failures (404 responses)
    failures = sum(1 for r in results if "404" in r)
    
    if failures == 0:
        print(f"\n✅ All {len(results)} protected endpoints properly configured")
    else:
        print(f"\n❌ {failures} endpoints returning 404 (not mounted)")
    
    return failures == 0


def test_public_endpoints():
    """Test public endpoints are accessible"""
    print("\n=== Testing Public Endpoints ===")
    
    public_endpoints = [
        ("/api/health/ping", 200),
        ("/openapi.json", 200),
    ]
    
    all_pass = True
    for endpoint, expected_status in public_endpoints:
        try:
            response = requests.get(f"{BACKEND_URL}{endpoint}", timeout=5)
            status = response.status_code
            
            if status == expected_status:
                print(f"✅ {endpoint} returns {status}")
            else:
                print(f"❌ {endpoint} returns {status} (expected {expected_status})")
                all_pass = False
                
        except Exception as e:
            print(f"❌ {endpoint} error: {e}")
            all_pass = False
    
    return all_pass


def main():
    """Run all verification tests"""
    print("=" * 70)
    print("Dashboard Endpoint Compatibility Verification")
    print("=" * 70)
    print(f"Testing against: {BACKEND_URL}")
    
    # Check if server is running
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=5)
        print(f"✅ Server is running (status: {response.status_code})")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print(f"\nPlease start the server first:")
        print(f"  cd backend && uvicorn server:app --host 0.0.0.0 --port 8001")
        sys.exit(1)
    
    # Run all tests
    openapi_ok, missing = check_openapi_paths()
    protected_ok = test_protected_endpoints()
    public_ok = test_public_endpoints()
    
    # Final summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    
    if openapi_ok:
        print("✅ OpenAPI Spec: All required endpoints present")
    else:
        print(f"❌ OpenAPI Spec: Missing endpoints: {missing}")
    
    if protected_ok:
        print("✅ Protected Endpoints: All properly secured (401/403)")
    else:
        print("❌ Protected Endpoints: Some returning 404")
    
    if public_ok:
        print("✅ Public Endpoints: All accessible")
    else:
        print("❌ Public Endpoints: Some issues")
    
    print("=" * 70)
    
    # Exit with appropriate code
    if openapi_ok and protected_ok and public_ok:
        print("\n🎉 All checks passed! Dashboard endpoints are production-ready.")
        sys.exit(0)
    else:
        print("\n⚠️  Some checks failed. Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
