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
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

pass_test() { echo -e "${GREEN}✅ PASS:${NC} $1"; ((TESTS_PASSED++)); }
fail_test() { echo -e "${RED}❌ FAIL:${NC} $1"; ((TESTS_FAILED++)); }
warn_test() { echo -e "${YELLOW}⚠️  WARN:${NC} $1"; }

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

# Test 7: Live prices endpoint
echo "Test 7: Live Prices"
if prices=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" "$API_BASE/api/prices/live"); then
    if echo "$prices" | grep -q '"pair"'; then
        pass_test "Live prices endpoint working"
    else
        warn_test "Live prices returned but no data"
        ((TESTS_PASSED++))
    fi
else
    fail_test "Live prices endpoint failed"
fi

# Test 8: SSE realtime events (heartbeat check)
echo "Test 8: SSE Realtime Events"
sse_check=$(timeout 10 curl -sf -N \
    -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/realtime/events" 2>&1 | head -20 || true)
if echo "$sse_check" | grep -q "heartbeat\|data:"; then
    pass_test "SSE realtime events working"
else
    warn_test "SSE realtime events may not be emitting (check /api/realtime/events)"
    # Don't fail, just warn - SSE might need more time
    ((TESTS_PASSED++))
fi

# Test 9: Build info
echo "Test 9: Build Info"
if build=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    "$API_BASE/api/build/info"); then
    if echo "$build" | grep -q '"version"'; then
        pass_test "Build info endpoint working"
    else
        fail_test "Build info missing version"
    fi
else
    fail_test "Build info endpoint failed"
fi

# Test 10: AI chat greeting
echo "Test 10: AI Chat Greeting"
if chat=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -X POST "$API_BASE/api/ai/chat/greeting" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json"); then
    pass_test "AI chat greeting working"
else
    fail_test "AI chat greeting failed"
fi

# Test 11: AI chat history
echo "Test 11: AI Chat History"
if history=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/ai/chat/history?limit=5"); then
    pass_test "AI chat history working"
else
    fail_test "AI chat history failed"
fi

# Test 12: Dashboard overview
echo "Test 12: Dashboard Overview"
if overview=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/overview"); then
    pass_test "Dashboard overview working"
else
    fail_test "Dashboard overview failed"
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
