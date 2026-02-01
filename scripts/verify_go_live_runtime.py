#!/usr/bin/env python3
"""
Go-Live Runtime Verification Script
Tests critical runtime features: API key testing, AI chat, and system health
Uses only standard library (urllib) - no external dependencies
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import os
import sys
from typing import Dict, Optional


class GoLiveVerifier:
    """Verifies go-live runtime functionality"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.token: Optional[str] = None
        self.tests_passed = 0
        self.tests_failed = 0
    
    def _make_request(self, method: str, path: str, data: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        """Make HTTP request using urllib"""
        url = f"{self.base_url}{path}"
        req_headers = {"Content-Type": "application/json"}
        
        if headers:
            req_headers.update(headers)
        
        if self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"
        
        req_data = None
        if data:
            req_data = json.dumps(data).encode('utf-8')
        
        request = urllib.request.Request(
            url,
            data=req_data,
            headers=req_headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = response.read().decode('utf-8')
                return {
                    "status": response.status,
                    "data": json.loads(response_data) if response_data else {}
                }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            return {
                "status": e.code,
                "data": json.loads(error_body) if error_body else {},
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": 0,
                "data": {},
                "error": str(e)
            }
    
    def login(self, email: str, password: str) -> bool:
        """Login and get JWT token"""
        print(f"🔐 Logging in as {email}...")
        
        response = self._make_request("POST", "/api/auth/login", {
            "email": email,
            "password": password
        })
        
        if response["status"] == 200 and "token" in response["data"]:
            self.token = response["data"]["token"]
            print("✅ Login successful")
            return True
        else:
            print(f"❌ Login failed: {response.get('error', response['data'])}")
            return False
    
    def test_preflight(self) -> bool:
        """Test 1: Check /api/health/preflight"""
        print("\n📋 Test 1: Preflight Check")
        print("  Endpoint: GET /api/health/preflight")
        
        response = self._make_request("GET", "/api/health/preflight")
        
        if response["status"] == 200:
            data = response["data"]
            if data.get("ok") or data.get("status") == "ok":
                print("  ✅ PASS - Preflight OK")
                self.tests_passed += 1
                return True
            else:
                print(f"  ❌ FAIL - Preflight not OK: {data}")
                self.tests_failed += 1
                return False
        else:
            print(f"  ❌ FAIL - HTTP {response['status']}: {response.get('error', response['data'])}")
            self.tests_failed += 1
            return False
    
    def test_keys_list(self) -> bool:
        """Test 2: Check /api/keys/list has at least one OpenAI key"""
        print("\n📋 Test 2: API Keys List")
        print("  Endpoint: GET /api/keys/list")
        
        response = self._make_request("GET", "/api/keys/list")
        
        if response["status"] == 200:
            data = response["data"]
            keys = data.get("keys", [])
            openai_keys = [k for k in keys if k.get("provider") == "openai"]
            
            if openai_keys:
                print(f"  ✅ PASS - Found {len(openai_keys)} OpenAI key(s)")
                self.tests_passed += 1
                return True
            else:
                print(f"  ❌ FAIL - No OpenAI keys found. Total keys: {len(keys)}")
                self.tests_failed += 1
                return False
        else:
            print(f"  ❌ FAIL - HTTP {response['status']}: {response.get('error', response['data'])}")
            self.tests_failed += 1
            return False
    
    def test_keys_test(self) -> bool:
        """Test 3: Test /api/keys/test with saved OpenAI key"""
        print("\n📋 Test 3: API Key Test")
        print("  Endpoint: POST /api/keys/test")
        
        response = self._make_request("POST", "/api/keys/test", {
            "provider": "openai",
            "model": "gpt-4o-mini"
        })
        
        if response["status"] == 200:
            data = response["data"]
            if data.get("ok") or data.get("success"):
                print(f"  ✅ PASS - Key test successful: {data.get('message', 'OK')}")
                self.tests_passed += 1
                return True
            else:
                print(f"  ❌ FAIL - Key test failed: {data}")
                self.tests_failed += 1
                return False
        else:
            print(f"  ❌ FAIL - HTTP {response['status']}: {response.get('error', response['data'])}")
            self.tests_failed += 1
            return False
    
    def test_ai_chat(self) -> bool:
        """Test 4: Test /api/ai/chat does not return 'Please save your OpenAI API key'"""
        print("\n📋 Test 4: AI Chat")
        print("  Endpoint: POST /api/ai/chat")
        
        response = self._make_request("POST", "/api/ai/chat", {
            "content": "Hello, what is the system status?",
            "request_action": False
        })
        
        if response["status"] == 200:
            data = response["data"]
            content = data.get("content", "")
            
            # Check for the error message that indicates no API key configured
            if "Please save your OpenAI API key" in content:
                print(f"  ❌ FAIL - AI chat returned config error: {content[:100]}")
                self.tests_failed += 1
                return False
            elif content:
                print(f"  ✅ PASS - AI chat responded: {content[:100]}...")
                self.tests_passed += 1
                return True
            else:
                print(f"  ❌ FAIL - AI chat returned empty content")
                self.tests_failed += 1
                return False
        else:
            print(f"  ❌ FAIL - HTTP {response['status']}: {response.get('error', response['data'])}")
            self.tests_failed += 1
            return False
    
    def run_all_tests(self) -> bool:
        """Run all tests and return overall pass/fail"""
        print("=" * 60)
        print("🚀 GO-LIVE RUNTIME VERIFICATION")
        print("=" * 60)
        
        # Get credentials from environment
        email = os.getenv("EMAIL")
        password = os.getenv("PASSWORD")
        
        if not email or not password:
            print("\n⚠️  SETUP REQUIRED:")
            print("  Set EMAIL and PASSWORD environment variables:")
            print("    export EMAIL='your-email@example.com'")
            print("    export PASSWORD='your-password'")
            print("\n  Or provide them as arguments:")
            print("    python3 verify_go_live_runtime.py <email> <password>")
            return False
        
        # Login
        if not self.login(email, password):
            return False
        
        # Run tests
        self.test_preflight()
        self.test_keys_list()
        self.test_keys_test()
        self.test_ai_chat()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 RESULTS")
        print("=" * 60)
        print(f"  ✅ Passed: {self.tests_passed}")
        print(f"  ❌ Failed: {self.tests_failed}")
        
        if self.tests_failed == 0:
            print("\n🎉 ALL TESTS PASSED - Go-Live Runtime Ready!")
            print("=" * 60)
            return True
        else:
            print("\n❌ SOME TESTS FAILED - Review errors above")
            print("=" * 60)
            return False


def main():
    """Main entry point"""
    # Get credentials from args or env
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")
    
    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]
    
    # Get base URL
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    if len(sys.argv) >= 4:
        base_url = sys.argv[3]
    
    # Run verifier
    verifier = GoLiveVerifier(base_url)
    
    success = verifier.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
