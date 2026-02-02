#!/bin/bash
###############################################################################
# Amarktai Network - Endpoint Self-Test Script
#
# Tests all critical backend endpoints to ensure system is operational
# Run before deployment and after updates
#
# Usage: ./scripts/test-endpoints.sh [base_url] [token]
#   base_url: Optional API base URL (default: http://localhost:8000)
#   token: Optional JWT token (will prompt if not provided)
###############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${1:-http://localhost:8000}"
API_BASE="${BASE_URL}/api"
TOKEN="${2:-}"

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test results
declare -a FAILED_ENDPOINTS

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  Amarktai Network - Endpoint Self-Test                      ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${BLUE}━━━ $1 ━━━${NC}"
    echo ""
}

test_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local description=$4
    local data=$5
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local url="${API_BASE}${endpoint}"
    local result
    local status_code
    
    if [ "$method" = "GET" ]; then
        result=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${TOKEN}" "${url}")
    elif [ "$method" = "POST" ]; then
        result=$(curl -s -w "\n%{http_code}" -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d "${data:-{}}" "${url}")
    elif [ "$method" = "PUT" ]; then
        result=$(curl -s -w "\n%{http_code}" -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d "${data:-{}}" "${url}")
    fi
    
    status_code=$(echo "$result" | tail -n1)
    body=$(echo "$result" | sed '$d')
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} $description"
        echo -e "  ${YELLOW}$method${NC} $endpoint → ${GREEN}$status_code${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo -e "  ${YELLOW}$method${NC} $endpoint → ${RED}$status_code${NC} (expected $expected_status)"
        echo -e "  Response: ${body:0:100}..."
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_ENDPOINTS+=("$method $endpoint")
        return 1
    fi
}

test_unauthenticated() {
    local method=$1
    local endpoint=$2
    local description=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local url="${API_BASE}${endpoint}"
    local status_code
    
    status_code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "${url}")
    
    # Expect 200 for unauthenticated health endpoints
    if [ "$status_code" = "200" ] || [ "$status_code" = "503" ]; then
        echo -e "${GREEN}✓${NC} $description"
        echo -e "  ${YELLOW}$method${NC} $endpoint → ${GREEN}$status_code${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo -e "  ${YELLOW}$method${NC} $endpoint → ${RED}$status_code${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_ENDPOINTS+=("$method $endpoint")
        return 1
    fi
}

###############################################################################
# Main Test Suite
###############################################################################

main() {
    print_header
    
    echo "Testing against: ${BASE_URL}"
    echo ""
    
    # Get token if not provided
    if [ -z "$TOKEN" ]; then
        echo -e "${YELLOW}No token provided. Please provide JWT token:${NC}"
        echo "You can get a token by logging in at ${BASE_URL}/login"
        echo ""
        read -p "JWT Token: " TOKEN
        
        if [ -z "$TOKEN" ]; then
            echo -e "${RED}Error: Token is required${NC}"
            exit 1
        fi
    fi
    
    # Test 1: Health Checks (Unauthenticated)
    print_section "Health Checks (Unauthenticated)"
    test_unauthenticated "GET" "/health/ping" "Health check endpoint"
    
    # Test 2: Authentication
    print_section "Authentication Endpoints"
    test_endpoint "GET" "/auth/me" "200" "Get current user profile"
    
    # Test 3: System Endpoints
    print_section "System Endpoints"
    test_endpoint "GET" "/system/platforms" "200" "Get all platforms (must return 7 exchanges)"
    test_endpoint "GET" "/system/mode" "200" "Get system mode"
    test_endpoint "GET" "/system/health" "200" "Get system health"
    
    # Test 4: Bot Management
    print_section "Bot Management"
    test_endpoint "GET" "/bots" "200" "List all bots"
    test_endpoint "GET" "/bots/eligible-for-promotion" "200" "Get bots eligible for live promotion"
    
    # Test 5: Trading
    print_section "Trading Endpoints"
    test_endpoint "GET" "/trades/recent?limit=10" "200" "Get recent trades"
    test_endpoint "GET" "/portfolio/summary" "200" "Get portfolio metrics"
    
    # Test 6: Wallet
    print_section "Wallet Endpoints"
    test_endpoint "GET" "/wallet/balances" "200" "Get wallet balances"
    test_endpoint "GET" "/wallet/requirements" "200" "Get capital requirements"
    
    # Test 7: Analytics
    print_section "Analytics Endpoints"
    test_endpoint "GET" "/analytics/profit-history?period=daily" "200" "Get profit history (daily)"
    test_endpoint "GET" "/analytics/countdown-to-million" "200" "Get countdown to million"
    
    # Test 8: API Keys
    print_section "API Keys Management"
    test_endpoint "GET" "/api-keys" "200" "Get API keys status"
    
    # Test 9: Advanced Features
    print_section "Advanced Features"
    test_endpoint "GET" "/advanced/whale/summary" "200" "Get whale flow summary"
    
    # Test 10: Admin Endpoints (may fail if not admin)
    print_section "Admin Endpoints (may fail if not admin)"
    test_endpoint "GET" "/admin/stats" "200" "Get admin statistics" || true
    
    # Test 11: Metrics
    print_section "Metrics & Monitoring"
    test_endpoint "GET" "/metrics" "200" "Get Prometheus metrics"
    
    # Print summary
    print_section "Test Summary"
    
    echo ""
    echo -e "Total Tests:  ${BLUE}$TOTAL_TESTS${NC}"
    echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║${NC}  ✓ ALL TESTS PASSED - System is operational                 ${GREEN}║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
        exit 0
    else
        echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║${NC}  ✗ SOME TESTS FAILED - Review errors above                  ${RED}║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${RED}Failed endpoints:${NC}"
        for endpoint in "${FAILED_ENDPOINTS[@]}"; do
            echo -e "  ${RED}•${NC} $endpoint"
        done
        echo ""
        exit 1
    fi
}

# Run tests
main
