#!/bin/bash
set -euo pipefail

# Smoke test for AI chat endpoint.
# Usage:
#   ./scripts/smoke_ai_chat.sh <BASE_URL> <TOKEN>
#   AMK_EMAIL=you@example.com AMK_PASSWORD=secret ./scripts/smoke_ai_chat.sh <BASE_URL>

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
TOKEN="${2:-${TOKEN:-}}"
EMAIL="${3:-${AMK_EMAIL:-}}"
PASSWORD="${4:-${AMK_PASSWORD:-}}"

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
    print_fail "No auth token available. Provide TOKEN or AMK_EMAIL/AMK_PASSWORD."
    exit 1
  fi
}

login_if_needed

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

content_length=$(python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    data = {}
content = data.get("content") or ""
print(len(content.strip()))
PY
<<< "$response_body")

if [ "$status_code" = "200" ] && [ "$success" = "true" ] && [ "$content_length" -gt 0 ]; then
  print_pass "AI chat succeeded with configured OpenAI key."
else
  print_fail "AI chat failed (HTTP $status_code). Ensure OpenAI key is saved and tested. Response: $response_body"
  exit 1
fi
