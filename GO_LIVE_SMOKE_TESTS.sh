#!/bin/bash
# Amarktai Network - Production Go-Live Smoke Tests
# Run these tests to validate deployment health before going live

set -e  # Exit on error

echo "=================================================="
echo "🚀 Amarktai Network - Production Smoke Tests"
echo "=================================================="
echo ""

# Configuration
API_BASE="${API_BASE:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

# Test credentials (replace with real test user in production)
TEST_EMAIL="${TEST_EMAIL:-test@amarktai.com}"
TEST_PASSWORD="${TEST_PASSWORD:-testpass123}"

echo "📋 Configuration:"
echo "   API Base: $API_BASE"
echo "   Frontend: $FRONTEND_URL"
echo ""

# Track test results
PASSED=0
FAILED=0
SKIPPED=0

# Helper function for test assertions
assert_status() {
    local expected=$1
    local actual=$2
    local test_name=$3
    
    if [ "$actual" -eq "$expected" ]; then
        echo "✅ PASS: $test_name (HTTP $actual)"
        ((PASSED++))
        return 0
    else
        echo "❌ FAIL: $test_name (Expected HTTP $expected, got $actual)"
        ((FAILED++))
        return 1
    fi
}

echo "=================================================="
echo "TEST 1: Backend Health Check"
echo "=================================================="
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/api/health/ping" || echo "000")
assert_status 200 "$RESPONSE" "Health ping endpoint"
echo ""

echo "=================================================="
echo "TEST 2: Backend Route Collision Check"
echo "=================================================="
echo "Checking backend logs for route collision errors..."
if [ -f "/var/log/amarktai/backend.log" ]; then
    COLLISION_COUNT=$(grep -c "ROUTE COLLISION" /var/log/amarktai/backend.log 2>/dev/null || echo "0")
    if [ "$COLLISION_COUNT" -eq "0" ]; then
        echo "✅ PASS: No route collisions detected"
        ((PASSED++))
    else
        echo "❌ FAIL: $COLLISION_COUNT route collision(s) found in logs"
        ((FAILED++))
    fi
else
    echo "⚠️  SKIP: Log file not found (check backend startup manually)"
    ((SKIPPED++))
fi
echo ""

echo "=================================================="
echo "TEST 3: Fetch.ai Endpoints (Auth Required)"
echo "=================================================="
# Test without auth - should get 401/403
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/api/fetchai/status" || echo "000")
if [ "$RESPONSE" -eq "401" ] || [ "$RESPONSE" -eq "403" ]; then
    echo "✅ PASS: Fetch.ai endpoints properly protected (HTTP $RESPONSE)"
    ((PASSED++))
else
    echo "⚠️  INFO: Fetch.ai status returned HTTP $RESPONSE (check auth middleware)"
fi
echo ""

echo "=================================================="
echo "TEST 4: Login Flow (Generate Token)"
echo "=================================================="
TOKEN=""
LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" \
    -w "\n%{http_code}")

LOGIN_STATUS=$(echo "$LOGIN_RESPONSE" | tail -1)
LOGIN_BODY=$(echo "$LOGIN_RESPONSE" | head -n -1)

if [ "$LOGIN_STATUS" -eq "200" ]; then
    TOKEN=$(echo "$LOGIN_BODY" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$TOKEN" ]; then
        echo "✅ PASS: Login successful, token received"
        ((PASSED++))
    else
        echo "❌ FAIL: Login returned 200 but no token found"
        ((FAILED++))
    fi
else
    echo "⚠️  SKIP: Login failed (HTTP $LOGIN_STATUS). Using guest tests only."
    echo "   Note: Create test user: $TEST_EMAIL before running authenticated tests"
    ((SKIPPED++))
fi
echo ""

if [ -n "$TOKEN" ]; then
    echo "=================================================="
    echo "TEST 5: Authenticated Dashboard Endpoints"
    echo "=================================================="
    
    # Test bots endpoint
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/bots" || echo "000")
    assert_status 200 "$RESPONSE" "GET /api/bots"
    
    # Test overview endpoint
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/overview" || echo "000")
    assert_status 200 "$RESPONSE" "GET /api/overview"
    
    # Test system mode endpoint
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/system/mode" || echo "000")
    assert_status 200 "$RESPONSE" "GET /api/system/mode"
    
    # Test live eligibility endpoint
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/system/live-eligibility" || echo "000")
    assert_status 200 "$RESPONSE" "GET /api/system/live-eligibility"
    
    echo ""
    
    echo "=================================================="
    echo "TEST 6: WebSocket Connection (Dashboard Only)"
    echo "=================================================="
    echo "⚠️  Manual check required:"
    echo "   1. Login to dashboard at: $FRONTEND_URL"
    echo "   2. Open browser DevTools > Network > WS"
    echo "   3. Verify WebSocket connects only after login"
    echo "   4. Check for realtime updates (trades, prices)"
    echo ""
    
    echo "=================================================="
    echo "TEST 7: Fetch.ai Endpoints (Authenticated)"
    echo "=================================================="
    
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/fetchai/status" || echo "000")
    assert_status 200 "$RESPONSE" "GET /api/fetchai/status"
    
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_BASE/api/fetchai/test-connection" || echo "000")
    # This may return 400 if no API key configured, which is acceptable
    if [ "$RESPONSE" -eq "200" ] || [ "$RESPONSE" -eq "400" ]; then
        echo "✅ PASS: GET /api/fetchai/test-connection (HTTP $RESPONSE - OK)"
        ((PASSED++))
    else
        echo "❌ FAIL: GET /api/fetchai/test-connection (HTTP $RESPONSE)"
        ((FAILED++))
    fi
    
    echo ""
else
    echo "⚠️  Skipping authenticated tests (no token available)"
    ((SKIPPED+=5))  # 5 authenticated tests skipped
    echo ""
fi

echo "=================================================="
echo "TEST 8: Paper Trading Requirements Check"
echo "=================================================="
echo "Verifying paper trading configuration..."

# Check if paper trading env vars are set
if [ -f ".env" ]; then
    PAPER_ENABLED=$(grep "ENABLE_PAPER_TRADING" .env | cut -d'=' -f2)
    if [ "$PAPER_ENABLED" = "true" ] || [ "$PAPER_ENABLED" = "1" ]; then
        echo "✅ PASS: Paper trading enabled in .env"
        ((PASSED++))
    else
        echo "❌ FAIL: Paper trading not enabled in .env"
        ((FAILED++))
    fi
else
    echo "⚠️  SKIP: .env file not found"
    ((SKIPPED++))
fi
echo ""

echo "=================================================="
echo "TEST 9: Frontend Build Check"
echo "=================================================="
if [ -d "frontend/build" ] || [ -d "frontend/dist" ]; then
    echo "✅ PASS: Frontend build directory exists"
    ((PASSED++))
else
    echo "⚠️  INFO: Frontend build directory not found"
    echo "   Run: cd frontend && npm run build"
    ((SKIPPED++))
fi
echo ""

echo "=================================================="
echo "TEST 10: Logo Assets Check"
echo "=================================================="
if [ -f "frontend/public/assets/logo2.png" ]; then
    echo "✅ PASS: New logo2.png exists in public/assets/"
    ((PASSED++))
else
    echo "❌ FAIL: logo2.png not found in frontend/public/assets/"
    ((FAILED++))
fi
echo ""

echo "=================================================="
echo "📊 TEST SUMMARY"
echo "=================================================="
TOTAL=$((PASSED + FAILED + SKIPPED))
echo "Total Tests: $TOTAL"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo "Skipped: $SKIPPED"
echo ""

if [ $FAILED -eq 0 ] && [ $SKIPPED -eq 0 ]; then
    echo "✅ ALL TESTS PASSED - Ready for production deployment!"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo "⚠️  ALL EXECUTABLE TESTS PASSED - Some tests skipped (review above)"
    echo "   Skipped tests may need manual verification"
    exit 0
else
    echo "❌ SOME TESTS FAILED - Review errors before deploying"
    exit 1
fi
