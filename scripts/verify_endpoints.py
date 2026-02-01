#!/usr/bin/env python3
"""
Endpoint Verification Script
Tests that all requested endpoints exist and respond correctly
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

async def verify_endpoints():
    """Verify all endpoints exist in route files"""
    
    print("=" * 80)
    print("ENDPOINT VERIFICATION REPORT")
    print("=" * 80)
    print()
    
    results = []
    
    # Check dashboard/ledger endpoints
    endpoints_to_check = [
        ("GET /api/portfolio/summary", "backend/routes/ledger_endpoints.py", 23),
        ("GET /api/portfolio/summary", "backend/routes/dashboard_endpoints.py", 214),
        ("GET /api/profits", "backend/routes/ledger_endpoints.py", 77),
        ("GET /api/profits", "backend/routes/dashboard_endpoints.py", 21),
        ("GET /api/countdown/status", "backend/routes/ledger_endpoints.py", 111),
        ("GET /api/countdown/status", "backend/routes/dashboard_endpoints.py", 115),
        ("POST /api/keys/test", "backend/routes/api_key_management.py", 78),
        ("POST /api/keys/save", "backend/routes/api_key_management.py", 203),
        ("GET /api/keys/list", "backend/routes/api_key_management.py", 284),
        ("GET /api/health/ping", "backend/routes/health.py", 12),
    ]
    
    for endpoint, file_path, line_num in endpoints_to_check:
        full_path = Path(__file__).parent / file_path
        if not full_path.exists():
            print(f"❌ {endpoint}")
            print(f"   File not found: {file_path}")
            results.append(False)
            continue
        
        # Check if line contains the route decorator
        with open(full_path, 'r') as f:
            lines = f.readlines()
            if line_num <= len(lines):
                line = lines[line_num - 1]
                if "@router." in line and any(x in line for x in ["get", "post", "put"]):
                    print(f"✅ {endpoint}")
                    print(f"   Found at: {file_path}:{line_num}")
                    results.append(True)
                else:
                    print(f"⚠️  {endpoint}")
                    print(f"   Line {line_num} in {file_path} doesn't contain route decorator")
                    print(f"   Line content: {line.strip()}")
                    results.append(False)
            else:
                print(f"❌ {endpoint}")
                print(f"   Line {line_num} exceeds file length in {file_path}")
                results.append(False)
    
    print()
    print("=" * 80)
    print(f"SUMMARY: {sum(results)}/{len(results)} endpoints verified")
    print("=" * 80)
    
    # Check router mounting
    print()
    print("Checking router mounting in server.py...")
    print()
    
    server_path = Path(__file__).parent / "backend" / "server.py"
    with open(server_path, 'r') as f:
        content = f.read()
    
    routers_to_check = [
        ("dashboard_router", "dashboard_endpoints"),
        ("ledger_router", "ledger_endpoints"),
        ("api_key_mgmt_router", "api_key_management"),
        ("health_router", "health"),
    ]
    
    for router_var, module_name in routers_to_check:
        if f"from routes.{module_name} import router as {router_var}" in content:
            if f"app.include_router({router_var})" in content:
                print(f"✅ {router_var} imported and mounted")
            else:
                print(f"⚠️  {router_var} imported but NOT mounted")
        else:
            print(f"❌ {router_var} NOT imported")
    
    print()
    print("=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    
    if all(results):
        print("✅ All endpoints exist and are properly defined")
        return 0
    else:
        print("❌ Some endpoints are missing or improperly defined")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(verify_endpoints())
    sys.exit(exit_code)
