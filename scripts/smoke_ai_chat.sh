#!/bin/bash
set -euo pipefail

# Smoke test for AI chat endpoint.
# Usage:
#   ./scripts/smoke_ai_chat.sh <BASE_URL> <TOKEN>
#   EMAIL=you@example.com PASSWORD=secret ./scripts/smoke_ai_chat.sh <BASE_URL>

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
TOKEN="${2:-${TOKEN:-}}"
EMAIL="${EMAIL:-${AMARKTAI_USER_EMAIL:-}}"
PASSWORD="${PASSWORD:-${AMARKTAI_USER_PASSWORD:-}}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
  echo -e "${YELLOW}[INFO]${NC} $1"
}

print_pass() {
  echo -e "${GREEN}[PASS]${NC} $1"
}

print_fail() {
  echo -e "${RED}[FAIL]${NC} $1"
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
    print_fail "No auth token available. Provide TOKEN or EMAIL/PASSWORD."
    exit 1
  fi
}

login_if_needed

print_info "Checking OpenAI key status..."
keys_status=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/keys/status")
openai_status=$(python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    data = {}
status = data.get("status_map", {}).get("openai", {}).get("status")
print(status or "")
PY
<<< "$keys_status")

chat_payload=$(python3 - <<'PY'
import json
print(json.dumps({
    "content": "Hello AI, quick smoke test.",
    "request_action": False
}))
PY
)

print_info "Calling /api/ai/chat..."
tmpfile=$(mktemp)
status_code=$(curl -s -o "$tmpfile" -w "%{http_code}" -X POST "$BASE_URL/api/ai/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$chat_payload" || true)

response_body=$(cat "$tmpfile")
rm -f "$tmpfile"

success=$(python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    data = {}
print("true" if data.get("success") is True else "false")
PY
<<< "$response_body")

if [ "$openai_status" = "configured_valid" ] || [ "$openai_status" = "configured_untested" ]; then
  if [ "$status_code" = "200" ] && [ "$success" = "true" ]; then
    print_pass "AI chat succeeded with configured OpenAI key."
  else
    print_fail "AI chat failed unexpectedly (HTTP $status_code): $response_body"
    exit 1
  fi
else
  if [ "$status_code" = "400" ] || [ "$status_code" = "409" ]; then
    if echo "$response_body" | grep -qi "openai"; then
      print_pass "AI chat returned clear error when OpenAI key missing."
    else
      print_fail "AI chat error response did not mention OpenAI key: $response_body"
      exit 1
    fi
  else
    print_fail "Expected AI chat error for missing key (HTTP 400/409), got HTTP $status_code."
    exit 1
  fi
fi
