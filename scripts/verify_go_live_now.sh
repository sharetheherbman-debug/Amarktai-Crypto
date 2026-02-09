#!/bin/bash
set -euo pipefail

echo "🔥 AMARKTAI GO-LIVE VERIFICATION"
echo "================================="

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
EMAIL="${AMK_EMAIL:-}"
PASSWORD="${AMK_PASSWORD:-}"
TIMEOUT="${TIMEOUT:-10}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

pass_test() { echo -e "${GREEN}✅ PASS:${NC} $1"; ((TESTS_PASSED++)); }
fail_test() { echo -e "${RED}❌ FAIL:${NC} $1"; ((TESTS_FAILED++)); }

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    fail_test "AMK_EMAIL and AMK_PASSWORD must be set"
    exit 1
fi

# Test 1: System ping
echo "Test 1: System Ping"
if curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" "$API_BASE/api/system/ping" | grep -q '"status"'; then
    pass_test "System ping"
else
    fail_test "System ping"
fi

# Test 2: Login
echo "Test 2: Login"
login_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -X POST "$API_BASE/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
if [ -n "$TOKEN" ]; then
    pass_test "Login successful"
else
    fail_test "Login failed"
    exit 1
fi

# Test 3: Exchanges (exactly 7)
echo "Test 3: Exchanges Registry"
exchanges=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" "$API_BASE/api/system/platforms")
exchange_count=$(echo "$exchanges" | grep -o '"total_count":[0-9]*' | cut -d':' -f2)
if [ "$exchange_count" -eq 7 ]; then
    pass_test "Exchange registry has 7 exchanges"
else
    fail_test "Exchange registry has $exchange_count (expected 7)"
fi

# Test 4: Providers (exactly 10)
echo "Test 4: Providers List"
providers=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" "$API_BASE/api/keys/providers")
count=$(echo "$providers" | grep -o '"id"' | wc -l)
if [ "$count" -eq 10 ]; then
    pass_test "Providers list has 10 providers"
else
    fail_test "Providers list has $count (expected 10)"
fi

# Test 5: Keys status (MUST NOT CRASH)
echo "Test 5: Keys Status"
if status=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" "$API_BASE/api/keys/status"); then
    if echo "$status" | grep -q '"success":true'; then
        pass_test "Keys status endpoint working"
    else
        fail_test "Keys status returned error"
    fi
else
    fail_test "Keys status endpoint crashed or failed"
fi

# Test 6: Keys list
echo "Test 6: Keys List"
if list=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" "$API_BASE/api/keys/list"); then
    pass_test "Keys list endpoint working"
else
    fail_test "Keys list endpoint failed"
fi

# Test 7: AI chat greeting
echo "Test 7: AI Chat Greeting"
if chat=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -X POST "$API_BASE/api/ai/chat/greeting" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json"); then
    pass_test "AI chat greeting working"
else
    fail_test "AI chat greeting failed"
fi

# Test 8: AI chat history
echo "Test 8: AI Chat History"
if history=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/ai/chat/history?limit=5"); then
    pass_test "AI chat history working"
else
    fail_test "AI chat history failed"
fi

# Summary
echo ""
echo "SUMMARY: $TESTS_PASSED passed, $TESTS_FAILED failed"
if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED - READY FOR GO-LIVE${NC}"
    exit 0
else
    echo -e "${RED}❌ TESTS FAILED${NC}"
    exit 1
fi
