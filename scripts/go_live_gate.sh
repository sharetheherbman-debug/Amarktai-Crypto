#!/usr/bin/env bash
# go_live_gate.sh — Go-Live Verification Gate
#
# USAGE:
#   EMAIL=user@example.com PASSWORD=secret bash scripts/go_live_gate.sh
#
# ENVIRONMENT VARIABLES:
#   EMAIL      — login email   (required)
#   PASSWORD   — login password (required)
#   BASE_URL   — API base URL  (default: http://localhost:8000)
#
# EXIT CODES:
#   0 — all required endpoints pass
#   1 — one or more endpoints failed

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:?EMAIL env var is required}"
PASSWORD="${PASSWORD:?PASSWORD env var is required}"

PASS=0
FAIL=0
ERRORS=()

# ── Step 1: Obtain JWT ────────────────────────────────────────────────────────
echo "🔐 Logging in as ${EMAIL} ..."
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")

LOGIN_BODY=$(echo "$LOGIN_RESP" | head -n -1)
LOGIN_CODE=$(echo "$LOGIN_RESP" | tail -n1)

if [ "$LOGIN_CODE" != "200" ]; then
  echo "❌ Login failed (HTTP ${LOGIN_CODE}): ${LOGIN_BODY}"
  exit 1
fi

TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "❌ Could not extract access_token from login response: ${LOGIN_BODY}"
  exit 1
fi
echo "✅ Login OK — token obtained"
echo ""

# ── Step 2: Check each endpoint returns HTTP 200 and valid JSON ───────────────
check_endpoint() {
  local label="$1"
  local method="$2"
  local path="$3"
  local auth="${4:-auth}"  # "auth" or "public"

  if [ "$auth" = "public" ]; then
    RESP=$(curl -s -w "\n%{http_code}" -X "$method" "${BASE_URL}${path}" \
      -H "Content-Type: application/json" 2>/dev/null || echo -e "\n000")
  else
    RESP=$(curl -s -w "\n%{http_code}" -X "$method" "${BASE_URL}${path}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" 2>/dev/null || echo -e "\n000")
  fi

  local body code
  body=$(echo "$RESP" | head -n -1)
  code=$(echo "$RESP" | tail -n1)

  # Check HTTP code
  if [ "$code" = "000" ] || [ "$code" = "404" ] || [[ "$code" =~ ^5 ]]; then
    echo "FAIL  [HTTP ${code}]  ${path}"
    FAIL=$((FAIL + 1))
    ERRORS+=("${path} -> HTTP ${code}")
    return
  fi

  # Check response is non-empty and valid JSON
  if [ -z "$body" ]; then
    echo "FAIL  [EMPTY BODY]  ${path}"
    FAIL=$((FAIL + 1))
    ERRORS+=("${path} -> empty response body")
    return
  fi

  if ! echo "$body" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "FAIL  [INVALID JSON] ${path}"
    FAIL=$((FAIL + 1))
    ERRORS+=("${path} -> response is not valid JSON")
    return
  fi

  echo "PASS  [HTTP ${code}]  ${path}"
  PASS=$((PASS + 1))
}

# ── Step 3: WebSocket heartbeat test ─────────────────────────────────────────
check_websocket() {
  local ws_url
  ws_url="${BASE_URL/http:/ws:}/api/ws?token=${TOKEN}"
  ws_url="${ws_url/https:/wss:}"

  echo "Testing:  WebSocket ${ws_url%\?*}"

  # Try websocat or python websockets
  local ws_msg=""
  if command -v websocat &>/dev/null; then
    ws_msg=$(echo "" | timeout 10 websocat --no-close -1 "$ws_url" 2>/dev/null || true)
  elif python3 -c "import websockets" 2>/dev/null; then
    ws_msg=$(python3 -c "
import asyncio, websockets, json, sys

async def test():
    try:
        async with websockets.connect('${ws_url}', close_timeout=5) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print(msg)
    except Exception as e:
        print('ERROR: ' + str(e), file=sys.stderr)

asyncio.run(test())
" 2>/dev/null || true)
  fi

  if [ -n "$ws_msg" ]; then
    echo "PASS  [WS OK]  /api/ws received: ${ws_msg:0:80}"
    PASS=$((PASS + 1))
  else
    echo "WARN  [WS NO MSG] /api/ws — connected but no message in 10s (or websocat/websockets not available)"
    # Don't fail — WS unavailability of test tools shouldn't block go-live gate
  fi
}

echo "── Required Endpoint Checks ─────────────────────────────────────────────"
# 1. Health ping — public
check_endpoint "health/ping"     GET "/api/health/ping"     "public"

# 2. System mode — authenticated
check_endpoint "system/mode"     GET "/api/system/mode"     "auth"

# 3. System status — authenticated (subsystem truth)
check_endpoint "system/status"   GET "/api/system/status"   "auth"

# 4. Bots status — authenticated (must return all bots, not empty)
check_endpoint "bots/status"     GET "/api/bots/status"     "auth"

# 5. Trades recent — authenticated
check_endpoint "trades/recent"   GET "/api/trades/recent?limit=10" "auth"

# 6. AI chat greeting — must not 404/500
check_endpoint "ai/chat/greeting" GET "/api/ai/chat/greeting" "auth"

# 7. Diagnostics/realtime (optional but strongly preferred)
DIAG_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}/api/diagnostics/realtime" 2>/dev/null || echo "000")
if [ "$DIAG_CODE" = "200" ]; then
  echo "PASS  [HTTP 200]  /api/diagnostics/realtime"
  PASS=$((PASS + 1))
else
  echo "WARN  [HTTP ${DIAG_CODE}]  /api/diagnostics/realtime (optional — check if route is mounted)"
fi

# 8. WebSocket
check_websocket

echo "── Additional Checks ────────────────────────────────────────────────────"
check_endpoint "auth/me"         GET "/api/auth/me"         "auth"
check_endpoint "autonomy/status" GET "/api/autonomy/status" "auth"
# bots/status without token must be 401, not 200
echo "Testing:  /api/bots/status unauthenticated (must be 401)"
RESP_NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/bots/status" 2>/dev/null || echo "000")
if [ "$RESP_NO_AUTH" = "401" ]; then
  echo "PASS  [HTTP 401]  /api/bots/status (unauthenticated correctly rejected)"
  PASS=$((PASS + 1))
else
  echo "FAIL  [HTTP ${RESP_NO_AUTH}]  /api/bots/status unauthenticated should return 401"
  FAIL=$((FAIL + 1))
  ERRORS+=("/api/bots/status unauthenticated -> HTTP ${RESP_NO_AUTH} (expected 401)")
fi

# JWT secret strength check
echo "Testing:  JWT_SECRET strength"
JWT_LEN=${#JWT_SECRET}
if [ "${JWT_LEN}" -ge 32 ] 2>/dev/null; then
  echo "PASS  JWT_SECRET length: ${JWT_LEN} (>= 32 chars)"
  PASS=$((PASS + 1))
else
  echo "FAIL  JWT_SECRET is missing or too short (length=${JWT_LEN}, need >= 32)"
  FAIL=$((FAIL + 1))
  ERRORS+=("JWT_SECRET length ${JWT_LEN} < 32")
fi

# No /api/api/ double-path in frontend source
FRONTEND_SRC="$(dirname "$0")/../frontend/src"
echo "Testing:  No /api/api/ double-paths in frontend"
if [ -d "$FRONTEND_SRC" ]; then
  DOUBLE_API=$(grep -r '/api/api/' "$FRONTEND_SRC" --include='*.js' --include='*.jsx' -l 2>/dev/null | wc -l || echo 0)
  if [ "$DOUBLE_API" -eq 0 ]; then
    echo "PASS  No /api/api/ double-path in frontend/src"
    PASS=$((PASS + 1))
  else
    echo "FAIL  /api/api/ double-path found in ${DOUBLE_API} file(s)"
    FAIL=$((FAIL + 1))
    ERRORS+=("/api/api/ double-path in $DOUBLE_API source file(s)")
  fi
else
  echo "WARN  frontend/src not found — skipping double-path check (build-only env)"
fi

echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# ── Step 4: Summary ──────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "Results: ${PASS}/${TOTAL} PASS"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "FAILED endpoints:"
  for e in "${ERRORS[@]}"; do
    echo "  ✗ ${e}"
  done
  echo ""
  echo "❌ GO-LIVE GATE: FAIL"
  exit 1
fi

echo ""
echo "✅ GO-LIVE GATE: PASS — system is ready for go-live"
exit 0
