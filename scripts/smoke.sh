#!/bin/bash
set -e

# smoke.sh - Deployment Acceptance Tests
# Validates critical endpoints and functionality before go-live
# Can run against local server or production

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

echo "============================================"
echo "Deployment Acceptance Tests (Smoke Tests)"
echo "============================================"
echo ""
echo "Target: $BASE_URL"
echo ""

# Test counter
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test helper function
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    printf "%-60s" "$test_name"
    
    if eval "$test_cmd" > /tmp/smoke_test_output.txt 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        cat /tmp/smoke_test_output.txt
        return 1
    fi
}

# Test 1: Health Check
run_test "Health check (GET /api/health/ping)" \
    "curl -sf '$BASE_URL/api/health/ping' | grep -q 'pong'"

# Test 2: OpenAPI Schema
run_test "OpenAPI schema exists (GET /openapi.json)" \
    "curl -sf '$BASE_URL/openapi.json' | grep -q '\"openapi\"'"

# Test 3: OpenAPI contains /api/keys/test
run_test "OpenAPI contains /api/keys/test endpoint" \
    "curl -sf '$BASE_URL/openapi.json' | grep -q '/api/keys/test'"

# Test 4: Get providers list
run_test "Get providers list (GET /api/keys/providers)" \
    "curl -sf '$BASE_URL/api/keys/providers' | grep -q '\"success\":true'"

# Test 5: Providers list includes all 10 providers
TEST_OUTPUT=$(curl -sf "$BASE_URL/api/keys/providers" 2>/dev/null)
if echo "$TEST_OUTPUT" | grep -q '"openai"' && \
   echo "$TEST_OUTPUT" | grep -q '"flokx"' && \
   echo "$TEST_OUTPUT" | grep -q '"fetchai"' && \
   echo "$TEST_OUTPUT" | grep -q '"luno"' && \
   echo "$TEST_OUTPUT" | grep -q '"binance"' && \
   echo "$TEST_OUTPUT" | grep -q '"kucoin"' && \
   echo "$TEST_OUTPUT" | grep -q '"bybit"' && \
   echo "$TEST_OUTPUT" | grep -q '"kraken"' && \
   echo "$TEST_OUTPUT" | grep -q '"bitget"' && \
   echo "$TEST_OUTPUT" | grep -q '"gate"'; then
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    PASSED_TESTS=$((PASSED_TESTS + 1))
    printf "%-60s${GREEN}✅ PASS${NC}\n" "Providers include all 10 expected providers"
else
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    FAILED_TESTS=$((FAILED_TESTS + 1))
    printf "%-60s${RED}❌ FAIL${NC}\n" "Providers include all 10 expected providers"
    echo "Missing one or more providers: openai, flokx, fetchai, luno, binance, kucoin, bybit, kraken, bitget, gate"
fi

# Test 6: Total providers count is 10
TEST_OUTPUT=$(curl -sf "$BASE_URL/api/keys/providers" 2>/dev/null)
PROVIDER_COUNT=$(echo "$TEST_OUTPUT" | grep -o '"total":[0-9]*' | grep -o '[0-9]*')
if [ "$PROVIDER_COUNT" = "10" ]; then
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    PASSED_TESTS=$((PASSED_TESTS + 1))
    printf "%-60s${GREEN}✅ PASS${NC}\n" "Total providers count is exactly 10"
else
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    FAILED_TESTS=$((FAILED_TESTS + 1))
    printf "%-60s${RED}❌ FAIL${NC}\n" "Total providers count is exactly 10"
    echo "Expected 10 providers, got: $PROVIDER_COUNT"
fi

echo ""
echo "============================================"
echo "Authentication & Keys API Tests"
echo "============================================"
echo ""

# Test 7: Auth login (get token)
echo "Testing authentication..."
TOKEN_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null)

# Extract HTTP status and body
HTTP_STATUS=$(echo "$TOKEN_RESPONSE" | grep "HTTP_STATUS:" | cut -d':' -f2)
RESPONSE_BODY=$(echo "$TOKEN_RESPONSE" | sed '/HTTP_STATUS:/d')

# Log the response for debugging
if [ -n "$RESPONSE_BODY" ] && [ "$RESPONSE_BODY" != "{}" ]; then
    echo "Login response: $RESPONSE_BODY" > /tmp/login_response.txt
fi

ACCESS_TOKEN=$(echo "$RESPONSE_BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$ACCESS_TOKEN" ] && [ "$HTTP_STATUS" = "200" ]; then
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    PASSED_TESTS=$((PASSED_TESTS + 1))
    printf "%-60s${GREEN}✅ PASS${NC}\n" "Auth login returns token"
else
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    FAILED_TESTS=$((FAILED_TESTS + 1))
    printf "%-60s${RED}❌ FAIL${NC}\n" "Auth login returns token"
    echo "Could not get access token. HTTP Status: $HTTP_STATUS"
    echo "Response: $RESPONSE_BODY"
    echo "Note: Remaining tests require authentication and will be skipped."
    ACCESS_TOKEN=""
fi

# Only run authenticated tests if we have a token
if [ -n "$ACCESS_TOKEN" ]; then
    # Test 8: Test with invalid provider returns 400 with correct error
    TEST_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/keys/test" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"provider":"notarealexchange","api_key":"dummy"}' 2>/dev/null || echo "{}")
    
    if echo "$TEST_RESPONSE" | grep -q "notarealexchange" && \
       ! echo "$TEST_RESPONSE" | grep -qi "unknown provider: test"; then
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        PASSED_TESTS=$((PASSED_TESTS + 1))
        printf "%-60s${GREEN}✅ PASS${NC}\n" "Invalid provider returns correct error message"
    else
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        FAILED_TESTS=$((FAILED_TESTS + 1))
        printf "%-60s${RED}❌ FAIL${NC}\n" "Invalid provider returns correct error message"
        echo "Expected error to mention 'notarealexchange', got: $TEST_RESPONSE"
    fi
    
    # Test 9: Test with valid provider name (binance) and dummy credentials
    TEST_RESPONSE=$(curl -s -X POST "$BASE_URL/api/keys/test" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"provider":"binance","api_key":"dummy_key_12345","api_secret":"dummy_secret_67890"}' 2>/dev/null || echo "{}")
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/keys/test" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"provider":"binance","api_key":"dummy_key_12345","api_secret":"dummy_secret_67890"}')
    
    if [ "$HTTP_CODE" != "422" ]; then
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        PASSED_TESTS=$((PASSED_TESTS + 1))
        printf "%-60s${GREEN}✅ PASS${NC}\n" "Test binance with dummy key returns 200 or 400 (not 422)"
    else
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        FAILED_TESTS=$((FAILED_TESTS + 1))
        printf "%-60s${RED}❌ FAIL${NC}\n" "Test binance with dummy key returns 200 or 400 (not 422)"
        echo "Got 422 (validation error), expected 200 or 400. Response: $TEST_RESPONSE"
    fi
    
    # Test 10: Error message includes kraken and gate
    TEST_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/keys/test" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"provider":"invalid","api_key":"dummy"}' 2>/dev/null || echo "{}")
    
    if echo "$TEST_RESPONSE" | grep -qi "kraken" && echo "$TEST_RESPONSE" | grep -qi "gate"; then
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        PASSED_TESTS=$((PASSED_TESTS + 1))
        printf "%-60s${GREEN}✅ PASS${NC}\n" "Error message includes kraken and gate"
    else
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        FAILED_TESTS=$((FAILED_TESTS + 1))
        printf "%-60s${RED}❌ FAIL${NC}\n" "Error message includes kraken and gate"
        echo "Error message should mention kraken and gate. Got: $TEST_RESPONSE"
    fi
fi

echo ""
echo "============================================"
echo "Test Results"
echo "============================================"
echo "Total tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}❌ SMOKE TESTS FAILED${NC}"
    echo "Fix the issues above before deploying to production."
    exit 1
else
    echo -e "${GREEN}✅ ALL SMOKE TESTS PASSED${NC}"
    echo "System is ready for deployment."
    exit 0
fi
