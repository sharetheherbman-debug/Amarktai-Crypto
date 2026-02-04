#!/bin/bash
# Deployment Smoke Test
# Verifies critical endpoints are responding correctly

set -e

echo "=========================================="
echo "Amarktai Deployment Smoke Test"
echo "=========================================="
echo ""

PASSED=0
FAILED=0

# Helper function for test results
pass() {
    echo "✅ PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "❌ FAIL: $1"
    FAILED=$((FAILED + 1))
}

# Test 1: Check port 8000 is listening
echo "Test 1: Checking if port 8000 is listening..."
if netstat -tuln 2>/dev/null | grep -q ":8000 " || ss -tuln 2>/dev/null | grep -q ":8000 "; then
    pass "Port 8000 is listening"
else
    fail "Port 8000 is NOT listening"
fi
echo ""

# Test 2: Curl /api/health/ping locally
echo "Test 2: Testing local health endpoint..."
if curl -f -s http://localhost:8000/api/health/ping > /dev/null 2>&1; then
    RESPONSE=$(curl -s http://localhost:8000/api/health/ping)
    if echo "$RESPONSE" | grep -q "pong"; then
        pass "Local health endpoint responds with 'pong'"
    else
        fail "Local health endpoint did not respond with 'pong': $RESPONSE"
    fi
else
    fail "Local health endpoint is not responding"
fi
echo ""

# Test 3: Curl https://amarktai.online/api/health/ping
echo "Test 3: Testing production health endpoint..."
if curl -f -s https://amarktai.online/api/health/ping > /dev/null 2>&1; then
    RESPONSE=$(curl -s https://amarktai.online/api/health/ping)
    if echo "$RESPONSE" | grep -q "pong"; then
        pass "Production health endpoint responds with 'pong'"
    else
        fail "Production health endpoint did not respond with 'pong': $RESPONSE"
    fi
else
    fail "Production health endpoint is not responding (may not be deployed yet)"
fi
echo ""

# Test 4: Check /api/platforms returns exactly 7 exchanges
echo "Test 4: Testing platforms endpoint returns 7 exchanges..."
PLATFORMS_RESPONSE=$(curl -s http://localhost:8000/api/platforms 2>/dev/null)
if [ $? -eq 0 ]; then
    # Count platforms using jq if available, otherwise use grep
    if command -v jq &> /dev/null; then
        PLATFORM_COUNT=$(echo "$PLATFORMS_RESPONSE" | jq '.platforms | length' 2>/dev/null)
    else
        # Fallback: count occurrences of exchange names
        PLATFORM_COUNT=$(echo "$PLATFORMS_RESPONSE" | grep -o '"luno"\|"binance"\|"kucoin"\|"bybit"\|"kraken"\|"bitget"\|"gate"' | wc -l)
    fi
    
    if [ "$PLATFORM_COUNT" = "7" ]; then
        pass "Platforms endpoint returns exactly 7 exchanges"
        
        # Verify the expected exchanges
        EXPECTED=("luno" "binance" "kucoin" "bybit" "kraken" "bitget" "gate")
        ALL_FOUND=true
        for exchange in "${EXPECTED[@]}"; do
            if ! echo "$PLATFORMS_RESPONSE" | grep -q "\"$exchange\""; then
                fail "Missing expected exchange: $exchange"
                ALL_FOUND=false
            fi
        done
        
        if [ "$ALL_FOUND" = true ]; then
            pass "All 7 expected exchanges are present (luno, binance, kucoin, bybit, kraken, bitget, gate)"
        fi
        
        # Check for forbidden exchanges
        FORBIDDEN=("valr" "ovex")
        for exchange in "${FORBIDDEN[@]}"; do
            if echo "$PLATFORMS_RESPONSE" | grep -qi "\"$exchange\""; then
                fail "Forbidden exchange found in response: $exchange"
            fi
        done
    else
        fail "Platforms endpoint returned $PLATFORM_COUNT exchanges, expected 7"
    fi
else
    fail "Platforms endpoint is not responding"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ All smoke tests passed!"
    exit 0
else
    echo "❌ Some smoke tests failed. Please review and fix."
    exit 1
fi
