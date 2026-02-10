#!/bin/bash
# Smoke test for admin overview endpoint (VPS runnable).

set -euo pipefail

API_URL="${1:-${AMARKTAI_API_URL:-http://localhost:8000}}"
EMAIL="${2:-${AMARKTAI_ADMIN_EMAIL:-}}"
PASSWORD="${3:-${AMARKTAI_ADMIN_PASSWORD:-}}"

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  echo "Usage: $0 <api_url> <admin_email> <admin_password>"
  echo "Or set AMARKTAI_API_URL, AMARKTAI_ADMIN_EMAIL, AMARKTAI_ADMIN_PASSWORD."
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
  echo "Admin login failed: $login_response"
  exit 1
fi

auth_header=("-H" "Authorization: Bearer $TOKEN")

response=$(curl -s -w "\n%{http_code}" "${auth_header[@]}" "$API_URL/api/admin/overview")
body=$(echo "$response" | sed '$d')
code=$(echo "$response" | tail -n1)

if [ "$code" != "200" ]; then
  echo "FAIL: GET /api/admin/overview (HTTP $code)"
  echo "$body"
  exit 1
fi

if ! echo "$body" | jq -e 'type=="object" and has("success") and has("stats") and (.stats|type=="object") and (.stats|has("users") and has("bots") and has("trades") and has("system_mode"))' >/dev/null 2>&1; then
  echo "FAIL: /api/admin/overview response shape mismatch"
  echo "$body"
  exit 1
fi

echo "PASS: GET /api/admin/overview returns expected stats"
echo "✅ smoke_admin.sh PASS"
