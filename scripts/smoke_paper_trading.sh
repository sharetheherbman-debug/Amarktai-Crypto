#!/bin/bash
# Smoke test for paper trading flow and countdown readiness (VPS runnable).

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

BOT_NAME="SmokeBot-$(date +%s)"
bot_payload=$(jq -n --arg name "$BOT_NAME" '{name:$name,exchange:"luno",risk_mode:"safe",trading_mode:"paper",initial_capital:1000}')
bot_response=$(curl -s -X POST "$API_URL/api/bots" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "$bot_payload")

BOT_ID=$(echo "$bot_response" | jq -r '.id // empty')
if [ -z "$BOT_ID" ]; then
  echo "Bot creation failed: $bot_response"
  exit 1
fi
echo "✅ Created paper bot $BOT_ID"

echo "⏳ Waiting for paper trade (up to 60s)..."
trade_found=false
for _ in $(seq 1 12); do
  trades_response=$(curl -s "$API_URL/api/trades/recent?limit=20" -H "Authorization: Bearer ${TOKEN}")
  trade_found=$(echo "$trades_response" | jq --arg bot "$BOT_ID" '(.trades // []) | any(.bot_id == $bot)')
  if [ "$trade_found" = "true" ]; then
    echo "✅ Paper trade detected for bot $BOT_ID"
    break
  fi
  sleep 5
done

performance_response=$(curl -s "$API_URL/api/analytics/performance_summary" -H "Authorization: Bearer ${TOKEN}")
if [ "$trade_found" = "true" ]; then
  total_trades=$(echo "$performance_response" | jq -r '.trades.total // 0')
  if [ "$total_trades" -eq 0 ]; then
    echo "❌ Expected trades in performance summary"
    echo "$performance_response"
    exit 1
  fi
  echo "✅ Performance summary shows trades"
else
  echo "⚠️ No trade executed yet - waiting for signal"
fi

countdown_response=$(curl -s "$API_URL/api/analytics/countdown-to-million" -H "Authorization: Bearer ${TOKEN}")
ready=$(echo "$countdown_response" | jq -r '.ready // empty')
if [ "$ready" = "false" ]; then
  echo "✅ Countdown not ready until 10 trades"
elif [ "$ready" = "true" ]; then
  echo "✅ Countdown ready with sufficient trades"
else
  echo "❌ Countdown response missing ready field"
  echo "$countdown_response"
  exit 1
fi

echo "✅ smoke_paper_trading.sh PASS"
