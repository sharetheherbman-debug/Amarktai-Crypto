#!/usr/bin/env bash
#
# smoke_test.sh
#
# Perform a quick health check against a running Amarktai instance.  This
# script verifies that the core API endpoints are reachable and respond
# with HTTP 200.  It can be executed locally or on a remote server by
# setting the `BASE_URL` environment variable.

set -euo pipefail

BASE_URL=${BASE_URL:-"http://localhost:8000/api"}

echo "🔍 Running Amarktai smoke tests against $BASE_URL"

fail_count=0

check() {
  local name="$1"
  local endpoint="$2"
  if curl -sSf "$BASE_URL$endpoint" > /dev/null; then
    echo "✅ $name OK ($endpoint)"
  else
    echo "❌ $name FAILED ($endpoint)"
    fail_count=$((fail_count+1))
  fi
}

# Health and ping endpoints
check "Health ping" "/health/ping"
check "System ping" "/system/ping"
check "Trades ping" "/trades/ping"

# OpenAPI schema should be available
if curl -sSf "$BASE_URL/../openapi.json" > /dev/null; then
  echo "✅ OpenAPI schema available"
else
  echo "❌ OpenAPI schema missing"
  fail_count=$((fail_count+1))
fi

# Summary
if [ "$fail_count" -eq 0 ]; then
  echo "🎉 All smoke tests passed!"
else
  echo "⚠️ $fail_count smoke test(s) failed"
  exit 1
fi