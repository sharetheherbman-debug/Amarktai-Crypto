#!/usr/bin/env bash
# Minimal API smoke verification for go-live checks.
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
EMAIL="${2:-${AMK_EMAIL:-}}"
PASSWORD="${3:-${AMK_PASSWORD:-}}"

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  echo "Usage: $0 <BASE_URL> <EMAIL> <PASSWORD>" >&2
  echo "Or set AMK_EMAIL/AMK_PASSWORD environment variables." >&2
  exit 1
fi

expected_exchanges=(luno binance kucoin bybit kraken bitget gate)

echo "🔎 Checking /api/health/ping..."
health_status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health/ping")
if [ "$health_status" != "200" ]; then
  echo "❌ /api/health/ping expected 200, got ${health_status}" >&2
  exit 1
fi
echo "✅ /api/health/ping OK"

echo "🔐 Logging in..."
login_response=$(curl -sS -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")
token=$(echo "$login_response" | jq -r '.access_token // empty')
if [ -z "$token" ]; then
  echo "❌ Login failed or missing access_token: ${login_response}" >&2
  exit 1
fi
echo "✅ Login returned access_token"

echo "📋 Checking /api/bots/status..."
bots_status_code=$(curl -s -o /tmp/bots_status.json -w "%{http_code}" \
  -H "Authorization: Bearer ${token}" \
  "${BASE_URL}/api/bots/status")
if [ "$bots_status_code" != "200" ]; then
  echo "❌ /api/bots/status expected 200, got ${bots_status_code}" >&2
  cat /tmp/bots_status.json || true
  exit 1
fi
if ! jq -e '.bots | type=="array"' /tmp/bots_status.json >/dev/null; then
  echo "❌ /api/bots/status bots field is not an array" >&2
  cat /tmp/bots_status.json || true
  exit 1
fi
bots_count=$(jq -r '.bots | length' /tmp/bots_status.json)
if [ "$bots_count" != "0" ]; then
  echo "❌ /api/bots/status expected empty bots list on fresh system, got ${bots_count}" >&2
  exit 1
fi
echo "✅ /api/bots/status returns empty bots list"

echo "📋 Checking /api/bots/status?meta=1..."
meta_status_code=$(curl -s -o /tmp/bots_status_meta.json -w "%{http_code}" \
  -H "Authorization: Bearer ${token}" \
  "${BASE_URL}/api/bots/status?meta=1")
if [ "$meta_status_code" != "200" ]; then
  echo "❌ /api/bots/status?meta=1 expected 200, got ${meta_status_code}" >&2
  cat /tmp/bots_status_meta.json || true
  exit 1
fi
if ! jq -e '.exchange_counts and .all_exchanges' /tmp/bots_status_meta.json >/dev/null; then
  echo "❌ /api/bots/status?meta=1 missing exchange_counts/all_exchanges" >&2
  cat /tmp/bots_status_meta.json || true
  exit 1
fi
expected_json=$(printf '%s\n' "${expected_exchanges[@]}" | jq -R . | jq -s 'sort')
if ! jq -e --argjson expected "$expected_json" '.all_exchanges | sort == $expected' /tmp/bots_status_meta.json >/dev/null; then
  echo "❌ /api/bots/status?meta=1 all_exchanges mismatch" >&2
  cat /tmp/bots_status_meta.json || true
  exit 1
fi
echo "✅ /api/bots/status?meta=1 returns exchange_counts + all_exchanges"
