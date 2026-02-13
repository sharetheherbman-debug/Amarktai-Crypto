#!/bin/bash
set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

echo "Running frontend + backend smoke checks"

echo "✅ Health check"
curl -sf "$BASE_URL/api/health/ping" | grep -q "pong"

echo "✅ Login and token"
TOKEN_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null)
HTTP_STATUS=$(echo "$TOKEN_RESPONSE" | grep "HTTP_STATUS:" | cut -d':' -f2)
RESPONSE_BODY=$(echo "$TOKEN_RESPONSE" | sed '/HTTP_STATUS:/d')
ACCESS_TOKEN=$(echo "$RESPONSE_BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ] || [ "$HTTP_STATUS" != "200" ]; then
  echo "❌ Login failed"
  echo "$RESPONSE_BODY"
  exit 1
fi

echo "✅ Authed overview/system endpoints"
curl -sf "$BASE_URL/api/overview/snapshot" -H "Authorization: Bearer $ACCESS_TOKEN" > /dev/null
curl -sf "$BASE_URL/api/system/status" -H "Authorization: Bearer $ACCESS_TOKEN" | grep -q "system_modes"
curl -sf "$BASE_URL/api/system/mode" -H "Authorization: Bearer $ACCESS_TOKEN" | grep -q "mode"

echo "✅ Chat missing key response (if key is not configured)"
CHAT_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/chat/message" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"status","request_action":true}' 2>/dev/null || echo "{}")

if echo "$CHAT_RESPONSE" | grep -q "OPENAI_KEY_MISSING"; then
  echo "✅ OPENAI_KEY_MISSING returned"
else
  echo "⚠️ OPENAI_KEY_MISSING not returned (key may be configured)"
fi

echo "✅ Autonomy status endpoint"
curl -sf "$BASE_URL/api/autonomy/status" -H "Authorization: Bearer $ACCESS_TOKEN" | grep -q "\"subsystems\""

echo "✅ Frontend build"
cd frontend
npm run build
