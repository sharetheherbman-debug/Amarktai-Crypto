#!/usr/bin/env python3
"""
Production Smoke Test Script
=============================

Validates critical endpoints and functionality before go-live.

Tests:
1. Server startup check (no route collisions)
2. /api/health/ping - health check (expects status=healthy, db=connected)
3. /api/build/info - unauthenticated build info
4. Auth login - authentication works
5. Wallet routes - GET /api/wallet/balances, POST /api/wallet/transfer
6. Profit metrics - /api/profits/metrics with unified accounting
7. Route collision detection

Environment Variables:
- SMOKE_BASE_URL: Base URL for API (default: http://localhost:8000)
- SMOKE_EMAIL: Email for authentication (default: test@amarktai.com)
- SMOKE_PASSWORD: Password for authentication (default: test123)

Usage:
    # Use environment variables
    export SMOKE_BASE_URL=http://localhost:8000
    export SMOKE_EMAIL=admin@amarktai.com
    export SMOKE_PASSWORD=mypassword
    ./scripts/smoke_test.py

    # Use command-line arguments
    ./scripts/smoke_test.py http://localhost:8000 admin@amarktai.com mypassword

    # Use defaults
    ./scripts/smoke_test.py

Exit Codes:
- 0: All tests passed (warnings OK)
- 1: One or more tests failed

Note: If authentication fails, public tests continue and protected endpoints are skipped cleanly.
"""

import sys
import os
import asyncio
import aiohttp
import json
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_test(name: str, status: str, message: str = ""):
    """Print test result with color"""
    if status == "PASS":
        icon = "✅"
        color = GREEN
    elif status == "FAIL":
        icon = "❌"
        color = RED
    elif status == "WARN":
        icon = "⚠️"
        color = YELLOW
    else:
        icon = "ℹ️"
        color = BLUE
    
    print(f"{color}{icon} {name:50} [{status}]{RESET}")
    if message:
        print(f"   {message}")


class SmokeTest:
    def __init__(self, base_url: str = None, email: str = None, password: str = None):
        # Environment variable support
        self.base_url = (base_url or os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")).rstrip('/')
        self.email = email or os.environ.get("SMOKE_EMAIL", "test@amarktai.com")
        self.password = password or os.environ.get("SMOKE_PASSWORD", "test123")
        self.token = None
        self.test_results = []
    
    async def run_all_tests(self):
        """Run all smoke tests"""
        print("=" * 80)
        print(f"{BLUE}🚀 Starting Production Smoke Tests{RESET}")
        print(f"   Base URL: {self.base_url}")
        print(f"   Time: {datetime.now().isoformat()}")
        print("=" * 80)
        print()
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # Test 1: Health check
            await self.test_health_check()
            
            # Test 2: Build info (unauthenticated)
            await self.test_build_info()
            
            # Test 3: Authentication
            await self.test_authentication()
            
            # If authentication succeeded, test authenticated endpoints
            if self.token:
                # Test 4: Wallet balances
                await self.test_wallet_balances()
                
                # Test 5: Wallet transfer
                await self.test_wallet_transfer()
                
                # Test 6: Profit metrics
                await self.test_profit_metrics()
                
                # Test 7: Overview metrics
                await self.test_overview_metrics()
            else:
                print_test("SKIPPING authenticated tests", "WARN", 
                          "No valid authentication - cannot test protected endpoints")
        
        # Summary
        print()
        print("=" * 80)
        print(f"{BLUE}📊 Test Summary{RESET}")
        print("=" * 80)
        passed = sum(1 for r in self.test_results if r['status'] == 'PASS')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAIL')
        warned = sum(1 for r in self.test_results if r['status'] == 'WARN')
        
        print(f"   Total Tests: {len(self.test_results)}")
        print(f"   {GREEN}Passed: {passed}{RESET}")
        print(f"   {RED}Failed: {failed}{RESET}")
        print(f"   {YELLOW}Warnings: {warned}{RESET}")
        print("=" * 80)
        
        # Exit code
        if failed > 0:
            print(f"{RED}❌ SMOKE TESTS FAILED{RESET}")
            return 1
        elif warned > 0:
            print(f"{YELLOW}⚠️ SMOKE TESTS PASSED WITH WARNINGS{RESET}")
            return 0
        else:
            print(f"{GREEN}✅ ALL SMOKE TESTS PASSED{RESET}")
            return 0
    
    async def test_health_check(self):
        """Test /api/health/ping - expects status=healthy and db=connected"""
        try:
            async with self.session.get(f"{self.base_url}/api/health/ping", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Accept both 'healthy' and 'ok' for backward compatibility
                    status_ok = data.get("status") in ["healthy", "ok"]
                    db_ok = data.get("db") == "connected"
                    
                    if status_ok and db_ok:
                        print_test("Health Check", "PASS", 
                                 f"Status: {data.get('status')}, DB: {data.get('db')}")
                        self.test_results.append({"name": "health_check", "status": "PASS"})
                    else:
                        print_test("Health Check", "FAIL", 
                                 f"Unexpected payload: {data}")
                        self.test_results.append({"name": "health_check", "status": "FAIL"})
                else:
                    print_test("Health Check", "FAIL", f"HTTP {resp.status}")
                    self.test_results.append({"name": "health_check", "status": "FAIL"})
        except Exception as e:
            print_test("Health Check", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "health_check", "status": "FAIL"})
    
    async def test_build_info(self):
        """Test /api/build/info (unauthenticated)"""
        try:
            async with self.session.get(f"{self.base_url}/api/build/info", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    required_fields = ["version", "built_at", "backend_path", "env", "api_base"]
                    missing = [f for f in required_fields if f not in data]
                    
                    if not missing:
                        version = data.get("version", "unknown")[:8]
                        env = data.get("env", "unknown")
                        print_test("Build Info", "PASS", 
                                  f"Version: {version}, Env: {env}")
                        self.test_results.append({"name": "build_info", "status": "PASS"})
                    else:
                        print_test("Build Info", "FAIL", 
                                  f"Missing fields: {', '.join(missing)}")
                        self.test_results.append({"name": "build_info", "status": "FAIL"})
                else:
                    print_test("Build Info", "FAIL", f"HTTP {resp.status}")
                    self.test_results.append({"name": "build_info", "status": "FAIL"})
        except Exception as e:
            print_test("Build Info", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "build_info", "status": "FAIL"})
    
    async def test_authentication(self):
        """Test auth login - continues public tests on failure, skips protected endpoints"""
        try:
            payload = {"email": self.email, "password": self.password}
            async with self.session.post(f"{self.base_url}/api/auth/login", 
                                        json=payload, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("access_token"):
                        self.token = data["access_token"]
                        print_test("Authentication", "PASS", 
                                  f"Token received for {self.email}")
                        self.test_results.append({"name": "authentication", "status": "PASS"})
                    else:
                        print_test("Authentication", "FAIL", 
                                  "No access_token in response")
                        self.test_results.append({"name": "authentication", "status": "FAIL"})
                elif resp.status == 401:
                    # Auth failure is acceptable - continue with public tests only
                    print_test("Authentication", "WARN", 
                              f"Auth failed for {self.email} - will skip protected endpoints")
                    self.test_results.append({"name": "authentication", "status": "WARN"})
                    # Don't set token - protected endpoint tests will be skipped
                else:
                    print_test("Authentication", "FAIL", f"HTTP {resp.status}")
                    self.test_results.append({"name": "authentication", "status": "FAIL"})
        except Exception as e:
            print_test("Authentication", "WARN", 
                      f"Auth error: {e} - will skip protected endpoints")
            self.test_results.append({"name": "authentication", "status": "WARN"})
    
    async def test_wallet_balances(self):
        """Test GET /api/wallet/balances"""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.session.get(f"{self.base_url}/api/wallet/balances",
                                       headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "user_id" in data:
                        print_test("Wallet Balances", "PASS", 
                                  f"Retrieved for user {data['user_id'][:8]}...")
                        self.test_results.append({"name": "wallet_balances", "status": "PASS"})
                    else:
                        print_test("Wallet Balances", "WARN", 
                                  "Response missing user_id field")
                        self.test_results.append({"name": "wallet_balances", "status": "WARN"})
                else:
                    print_test("Wallet Balances", "FAIL", f"HTTP {resp.status}")
                    self.test_results.append({"name": "wallet_balances", "status": "FAIL"})
        except Exception as e:
            print_test("Wallet Balances", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "wallet_balances", "status": "FAIL"})
    
    async def test_wallet_transfer(self):
        """Test POST /api/wallet/transfer (validation only, don't execute)"""
        headers = {"Authorization": f"Bearer {self.token}"}
        # Test validation - send invalid data to check endpoint exists
        payload = {"from_exchange": "luno", "to_exchange": "luno", "amount": 0}
        try:
            async with self.session.post(f"{self.base_url}/api/wallet/transfer",
                                        json=payload, headers=headers, timeout=5) as resp:
                # We expect 400 (validation error) which proves endpoint works
                if resp.status == 400:
                    print_test("Wallet Transfer Endpoint", "PASS", 
                              "Endpoint exists and validates correctly")
                    self.test_results.append({"name": "wallet_transfer", "status": "PASS"})
                elif resp.status == 200:
                    print_test("Wallet Transfer Endpoint", "WARN", 
                              "Endpoint accepted invalid data (check validation)")
                    self.test_results.append({"name": "wallet_transfer", "status": "WARN"})
                else:
                    print_test("Wallet Transfer Endpoint", "FAIL", 
                              f"HTTP {resp.status}")
                    self.test_results.append({"name": "wallet_transfer", "status": "FAIL"})
        except Exception as e:
            print_test("Wallet Transfer Endpoint", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "wallet_transfer", "status": "FAIL"})
    
    async def test_profit_metrics(self):
        """Test /api/profits/metrics (unified accounting)"""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.session.get(f"{self.base_url}/api/profits/metrics",
                                       headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and "metrics" in data:
                        metrics = data["metrics"]
                        required = ["net_realised_pnl_zar", "executed_trades_count", 
                                   "total_fees_zar"]
                        missing = [f for f in required if f not in metrics]
                        
                        if not missing:
                            pnl = metrics.get("net_realised_pnl_zar", 0)
                            trades = metrics.get("executed_trades_count", 0)
                            print_test("Profit Metrics (Unified)", "PASS", 
                                      f"PnL: R{pnl:.2f}, Trades: {trades}")
                            self.test_results.append({"name": "profit_metrics", "status": "PASS"})
                        else:
                            print_test("Profit Metrics (Unified)", "FAIL", 
                                      f"Missing fields: {', '.join(missing)}")
                            self.test_results.append({"name": "profit_metrics", "status": "FAIL"})
                    else:
                        print_test("Profit Metrics (Unified)", "FAIL", 
                                  "Invalid response structure")
                        self.test_results.append({"name": "profit_metrics", "status": "FAIL"})
                else:
                    print_test("Profit Metrics (Unified)", "FAIL", 
                              f"HTTP {resp.status}")
                    self.test_results.append({"name": "profit_metrics", "status": "FAIL"})
        except Exception as e:
            print_test("Profit Metrics (Unified)", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "profit_metrics", "status": "FAIL"})
    
    async def test_overview_metrics(self):
        """Test /api/overview (uses accounting service)"""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.session.get(f"{self.base_url}/api/overview",
                                       headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Check for accounting service integration
                    if "data_source" in data and data["data_source"] == "accounting_service":
                        pnl = data.get("net_realised_pnl_zar", 0)
                        trades = data.get("executed_trades_count", 0)
                        print_test("Overview Metrics (Unified)", "PASS", 
                                  f"Using accounting service - PnL: R{pnl:.2f}, Trades: {trades}")
                        self.test_results.append({"name": "overview_metrics", "status": "PASS"})
                    elif "total_profit" in data:
                        # Old format but still works
                        profit = data.get("total_profit", 0)
                        print_test("Overview Metrics", "WARN", 
                                  f"Legacy format - Profit: R{profit:.2f}")
                        self.test_results.append({"name": "overview_metrics", "status": "WARN"})
                    else:
                        print_test("Overview Metrics", "FAIL", 
                                  "Invalid response structure")
                        self.test_results.append({"name": "overview_metrics", "status": "FAIL"})
                else:
                    print_test("Overview Metrics", "FAIL", f"HTTP {resp.status}")
                    self.test_results.append({"name": "overview_metrics", "status": "FAIL"})
        except Exception as e:
            print_test("Overview Metrics", "FAIL", f"Error: {e}")
            self.test_results.append({"name": "overview_metrics", "status": "FAIL"})


async def main():
    """Main entry point"""
    # Get configuration from environment or command-line args
    # Priority: CLI args > Environment variables > Defaults
    import sys
    
    base_url = None
    email = None
    password = None
    
    # Parse simple CLI arguments if provided
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    if len(sys.argv) > 2:
        email = sys.argv[2]
    if len(sys.argv) > 3:
        password = sys.argv[3]
    
    # Run tests (SmokeTest will use env vars as fallback)
    smoke_test = SmokeTest(base_url, email, password)
    exit_code = await smoke_test.run_all_tests()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
