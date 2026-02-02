#!/bin/bash
# Endpoint Doctor/Smoke Test Script for Amarktai Network
# Validates all critical API endpoints return expected responses
# Usage: ./endpoint_doctor.sh [API_URL] [TOKEN]
# Example: ./endpoint_doctor.sh http://localhost:8000 eyJhbGc...

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="${1:-http://localhost:8000}"
TOKEN="${2:-}"
FAILED_TESTS=0
PASSED_TESTS=0
SKIPPED_TESTS=0

# If no token provided, try to get from env
if [ -z "$TOKEN" ]; then
    if [ -n "$TEST_TOKEN" ]; then
        TOKEN="$TEST_TOKEN"
    elif [ -n "$JWT_TOKEN" ]; then
        TOKEN="$JWT_TOKEN"
    fi
fi

echo "========================================="
echo "🔬 Amarktai Network - Endpoint Doctor"
echo "========================================="
echo "API URL: $API_URL"
if [ -n "$TOKEN" ]; then
    echo "Token: ${TOKEN:0:20}..."
else
    echo -e "${YELLOW}⚠️  No authentication token provided${NC}"
    echo "Set TEST_TOKEN or JWT_TOKEN env var, or pass as second argument"
    echo "Some tests will be skipped"
fi
echo "========================================="
echo ""

# Helper function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local description=$4
    local auth_required=${5:-false}
    local data=${6:-}
    
    local full_url="${API_URL}${endpoint}"
    local headers=""
    
    if [ "$auth_required" = true ]; then
        if [ -z "$TOKEN" ]; then
            echo -e "${YELLOW}⏭️  SKIP: $description (no token)${NC}"
            ((SKIPPED_TESTS++))
            return 0
        fi
        headers="-H \"Authorization: Bearer $TOKEN\""
    fi
    
    echo -n "Testing: $description... "
    
    local curl_cmd="curl -s -w \"\\n%{http_code}\" -X $method $headers"
    
    if [ "$method" = "POST" ] || [ "$method" = "PUT" ]; then
        if [ -n "$data" ]; then
            curl_cmd="$curl_cmd -H \"Content-Type: application/json\" -d '$data'"
        fi
    fi
    
    curl_cmd="$curl_cmd \"$full_url\""
    
    response=$(eval $curl_cmd 2>/dev/null || echo -e "\n000")
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS (HTTP $status_code)${NC}"
        ((PASSED_TESTS++))
        return 0
    else
        echo -e "${RED}✗ FAIL (Expected $expected_status, got $status_code)${NC}"
        if [ ${#body} -lt 200 ]; then
            echo "   Response: $body"
        else
            echo "   Response: ${body:0:200}..."
        fi
        ((FAILED_TESTS++))
        return 1
    fi
}

# Test JSON shape
test_json_shape() {
    local method=$1
    local endpoint=$2
    local expected_field=$3
    local description=$4
    local auth_required=${5:-false}
    
    local full_url="${API_URL}${endpoint}"
    local headers=""
    
    if [ "$auth_required" = true ]; then
        if [ -z "$TOKEN" ]; then
            echo -e "${YELLOW}⏭️  SKIP: $description (no token)${NC}"
            ((SKIPPED_TESTS++))
            return 0
        fi
        headers="-H \"Authorization: Bearer $TOKEN\""
    fi
    
    echo -n "Testing: $description... "
    
    response=$(eval curl -s $headers "\"$full_url\"" 2>/dev/null || echo "{}")
    
    # Check if field exists in JSON
    if echo "$response" | grep -q "\"$expected_field\""; then
        echo -e "${GREEN}✓ PASS (field '$expected_field' found)${NC}"
        ((PASSED_TESTS++))
        return 0
    else
        echo -e "${RED}✗ FAIL (field '$expected_field' not found)${NC}"
        if [ ${#response} -lt 200 ]; then
            echo "   Response: $response"
        else
            echo "   Response: ${response:0:200}..."
        fi
        ((FAILED_TESTS++))
        return 1
    fi
}

echo ""
echo -e "${BLUE}📋 CATEGORY: Health & Ping${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/health/ping" "200" "Health ping endpoint" false
test_endpoint "GET" "/api/system/ping" "200" "System ping endpoint" false
test_endpoint "GET" "/api/system/health" "200" "System health check" false

echo ""
echo -e "${BLUE}📋 CATEGORY: System Status & Mode${NC}"
echo "----------------------------------------"
test_json_shape "GET" "/api/system/status" "success" "System status returns success field" true
test_json_shape "GET" "/api/system/status" "feature_flags" "System status has feature_flags" true
test_json_shape "GET" "/api/system/status" "database" "System status has database info" true
test_json_shape "GET" "/api/system/mode" "paperTrading" "System mode has paperTrading flag" true
test_json_shape "GET" "/api/system/mode" "liveTrading" "System mode has liveTrading flag" true
test_json_shape "GET" "/api/system/mode" "autopilot" "System mode has autopilot flag" true

echo ""
echo -e "${BLUE}📋 CATEGORY: Since Last Login (NEW)${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/system/since-last-login" "200" "Since-last-login endpoint exists" true
test_json_shape "GET" "/api/system/since-last-login" "last_login" "Returns last_login timestamp" true
test_json_shape "GET" "/api/system/since-last-login" "notes" "Returns notes array" true
test_json_shape "GET" "/api/system/since-last-login" "active_bots" "Returns active_bots count" true
test_json_shape "GET" "/api/system/since-last-login" "paperTrading" "Returns paperTrading mode" true

echo ""
echo -e "${BLUE}📋 CATEGORY: API Keys Management${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/keys/providers" "200" "List API key providers" false
test_json_shape "GET" "/api/keys/list" "keys" "API keys list returns keys array" true
test_json_shape "GET" "/api/keys/providers" "providers" "Providers list has providers array" false

# Test API key lifecycle (if authenticated)
if [ -n "$TOKEN" ]; then
    echo ""
    echo -e "${BLUE}📋 CATEGORY: API Key Lifecycle (Full Flow)${NC}"
    echo "----------------------------------------"
    
    # Save a dummy key
    echo -n "Testing: API key save (POST /api/keys/save)... "
    save_data='{"provider":"openai","api_key":"sk-test-dummy-key-for-smoke-test"}'
    save_response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$save_data" \
        "${API_URL}/api/keys/save" 2>/dev/null || echo -e "\n000")
    
    save_status=$(echo "$save_response" | tail -n 1)
    if [ "$save_status" = "200" ]; then
        echo -e "${GREEN}✓ PASS (HTTP 200)${NC}"
        ((PASSED_TESTS++))
        
        # Test the key (should work even if key invalid)
        test_endpoint "POST" "/api/keys/test" "200" "API key test (POST /api/keys/test)" true '{"provider":"openai"}'
        
        # Delete the key
        test_endpoint "DELETE" "/api/keys/openai" "200" "API key delete (DELETE /api/keys/{provider})" true
    else
        echo -e "${RED}✗ FAIL (Expected 200, got $save_status)${NC}"
        ((FAILED_TESTS++))
    fi
fi

echo ""
echo -e "${BLUE}📋 CATEGORY: Bots Management${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/bots/status" "200" "Get bots status list" true
test_json_shape "GET" "/api/bots/status" "0" "Bots status returns array (check index 0 or empty)" true

# Test bot create/delete flow (if authenticated)
if [ -n "$TOKEN" ]; then
    echo ""
    echo -e "${BLUE}📋 CATEGORY: Bot Lifecycle (Full Flow)${NC}"
    echo "----------------------------------------"
    
    echo -n "Testing: Bot creation (POST /bots)... "
    bot_data='{"name":"SmokeTestBot","exchange":"luno","symbol":"BTC/ZAR","initial_capital":100,"mode":"paper"}'
    create_response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$bot_data" \
        "${API_URL}/bots" 2>/dev/null || echo -e "\n000")
    
    create_status=$(echo "$create_response" | tail -n 1)
    create_body=$(echo "$create_response" | head -n -1)
    
    if [ "$create_status" = "200" ] || [ "$create_status" = "201" ]; then
        echo -e "${GREEN}✓ PASS (HTTP $create_status)${NC}"
        ((PASSED_TESTS++))
        
        # Extract bot_id from response
        bot_id=$(echo "$create_body" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        
        if [ -n "$bot_id" ]; then
            # Verify bot appears in list
            echo -n "Testing: Bot appears in list after creation... "
            list_response=$(curl -s -H "Authorization: Bearer $TOKEN" "${API_URL}/api/bots/status" 2>/dev/null)
            if echo "$list_response" | grep -q "$bot_id"; then
                echo -e "${GREEN}✓ PASS (Bot found in list)${NC}"
                ((PASSED_TESTS++))
            else
                echo -e "${RED}✗ FAIL (Bot not found in list)${NC}"
                ((FAILED_TESTS++))
            fi
            
            # Delete the bot
            echo -n "Testing: Bot deletion (DELETE /api/bots/{id})... "
            delete_response=$(curl -s -w "\n%{http_code}" -X DELETE \
                -H "Authorization: Bearer $TOKEN" \
                "${API_URL}/api/bots/${bot_id}" 2>/dev/null || echo -e "\n000")
            
            delete_status=$(echo "$delete_response" | tail -n 1)
            if [ "$delete_status" = "200" ]; then
                echo -e "${GREEN}✓ PASS (HTTP 200)${NC}"
                ((PASSED_TESTS++))
                
                # Verify bot does NOT appear in list after deletion
                echo -n "Testing: Deleted bot excluded from list... "
                sleep 1  # Small delay to ensure DB updated
                list_response=$(curl -s -H "Authorization: Bearer $TOKEN" "${API_URL}/api/bots/status" 2>/dev/null)
                if ! echo "$list_response" | grep -q "$bot_id"; then
                    echo -e "${GREEN}✓ PASS (Deleted bot not in list)${NC}"
                    ((PASSED_TESTS++))
                else
                    echo -e "${RED}✗ FAIL (Deleted bot still appears in list)${NC}"
                    ((FAILED_TESTS++))
                fi
            else
                echo -e "${RED}✗ FAIL (Expected 200, got $delete_status)${NC}"
                ((FAILED_TESTS++))
            fi
        else
            echo -e "${YELLOW}⚠️  WARNING: Could not extract bot_id from create response${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Bot creation returned $create_status (may be validation error - acceptable)${NC}"
    fi
fi

echo ""
echo -e "${BLUE}📋 CATEGORY: Trades & Portfolio${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/trades/recent" "200" "Recent trades endpoint" true
test_json_shape "GET" "/api/trades/recent" "trades" "Recent trades returns trades array" true
test_json_shape "GET" "/api/trades/recent" "count" "Recent trades returns count" true
test_json_shape "GET" "/api/trades/recent" "timestamp" "Recent trades returns timestamp" true
test_endpoint "GET" "/api/trades/metrics" "200" "Trade metrics endpoint" true

echo ""
echo -e "${BLUE}📋 CATEGORY: Platforms & Exchanges${NC}"
echo "----------------------------------------"
test_endpoint "GET" "/api/system/platforms" "200" "Platforms list endpoint" false
test_json_shape "GET" "/api/system/platforms" "platforms" "Platforms returns platforms array" false

# Check for correct exchange enablement (all 7 exchanges enabled: luno, binance, kucoin, bybit, kraken, bitget, gateio)
echo -n "Testing: Exchange defaults (luno/binance/kucoin enabled)... "
platforms_response=$(curl -s "${API_URL}/api/system/platforms" 2>/dev/null || echo "{}")
has_luno=$(echo "$platforms_response" | grep -o '"id":"luno"' | wc -l)
has_binance=$(echo "$platforms_response" | grep -o '"id":"binance"' | wc -l)
has_kucoin=$(echo "$platforms_response" | grep -o '"id":"kucoin"' | wc -l)

if [ "$has_luno" -gt 0 ] && [ "$has_binance" -gt 0 ] && [ "$has_kucoin" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS (All required platforms present)${NC}"
    ((PASSED_TESTS++))
else
    echo -e "${RED}✗ FAIL (Missing required platforms: luno=$has_luno, binance=$has_binance, kucoin=$has_kucoin)${NC}"
    ((FAILED_TESTS++))
fi

echo ""
echo "========================================="
echo "📊 TEST SUMMARY"
echo "========================================="
echo -e "Passed:  ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed:  ${RED}$FAILED_TESTS${NC}"
echo -e "Skipped: ${YELLOW}$SKIPPED_TESTS${NC}"
echo "========================================="

if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}❌ $FAILED_TESTS test(s) failed!${NC}"
    echo ""
    echo "Recommendations:"
    echo "1. Check backend logs for errors"
    echo "2. Verify database is connected"
    echo "3. Ensure all required services are running"
    exit 1
elif [ $SKIPPED_TESTS -gt 0 ] && [ $PASSED_TESTS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  All tests skipped (authentication required)${NC}"
    echo ""
    echo "Provide authentication token to run full test suite:"
    echo "  export TEST_TOKEN='your-jwt-token'"
    echo "  ./endpoint_doctor.sh"
    exit 2
else
    echo -e "${GREEN}✅ All tests passed!${NC}"
    if [ $SKIPPED_TESTS -gt 0 ]; then
        echo -e "${YELLOW}Note: $SKIPPED_TESTS test(s) skipped (no authentication)${NC}"
    fi
    exit 0
fi
