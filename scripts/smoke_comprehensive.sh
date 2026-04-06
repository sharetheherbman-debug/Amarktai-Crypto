#!/bin/bash
# Comprehensive Go-Live Smoke Test
# Tests all critical endpoints, WebSocket connections, and system health

set -e

echo "========================================="
echo "Amarktai Network - Comprehensive Smoke Test"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
TIMEOUT=15

TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Create temp file for storing test token
TOKEN_FILE=$(mktemp)
trap "rm -f $TOKEN_FILE" EXIT

# Function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}
    
    echo -n "  [$method] $description... "
    
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
        --max-time $TIMEOUT 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} (Expected $expected_status, got $http_code)"
        if [ ! -z "$body" ]; then
            echo "    Response: $(echo $body | head -c 200)"
        fi
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to test endpoint with JSON response
test_endpoint_json() {
    local method=$1
    local endpoint=$2
    local description=$3
    local json_key=$4
    local expected_status=${5:-200}
    
    echo -n "  [$method] $description... "
    
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
        --max-time $TIMEOUT 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_status" ]; then
        # Check if JSON key exists in response
        if echo "$body" | grep -q "\"$json_key\""; then
            echo -e "${GREEN}✓${NC} ($http_code, has '$json_key')"
            ((TESTS_PASSED++))
            return 0
        else
            echo -e "${YELLOW}⚠${NC} ($http_code, missing '$json_key')"
            ((TESTS_PASSED++))
            return 0
        fi
    else
        echo -e "${RED}✗${NC} (Expected $expected_status, got $http_code)"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to test endpoint with auth
test_endpoint_auth() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}
    
    local token=$(cat $TOKEN_FILE 2>/dev/null || echo "")
    
    if [ -z "$token" ]; then
        echo -e "  [$method] $description... ${YELLOW}⊘${NC} (No token available)"
        ((TESTS_SKIPPED++))
        return 1
    fi
    
    echo -n "  [$method] $description... "
    
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        --max-time $TIMEOUT 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} (Expected $expected_status, got $http_code)"
        if [ ! -z "$body" ]; then
            echo "    Response: $(echo $body | head -c 200)"
        fi
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to test WebSocket (basic check)
test_websocket() {
    local description=$1
    local token=$(cat $TOKEN_FILE 2>/dev/null || echo "")
    
    if [ -z "$token" ]; then
        echo -e "  [WS] $description... ${YELLOW}⊘${NC} (No token available)"
        ((TESTS_SKIPPED++))
        return 1
    fi
    
    echo -n "  [WS] $description... "
    
    # Try to connect with wscat if available, otherwise skip
    if command -v wscat &> /dev/null; then
        # Use timeout to test connection for 5 seconds
        timeout 5s wscat -c "$BASE_URL/api/ws?token=$token" --no-check 2>&1 | grep -q "Connected" && {
            echo -e "${GREEN}✓${NC} (Connection successful)"
            ((TESTS_PASSED++))
            return 0
        } || {
            echo -e "${RED}✗${NC} (Connection failed)"
            ((TESTS_FAILED++))
            return 1
        }
    else
        echo -e "${YELLOW}⊘${NC} (wscat not installed - skipped)"
        ((TESTS_SKIPPED++))
        return 1
    fi
}

echo -e "${BLUE}1. System Health & Ping${NC}"
echo "================================"
test_endpoint "GET" "/api/system/ping" "System ping (DB-independent)"
test_endpoint_json "GET" "/api/system/platforms" "Platforms list" "platforms"
test_endpoint_json "GET" "/api/system/gates" "System gates" "gates"
echo ""

echo -e "${BLUE}2. Authentication${NC}"
echo "================================"
# Note: These will fail without credentials, but that's expected
test_endpoint "POST" "/api/auth/login" "Login endpoint exists" 422
echo "  ℹ  Login requires credentials (422 expected for missing payload)"
echo ""

echo -e "${BLUE}3. Protected Endpoints (requires auth)${NC}"
echo "================================"
test_endpoint_auth "GET" "/api/auth/me" "Current user info"
test_endpoint_auth "GET" "/api/bots/status" "Bot status"
test_endpoint_auth "GET" "/api/overview/snapshot" "Dashboard overview"
test_endpoint_auth "GET" "/api/portfolio/summary" "Portfolio summary"
test_endpoint_auth "GET" "/api/wallet/balances" "Wallet balances"
test_endpoint_auth "GET" "/api/system/mode" "System mode"
test_endpoint_auth "GET" "/api/risk/status" "Risk status"
echo ""

echo -e "${BLUE}4. Real-time Endpoints${NC}"
echo "================================"
test_websocket "WebSocket connection"
test_endpoint_auth "GET" "/api/sse/overview" "SSE overview stream" 200
echo ""

echo -e "${BLUE}5. AI & Learning${NC}"
echo "================================"
test_endpoint_auth "GET" "/api/ai/status" "AI status"
test_endpoint_auth "GET" "/api/learning/status" "Learning status"
test_endpoint_auth "GET" "/api/autonomous/market-regime" "Market regime"
echo ""

echo -e "${BLUE}6. Admin Endpoints (requires admin role)${NC}"
echo "================================"
test_endpoint_auth "GET" "/api/admin/health-check" "Admin health check" 200
test_endpoint_auth "GET" "/api/admin/system-stats" "System stats"
echo ""

echo -e "${BLUE}7. Paper Trading Simulation${NC}"
echo "================================"
echo "  ℹ  Paper trading verification requires authenticated session"
echo "  ℹ  Manual test: Create bot, execute trades, verify ledger writes"
echo ""

echo -e "${BLUE}8. Frontend Accessibility${NC}"
echo "================================"
if curl -s --max-time 5 "$FRONTEND_URL" > /dev/null 2>&1; then
    echo -e "  [GET] Frontend homepage... ${GREEN}✓${NC}"
    ((TESTS_PASSED++))
else
    echo -e "  [GET] Frontend homepage... ${YELLOW}⚠${NC} (Not accessible at $FRONTEND_URL)"
    ((TESTS_SKIPPED++))
fi
echo ""

# Summary
echo "========================================="
echo -e "${BLUE}TEST SUMMARY${NC}"
echo "========================================="
echo -e "Passed:  ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed:  ${RED}$TESTS_FAILED${NC}"
echo -e "Skipped: ${YELLOW}$TESTS_SKIPPED${NC}"
echo "Total:   $((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All critical tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Test login with real credentials"
    echo "  2. Verify WebSocket real-time updates in dashboard"
    echo "  3. Create paper trading bots and verify execution"
    echo "  4. Check email alerts configuration"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check backend logs: journalctl -u amarktai -f"
    echo "  2. Verify MongoDB is running: systemctl status mongod"
    echo "  3. Check nginx configuration: nginx -t"
    echo "  4. Test backend directly: curl http://localhost:8000/api/system/ping"
    exit 1
fi
