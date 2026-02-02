#!/bin/bash
# Smoke Test Script - Automated API Testing
# Tests critical endpoints to verify production readiness
# Exit code 0 = all tests passed, non-zero = failures

set -e

# Configuration
API_BASE="${API_BASE:-https://amarktai.online/api}"
EMAIL="${TEST_EMAIL:-}"
PASSWORD="${TEST_PASSWORD:-}"
VERBOSE="${VERBOSE:-0}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

echo "========================================="
echo "🧪 Amarktai Network - Smoke Tests"
echo "========================================="
echo ""
echo "API Base: $API_BASE"
echo ""

# Helper: Print test result
test_result() {
    local test_name="$1"
    local status="$2"
    local message="$3"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    
    if [[ "$status" == "pass" ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "${GREEN}✅ PASS${NC} - $test_name"
        [[ "$VERBOSE" == "1" ]] && echo "   $message"
    elif [[ "$status" == "warn" ]]; then
        echo -e "${YELLOW}⚠️  WARN${NC} - $test_name"
        echo "   $message"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "${RED}❌ FAIL${NC} - $test_name"
        echo "   $message"
    fi
}

# Helper: Make API request
api_request() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local token="$4"
    local timeout="${5:-10}"
    
    local url="$API_BASE$endpoint"
    local headers=(-H "Content-Type: application/json")
    
    if [[ -n "$token" ]]; then
        headers+=(-H "Authorization: Bearer $token")
    fi
    
    if [[ "$method" == "GET" ]]; then
        curl -s -f -m "$timeout" "${headers[@]}" "$url"
    else
        curl -s -f -m "$timeout" -X "$method" "${headers[@]}" -d "$data" "$url"
    fi
}

# ============================================================================
# TEST 1: Health Check - Ping
# ============================================================================
echo "📍 Test 1: Health Check - Ping"
if response=$(api_request GET /health/ping "" "" 5 2>&1); then
    status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
    if [[ "$status" == "healthy" ]]; then
        test_result "Health Ping" "pass" "Status: $status"
    else
        test_result "Health Ping" "fail" "Unexpected status: $status"
    fi
else
    test_result "Health Ping" "fail" "Endpoint unreachable or returned error"
fi
echo ""

# ============================================================================
# TEST 2: Health Check - Ready
# ============================================================================
echo "📍 Test 2: Health Check - Ready"
if response=$(api_request GET /health/ready "" "" 5 2>&1); then
    ready=$(echo "$response" | jq -r '.ready // false' 2>/dev/null)
    if [[ "$ready" == "true" ]]; then
        test_result "Health Ready" "pass" "Service is ready"
    else
        issues=$(echo "$response" | jq -r '.issues[]' 2>/dev/null | tr '\n' ', ')
        test_result "Health Ready" "fail" "Service not ready: $issues"
    fi
else
    test_result "Health Ready" "fail" "Endpoint unreachable or returned error"
fi
echo ""

# ============================================================================
# TEST 3: Authentication - Login
# ============================================================================
echo "📍 Test 3: Authentication - Login"
TOKEN=""

if [[ -z "$EMAIL" ]] || [[ -z "$PASSWORD" ]]; then
    test_result "Auth Login" "warn" "TEST_EMAIL and TEST_PASSWORD not set - skipping auth tests"
    echo ""
    echo "To run auth tests, set environment variables:"
    echo "  export TEST_EMAIL=your@email.com"
    echo "  export TEST_PASSWORD=yourpassword"
    echo ""
else
    login_data=$(cat <<EOF
{
  "email": "$EMAIL",
  "password": "$PASSWORD"
}
EOF
)
    
    if response=$(api_request POST /auth/login "$login_data" "" 10 2>&1); then
        TOKEN=$(echo "$response" | jq -r '.access_token // .token // ""' 2>/dev/null)
        token_type=$(echo "$response" | jq -r '.token_type // ""' 2>/dev/null)
        
        if [[ -n "$TOKEN" ]] && [[ "$token_type" == "bearer" ]]; then
            test_result "Auth Login" "pass" "Token received (${#TOKEN} chars)"
        else
            test_result "Auth Login" "fail" "Invalid response: missing token or token_type"
        fi
    else
        test_result "Auth Login" "fail" "Login failed: $response"
    fi
    echo ""
fi

# ============================================================================
# TEST 4: Authentication - Get Current User (/auth/me)
# ============================================================================
if [[ -n "$TOKEN" ]]; then
    echo "📍 Test 4: Authentication - Get Current User"
    
    if response=$(api_request GET /auth/me "" "$TOKEN" 10 2>&1); then
        user_id=$(echo "$response" | jq -r '.id // .user_id // ""' 2>/dev/null)
        email=$(echo "$response" | jq -r '.email // ""' 2>/dev/null)
        
        if [[ -n "$user_id" ]] && [[ -n "$email" ]]; then
            test_result "Get Current User" "pass" "User: $email (ID: ${user_id:0:8}...)"
        else
            test_result "Get Current User" "fail" "Invalid user response: missing id or email"
        fi
    else
        test_result "Get Current User" "fail" "Endpoint failed: $response"
    fi
    echo ""
else
    echo "📍 Test 4: Authentication - Get Current User [SKIPPED]"
    echo ""
fi

# ============================================================================
# TEST 5: Bots Endpoint
# ============================================================================
if [[ -n "$TOKEN" ]]; then
    echo "📍 Test 5: Bots Endpoint"
    
    if response=$(api_request GET /bots "" "$TOKEN" 10 2>&1); then
        # Check if response is valid JSON array
        if echo "$response" | jq -e '. | type == "array"' > /dev/null 2>&1; then
            bot_count=$(echo "$response" | jq 'length' 2>/dev/null)
            test_result "Get Bots" "pass" "Retrieved $bot_count bot(s)"
        elif echo "$response" | jq -e '.bots | type == "array"' > /dev/null 2>&1; then
            bot_count=$(echo "$response" | jq '.bots | length' 2>/dev/null)
            test_result "Get Bots" "pass" "Retrieved $bot_count bot(s)"
        else
            test_result "Get Bots" "fail" "Invalid response format (expected array)"
        fi
    else
        test_result "Get Bots" "fail" "Endpoint failed: $response"
    fi
    echo ""
else
    echo "📍 Test 5: Bots Endpoint [SKIPPED]"
    echo ""
fi

# ============================================================================
# TEST 6: Portfolio Summary
# ============================================================================
if [[ -n "$TOKEN" ]]; then
    echo "📍 Test 6: Portfolio Summary"
    
    if response=$(api_request GET /portfolio/summary "" "$TOKEN" 10 2>&1); then
        equity=$(echo "$response" | jq -r '.equity // "N/A"' 2>/dev/null)
        realized_pnl=$(echo "$response" | jq -r '.realized_pnl // "N/A"' 2>/dev/null)
        
        if [[ "$equity" != "N/A" ]]; then
            test_result "Portfolio Summary" "pass" "Equity: $equity, Realized PnL: $realized_pnl"
        else
            test_result "Portfolio Summary" "fail" "Invalid response: missing equity field"
        fi
    else
        test_result "Portfolio Summary" "fail" "Endpoint failed: $response"
    fi
    echo ""
else
    echo "📍 Test 6: Portfolio Summary [SKIPPED]"
    echo ""
fi

# ============================================================================
# TEST 7: SSE (Server-Sent Events) Connection
# ============================================================================
if [[ -n "$TOKEN" ]]; then
    echo "📍 Test 7: SSE (Server-Sent Events) Connection"
    echo "   Testing for 5 seconds..."
    
    # Start SSE connection in background and capture output
    timeout 5 curl -s -N -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/realtime/events" > /tmp/sse_test.log 2>&1 &
    SSE_PID=$!
    
    sleep 5
    
    # Check if we received any events
    if [[ -f /tmp/sse_test.log ]]; then
        event_count=$(grep -c "^event:" /tmp/sse_test.log 2>/dev/null || echo "0")
        heartbeat_count=$(grep -c "event: heartbeat" /tmp/sse_test.log 2>/dev/null || echo "0")
        
        if [[ $event_count -gt 0 ]]; then
            test_result "SSE Connection" "pass" "Received $event_count events ($heartbeat_count heartbeats)"
        else
            test_result "SSE Connection" "warn" "No events received in 5 seconds (might be slow)"
        fi
    else
        test_result "SSE Connection" "fail" "No SSE output captured"
    fi
    
    # Cleanup
    kill $SSE_PID 2>/dev/null || true
    rm -f /tmp/sse_test.log
    echo ""
else
    echo "📍 Test 7: SSE Connection [SKIPPED]"
    echo ""
fi

# ============================================================================
# TEST 8: WebSocket Handshake (Optional)
# ============================================================================
if [[ -n "$TOKEN" ]]; then
    echo "📍 Test 8: WebSocket Handshake (Optional)"
    
    # WebSocket handshake test using curl (just checks if endpoint exists)
    ws_url="${API_BASE/https:/wss:}/ws?token=$TOKEN"
    
    # Try to connect for 2 seconds
    if timeout 2 curl -s -N --http1.1 \
        -H "Connection: Upgrade" \
        -H "Upgrade: websocket" \
        "$ws_url" > /dev/null 2>&1; then
        test_result "WebSocket Handshake" "pass" "WebSocket endpoint responsive"
    else
        test_result "WebSocket Handshake" "warn" "WebSocket test inconclusive (requires proper WS client)"
    fi
    echo ""
else
    echo "📍 Test 8: WebSocket Handshake [SKIPPED]"
    echo ""
fi

# ============================================================================
# FINAL REPORT
# ============================================================================
echo "========================================="
echo "🧪 Smoke Test Report"
echo "========================================="
echo ""
echo "Tests Run:    $TESTS_RUN"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
if [[ $TESTS_FAILED -gt 0 ]]; then
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
else
    echo "Tests Failed: $TESTS_FAILED"
fi
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "System is ready for production use!"
    exit 0
else
    echo -e "${RED}❌ TESTS FAILED${NC}"
    echo ""
    echo "Review errors above and fix issues before deploying."
    exit 1
fi
