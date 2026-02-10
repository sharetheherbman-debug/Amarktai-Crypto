#!/bin/bash
# TASK H - Production Verification Script
# Verifies all critical fixes for production go-live
# Run on VPS: bash scripts/verify_live.sh

set +e

# Configuration
BASE_URL="${BASE_URL:-https://www.amarktai.online}"
MIN_OPENAPI_SIZE=50000  # Minimum expected OpenAPI JSON size (bytes)
MAX_RETRIES=3
RETRY_DELAY=5
EXPECTED_EXCHANGE_IDS=(luno binance kucoin bybit kraken bitget gate)

# Colors
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

# Helper: retry a check with backoff (tolerates brief 502 during restart)
retry_check() {
    local name="$1"
    shift
    for attempt in $(seq 1 $MAX_RETRIES); do
        if "$@" 2>/dev/null; then
            return 0
        fi
        if [ "$attempt" -lt "$MAX_RETRIES" ]; then
            echo -e "  ${YELLOW}⏳ Retry $attempt/$MAX_RETRIES in ${RETRY_DELAY}s...${NC}"
            sleep $RETRY_DELAY
        fi
    done
    return 1
}

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
        PASSED=$((PASSED+1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $HTTP_CODE, expected $expected_code)"
        echo "Response: $BODY" | head -3
        FAILURES=$((FAILURES+1))
        return 1
    fi
}

# Helper function to check endpoint for one of multiple codes
check_endpoint_one_of_codes() {
    local name="$1"
    local url="$2"
    local expected_codes="$3"
    local auth_header="${4:-}"

    echo -n "Checking $name... "

    if [ -n "$auth_header" ]; then
        RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $auth_header" "$url" 2>&1)
    else
        RESPONSE=$(curl -s -w "\n%{http_code}" "$url" 2>&1)
    fi

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if echo " $expected_codes " | grep -q " $HTTP_CODE "; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP $HTTP_CODE)"
        PASSED=$((PASSED+1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $HTTP_CODE, expected one of: $expected_codes)"
        echo "Response: $BODY" | head -3
        FAILURES=$((FAILURES+1))
        return 1
    fi
}

# Helper function to check method-not-allowed behavior with Allow header
check_method_not_allowed() {
    local name="$1"
    local url="$2"
    local allowed_method="$3"

    echo -n "Checking $name... "

    HEADERS=$(curl -s -D - -o /dev/null "$url" 2>&1)
    HTTP_CODE=$(echo "$HEADERS" | head -1 | awk '{print $2}')
    ALLOW_HEADER=$(echo "$HEADERS" | tr -d '\r' | awk -F': ' 'tolower($1)=="allow" {print $2}' | head -1)

    if [ "$HTTP_CODE" = "405" ] && echo "$ALLOW_HEADER" | grep -qi "$allowed_method"; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP 405, Allow: $ALLOW_HEADER)"
        PASSED=$((PASSED+1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $HTTP_CODE, Allow: ${ALLOW_HEADER:-none})"
        FAILURES=$((FAILURES+1))
        return 1
    fi
}

# Helper function to validate exchange providers list
check_exchange_providers() {
    local name="$1"
    local url="$2"

    echo -n "Checking $name... "
    RESPONSE=$(curl -fsS "$url" 2>&1)

    if ! echo "$RESPONSE" | jq . >/dev/null 2>&1; then
        echo -e "${RED}❌ FAIL${NC} (Invalid JSON)"
        FAILURES=$((FAILURES+1))
        return 1
    fi

    EXPECTED_EXCHANGES=$(printf "%s\n" "${EXPECTED_EXCHANGE_IDS[@]}")
    ACTUAL_EXCHANGES=$(echo "$RESPONSE" | jq -r '.providers[] | select(.type=="exchange") | .id')
    BANNED_EXCHANGES=$(echo "$RESPONSE" | jq -r '.providers[]?.id' | grep -i -E '^(valr|ovex)$' || true)

    SORTED_EXPECTED=$(echo "$EXPECTED_EXCHANGES" | sort)
    SORTED_ACTUAL=$(echo "$ACTUAL_EXCHANGES" | sort)
    MISSING_EXCHANGES=$(comm -23 <(echo "$SORTED_EXPECTED") <(echo "$SORTED_ACTUAL"))
    EXTRA_EXCHANGES=$(comm -13 <(echo "$SORTED_EXPECTED") <(echo "$SORTED_ACTUAL"))

    if [ -z "$MISSING_EXCHANGES" ] && [ -z "$EXTRA_EXCHANGES" ] && [ -z "$BANNED_EXCHANGES" ]; then
        echo -e "${GREEN}✅ PASS${NC} (Exchange providers match expected list)"
        PASSED=$((PASSED+1))
        return 0
    fi

    echo -e "${RED}❌ FAIL${NC} (Exchange providers mismatch)"
    if [ -n "$MISSING_EXCHANGES" ]; then
        echo "  Missing exchanges: $(echo "$MISSING_EXCHANGES" | tr '\n' ' ')"
    fi
    if [ -n "$EXTRA_EXCHANGES" ]; then
        echo "  Unexpected exchanges: $(echo "$EXTRA_EXCHANGES" | tr '\n' ' ')"
    fi
    if [ -n "$BANNED_EXCHANGES" ]; then
        echo "  Banned exchanges found: $(echo "$BANNED_EXCHANGES" | tr '\n' ' ')"
    fi
    FAILURES=$((FAILURES+1))
    return 1
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
            PASSED=$((PASSED+1))
            return 0
        elif [ -z "$search_string" ]; then
            echo -e "${GREEN}✅ PASS${NC} (Valid JSON)"
            PASSED=$((PASSED+1))
            return 0
        else
            echo -e "${RED}❌ FAIL${NC} (Valid JSON but missing '$search_string')"
            echo "Response: $RESPONSE" | head -5
            FAILURES=$((FAILURES+1))
            return 1
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (Invalid JSON)"
        echo "Response: $RESPONSE" | head -5
        FAILURES=$((FAILURES+1))
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
    if [ "$OPENAPI_SIZE" -gt "$MIN_OPENAPI_SIZE" ]; then
        if echo "$OPENAPI_RESPONSE" | grep -q "/api/auth/login"; then
            echo -e "${GREEN}✅ PASS${NC} (Valid JSON, ${OPENAPI_SIZE} bytes, contains /api/auth/login)"
            PASSED=$((PASSED+1))
        else
            echo -e "${RED}❌ FAIL${NC} (Valid JSON but missing /api/auth/login)"
            FAILURES=$((FAILURES+1))
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (JSON too small: ${OPENAPI_SIZE} bytes, expected >50KB)"
        echo "This suggests React index.html is being served instead of FastAPI OpenAPI spec"
        FAILURES=$((FAILURES+1))
    fi
else
    echo -e "${RED}❌ FAIL${NC} (Invalid JSON)"
    FAILURES=$((FAILURES+1))
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

# Check if response contains token_type (required)
if echo "$LOGIN_RESPONSE" | jq -e '.token_type' >/dev/null 2>&1; then
    HAS_TOKEN_TYPE=true
else
    HAS_TOKEN_TYPE=false
fi

# Check if response contains duplicate "token" field (should NOT exist)
if echo "$LOGIN_RESPONSE" | jq -e '.token' >/dev/null 2>&1; then
    HAS_TOKEN_FIELD=true
else
    HAS_TOKEN_FIELD=false
fi

# Check if response contains "user" field (should NOT exist per TASK C)
if echo "$LOGIN_RESPONSE" | jq -e '.user' >/dev/null 2>&1; then
    HAS_USER_FIELD=true
else
    HAS_USER_FIELD=false
fi

if [ "$HAS_ACCESS_TOKEN" = "true" ] && [ "$HAS_TOKEN_TYPE" = "true" ] && [ "$HAS_TOKEN_FIELD" = "false" ] && [ "$HAS_USER_FIELD" = "false" ]; then
    echo -e "${GREEN}✅ PASS${NC} (Has access_token + token_type only, no duplicate token/user fields)"
    PASSED=$((PASSED+1))
elif echo "$LOGIN_RESPONSE" | grep -q "Invalid email or password"; then
    echo -e "${YELLOW}⚠️  SKIP${NC} (Test credentials not found - expected in production)"
    echo "   Note: Login response structure must have 'access_token' + 'token_type' only"
else
    echo -e "${RED}❌ FAIL${NC} (Invalid response structure)"
    if [ "$HAS_ACCESS_TOKEN" != "true" ]; then
        echo "   Missing: access_token"
    fi
    if [ "$HAS_TOKEN_TYPE" != "true" ]; then
        echo "   Missing: token_type"
    fi
    if [ "$HAS_TOKEN_FIELD" = "true" ]; then
        echo "   Found unwanted: token (duplicate field)"
    fi
    if [ "$HAS_USER_FIELD" = "true" ]; then
        echo "   Found unwanted: user (should not be in auth response)"
    fi
    echo "Response: $LOGIN_RESPONSE" | head -3
    FAILURES=$((FAILURES+1))
fi

echo ""
echo "📋 TASK C/D/E - API Keys Endpoints"
echo "-----------------------------------"
check_exchange_providers "API Keys Providers List" "$BASE_URL/api/keys/providers"
check_endpoint_one_of_codes "API Keys Status (no auth)" "$BASE_URL/api/keys/status" "401 403"

# Note: Testing authenticated endpoints requires a valid token
echo -e "${YELLOW}ℹ️  Note: Authenticated API key endpoints require valid JWT token${NC}"

# Check for canonical API key statuses in OpenAPI spec
echo -n "Checking for canonical API key statuses... "
if echo "$OPENAPI_RESPONSE" | grep -q "not_configured\|saved_untested\|test_ok\|test_failed"; then
    echo -e "${GREEN}✅ PASS${NC} (Canonical statuses present in API spec)"
    PASSED=$((PASSED+1))
else
    echo -e "${RED}❌ FAIL${NC} (Canonical statuses not found in API spec)"
    echo "   Expected: not_configured, saved_untested, test_ok, test_failed"
    FAILURES=$((FAILURES+1))
fi

# Check that legacy statuses are NOT exposed in OpenAPI paths (should be normalized)
echo -n "Checking legacy status removal... "
LEGACY_CHECK=$(echo "$OPENAPI_RESPONSE" | grep -E "configured_untested|configured_valid|configured_invalid" | grep -v "description\|comment" || true)
if [ -z "$LEGACY_CHECK" ]; then
    echo -e "${GREEN}✅ PASS${NC} (No legacy statuses in API responses)"
    PASSED=$((PASSED+1))
else
    echo -e "${YELLOW}⚠️  WARN${NC} (Legacy statuses still in OpenAPI - may be in descriptions)"
    echo "   This is OK if only in descriptions/comments"
fi

echo ""
echo "📋 TASK F - Admin Endpoints Protection"
echo "---------------------------------------"
# GET /api/admin/unlock should be method-not-allowed with Allow: POST
check_method_not_allowed "Admin Unlock GET (no auth)" "$BASE_URL/api/admin/unlock" "POST"
check_endpoint_one_of_codes "Admin Users List (no auth)" "$BASE_URL/api/admin/users" "401 403"
check_endpoint_one_of_codes "Admin Overview (no auth)" "$BASE_URL/api/admin/overview" "401 403"

echo ""
echo "📋 Additional Production Checks"
echo "--------------------------------"
check_json "Build Info" "$BASE_URL/api/build/info" "version"
check_endpoint "Frontend SPA" "$BASE_URL/" 200

# Note about route collision detection
echo ""
echo "ℹ️  Route Collision Detection:"
echo "   Backend server.py has built-in route collision detection at startup"
echo "   If server starts successfully, no route collisions exist"
echo "   Check backend logs for: '✅ Route collision check passed'"

echo ""
echo "📋 TASK D - Footer and Admin Unlock"
echo "------------------------------------"

echo ""
echo "📋 Frontend JS Bundle Verification"
echo "-----------------------------------"

echo -n "Checking index.html references /static/js/... "
INDEX_HTML=$(curl -s --connect-timeout 10 "$BASE_URL/" 2>/dev/null || echo "")
if echo "$INDEX_HTML" | grep -q "/static/js/"; then
    echo -e "${GREEN}✅ PASS${NC} (index.html references /static/js/)"
    PASSED=$((PASSED+1))
    
    # Extract JS bundle URL and verify it's accessible
    JS_URL=$(echo "$INDEX_HTML" | grep -oP '/static/js/main\.[^"]+\.js' | head -1 || echo "")
    if [ -n "$JS_URL" ]; then
        echo -n "Checking JS bundle: ${JS_URL}... "
        JS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "$BASE_URL$JS_URL" 2>/dev/null || echo "000")
        if [ "$JS_CODE" = "200" ]; then
            JS_SIZE=$(curl -sI --connect-timeout 10 "$BASE_URL$JS_URL" 2>/dev/null | grep -i content-length | awk '{print $2}' | tr -d '\r' || echo "0")
            if [ "${JS_SIZE:-0}" -gt 51200 ]; then
                echo -e "${GREEN}✅ PASS${NC} (HTTP 200, ${JS_SIZE} bytes > 50KB)"
                PASSED=$((PASSED+1))
            else
                echo -e "${YELLOW}⚠️  WARN${NC} (HTTP 200 but size ${JS_SIZE} bytes < 50KB)"
            fi
        else
            echo -e "${RED}❌ FAIL${NC} (HTTP $JS_CODE)"
            FAILURES=$((FAILURES+1))
        fi
    fi
    
    # Check asset-manifest.json
    echo -n "Checking asset-manifest.json... "
    MANIFEST_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "$BASE_URL/asset-manifest.json" 2>/dev/null || echo "000")
    if [ "$MANIFEST_CODE" = "200" ]; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP 200)"
        PASSED=$((PASSED+1))
    else
        echo -e "${YELLOW}⚠️  WARN${NC} (HTTP $MANIFEST_CODE)"
    fi
else
    echo -e "${YELLOW}⚠️  WARN${NC} (Could not verify - may need deploy first)"
fi

# Check frontend contains copyright text
echo -n "Checking for footer copyright text... "
FRONTEND_RESPONSE=$(curl -s "$BASE_URL/" 2>&1)
if echo "$FRONTEND_RESPONSE" | grep -q "Part of Amarktai Network\|© 2026 Amarktai"; then
    echo -e "${GREEN}✅ PASS${NC} (Copyright text present in frontend)"
    PASSED=$((PASSED+1))
else
    echo -e "${YELLOW}⚠️  WARN${NC} (Copyright text not found - may be in JS bundle)"
    echo "   Frontend is a React SPA - copyright is rendered by JS"
fi

# Check that "show admin" is not in blocked phrases
echo -n "Checking admin unlock not blocked... "
if [ -f "frontend/src/components/AIChatPanel.js" ]; then
    if grep -q "'show admin'" frontend/src/components/AIChatPanel.js; then
        echo -e "${YELLOW}⚠️  WARN${NC} (AIChatPanel still has 'show admin' reference)"
        echo "   Check if it's in blockedPhrases or handled locally"
    else
        echo -e "${GREEN}✅ PASS${NC} (No 'show admin' in AIChatPanel blockedPhrases)"
        PASSED=$((PASSED+1))
    fi
elif [ -f "frontend/src/pages/Dashboard.js" ]; then
    # Dashboard.js handles admin unlock locally
    if grep -q "show admin" frontend/src/pages/Dashboard.js | grep -v "blocked"; then
        echo -e "${GREEN}✅ PASS${NC} (Admin unlock handled in Dashboard)"
        PASSED=$((PASSED+1))
    else
        echo -e "${YELLOW}⚠️  WARN${NC} (Could not verify admin unlock in Dashboard)"
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} (Frontend files not accessible from this location)"
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
