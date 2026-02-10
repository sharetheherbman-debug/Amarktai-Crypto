#!/usr/bin/env bash
# Contract Test Gate - Verifies critical API responses for UI parity
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
EMAIL="${AMK_EMAIL:-}"
PASSWORD="${AMK_PASSWORD:-}"
ADMIN_EMAIL="${AMK_ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${AMK_ADMIN_PASSWORD:-}"
if [ -n "${AMK_EXCHANGES:-}" ]; then
  IFS=',' read -r -a EXPECTED_EXCHANGE_IDS <<< "$AMK_EXCHANGES"
else
  EXPECTED_EXCHANGE_IDS=(luno binance kucoin bybit kraken bitget gate)
fi

fail() {
  echo "❌ $1" >&2
  exit 1
}

pass() {
  echo "✅ $1"
}

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  fail "AMK_EMAIL and AMK_PASSWORD must be set for contract tests"
fi

if [ -z "$ADMIN_EMAIL" ] || [ -z "$ADMIN_PASSWORD" ]; then
  fail "AMK_ADMIN_EMAIL and AMK_ADMIN_PASSWORD must be set for admin checks"
fi

login() {
  local email="$1"
  local password="$2"
  local response
  response=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}")
  echo "$response"
}

verify_jq() {
  command -v jq >/dev/null 2>&1 || fail "jq is required for contract tests"
}

verify_jq

login_response=$(login "$EMAIL" "$PASSWORD")
token=$(echo "$login_response" | jq -r '.access_token // empty')
token_type=$(echo "$login_response" | jq -r '.token_type // empty')
if [ -z "$token" ] || [ -z "$token_type" ]; then
  fail "Login failed or missing access_token/token_type"
fi
pass "Login returned access_token/token_type"

admin_login_response=$(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")
admin_token=$(echo "$admin_login_response" | jq -r '.access_token // empty')
if [ -z "$admin_token" ]; then
  fail "Admin login failed or missing access_token"
fi

prices=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/prices/live")
echo "$prices" | jq -e 'type=="array"' >/dev/null || fail "/api/prices/live must return array"
for pair in "BTC/ZAR" "ETH/ZAR" "XRP/ZAR"; do
  echo "$prices" | jq -e --arg pair "$pair" \
    '.[] | select(.pair==$pair and (.price|tonumber)>0)' >/dev/null \
    || fail "/api/prices/live missing $pair with price > 0"
done
pass "/api/prices/live contains BTC/ETH/XRP ZAR prices"

bots_status=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/bots/status")
echo "$bots_status" | jq -e '.bots and (.total|type=="number") and .exchange_counts and .all_exchanges' >/dev/null \
  || fail "/api/bots/status missing required fields"
expected_exchanges_json=$(printf '%s\n' "${EXPECTED_EXCHANGE_IDS[@]}" | jq -R . | jq -s 'sort')
echo "$bots_status" | jq -e --argjson expected "$expected_exchanges_json" '.all_exchanges | sort == $expected' >/dev/null \
  || fail "/api/bots/status all_exchanges must include exactly 7 exchanges"
pass "/api/bots/status includes required fields and exchanges"

overview=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/overview")
echo "$overview" | jq -e '.total_profit != null and .active_bots != null and .risk_level != null and .ai_sentiment != null' >/dev/null \
  || fail "/api/overview missing required fields"
pass "/api/overview includes required metrics"

dashboard_overview=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/dashboard/overview")
echo "$dashboard_overview" | jq -e '.total_profit != null and .active_bots != null and .paused_bots != null and .system_mode' >/dev/null \
  || fail "/api/dashboard/overview missing required fields"
pass "/api/dashboard/overview includes required fields"

quarantine_status=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/quarantine/status")
echo "$quarantine_status" | jq -e '.quarantined_bots | type=="array"' >/dev/null \
  || fail "/api/quarantine/status missing quarantined_bots array"
echo "$quarantine_status" | jq -e \
  'all(.quarantined_bots[]; (.quarantine_reason != null) and ((.retraining_until != null) or (.remaining_seconds != null)))' >/dev/null \
  || fail "Quarantine entries must include reason and timer"
pass "/api/quarantine/status includes reason and timer"

keys_providers=$(curl -fsS "$BASE_URL/api/keys/providers")
provider_ids=$(echo "$keys_providers" | jq -r '.providers[].id' | sort)
exchange_ids=$(echo "$keys_providers" | jq -c '[.providers[] | select(.type=="exchange") | .id] | sort')
echo "$exchange_ids" | jq -e 'length==7' >/dev/null || fail "/api/keys/providers must include 7 exchanges"
echo "$exchange_ids" | jq -e --argjson expected "$expected_exchanges_json" '. == $expected' >/dev/null \
  || fail "/api/keys/providers exchange list mismatch"
for required in "${EXPECTED_EXCHANGE_IDS[@]}"; do
  echo "$exchange_ids" | jq -e --arg id "$required" 'index($id)' >/dev/null \
    || fail "Missing exchange provider: $required"
done

keys_status=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/keys/status")
for provider in $provider_ids; do
  echo "$keys_status" | jq -e --arg provider "$provider" '.status_map[$provider]' >/dev/null \
    || fail "Missing status_map entry for provider: $provider"
done
pass "/api/keys/status includes status_map for all providers"

system_mode=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/system/mode")
echo "$system_mode" | jq -e '.paperTrading != null and .liveTrading != null and .autopilot != null' >/dev/null \
  || fail "/api/system/mode missing required flags"
pass "/api/system/mode includes mode flags"

risk_status=$(curl -fsS -H "Authorization: Bearer $token" "$BASE_URL/api/risk/status")
echo "$risk_status" | jq -e '.daily_loss_lock and .emergency_stop and .bodyguard_lock and .quarantine_active' >/dev/null \
  || fail "/api/risk/status missing required lock fields"
pass "/api/risk/status includes lock data"

admin_status=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $token" "$BASE_URL/api/admin/users")
if [ "$admin_status" != "403" ]; then
  fail "/api/admin/users should return 403 for non-admin token"
fi

admin_ok=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $admin_token" "$BASE_URL/api/admin/users")
if [ "$admin_ok" != "200" ]; then
  fail "/api/admin/users should return 200 for admin token"
fi
pass "Admin endpoint access checks passed"

pass "Contract tests completed successfully"
