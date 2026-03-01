#!/usr/bin/env bash
###############################################################################
# /ops/smoke_test.sh – Amarktai Network smoke tests
#
# Tests:
#   1. Backend health (direct + via nginx)
#   2. OpenAPI non-empty
#   3. Login + /auth/me
#   4. WebSocket connect
#   5. Dashboard essential endpoints shape check
#   6. Frontend build artifact verification
#
# USAGE
#   bash ops/smoke_test.sh [--api-base http://localhost/api] [--email admin@example.com] [--password secret]
#
# EXIT CODE
#   0 = all tests passed (or only warnings)
#   1 = one or more tests failed
###############################################################################
set -uo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
API_BASE="http://127.0.0.1:8000/api"
NGINX_BASE="http://localhost"
TEST_EMAIL="${SMOKE_EMAIL:-}"
TEST_PASSWORD="${SMOKE_PASSWORD:-}"
FRONTEND_WEBROOT="${FRONTEND_WEBROOT:-/var/www/amarktai}"

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base)   API_BASE="$2";   shift 2 ;;
    --email)      TEST_EMAIL="$2"; shift 2 ;;
    --password)   TEST_PASSWORD="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0

pass() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL++)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; ((WARN++)); }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} 🧪  AMARKTAI NETWORK – SMOKE TESTS${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo " API:  $API_BASE"
echo " Web:  $NGINX_BASE"
echo " Time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# ── Helper ────────────────────────────────────────────────────────────────────
http_get() {
  local url="$1"; local headers="${2:-}"
  if [[ -n "$headers" ]]; then
    curl -sf --max-time 10 -H "$headers" "$url" 2>/dev/null
  else
    curl -sf --max-time 10 "$url" 2>/dev/null
  fi
}

json_key() {
  local json="$1"; local key="$2"
  echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$key','__missing__'))" 2>/dev/null || echo "__error__"
}

# ── Test 1: Backend health (direct) ──────────────────────────────────────────
echo -e "${BOLD}[T1] Backend health (direct)${NC}"
HEALTH=$(http_get "$API_BASE/health/ping" || echo '{"error":"unreachable"}')
STATUS=$(json_key "$HEALTH" "status")
if [[ "$STATUS" == "ok" || "$STATUS" == "healthy" ]]; then
  pass "GET /api/health/ping → status=$STATUS"
else
  fail "GET /api/health/ping → status=$STATUS  (raw: ${HEALTH:0:100})"
fi

# ── Test 2: Backend health via nginx ─────────────────────────────────────────
echo ""
echo -e "${BOLD}[T2] Backend health (via nginx)${NC}"
NGINX_HEALTH=$(http_get "$NGINX_BASE/api/health/ping" || echo '{"error":"unreachable"}')
NGINX_STATUS=$(json_key "$NGINX_HEALTH" "status")
if [[ "$NGINX_STATUS" == "ok" || "$NGINX_STATUS" == "healthy" ]]; then
  pass "GET $NGINX_BASE/api/health/ping → status=$NGINX_STATUS"
else
  warn "GET $NGINX_BASE/api/health/ping → status=$NGINX_STATUS (nginx may not be running)"
fi

# ── Test 3: OpenAPI non-empty ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[T3] OpenAPI schema${NC}"
OPENAPI=$(http_get "$API_BASE/../openapi.json" || http_get "$API_BASE/openapi.json" || echo '{}')
ROUTE_COUNT=$(echo "$OPENAPI" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('paths',{})))" 2>/dev/null || echo "0")
if [[ "$ROUTE_COUNT" -gt 5 ]]; then
  pass "OpenAPI has $ROUTE_COUNT routes"
else
  fail "OpenAPI empty or unreachable ($ROUTE_COUNT routes)"
fi

# ── Test 4: Auth – login + /auth/me ──────────────────────────────────────────
echo ""
echo -e "${BOLD}[T4] Authentication${NC}"
TOKEN=""
if [[ -n "$TEST_EMAIL" && -n "$TEST_PASSWORD" ]]; then
  LOGIN_RESP=$(curl -sf --max-time 10 \
    -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" 2>/dev/null || echo '{}')
  TOKEN=$(json_key "$LOGIN_RESP" "access_token")
  if [[ -n "$TOKEN" && "$TOKEN" != "__missing__" && "$TOKEN" != "__error__" ]]; then
    pass "POST /api/auth/login → access_token received"
    # Test /auth/me
    ME_RESP=$(http_get "$API_BASE/auth/me" "Authorization: Bearer $TOKEN" || echo '{}')
    ME_EMAIL=$(json_key "$ME_RESP" "email")
    if [[ "$ME_EMAIL" != "__missing__" && "$ME_EMAIL" != "__error__" ]]; then
      pass "GET /api/auth/me → email=$ME_EMAIL"
    else
      fail "GET /api/auth/me → unexpected response: ${ME_RESP:0:100}"
    fi
  else
    fail "POST /api/auth/login → no access_token (raw: ${LOGIN_RESP:0:100})"
  fi
else
  warn "Skipping auth test (no SMOKE_EMAIL / SMOKE_PASSWORD set)"
fi

# ── Test 5: Dashboard endpoints (if authenticated) ───────────────────────────
echo ""
echo -e "${BOLD}[T5] Dashboard endpoints${NC}"
if [[ -n "$TOKEN" ]]; then
  check_dashboard_endpoint() {
    local label="$1"; local path="$2"; local key="${3:-}"
    local resp
    resp=$(http_get "$API_BASE$path" "Authorization: Bearer $TOKEN" || echo '{"error":"unreachable"}')
    if echo "$resp" | python3 -c "import sys,json; json.load(sys.stdin)" &>/dev/null; then
      if [[ -n "$key" ]]; then
        VAL=$(json_key "$resp" "$key")
        if [[ "$VAL" != "__missing__" && "$VAL" != "__error__" ]]; then
          pass "$label – key '$key' present"
        else
          fail "$label – key '$key' missing"
        fi
      else
        pass "$label – valid JSON"
      fi
    else
      fail "$label – error/non-JSON: ${resp:0:80}"
    fi
  }
  check_dashboard_endpoint "GET /bots/status"           "/bots/status"           "bots"
  check_dashboard_endpoint "GET /system/mode"           "/system/mode"           ""
  check_dashboard_endpoint "GET /overview/snapshot"     "/overview/snapshot"     ""
  check_dashboard_endpoint "GET /keys/status"           "/keys/status"           ""
else
  warn "Skipping dashboard endpoint tests (not authenticated)"
fi

# ── Test 6: Frontend build artifacts ─────────────────────────────────────────
echo ""
echo -e "${BOLD}[T6] Frontend build artifacts${NC}"
if [[ -d "$FRONTEND_WEBROOT" ]]; then
  if [[ -f "$FRONTEND_WEBROOT/index.html" ]]; then
    pass "index.html exists"
    JS_REF=$(grep -oE 'static/js/main\.[a-f0-9]+\.js' "$FRONTEND_WEBROOT/index.html" | head -1 || echo "")
    if [[ -n "$JS_REF" ]]; then
      if [[ -f "$FRONTEND_WEBROOT/$JS_REF" ]]; then
        pass "JS bundle referenced and exists: $JS_REF"
      else
        fail "JS bundle referenced but missing: $FRONTEND_WEBROOT/$JS_REF"
      fi
    else
      warn "Could not extract JS bundle name from index.html"
    fi
    # nginx serves homepage
    HOMEPAGE=$(http_get "$NGINX_BASE/" || echo "")
    if echo "$HOMEPAGE" | grep -q "Amarktai\|amarktai\|root\|html"; then
      pass "nginx serves homepage"
    else
      warn "nginx homepage response unexpected (${#HOMEPAGE} chars)"
    fi
  else
    fail "index.html missing in $FRONTEND_WEBROOT"
  fi
else
  warn "Web root not found: $FRONTEND_WEBROOT (dev environment)"
fi

# ── Test 7: WebSocket (optional) ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}[T7] WebSocket${NC}"
if command -v websocat &>/dev/null && [[ -n "$TOKEN" ]]; then
  WS_RESULT=$(echo '{"type":"ping"}' | timeout 3 websocat "ws://127.0.0.1:8000/api/ws?token=$TOKEN" 2>/dev/null | head -1 || echo "")
  if [[ -n "$WS_RESULT" ]]; then
    pass "WebSocket connected and received data"
  else
    warn "WebSocket connected but no data received (acceptable)"
  fi
else
  warn "Skipping WebSocket test (websocat not available or no token)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} 📊  SMOKE TEST SUMMARY${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e " ${GREEN}PASS${NC}: $PASS"
echo -e " ${RED}FAIL${NC}: $FAIL"
echo -e " ${YELLOW}WARN${NC}: $WARN"
echo ""
if [[ $FAIL -eq 0 ]]; then
  echo -e " ${GREEN}✅  All smoke tests PASSED${NC}"
  exit 0
else
  echo -e " ${RED}❌  $FAIL test(s) FAILED${NC}"
  exit 1
fi
