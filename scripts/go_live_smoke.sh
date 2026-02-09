#!/bin/bash
# Go-Live Smoke Test Script
# Verifies all critical functionality before go-live
# Uses environment variables for credentials

set -euo pipefail

echo "🔥 Go-Live Smoke Test"
echo "====================="
echo ""

# Configuration
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
EMAIL="${AMK_EMAIL:-}"
PASSWORD="${AMK_PASSWORD:-}"
TIMEOUT="${TIMEOUT:-10}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✅ PASS:${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}❌ FAIL:${NC} $1"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠️  WARN:${NC} $1"
}

# Check environment
if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    fail "Environment variables AMK_EMAIL and AMK_PASSWORD must be set"
    echo "Example: AMK_EMAIL=user@example.com AMK_PASSWORD=secret ./scripts/go_live_smoke.sh"
    exit 1
fi

echo "Testing API at: $API_BASE"
echo ""

# Test 1: System ping
echo "Test 1: System Ping"
response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/system/ping")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" = "200" ]; then
    pass "System ping successful"
else
    fail "System ping failed (HTTP $http_code)"
fi

# Test 2: Login
echo ""
echo "Test 2: User Login"
login_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" -X POST "$API_BASE/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

login_http_code=$(echo "$login_response" | tail -n1)
login_body=$(echo "$login_response" | head -n-1)

if [ "$login_http_code" = "200" ]; then
    TOKEN=$(echo "$login_body" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4 || echo "")
    if [ -n "$TOKEN" ]; then
        pass "Login successful, token obtained"
    else
        fail "Login returned 200 but no token found"
        exit 1
    fi
else
    fail "Login failed (HTTP $login_http_code)"
    echo "Response: $login_body"
    exit 1
fi

# Test 3: Providers endpoint returns 10
echo ""
echo "Test 3: Providers List (CRITICAL)"
platforms_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/keys/providers" \
    -H "Authorization: Bearer $TOKEN")

platforms_http_code=$(echo "$platforms_response" | tail -n1)
platforms_body=$(echo "$platforms_response" | head -n-1)

if [ "$platforms_http_code" = "200" ]; then
    platform_count=$(echo "$platforms_body" | grep -o '"id"' | wc -l)
    if [ "$platform_count" = "10" ]; then
        pass "Providers list returns 10 providers"
        
        # Check for all providers (3 AI + 7 exchanges = 10 total)
        for provider in openai flokx fetchai luno binance kucoin bybit kraken bitget gate; do
            if echo "$platforms_body" | grep -q "\"id\":\"$provider\""; then
                echo "  ✓ $provider found"
            else
                warn "$provider not found in providers list"
            fi
        done
    else
        fail "Providers list returns $platform_count providers (expected 10)"
    fi
else
    fail "Providers list request failed (HTTP $platforms_http_code)"
fi

# Test 4: Overview endpoint
echo ""
echo "Test 4: Overview Metrics"
overview_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/overview" \
    -H "Authorization: Bearer $TOKEN")

overview_http_code=$(echo "$overview_response" | tail -n1)
overview_body=$(echo "$overview_response" | head -n-1)

if [ "$overview_http_code" = "200" ]; then
    # Check for required fields
    required_fields=("total_profit" "active_bots" "paper_bots" "live_bots" "total_bots")
    all_found=true
    
    for field in "${required_fields[@]}"; do
        if echo "$overview_body" | grep -q "\"$field\""; then
            echo "  ✓ $field present"
        else
            warn "$field missing from overview"
            all_found=false
        fi
    done
    
    if [ "$all_found" = true ]; then
        pass "Overview returns all required fields"
    else
        warn "Overview missing some fields"
    fi
else
    fail "Overview request failed (HTTP $overview_http_code)"
fi


# Test 6: API keys endpoint
echo ""
echo "Test 6: API Keys Endpoint"
keys_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/api-keys" \
    -H "Authorization: Bearer $TOKEN")

keys_http_code=$(echo "$keys_response" | tail -n1)
keys_body=$(echo "$keys_response" | head -n-1)

if [ "$keys_http_code" = "200" ]; then
    pass "API keys endpoint accessible"
else
    fail "API keys endpoint failed (HTTP $keys_http_code)"
fi

# Test 7: OpenAI key test endpoint exists
echo ""
echo "Test 7: OpenAI Key Test Endpoint"
# Just check that the endpoint exists (don't actually test without key)
test_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" -X POST "$API_BASE/api/api-keys/openai/test" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"api_key":"dummy"}' || true)

test_http_code=$(echo "$test_response" | tail -n1)

if [ "$test_http_code" = "200" ] || [ "$test_http_code" = "400" ]; then
    # 400 is OK - means endpoint exists but key is invalid
    pass "OpenAI test endpoint exists"
else
    warn "OpenAI test endpoint may have issues (HTTP $test_http_code)"
fi

# Test 8: Chat Diagnostics (NEW)
echo ""
echo "Test 8: Chat Diagnostics"
chat_diag_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/diagnostics/chat" \
    -H "Authorization: Bearer $TOKEN")

chat_diag_http_code=$(echo "$chat_diag_response" | tail -n1)
chat_diag_body=$(echo "$chat_diag_response" | head -n-1)

if [ "$chat_diag_http_code" = "200" ]; then
    if echo "$chat_diag_body" | grep -q '"chat_available":true'; then
        pass "Chat diagnostics - chat is available"
    elif echo "$chat_diag_body" | grep -q '"chat_available":false'; then
        warn "Chat diagnostics - chat not available (OpenAI key not configured)"
    else
        fail "Chat diagnostics returned unexpected format"
    fi
else
    fail "Chat diagnostics endpoint failed (HTTP $chat_diag_http_code)"
fi

# Test 9: API Keys Status (NEW)
echo ""
echo "Test 9: API Keys Status"
keys_status_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/keys/status" \
    -H "Authorization: Bearer $TOKEN")

keys_status_http_code=$(echo "$keys_status_response" | tail -n1)
keys_status_body=$(echo "$keys_status_response" | head -n-1)

if [ "$keys_status_http_code" = "200" ]; then
    # Check for required exchanges
    all_exchanges_present=true
    for exchange in luno binance kucoin bybit kraken bitget gate openai; do
        if echo "$keys_status_body" | grep -q "\"$exchange\""; then
            echo "  ✓ $exchange status present"
        else
            warn "$exchange status missing"
            all_exchanges_present=false
        fi
    done
    
    if [ "$all_exchanges_present" = true ]; then
        pass "API keys status returns all required providers"
    else
        warn "API keys status missing some providers"
    fi
else
    fail "API keys status endpoint failed (HTTP $keys_status_http_code)"
fi

# Test 10: Realtime Smoke Test
echo ""
echo "Test 10: Realtime Events System"
realtime_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/diagnostics/realtime-smoke" \
    -H "Authorization: Bearer $TOKEN")

realtime_http_code=$(echo "$realtime_response" | tail -n1)
realtime_body=$(echo "$realtime_response" | head -n-1)

if [ "$realtime_http_code" = "200" ]; then
    if echo "$realtime_body" | grep -q '"success".*true'; then
        pass "Realtime events system operational"
    else
        fail "Realtime smoke test returned success=false"
    fi
else
    fail "Realtime smoke test failed (HTTP $realtime_http_code)"
fi

# Test 11: Analytics Performance Endpoint (Frontend Critical)
echo ""
echo "Test 11: Analytics Performance Endpoint"
analytics_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/analytics/performance" \
    -H "Authorization: Bearer $TOKEN")

analytics_http_code=$(echo "$analytics_response" | tail -n1)
analytics_body=$(echo "$analytics_response" | head -n-1)

if [ "$analytics_http_code" = "200" ]; then
    if echo "$analytics_body" | grep -q '"total_trades"\|"win_rate"'; then
        pass "Analytics performance endpoint working (no 404)"
    else
        warn "Analytics endpoint returned 200 but missing expected fields"
    fi
else
    fail "Analytics performance endpoint failed (HTTP $analytics_http_code) - Frontend will get 404s"
fi

# Test 10: Admin Users List (if admin)
echo ""
echo "Test 12: Admin Endpoints"
admin_response=$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w "\n%{http_code}" "$API_BASE/api/admin/users/list" \
    -H "Authorization: Bearer $TOKEN")

admin_http_code=$(echo "$admin_response" | tail -n1)

if [ "$admin_http_code" = "200" ]; then
    pass "Admin users list endpoint working"
elif [ "$admin_http_code" = "403" ]; then
    warn "Admin access denied (expected if user is not admin)"
else
    warn "Admin endpoint returned unexpected status (HTTP $admin_http_code)"
fi

# Summary
echo ""
echo "================================"
echo "Smoke Test Summary"
echo "================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All critical tests passed!${NC}"
    echo "System is ready for go-live."
    exit 0
else
    echo -e "${RED}💥 Some tests failed!${NC}"
    echo "Please fix issues before go-live."
    exit 1
fi
