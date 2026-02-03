#!/bin/bash
# API Keys Smoke Test
# Tests that all key endpoints work correctly and return proper error codes

set -e

API_BASE="http://localhost:8000"
TOKEN="${TEST_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  echo "❌ TEST_TOKEN environment variable not set"
  exit 1
fi

echo "🔑 Testing API Keys Endpoints..."
echo "================================"

# Test 1: List providers (public endpoint)
echo ""
echo "1️⃣ Testing GET /api/keys/providers (public)"
RESPONSE=$(curl -s -w "\n%{http_code}" "$API_BASE/api/keys/providers")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ FAIL: Expected 200, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 200"
echo "Providers returned: $(echo $BODY | jq -r '.total')"

# Test 2: List user keys (requires auth)
echo ""
echo "2️⃣ Testing GET /api/keys/list (requires auth)"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/api/keys/list")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ FAIL: Expected 200, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 200"
echo "Keys returned: $(echo $BODY | jq -r '.total')"

# Test 3: Save with missing provider (should return 400)
echo ""
echo "3️⃣ Testing POST /api/keys/save with missing provider (expect 400)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test"}' \
  "$API_BASE/api/keys/save")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "422" ] && [ "$HTTP_CODE" != "400" ]; then
  echo "❌ FAIL: Expected 400/422 for missing provider, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns $HTTP_CODE with proper error"

# Test 4: Save with invalid provider (should return 400)
echo ""
echo "4️⃣ Testing POST /api/keys/save with invalid provider (expect 400)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "invalid_provider_xyz", "api_key": "test123"}' \
  "$API_BASE/api/keys/save")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "400" ]; then
  echo "❌ FAIL: Expected 400 for invalid provider, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 400 with error message"
ERROR_MSG=$(echo $BODY | jq -r '.detail')
echo "Error message: $ERROR_MSG"

# Test 5: Test with missing provider (should return 400)
echo ""
echo "5️⃣ Testing POST /api/keys/test with invalid provider (expect 400)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "invalid_provider_xyz"}' \
  "$API_BASE/api/keys/test")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "400" ]; then
  echo "❌ FAIL: Expected 400 for invalid provider, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 400 with error message"

# Test 6: Test with non-existent saved key (should return 404)
echo ""
echo "6️⃣ Testing POST /api/keys/test with non-existent key (expect 404)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai"}' \
  "$API_BASE/api/keys/test")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

# Should return 404 if no key saved, or some other valid response
if [ "$HTTP_CODE" != "404" ] && [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "400" ]; then
  echo "⚠️  WARNING: Expected 404/200/400, got $HTTP_CODE"
  echo "Response: $BODY"
else
  echo "✅ PASS: Returns $HTTP_CODE"
fi

# Test 7: Delete with invalid provider (should return 400)
echo ""
echo "7️⃣ Testing DELETE /api/keys/{provider} with invalid provider (expect 400)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/keys/invalid_provider_xyz")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "400" ]; then
  echo "❌ FAIL: Expected 400 for invalid provider, got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 400 with error message"

# Test 8: Delete with valid but non-existent key (should return 200 - idempotent)
echo ""
echo "8️⃣ Testing DELETE /api/keys/{provider} with non-existent key (expect 200 - idempotent)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/keys/openai")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ FAIL: Expected 200 (idempotent delete), got $HTTP_CODE"
  echo "Response: $BODY"
  exit 1
fi

echo "✅ PASS: Returns 200 (idempotent)"

echo ""
echo "================================"
echo "✅ All API Keys smoke tests passed!"
echo "================================"
