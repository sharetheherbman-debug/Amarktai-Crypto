#!/bin/bash
# Smoke test for user-facing endpoints (VPS runnable).

set -euo pipefail

API_URL="${1:-${AMARKTAI_API_URL:-http://localhost:8000}}"
EMAIL="${2:-${AMARKTAI_USER_EMAIL:-}}"
PASSWORD="${3:-${AMARKTAI_USER_PASSWORD:-}}"

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  echo "Usage: $0 <api_url> <email> <password>"
  echo "Or set AMARKTAI_API_URL, AMARKTAI_USER_EMAIL, AMARKTAI_USER_PASSWORD."
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for smoke tests."
  exit 1
fi

login_payload=$(jq -n --arg email "$EMAIL" --arg password "$PASSWORD" '{email:$email,password:$password}')
login_response=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "$login_payload")

TOKEN=$(echo "$login_response" | jq -r '.token // empty')
if [ -z "$TOKEN" ]; then
  echo "Login failed: $login_response"
  exit 1
fi

auth_header=("-H" "Authorization: Bearer $TOKEN")

check_json() {
  local endpoint=$1
  local jq_filter=$2
  local description=$3
  local response
  local body
  local code

  response=$(curl -s -w "\n%{http_code}" "${auth_header[@]}" "$API_URL$endpoint")
  body=$(echo "$response" | sed '$d')
  code=$(echo "$response" | tail -n1)

  if [ "$code" != "200" ]; then
    echo "FAIL: $description (HTTP $code)"
    echo "$body"
    exit 1
  fi

  if ! echo "$body" | jq -e "$jq_filter" >/dev/null 2>&1; then
    echo "FAIL: $description (shape mismatch)"
    echo "$body"
    exit 1
  fi

  echo "PASS: $description"
}

check_json "/api/overview" 'type=="object"' "GET /api/overview returns object"
check_json "/api/bots" 'type=="array"' "GET /api/bots returns array"
check_json "/api/bots/status" 'type=="array"' "GET /api/bots/status returns array"
check_json "/api/prices/live" 'type=="array"' "GET /api/prices/live returns array"
check_json "/api/system/mode" 'type=="object" and has("paperTrading") and has("liveTrading") and has("autopilot")' "GET /api/system/mode returns mode flags"
check_json "/api/keys/status" 'type=="object" and ((has("status_map") and (.status_map|type=="object")) or (has("keys") and (.keys|type=="array")))' "GET /api/keys/status returns status_map or keys"
check_json "/api/risk/daily-loss-lock" 'type=="object" and has("active")' "GET /api/risk/daily-loss-lock returns active flag"

echo "✅ smoke_user.sh PASS"
