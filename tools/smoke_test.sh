#!/usr/bin/env bash
#
# smoke_test.sh - Comprehensive smoke test for Amarktai Network
#
# This script validates all critical functionality before go-live:
# 1. Health check
# 2. Platform registry (7 exchanges)
# 3. Auth (register/login with invite code + name mapping)
# 4. API key management
# 5. Realtime connectivity
# 6. Bodyguard status
#
# Exit codes: 0=PASS, 1=FAIL

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
INVITE_CODE="${INVITE_CODE:-AMARKTAI2024}"
TEST_EMAIL="smoketest_$(date +%s)@test.local"
TEST_PASSWORD="TestPass123!"
TEST_FIRST_NAME="SmokeTest"

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test output
FAILED_TESTS=()

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((TESTS_PASSED++)) || true
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ((TESTS_FAILED++)) || true
    FAILED_TESTS+=("$1")
}

log_test() {
    echo -e "${YELLOW}🧪 TEST: $1${NC}"
    ((TESTS_RUN++)) || true
}

log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Helper to make API calls
api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local token="${4:-}"
    
    local curl_opts=("-s" "-w" "\n%{http_code}")
    
    if [ -n "$token" ]; then
        curl_opts+=("-H" "Authorization: Bearer $token")
    fi
    
    if [ -n "$data" ]; then
        curl_opts+=("-H" "Content-Type: application/json" "-d" "$data")
    fi
    
    curl "${curl_opts[@]}" -X "$method" "${API_BASE_URL}${endpoint}"
}

# Extract HTTP status code from response
extract_status() {
    echo "$1" | tail -n1
}

# Extract body from response
extract_body() {
    echo "$1" | head -n-1
}

# ============================================================================
# TEST SUITE
# ============================================================================

log_section "AMARKTAI NETWORK - SMOKE TEST SUITE"
log_info "API Base URL: $API_BASE_URL"
log_info "Test Email: $TEST_EMAIL"

# ----------------------------------------------------------------------------
# Test 1: Health Check
# ----------------------------------------------------------------------------
log_section "1. Health Check"
log_test "GET /api/health/ping"

RESPONSE=$(api_call GET "/api/health/ping" "" "" || echo "CURL_FAILED")

if [ "$RESPONSE" = "CURL_FAILED" ]; then
    log_error "Health check failed - server not reachable"
    echo ""
    echo "SMOKE TEST RESULT: ❌ FAIL"
    echo "Critical failure: API server is not running or not reachable"
    exit 1
fi

STATUS=$(extract_status "$RESPONSE")
BODY=$(extract_body "$RESPONSE")

if [ "$STATUS" = "200" ]; then
    log_success "Health check passed (HTTP $STATUS)"
else
    log_error "Health check failed (HTTP $STATUS)"
fi

# ----------------------------------------------------------------------------
# Test 2: Platform Registry
# ----------------------------------------------------------------------------
log_section "2. Platform Registry"
log_test "GET /api/platforms returns exactly 7 exchanges"

RESPONSE=$(api_call GET "/api/platforms" "" "")
STATUS=$(extract_status "$RESPONSE")
BODY=$(extract_body "$RESPONSE")

if [ "$STATUS" = "200" ]; then
    # Check platform count
    PLATFORM_COUNT=$(echo "$BODY" | grep -o '"id"' | wc -l)
    
    if [ "$PLATFORM_COUNT" = "7" ]; then
        log_success "Platform registry returns exactly 7 exchanges"
    else
        log_error "Platform registry returns $PLATFORM_COUNT exchanges (expected 7)"
    fi
    
    # Verify all 7 supported exchanges are present
    PLATFORMS_OK=true
    for platform in luno binance kucoin bybit kraken bitget gate; do
        if echo "$BODY" | grep -q "\"$platform\""; then
            echo "  ✓ Platform '$platform' present"
        else
            echo "  ✗ Platform '$platform' MISSING"
            PLATFORMS_OK=false
        fi
    done
    
    if [ "$PLATFORMS_OK" = true ]; then
        log_success "All 7 platforms (luno, binance, kucoin, bybit, kraken, bitget, gate) are present"
    else
        log_error "Not all required platforms are present"
    fi
else
    log_error "Platform registry failed (HTTP $STATUS)"
fi

# ----------------------------------------------------------------------------
# Test 3: User Registration with Invite Code
# ----------------------------------------------------------------------------
log_section "3. User Registration"
log_test "POST /api/auth/register with invite code and name->first_name mapping"

# Test with first_name field
REGISTER_DATA=$(cat <<EOF
{
  "email": "$TEST_EMAIL",
  "password": "$TEST_PASSWORD",
  "first_name": "$TEST_FIRST_NAME",
  "invite_code": "$INVITE_CODE"
}
EOF
)

RESPONSE=$(api_call POST "/api/auth/register" "$REGISTER_DATA" "")
STATUS=$(extract_status "$RESPONSE")
BODY=$(extract_body "$RESPONSE")

if [ "$STATUS" = "200" ]; then
    # Verify response structure
    if echo "$BODY" | grep -q '"access_token"' && \
       echo "$BODY" | grep -q '"token_type"' && \
       echo "$BODY" | grep -q '"user"'; then
        log_success "Registration successful with correct response structure"
        
        # Extract token for future tests
        ACCESS_TOKEN=$(echo "$BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
        
        if [ -n "$ACCESS_TOKEN" ]; then
            log_success "Access token extracted: ${ACCESS_TOKEN:0:20}..."
        else
            log_error "Could not extract access token"
        fi
        
        # Verify no password fields in response
        if echo "$BODY" | grep -qE '"(password|password_hash|hashed_password)"[ ]*:'; then
            log_error "Response contains password fields (security violation)"
        else
            log_success "No password fields in response (secure)"
        fi
        
        # Verify token_type is "bearer"
        if echo "$BODY" | grep -q '"token_type":"bearer"'; then
            log_success "Token type is 'bearer' (correct)"
        else
            log_error "Token type is not 'bearer'"
        fi
        
    else
        log_error "Registration response missing required fields"
    fi
else
    log_error "Registration failed (HTTP $STATUS)"
    echo "Response: $BODY"
fi

# ----------------------------------------------------------------------------
# Test 4: User Login
# ----------------------------------------------------------------------------
log_section "4. User Login"
log_test "POST /api/auth/login"

if [ -z "${ACCESS_TOKEN:-}" ]; then
    log_error "Skipping login test - no token from registration"
else
    LOGIN_DATA=$(cat <<EOF
{
  "email": "$TEST_EMAIL",
  "password": "$TEST_PASSWORD"
}
EOF
)

    RESPONSE=$(api_call POST "/api/auth/login" "$LOGIN_DATA" "")
    STATUS=$(extract_status "$RESPONSE")
    BODY=$(extract_body "$RESPONSE")
    
    if [ "$STATUS" = "200" ]; then
        if echo "$BODY" | grep -q '"access_token"'; then
            log_success "Login successful"
        else
            log_error "Login response missing access_token"
        fi
    else
        log_error "Login failed (HTTP $STATUS)"
    fi
fi

# ----------------------------------------------------------------------------
# Test 5: Profile Endpoint
# ----------------------------------------------------------------------------
log_section "5. User Profile"
log_test "GET /api/auth/profile"

if [ -z "${ACCESS_TOKEN:-}" ]; then
    log_error "Skipping profile test - no auth token"
else
    RESPONSE=$(api_call GET "/api/auth/profile" "" "$ACCESS_TOKEN")
    STATUS=$(extract_status "$RESPONSE")
    BODY=$(extract_body "$RESPONSE")
    
    if [ "$STATUS" = "200" ]; then
        # Verify no password fields leaked
        if echo "$BODY" | grep -qE '"(password|password_hash|hashed_password)"[ ]*:'; then
            log_error "Profile response contains password fields (security violation)"
        else
            log_success "Profile retrieved without password leaks"
        fi
    else
        log_error "Profile retrieval failed (HTTP $STATUS)"
    fi
fi

# ----------------------------------------------------------------------------
# Test 6: API Key Management (if enabled)
# ----------------------------------------------------------------------------
log_section "6. API Key Management"
log_test "API key endpoints are accessible"

if [ -z "${ACCESS_TOKEN:-}" ]; then
    log_error "Skipping API key tests - no auth token"
else
    # Test getting keys for a platform
    RESPONSE=$(api_call GET "/api/user/api-keys/luno" "" "$ACCESS_TOKEN")
    STATUS=$(extract_status "$RESPONSE")
    
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "404" ]; then
        log_success "API key endpoint accessible (HTTP $STATUS)"
    else
        log_error "API key endpoint failed (HTTP $STATUS)"
    fi
fi

# ----------------------------------------------------------------------------
# Test 7: Realtime Connectivity Check
# ----------------------------------------------------------------------------
log_section "7. Realtime Connectivity"
log_test "Realtime endpoint is available"

# Check if realtime endpoint exists
RESPONSE=$(api_call GET "/api/realtime/status" "" "" || echo "ENDPOINT_NOT_FOUND")

if [ "$RESPONSE" != "ENDPOINT_NOT_FOUND" ]; then
    STATUS=$(extract_status "$RESPONSE")
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "401" ]; then
        log_success "Realtime endpoint exists (HTTP $STATUS)"
    else
        log_error "Realtime endpoint error (HTTP $STATUS)"
    fi
else
    log_info "Realtime endpoint not found (optional feature)"
fi

# ----------------------------------------------------------------------------
# Test 8: Bodyguard Status
# ----------------------------------------------------------------------------
log_section "8. Bodyguard Status"
log_test "Bodyguard status endpoint"

if [ -z "${ACCESS_TOKEN:-}" ]; then
    log_error "Skipping bodyguard test - no auth token"
else
    # Check multiple possible bodyguard endpoints
    BODYGUARD_FOUND=false
    
    for endpoint in "/api/system/bodyguard" "/api/system/status"; do
        RESPONSE=$(api_call GET "$endpoint" "" "$ACCESS_TOKEN" || echo "NOT_FOUND")
        if [ "$RESPONSE" != "NOT_FOUND" ]; then
            STATUS=$(extract_status "$RESPONSE")
            if [ "$STATUS" = "200" ]; then
                log_success "Bodyguard status accessible at $endpoint"
                BODYGUARD_FOUND=true
                break
            fi
        fi
    done
    
    if [ "$BODYGUARD_FOUND" = false ]; then
        log_info "Bodyguard endpoint not found (may be disabled)"
    fi
fi

# ============================================================================
# SUMMARY
# ============================================================================
log_section "SMOKE TEST SUMMARY"

echo ""
echo "Tests Run:    $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}═══════════════════════════════════════${NC}"
    echo -e "${GREEN}   SMOKE TEST RESULT: ✅ PASS${NC}"
    echo -e "${GREEN}═══════════════════════════════════════${NC}"
    echo ""
    log_success "All critical functionality validated"
    log_success "System is ready for production deployment"
    exit 0
else
    echo -e "${RED}═══════════════════════════════════════${NC}"
    echo -e "${RED}   SMOKE TEST RESULT: ❌ FAIL${NC}"
    echo -e "${RED}═══════════════════════════════════════${NC}"
    echo ""
    echo -e "${RED}Failed tests:${NC}"
    for failed_test in "${FAILED_TESTS[@]}"; do
        echo -e "${RED}  • $failed_test${NC}"
    done
    echo ""
    log_error "System is NOT ready for production"
    log_error "Fix failed tests before deploying"
    exit 1
fi
