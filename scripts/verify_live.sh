#!/bin/bash
# TASK H - Production Verification Script
# Verifies all critical fixes for production go-live
# Run on VPS: bash scripts/verify_live.sh

set -e

BASE_URL="${BASE_URL:-https://www.amarktai.online}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "🚀 Amarktai Network - Production Verification"
echo "=================================================="
echo "Base URL: $BASE_URL"
echo ""

# Track failures
FAILURES=0
PASSED=0

# Helper function to check endpoint
check_endpoint() {
    local name="$1"
    local url="$2"
    local expected_code="${3:-200}"
    local auth_header="${4:-}"
    
    echo -n "Checking $name... "
    
    if [ -n "$auth_header" ]; then
        RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $auth_header" "$url" 2>&1)
    else
        RESPONSE=$(curl -s -w "\n%{http_code}" "$url" 2>&1)
    fi
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" = "$expected_code" ]; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP $HTTP_CODE)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $HTTP_CODE, expected $expected_code)"
        echo "Response: $BODY" | head -3
        ((FAILURES++))
        return 1
    fi
}

# Helper function to check JSON response
check_json() {
    local name="$1"
    local url="$2"
    local search_string="$3"
    local auth_header="${4:-}"
    
    echo -n "Checking $name... "
    
    if [ -n "$auth_header" ]; then
        RESPONSE=$(curl -fsS -H "Authorization: Bearer $auth_header" "$url" 2>&1)
    else
        RESPONSE=$(curl -fsS "$url" 2>&1)
    fi
    
    if echo "$RESPONSE" | jq . >/dev/null 2>&1; then
        if [ -n "$search_string" ] && echo "$RESPONSE" | grep -q "$search_string"; then
            echo -e "${GREEN}✅ PASS${NC} (Valid JSON, contains '$search_string')"
            ((PASSED++))
            return 0
        elif [ -z "$search_string" ]; then
            echo -e "${GREEN}✅ PASS${NC} (Valid JSON)"
            ((PASSED++))
            return 0
        else
            echo -e "${RED}❌ FAIL${NC} (Valid JSON but missing '$search_string')"
            echo "Response: $RESPONSE" | head -5
            ((FAILURES++))
            return 1
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (Invalid JSON)"
        echo "Response: $RESPONSE" | head -5
        ((FAILURES++))
        return 1
    fi
}

echo "📋 TASK A - OpenAPI Routing"
echo "----------------------------"
check_endpoint "Health Ping" "$BASE_URL/api/health/ping" 200

# Check OpenAPI JSON is valid and large enough
echo -n "Checking OpenAPI JSON... "
OPENAPI_RESPONSE=$(curl -fsS "$BASE_URL/api/openapi.json" 2>&1)
OPENAPI_SIZE=$(echo -n "$OPENAPI_RESPONSE" | wc -c)

if echo "$OPENAPI_RESPONSE" | jq . >/dev/null 2>&1; then
    if [ "$OPENAPI_SIZE" -gt 50000 ]; then
        if echo "$OPENAPI_RESPONSE" | grep -q "/api/auth/login"; then
            echo -e "${GREEN}✅ PASS${NC} (Valid JSON, ${OPENAPI_SIZE} bytes, contains /api/auth/login)"
            ((PASSED++))
        else
            echo -e "${RED}❌ FAIL${NC} (Valid JSON but missing /api/auth/login)"
            ((FAILURES++))
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (JSON too small: ${OPENAPI_SIZE} bytes, expected >50KB)"
        echo "This suggests React index.html is being served instead of FastAPI OpenAPI spec"
        ((FAILURES++))
    fi
else
    echo -e "${RED}❌ FAIL${NC} (Invalid JSON)"
    echo "First 200 chars: ${OPENAPI_RESPONSE:0:200}"
    ((FAILURES++))
fi

check_endpoint "Docs UI" "$BASE_URL/api/docs" 200
check_endpoint "ReDoc UI" "$BASE_URL/api/redoc" 200

echo ""
echo "📋 TASK B - Auth Response Consistency"
echo "--------------------------------------"
echo "Testing login endpoint..."

# Create a test login payload
LOGIN_PAYLOAD='{"email":"test@example.com","password":"testpass123"}'

echo -n "Checking login response format... "
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "$LOGIN_PAYLOAD" 2>&1)

# Check if response contains access_token (required)
if echo "$LOGIN_RESPONSE" | jq -e '.access_token' >/dev/null 2>&1; then
    HAS_ACCESS_TOKEN=true
else
    HAS_ACCESS_TOKEN=false
fi

# Check if response contains duplicate "token" field (should NOT exist)
if echo "$LOGIN_RESPONSE" | jq -e '.token' >/dev/null 2>&1; then
    HAS_TOKEN_FIELD=true
else
    HAS_TOKEN_FIELD=false
fi

if [ "$HAS_ACCESS_TOKEN" = "true" ] && [ "$HAS_TOKEN_FIELD" = "false" ]; then
    echo -e "${GREEN}✅ PASS${NC} (Has access_token, no duplicate token field)"
    ((PASSED++))
elif [ "$HAS_ACCESS_TOKEN" = "true" ] && [ "$HAS_TOKEN_FIELD" = "true" ]; then
    echo -e "${RED}❌ FAIL${NC} (Has access_token but also has duplicate token field)"
    ((FAILURES++))
elif echo "$LOGIN_RESPONSE" | grep -q "Invalid email or password"; then
    echo -e "${YELLOW}⚠️  SKIP${NC} (Test credentials not found - expected in production)"
    echo "   Note: Login response structure must have 'access_token' only, no 'token' field"
else
    echo -e "${RED}❌ FAIL${NC} (Missing access_token or unexpected response)"
    echo "Response: $LOGIN_RESPONSE" | head -3
    ((FAILURES++))
fi

echo ""
echo "📋 TASK C/D/E - API Keys Endpoints"
echo "-----------------------------------"
check_json "API Keys Providers List" "$BASE_URL/api/keys/providers" "providers"
check_endpoint "API Keys Status (no auth)" "$BASE_URL/api/keys/status" 401

# Note: Testing authenticated endpoints requires a valid token
echo -e "${YELLOW}ℹ️  Note: Authenticated API key endpoints require valid JWT token${NC}"

echo ""
echo "📋 TASK F - Admin Endpoints Protection"
echo "---------------------------------------"
check_endpoint "Admin Unlock (no auth)" "$BASE_URL/api/admin/unlock" 401
check_endpoint "Admin Users List (no auth)" "$BASE_URL/api/admin/users" 401
check_endpoint "Admin Overview (no auth)" "$BASE_URL/api/admin/overview" 401

echo ""
echo "📋 Additional Production Checks"
echo "--------------------------------"
check_json "Build Info" "$BASE_URL/api/build/info" "version"
check_endpoint "Frontend SPA" "$BASE_URL/" 200

# Check for banned exchanges (valr, ovex)
echo -n "Checking for banned exchanges... "
OPENAPI_CHECK=$(echo "$OPENAPI_RESPONSE" | grep -i "valr\|ovex" || true)
if [ -z "$OPENAPI_CHECK" ]; then
    echo -e "${GREEN}✅ PASS${NC} (No valr/ovex in OpenAPI)"
    ((PASSED++))
else
    echo -e "${RED}❌ FAIL${NC} (Found banned exchanges: valr/ovex)"
    echo "$OPENAPI_CHECK"
    ((FAILURES++))
fi

echo ""
echo "=================================================="
echo "📊 RESULTS"
echo "=================================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILURES${NC}"

if [ "$FAILURES" -eq 0 ]; then
    echo -e "\n${GREEN}✅ ALL CHECKS PASSED - Production ready!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ SOME CHECKS FAILED - Review issues above${NC}"
    exit 1
fi
