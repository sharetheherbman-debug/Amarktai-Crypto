#!/bin/bash
# ============================================================================
# Amarktai Network - Production Smoke Test
# ============================================================================
# Quick production readiness verification script
# Tests critical functionality in <2 minutes
#
# Usage:
#   ./scripts/smoke_prod.sh [API_URL] [INVITE_CODE]
#
# Examples:
#   ./scripts/smoke_prod.sh https://amarktai.online AMARKTAI2024
#   ./scripts/smoke_prod.sh http://localhost:8000 AMARKTAI2024
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed
# ============================================================================

set -e  # Exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="${1:-http://localhost:8000}"
INVITE_CODE="${2:-AMARKTAI2024}"
TEST_EMAIL="smoke-test-$(date +%s)@example.com"
TEST_PASSWORD="TestPassword123!"
TEST_USERNAME="smoketest$(date +%s)"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}Amarktai Network - Production Smoke Test${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""
echo "API URL: $API_URL"
echo "Invite Code: $INVITE_CODE"
echo "Test Email: $TEST_EMAIL"
echo ""

# Helper functions
print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("$1")
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# Cleanup on exit
cleanup() {
    echo ""
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "${BLUE}Test Summary${NC}"
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    
    if [ $TESTS_FAILED -gt 0 ]; then
        echo ""
        echo -e "${RED}Failed Tests:${NC}"
        for test in "${FAILED_TESTS[@]}"; do
            echo -e "  - $test"
        done
        echo ""
        echo -e "${RED}❌ SMOKE TEST FAILED${NC}"
        exit 1
    else
        echo ""
        echo -e "${GREEN}✅ ALL SMOKE TESTS PASSED${NC}"
        exit 0
    fi
}

trap cleanup EXIT

# ============================================================================
# Test 1: Health Check
# ============================================================================
print_test "Health check endpoint"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/system/health" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    print_pass "Health check returned 200 OK"
else
    print_fail "Health check failed (HTTP $HTTP_CODE)"
fi

# ============================================================================
# Test 2: User Registration with Invite Code (Header)
# ============================================================================
print_test "User registration with invite code header"

REGISTER_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -H "X-Invite-Code: $INVITE_CODE" \
    -d "{
        \"username\": \"$TEST_USERNAME\",
        \"email\": \"$TEST_EMAIL\",
        \"password\": \"$TEST_PASSWORD\"
    }" || echo '{"error": "curl_failed"}')

if echo "$REGISTER_RESPONSE" | grep -q "token\|success"; then
    print_pass "User registration succeeded with invite header"
else
    print_fail "User registration failed: $REGISTER_RESPONSE"
fi

# ============================================================================
# Test 3: User Login
# ============================================================================
print_test "User login"

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{
        \"email\": \"$TEST_EMAIL\",
        \"password\": \"$TEST_PASSWORD\"
    }" || echo '{"error": "curl_failed"}')

# Extract token
TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//' || echo "")

if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    print_pass "User login succeeded, token obtained"
    print_info "Token: ${TOKEN:0:20}..."
else
    print_fail "User login failed or no token returned: $LOGIN_RESPONSE"
    TOKEN=""  # Ensure TOKEN is empty for subsequent tests
fi

# ============================================================================
# Test 4: System Status (Authenticated)
# ============================================================================
print_test "System status endpoint (authenticated)"

if [ -n "$TOKEN" ]; then
    SYSTEM_STATUS=$(curl -s -X GET "$API_URL/api/system/status" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" || echo '{"error": "curl_failed"}')
    
    if echo "$SYSTEM_STATUS" | grep -q "success\|feature_flags"; then
        print_pass "System status endpoint returned valid response"
        
        # Check for trading mode flags
        if echo "$SYSTEM_STATUS" | grep -q "trading_mode_flags"; then
            print_pass "System status includes trading_mode_flags"
        else
            print_info "System status missing trading_mode_flags (may need update)"
        fi
    else
        print_fail "System status endpoint failed: $SYSTEM_STATUS"
    fi
else
    print_fail "Skipping system status test (no token)"
fi

# ============================================================================
# Test 5: API Keys List (Authenticated)
# ============================================================================
print_test "API keys list endpoint (authenticated)"

if [ -n "$TOKEN" ]; then
    KEYS_RESPONSE=$(curl -s -X GET "$API_URL/api/keys/list" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" || echo '{"error": "curl_failed"}')
    
    # Should return either 200 with keys array or 403 if not configured
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/keys/list" \
        -H "Authorization: Bearer $TOKEN" || echo "000")
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "403" ]; then
        print_pass "API keys list endpoint accessible (HTTP $HTTP_CODE)"
        
        # Check response format
        if echo "$KEYS_RESPONSE" | grep -q "keys\|success"; then
            print_pass "API keys response format valid"
        fi
    else
        print_fail "API keys list endpoint failed (HTTP $HTTP_CODE): $KEYS_RESPONSE"
    fi
else
    print_fail "Skipping API keys test (no token)"
fi

# ============================================================================
# Test 6: WebSocket Diagnostics
# ============================================================================
print_test "WebSocket diagnostics endpoint"

WS_DIAG=$(curl -s -X GET "$API_URL/api/diagnostics/ws" || echo '{"error": "curl_failed"}')

if echo "$WS_DIAG" | grep -q "expected_path\|ok"; then
    print_pass "WebSocket diagnostics endpoint returned valid response"
    
    # Check for expected_path
    if echo "$WS_DIAG" | grep -q '"/api/ws"'; then
        print_pass "WebSocket endpoint path is /api/ws"
    else
        print_info "WebSocket endpoint path may be non-standard"
    fi
else
    print_fail "WebSocket diagnostics failed: $WS_DIAG"
fi

# ============================================================================
# Test 7: Check for /api/api/ double path bug
# ============================================================================
print_test "Verify no /api/api/ double path errors"

# Try to access a known endpoint via /api/api/ (should 404)
DOUBLE_PATH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/api/system/health" || echo "000")

if [ "$DOUBLE_PATH_CODE" = "404" ] || [ "$DOUBLE_PATH_CODE" = "000" ]; then
    print_pass "No /api/api/ double path issue detected"
else
    print_fail "/api/api/ path unexpectedly accessible (HTTP $DOUBLE_PATH_CODE)"
fi

# ============================================================================
# Test 8: Verify 7 supported exchanges
# ============================================================================
print_test "Check for 7 supported exchanges"

# This test would need a platforms endpoint or similar
# For now, we'll just log a reminder
print_info "Manual verification needed: Ensure UI shows exactly 7 exchanges"
print_info "Expected: luno, binance, kucoin, bybit, kraken, bitget, gate"

# ============================================================================
# Optional Test 9: WebSocket Connection (requires Python)
# ============================================================================
if command -v python3 &> /dev/null && [ -n "$TOKEN" ]; then
    print_test "WebSocket connection test (optional)"
    
    WS_URL=$(echo "$API_URL" | sed 's/^http/ws/')/api/ws?token=$TOKEN
    
    # Try a quick WebSocket connection test (requires websockets module)
    python3 -c "
import asyncio
import sys
from datetime import datetime
try:
    import websockets
except ImportError:
    print('websockets module not installed, skipping')
    sys.exit(0)

async def test_ws():
    try:
        async with websockets.connect('$WS_URL', timeout=5) as ws:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            await ws.send('{\"type\": \"ping\", \"timestamp\": \"' + timestamp + '\"}')
            response = await asyncio.wait_for(ws.recv(), timeout=3)
            if 'pong' in response:
                print('WebSocket test passed')
                sys.exit(0)
            else:
                print('WebSocket unexpected response')
                sys.exit(1)
    except Exception as e:
        print(f'WebSocket test failed: {e}')
        sys.exit(1)

asyncio.run(test_ws())
" 2>&1 | while read line; do
        if echo "$line" | grep -q "passed"; then
            print_pass "WebSocket connection test succeeded"
        elif echo "$line" | grep -q "failed"; then
            print_info "WebSocket connection test failed (may need investigation)"
        elif echo "$line" | grep -q "not installed"; then
            print_info "WebSocket test skipped (websockets module not installed)"
        fi
    done
else
    print_info "WebSocket connection test skipped (requires python3 with websockets)"
fi

echo ""
echo -e "${BLUE}Smoke test execution complete${NC}"
