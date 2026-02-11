#!/bin/bash
set -euo pipefail

# Section-by-section smoke tests for go-live readiness.
# Usage:
#   ./scripts/smoke_sections.sh <BASE_URL> <TOKEN>
#   EMAIL=you@example.com PASSWORD=secret ./scripts/smoke_sections.sh <BASE_URL>

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
TOKEN="${2:-${TOKEN:-}}"
EMAIL="${EMAIL:-${AMARKTAI_USER_EMAIL:-}}"
PASSWORD="${PASSWORD:-${AMARKTAI_USER_PASSWORD:-}}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
CRITICAL_FAILED=0

print_test() {
  echo -e "${BLUE}[TEST]${NC} $1"
}

print_pass() {
  echo -e "${GREEN}[PASS]${NC} $1"
  PASSED=$((PASSED + 1))
}

print_fail() {
  echo -e "${RED}[FAIL]${NC} $1"
  FAILED=$((FAILED + 1))
  CRITICAL_FAILED=1
}

print_info() {
  echo -e "${YELLOW}[INFO]${NC} $1"
}

request() {
  local method="$1"
  local path="$2"
  local auth="$3"
  local tmpfile
  tmpfile=$(mktemp)
  local status
  if [ "$auth" = "auth" ]; then
    status=$(curl -s -o "$tmpfile" -w "%{http_code}" -X "$method" "$BASE_URL$path" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" || true)
  else
    status=$(curl -s -o "$tmpfile" -w "%{http_code}" -X "$method" "$BASE_URL$path" \
      -H "Content-Type: application/json" || true)
  fi
  echo "$status" > "${tmpfile}.code"
  echo "$tmpfile"
}

login_if_needed() {
  if [ -n "$TOKEN" ]; then
    return
  fi

  if [ -n "$EMAIL" ] && [ -n "$PASSWORD" ]; then
    print_info "Logging in to obtain token..."
    login_payload=$(EMAIL="$EMAIL" PASSWORD="$PASSWORD" python3 - <<'PY'
import json
import os

print(json.dumps({
    "email": os.environ.get("EMAIL", ""),
    "password": os.environ.get("PASSWORD", "")
}))
PY
)
    response=$(curl -s -X POST "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d "$login_payload")
    TOKEN=$(python3 - <<PY
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    data = {}
print(data.get("token") or data.get("access_token") or "")
PY
<<< "$response")
  fi

  if [ -z "$TOKEN" ]; then
    print_info "No token available. Provide TOKEN or EMAIL/PASSWORD for authenticated tests."
  fi
}

login_if_needed

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Amarktai Section Smoke Test${NC}"
echo -e "${BLUE}============================================${NC}"
echo "Base URL: $BASE_URL"
echo ""

print_test "Health: GET /api/health/ping"
tmp=$(request GET "/api/health/ping" "public")
code=$(cat "${tmp}.code")
body=$(cat "$tmp")
if [ "$code" = "200" ]; then
  print_pass "Health endpoint reachable"
else
  print_fail "Health endpoint failed (HTTP $code): $body"
fi
rm -f "$tmp" "${tmp}.code"

if [ -z "$TOKEN" ]; then
  print_fail "Auth token missing (required for remaining sections)"
else
  print_test "Auth: GET /api/auth/me"
  tmp=$(request GET "/api/auth/me" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Auth check OK"
  else
    print_fail "Auth check failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "System Status: GET /api/system/status"
  tmp=$(request GET "/api/system/status" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ] && echo "$body" | grep -q "system_modes"; then
    print_pass "System status OK"
  else
    print_fail "System status failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Keys: GET /api/keys/status"
  tmp=$(request GET "/api/keys/status" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Keys status OK"
  else
    print_fail "Keys status failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Wallet: GET /api/wallet/health"
  tmp=$(request GET "/api/wallet/health" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Wallet health OK"
  else
    print_fail "Wallet health failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Prices: GET /api/prices/live"
  tmp=$(request GET "/api/prices/live" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Prices endpoint OK"
  else
    print_fail "Prices endpoint failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Bots: GET /api/bots/status"
  tmp=$(request GET "/api/bots/status" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Bots status OK"
  else
    print_fail "Bots status failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Trades: GET /api/trades/recent?limit=5"
  tmp=$(request GET "/api/trades/recent?limit=5" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Trades endpoint OK"
  else
    print_fail "Trades endpoint failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Analytics: GET /api/analytics/performance_summary"
  tmp=$(request GET "/api/analytics/performance_summary" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Analytics summary OK"
  else
    print_fail "Analytics summary failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Countdown: GET /api/analytics/countdown-to-million"
  tmp=$(request GET "/api/analytics/countdown-to-million" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Countdown endpoint OK"
  else
    print_fail "Countdown endpoint failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "Realtime diagnostics: GET /api/diagnostics/realtime"
  tmp=$(request GET "/api/diagnostics/realtime" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ] && echo "$body" | grep -q "ws_connected"; then
    print_pass "Realtime diagnostics OK"
  else
    print_fail "Realtime diagnostics failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"

  print_test "WebSocket handshake"
  if TOKEN="$TOKEN" BASE_URL="$BASE_URL" python3 - <<'PY'
import asyncio
import sys
import os
import ssl
import websockets
import urllib.parse

base_url = os.environ.get("BASE_URL", "")
token = os.environ.get("TOKEN", "")
encoded_token = urllib.parse.quote(token, safe="")
ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + f"/api/ws?token={encoded_token}"

ssl_context = None
if ws_url.startswith("wss://") and os.getenv("AMARKTAI_WS_INSECURE") == "1":
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

async def run():
    async with websockets.connect(ws_url, open_timeout=10, ssl=ssl_context) as ws:
        await asyncio.wait_for(ws.recv(), timeout=10)

asyncio.run(run())
PY
  then
    print_pass "WebSocket handshake OK"
  else
    print_fail "WebSocket handshake failed"
  fi

  print_test "Admin: GET /api/admin/system-stats"
  tmp=$(request GET "/api/admin/system-stats" "auth")
  code=$(cat "${tmp}.code")
  body=$(cat "$tmp")
  if [ "$code" = "200" ]; then
    print_pass "Admin system stats OK"
  else
    print_fail "Admin system stats failed (HTTP $code): $body"
  fi
  rm -f "$tmp" "${tmp}.code"
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ "$CRITICAL_FAILED" = "1" ]; then
  echo -e "${RED}❌ One or more critical checks failed${NC}"
  exit 1
fi

echo -e "${GREEN}✅ All critical checks passed${NC}"
exit 0
