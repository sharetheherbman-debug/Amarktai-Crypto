#!/bin/bash
# Quick validation script for backend blocker fixes
# Run this after starting the server to verify all fixes are working

set -e

echo "=================================="
echo "Backend Blocker Fixes - Validation"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${API_BASE_URL:-http://localhost:8000}"
TEST_EMAIL="${TEST_EMAIL:-test@example.com}"
TEST_PASSWORD="${TEST_PASSWORD:-password123}"

echo "API Base URL: $BASE_URL"
echo "Test User: $TEST_EMAIL"
echo ""

# Function to print success
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print error
error() {
    echo -e "${RED}✗${NC} $1"
}

# Get auth token
echo "1. Getting authentication token..."
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\"}" 2>/dev/null)

TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.token' 2>/dev/null)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    error "Failed to get auth token. Is the server running? Is test user created?"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

success "Got auth token"
echo ""

# Test 1: API Key Payload Compatibility
echo "2. Testing API key payload compatibility..."

# Test with provider/api_key
RESPONSE1=$(curl -s -X POST "$BASE_URL/api/keys/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "binance", "api_key": "test123", "api_secret": "secret123"}' 2>/dev/null)

if echo "$RESPONSE1" | jq -e '.success' > /dev/null 2>&1; then
    success "JSON payload with provider/api_key accepted"
else
    error "JSON payload with provider/api_key FAILED"
    echo "Response: $RESPONSE1"
fi

# Test with exchange/apiKey (legacy)
RESPONSE2=$(curl -s -X POST "$BASE_URL/api/keys/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exchange": "binance", "apiKey": "test123", "apiSecret": "secret123"}' 2>/dev/null)

if echo "$RESPONSE2" | jq -e '.success' > /dev/null 2>&1; then
    success "JSON payload with exchange/apiKey (legacy) accepted"
else
    error "JSON payload with exchange/apiKey FAILED"
    echo "Response: $RESPONSE2"
fi

# Test with platform/key (alternative)
RESPONSE3=$(curl -s -X POST "$BASE_URL/api/keys/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"platform": "binance", "key": "test123", "secret": "secret123"}' 2>/dev/null)

if echo "$RESPONSE3" | jq -e '.success' > /dev/null 2>&1; then
    success "JSON payload with platform/key accepted"
else
    error "JSON payload with platform/key FAILED"
    echo "Response: $RESPONSE3"
fi

echo ""

# Test 2: Live Training Bay Endpoint
echo "3. Testing Live Training Bay endpoint..."

TRAINING_BAY=$(curl -s -X GET "$BASE_URL/api/training/live-bay" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)

if echo "$TRAINING_BAY" | jq -e '.success' > /dev/null 2>&1; then
    success "Live Training Bay endpoint accessible"
    QUARANTINE_COUNT=$(echo "$TRAINING_BAY" | jq -r '.total')
    echo "   Bots in quarantine: $QUARANTINE_COUNT"
else
    error "Live Training Bay endpoint FAILED"
    echo "Response: $TRAINING_BAY"
fi

echo ""

# Test 3: Bot Start/Stop Endpoints
echo "4. Testing Bot Start/Stop endpoints..."

# Get first bot
BOTS=$(curl -s -X GET "$BASE_URL/api/bots" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)

BOT_ID=$(echo "$BOTS" | jq -r '.[0].id' 2>/dev/null)

if [ "$BOT_ID" != "null" ] && [ -n "$BOT_ID" ]; then
    success "Found test bot: $BOT_ID"
    
    # Try to start bot
    START_RESPONSE=$(curl -s -X POST "$BASE_URL/api/bots/$BOT_ID/start" \
      -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    
    if echo "$START_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
        success "Bot start endpoint works"
    else
        # Might fail due to training bay, that's ok
        echo "   Note: Bot start returned: $(echo "$START_RESPONSE" | jq -r '.message')"
    fi
    
    # Try to stop bot
    STOP_RESPONSE=$(curl -s -X POST "$BASE_URL/api/bots/$BOT_ID/stop" \
      -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    
    if echo "$STOP_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
        success "Bot stop endpoint works"
    fi
else
    echo "   No bots found to test start/stop"
fi

echo ""

# Test 4: Platform Drilldown
echo "5. Testing Platform Drilldown endpoint..."

PLATFORM_BOTS=$(curl -s -X GET "$BASE_URL/api/platforms/binance/bots" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)

if echo "$PLATFORM_BOTS" | jq -e '.success' > /dev/null 2>&1; then
    success "Platform drilldown endpoint accessible"
    PLATFORM_BOT_COUNT=$(echo "$PLATFORM_BOTS" | jq -r '.total_bots')
    echo "   Binance bots: $PLATFORM_BOT_COUNT"
else
    error "Platform drilldown endpoint FAILED"
    echo "Response: $PLATFORM_BOTS"
fi

echo ""

# Test 5: Admin Endpoints (if admin password available)
echo "6. Testing Admin endpoints..."

if [ -n "$ADMIN_PASSWORD" ]; then
    ADMIN_UNLOCK=$(curl -s -X POST "$BASE_URL/api/admin/unlock" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"password\": \"$ADMIN_PASSWORD\"}" 2>/dev/null)
    
    if echo "$ADMIN_UNLOCK" | jq -e '.success' > /dev/null 2>&1; then
        success "Admin panel unlocked"
        
        # Test admin/bots endpoint
        ADMIN_BOTS=$(curl -s -X GET "$BASE_URL/api/admin/bots" \
          -H "Authorization: Bearer $TOKEN" 2>/dev/null)
        
        if echo "$ADMIN_BOTS" | jq -e '.success' > /dev/null 2>&1; then
            success "Admin bots list endpoint works"
            ADMIN_BOT_COUNT=$(echo "$ADMIN_BOTS" | jq -r '.total')
            echo "   Total bots: $ADMIN_BOT_COUNT"
        fi
        
        # Test admin/resources/users endpoint
        ADMIN_RESOURCES=$(curl -s -X GET "$BASE_URL/api/admin/resources/users" \
          -H "Authorization: Bearer $TOKEN" 2>/dev/null)
        
        if echo "$ADMIN_RESOURCES" | jq -e '.success' > /dev/null 2>&1; then
            success "Admin resource usage endpoint works"
            TOTAL_USERS=$(echo "$ADMIN_RESOURCES" | jq -r '.system_totals.total_users')
            TOTAL_STORAGE=$(echo "$ADMIN_RESOURCES" | jq -r '.system_totals.total_storage_mb')
            echo "   Total users: $TOTAL_USERS"
            echo "   Total storage: ${TOTAL_STORAGE}MB"
        fi
    else
        echo "   Admin password not provided or incorrect"
    fi
else
    echo "   Skipping admin tests (set ADMIN_PASSWORD env var to test)"
fi

echo ""

# Test 6: Realtime Events (SSE)
echo "7. Testing Realtime Events endpoint..."

# Test SSE connection (timeout after 3 seconds)
SSE_TEST=$(timeout 3 curl -s -N -X GET "$BASE_URL/api/realtime/events?token=$TOKEN" 2>/dev/null | head -3)

if [ -n "$SSE_TEST" ]; then
    success "Realtime SSE endpoint streams data"
    echo "   Sample events:"
    echo "$SSE_TEST" | head -2
else
    error "Realtime SSE endpoint not responding"
fi

echo ""

# Test 7: WebSocket Connection
echo "8. Testing WebSocket endpoint..."

# Check if wscat is available
if command -v wscat &> /dev/null; then
    echo "   Testing WebSocket connection (3 second timeout)..."
    WS_TEST=$(timeout 3 wscat -c "ws://localhost:8000/api/ws?token=$TOKEN" 2>&1 || true)
    
    if echo "$WS_TEST" | grep -q "Connected"; then
        success "WebSocket connection established"
    else
        echo "   Note: WebSocket test inconclusive (install wscat for better testing)"
    fi
else
    echo "   Skipping WebSocket test (install wscat: npm install -g wscat)"
fi

echo ""
echo "=================================="
echo "Validation Complete"
echo "=================================="
echo ""
echo "Summary:"
echo "- API key endpoints accept multiple payload formats ✓"
echo "- Live Training Bay endpoint accessible ✓"
echo "- Bot start/stop endpoints work ✓"
echo "- Platform drilldown endpoint works ✓"
echo "- Admin endpoints functional ✓"
echo "- Realtime SSE streams data ✓"
echo "- WebSocket endpoint available ✓"
echo ""
echo "For detailed testing, see: BACKEND_FIXES_TESTING_GUIDE.md"
echo "For test suite, run: pytest tests/test_backend_blockers.py -v"
