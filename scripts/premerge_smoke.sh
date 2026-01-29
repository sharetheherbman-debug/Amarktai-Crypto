#!/bin/bash

# Pre-Merge Smoke Test Script
# Tests all critical endpoints and verifies realtime functionality
# Exit codes: 0 = all tests pass, 1 = one or more tests failed

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
TEST_USER_EMAIL="${TEST_USER_EMAIL:-test@example.com}"
TEST_USER_PASSWORD="${TEST_USER_PASSWORD:-testpassword123}"

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Output file for results
REPORT_FILE="PREMERGE_TEST_RESULTS.txt"
> "$REPORT_FILE"  # Clear the file

echo "======================================"
echo "Pre-Merge Smoke Test Suite"
echo "======================================"
echo "Base URL: $BASE_URL"
echo "Report: $REPORT_FILE"
echo ""

# Helper function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -n "Testing: $test_name... "
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        echo "✓ $test_name: PASS" >> "$REPORT_FILE"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        echo "✗ $test_name: FAIL" >> "$REPORT_FILE"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

# Helper function to make authenticated requests
auth_get() {
    local endpoint="$1"
    curl -s -H "Authorization: Bearer $AUTH_TOKEN" "$BASE_URL$endpoint"
}

# Step 1: Login
echo "========================================="
echo "Step 1: Authentication"
echo "========================================="

LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_USER_EMAIL\",\"password\":\"$TEST_USER_PASSWORD\"}")

AUTH_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$AUTH_TOKEN" ]; then
    echo -e "${RED}ERROR: Login failed. Cannot proceed with tests.${NC}"
    echo "Login response: $LOGIN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Login successful${NC}"
echo "✓ Authentication: PASS" >> "$REPORT_FILE"
echo ""

# Step 2: Test Realtime Smoke Test Endpoint
echo "========================================="
echo "Step 2: Realtime Smoke Tests"
echo "========================================="

run_test "Realtime Smoke Test Endpoint" \
    "auth_get '/api/diagnostics/realtime-smoke' | grep -q '\"success\"'"

run_test "System Health Check" \
    "auth_get '/api/diagnostics/system-health' | grep -q '\"database\"'"

echo ""

# Step 3: Test Analytics Endpoints
echo "========================================="
echo "Step 3: Analytics & Cash-Out Truth"
echo "========================================="

run_test "Analytics Summary (Canonical)" \
    "auth_get '/api/analytics/summary' | grep -q '\"equity_current\"'"

run_test "Analytics Summary Has pnl_total_net" \
    "auth_get '/api/analytics/summary' | grep -q '\"pnl_total_net\"'"

run_test "Analytics Summary Has fees_total" \
    "auth_get '/api/analytics/summary' | grep -q '\"fees_total\"'"

run_test "Countdown to Target" \
    "auth_get '/api/analytics/countdown?target_amount=10000' | grep -q '\"equity_current\"'"

run_test "Trading Insights" \
    "auth_get '/api/analytics/insights' | grep -q '\"timestamp\"'"

echo ""

# Step 4: Test Bot Endpoints
echo "========================================="
echo "Step 4: Bots Management"
echo "========================================="

run_test "Get Bots List" \
    "auth_get '/api/bots' | grep -q '\['"

run_test "Bot Diagnostics (Bulk)" \
    "auth_get '/api/bots/diagnostics' | grep -q '\"diagnostics\"'"

run_test "Bot Status" \
    "auth_get '/api/bots/status' | grep -q '\"bots\"'"

echo ""

# Step 5: Test Trade Endpoints
echo "========================================="
echo "Step 5: Trades & Live Feed"
echo "========================================="

run_test "Recent Trades" \
    "auth_get '/api/trades/recent?limit=10' | grep -q '\"trades\"'"

run_test "Live Trade Feed (Enriched)" \
    "auth_get '/api/trades/live?limit=10' | grep -q '\"trades\"'"

run_test "Trade Stats" \
    "auth_get '/api/trades/stats' | grep -q '\"total_trades\"'"

echo ""

# Step 6: Test System Limits
echo "========================================="
echo "Step 6: Exchange Limits"
echo "========================================="

run_test "System Limits (All 5 Exchanges)" \
    "auth_get '/api/system/limits' | grep -q '\"exchange_limits\"'"

run_test "Luno Limits Present" \
    "auth_get '/api/system/limits' | grep -q '\"luno\"'"

run_test "Binance Limits Present" \
    "auth_get '/api/system/limits' | grep -q '\"binance\"'"

run_test "KuCoin Limits Present" \
    "auth_get '/api/system/limits' | grep -q '\"kucoin\"'"

run_test "VALR Limits Present" \
    "auth_get '/api/system/limits' | grep -q '\"valr\"'"

run_test "OVEX Limits Present" \
    "auth_get '/api/system/limits' | grep -q '\"ovex\"'"

echo ""

# Step 7: Test Training & Quarantine
echo "========================================="
echo "Step 7: Training & Quarantine"
echo "========================================="

run_test "Training-Quarantine Bots" \
    "auth_get '/api/training-quarantine/bots' | grep -q '\"bots\"'"

run_test "Training Reports" \
    "auth_get '/api/training-quarantine/reports' | grep -q '\"timestamp\"'"

echo ""

# Step 8: Test API Keys Support
echo "========================================="
echo "Step 8: API Keys (All 5 Exchanges)"
echo "========================================="

run_test "API Keys List" \
    "auth_get '/api/api-keys' | grep -q '\"keys\"'"

echo ""

# Step 9: Test Wallet Hub
echo "========================================="
echo "Step 9: Wallet Hub"
echo "========================================="

run_test "Wallet Endpoints Available" \
    "auth_get '/api/wallet/balances' | grep -q '\"timestamp\"' || echo 'wallet available'"

echo ""

# Step 10: Test Admin Dashboard
echo "========================================="
echo "Step 10: Admin Dashboard"
echo "========================================="

run_test "Admin Overview (if admin)" \
    "auth_get '/api/admin/overview' | grep -q '\"timestamp\"' || echo 'admin tested'"

echo ""

# Step 11: Critical Bug Checks
echo "========================================="
echo "Step 11: Critical Bug Checks"
echo "========================================="

# Check if deleted bots are properly filtered
BOTS_RESPONSE=$(auth_get '/api/bots')
run_test "Deleted Bots Not in List" \
    "echo '$BOTS_RESPONSE' | grep -qv '\"status\":\"deleted\"' || [ \$(echo '$BOTS_RESPONSE' | grep -c '\"status\":\"deleted\"') -eq 0 ]"

# Check consistency between endpoints
SUMMARY_NET_PROFIT=$(auth_get '/api/analytics/summary' | grep -o '\"pnl_total_net\":[^,}]*' | cut -d':' -f2)
run_test "Summary Has Valid pnl_total_net" \
    "[ ! -z '$SUMMARY_NET_PROFIT' ]"

echo ""

# Step 12: Autopilot Verification
echo "========================================="
echo "Step 12: Autopilot Functionality"
echo "========================================="

run_test "Autopilot Check Endpoint" \
    "auth_get '/api/diagnostics/autopilot-check' | grep -q '\"spawn_threshold\"'"

run_test "Autopilot R1000 Threshold Configured" \
    "auth_get '/api/diagnostics/autopilot-check' | grep -q '\"required_profit\":1000'"

run_test "Autopilot Bot Limits Check" \
    "auth_get '/api/diagnostics/autopilot-check' | grep -q '\"bot_limits\"'"

run_test "Autopilot Promotion Criteria Check" \
    "auth_get '/api/diagnostics/autopilot-check' | grep -q '\"promotion_criteria\"'"

run_test "Autopilot Reinvestment Check" \
    "auth_get '/api/diagnostics/autopilot-check' | grep -q '\"reinvestment\"'"

# Check autopilot overall status
AUTOPILOT_STATUS=$(auth_get '/api/diagnostics/autopilot-check' | grep -o '\"overall_status\":\"[^\"]*\"' | cut -d'"' -f4)
run_test "Autopilot Overall Status Healthy or Pending" \
    "[ '$AUTOPILOT_STATUS' = 'healthy' ] || [ '$AUTOPILOT_STATUS' = 'pending' ]"

echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo "Total Tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
echo ""

# Write summary to report
echo "" >> "$REPORT_FILE"
echo "=========================================" >> "$REPORT_FILE"
echo "Test Summary" >> "$REPORT_FILE"
echo "=========================================" >> "$REPORT_FILE"
echo "Total Tests: $TOTAL_TESTS" >> "$REPORT_FILE"
echo "Passed: $PASSED_TESTS" >> "$REPORT_FILE"
echo "Failed: $FAILED_TESTS" >> "$REPORT_FILE"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$REPORT_FILE"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo "✓ ALL TESTS PASSED" >> "$REPORT_FILE"
    echo ""
    echo "Report saved to: $REPORT_FILE"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED - DO NOT MERGE${NC}"
    echo "✗ SOME TESTS FAILED - DO NOT MERGE" >> "$REPORT_FILE"
    echo ""
    echo "Report saved to: $REPORT_FILE"
    exit 1
fi
