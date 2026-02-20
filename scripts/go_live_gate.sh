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
#   0 — all endpoints returned non-404
#   1 — one or more endpoints failed or returned 404

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

# ── Step 2: Check each endpoint ──────────────────────────────────────────────
check_endpoint() {
  local label="$1"
  local method="$2"
  local path="$3"

  RESP=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "${BASE_URL}${path}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" 2>/dev/null || echo "000")

  if [ "$RESP" = "404" ] || [ "$RESP" = "000" ] || [[ "$RESP" =~ ^5 ]]; then
    echo "FAIL  [HTTP ${RESP}]  ${path}"
    FAIL=$((FAIL + 1))
    ERRORS+=("${path} -> HTTP ${RESP}")
  else
    echo "PASS  [HTTP ${RESP}]  ${path}"
    PASS=$((PASS + 1))
  fi
}

echo "── Checking endpoints ───────────────────────────────────────────────────"
check_endpoint "health/ping"        GET  "/api/health/ping"
check_endpoint "system/mode"        GET  "/api/system/mode"
check_endpoint "bots/status"        GET  "/api/bots/status"
check_endpoint "trades/recent"      GET  "/api/trades/recent?limit=10"
check_endpoint "fetchai/status"     GET  "/api/fetchai/status"
check_endpoint "admin/unlock"       POST "/api/admin/unlock"
check_endpoint "ai/chat/greeting"   POST "/api/ai/chat/greeting"
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# ── Step 3: Summary ──────────────────────────────────────────────────────────
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
