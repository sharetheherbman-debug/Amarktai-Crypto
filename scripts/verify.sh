#!/bin/bash
# Verification Script - Run after deployment
# Tests health, login, diagnostics, emergency stop, wallet status

set -e

echo "========================================="
echo "Amarktai Network - Post-Deployment Verification"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMEOUT=10

TESTS_PASSED=0
TESTS_FAILED=0

# Function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}
    
    echo -n "Testing: $description... "
    
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" --max-time $TIMEOUT 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        ((TESTS_PASSED++))
        return 0
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
    local token=$4
    local expected_status=${5:-200}
    
    echo -n "Testing: $description... "
    
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
        -H "Authorization: Bearer $token" \
        --max-time $TIMEOUT 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n 1)
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} (Expected $expected_status, got $http_code)"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "1. Basic Health Checks"
echo "----------------------"
test_endpoint "GET" "/health" "Health endpoint"
test_endpoint "GET" "/api/health" "API health endpoint"
test_endpoint "GET" "/" "Root endpoint"
echo ""

echo "2. Authentication Endpoints"
echo "---------------------------"
test_endpoint "POST" "/api/auth/register" "Registration endpoint" "200|400|422"
test_endpoint "POST" "/api/auth/login" "Login endpoint" "200|401|422"
echo ""

echo "3. Public API Endpoints"
echo "-----------------------"
test_endpoint "GET" "/api/system/status" "System status"
test_endpoint "GET" "/api/system/health" "System health"
test_endpoint "GET" "/api/build-info" "Build info"
echo ""

echo "4. Diagnostics Endpoints (may require auth)"
echo "--------------------------------------------"
test_endpoint "GET" "/api/diagnostics/system-health" "System health diagnostics"
test_endpoint "GET" "/api/diagnostics/paper-status" "Paper trading status"
test_endpoint "GET" "/api/diagnostics/autopilot-check" "Autopilot check"
test_endpoint "GET" "/api/diagnostics/auto-spawn" "Auto-spawn diagnostics"
echo ""

echo "5. Emergency Stop Endpoints"
echo "---------------------------"
test_endpoint "GET" "/api/emergency-stop/status" "Emergency stop status"
echo ""

echo "6. Wallet Endpoints (may require auth)"
echo "---------------------------------------"
test_endpoint "GET" "/api/wallet/balance/summary" "Wallet balance summary" "200|401"
test_endpoint "GET" "/api/wallet/transfers" "Wallet transfers list" "200|401"
test_endpoint "GET" "/api/wallet/health" "Wallet health" "200"
echo ""

echo "7. Wallet Diagnostics"
echo "---------------------"
test_endpoint "GET" "/api/diagnostics/wallet-status" "Wallet status diagnostics" "200"
test_endpoint "GET" "/api/diagnostics/transfers" "Transfer diagnostics" "200"
test_endpoint "GET" "/api/diagnostics/email-status" "Email service status" "200"
echo ""

echo "8. Real-time Features"
echo "---------------------"
test_endpoint "GET" "/api/diagnostics/realtime" "Real-time diagnostics"
echo ""

echo "9. Advanced Features"
echo "--------------------"
test_endpoint "GET" "/api/execution-quality/status" "Execution quality status" "200|404"
test_endpoint "GET" "/api/treasury/status" "Treasury status" "200|404"
test_endpoint "GET" "/api/diagnostics/regime" "Market regime" "200|404"
echo ""

# Summary
echo ""
echo "========================================="
echo "Verification Summary"
echo "========================================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "Deployment verified successfully."
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed${NC}"
    echo ""
    echo "Review failed tests and check logs."
    exit 1
fi
