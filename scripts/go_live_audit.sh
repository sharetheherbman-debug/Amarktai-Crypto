#!/bin/bash
# Go-Live Audit Script - Paper mode readiness checks

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${AMARKTAI_EMAIL:-}"
PASSWORD="${AMARKTAI_PASSWORD:-}"
FRONTEND_DIR="${FRONTEND_DIR:-frontend}"

PASS_COUNT=0
FAIL_COUNT=0

log_pass() {
  echo -e "${GREEN}✓${NC} $1"
  ((PASS_COUNT++))
}

log_fail() {
  echo -e "${RED}✗${NC} $1"
  ((FAIL_COUNT++))
}

echo "========================================="
echo "Amarktai Network - Go Live Audit"
echo "========================================="

echo "Checking backend health..."
if curl -fsS "$BASE_URL/health" >/dev/null; then
  log_pass "Backend /health"
else
  log_fail "Backend /health"
fi

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  log_fail "AMARKTAI_EMAIL and AMARKTAI_PASSWORD must be set"
  echo "Set credentials and re-run. Example:"
  echo "  AMARKTAI_EMAIL=user@example.com AMARKTAI_PASSWORD=secret ./scripts/go_live_audit.sh"
  exit 1
fi

echo "Logging in..."
login_response=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"${EMAIL}\", \"password\": \"${PASSWORD}\"}")

token=$(python3 - <<'PY'
import json, sys
data = json.loads(sys.stdin.read() or "{}")
print(data.get("access_token", ""))
PY
<<<"$login_response")

if [ -z "$token" ]; then
  log_fail "Login failed (no access_token)"
  exit 1
fi
log_pass "Login OK"

auth_get() {
  local endpoint="$1"
  curl -fsS -H "Authorization: Bearer $token" "$BASE_URL$endpoint" >/dev/null
}

auth_post() {
  local endpoint="$1"
  local body="$2"
  curl -fsS -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -X POST "$BASE_URL$endpoint" -d "$body"
}

echo "Calling authenticated endpoints..."
for endpoint in \
  "/api/system/status" \
  "/api/system/mode" \
  "/api/bots" \
  "/api/bots/status" \
  "/api/wallet/paper" \
  "/api/diagnostics/autopilot" \
  "/api/diagnostics/accounting"
do
  if auth_get "$endpoint"; then
    log_pass "$endpoint"
  else
    log_fail "$endpoint"
  fi
done

echo "Testing AI chat response..."
ai_response=$(auth_post "/api/ai/chat" "{\"message\": \"Audit ping\", \"context\": \"audit\"}" || true)
ai_content=$(python3 - <<'PY'
import json, sys
data = json.loads(sys.stdin.read() or "{}")
print(data.get("content", "") or data.get("message", "") or "")
PY
<<<"$ai_response")

if [ -n "$ai_content" ]; then
  log_pass "AI chat returned content"
else
  log_fail "AI chat returned empty response"
fi

echo "Building frontend..."
if (cd "$FRONTEND_DIR" && npm ci && npm run build); then
  log_pass "Frontend build"
else
  log_fail "Frontend build"
fi

echo "========================================="
echo "Audit Summary: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
echo "========================================="

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
