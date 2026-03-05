#!/bin/bash
# Smoke test for realtime WebSocket connectivity (VPS runnable).

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

if [[ "$API_URL" == https://* ]]; then
  WS_BASE="wss://${API_URL#https://}"
else
  WS_BASE="ws://${API_URL#http://}"
fi

WS_URL="${WS_BASE}/api/ws?token=${TOKEN}"

echo "🔍 Checking /api/prices/live change_24h..."
prices_response=$(curl -s "$API_URL/api/prices/live" -H "Authorization: Bearer ${TOKEN}")
non_zero_change=$(echo "$prices_response" | jq '[.[] | .change_24h] | any(. != 0)')
if [ "$non_zero_change" != "true" ]; then
  echo "❌ change_24h appears to be zero for all pairs"
  echo "$prices_response"
  exit 1
fi
echo "✅ change_24h looks non-zero"

echo "🔍 Checking /api/coinstats/status..."
curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/coinstats/status" -H "Authorization: Bearer ${TOKEN}" | grep -q "200"
echo "✅ /api/coinstats/status OK"

echo "🔍 Checking /api/diagnostics/websocket..."
curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/diagnostics/websocket" -H "Authorization: Bearer ${TOKEN}" | grep -q "200"
echo "✅ /api/diagnostics/websocket OK"

if [ "${AMARKTAI_WS_INSECURE:-}" = "1" ]; then
  echo "Warning: AMARKTAI_WS_INSECURE=1 disables TLS verification for tests only."
fi

python3 - "$WS_URL" <<'PY'
import asyncio
import json
import os
import ssl
import sys
import time

import websockets

uri = sys.argv[1]
ssl_context = None
if uri.startswith("wss://") and os.getenv("AMARKTAI_WS_INSECURE") == "1":
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE


async def run():
    async with websockets.connect(uri, open_timeout=10, ssl=ssl_context) as ws:
        got_heartbeat = False
        got_prices = False
        deadline = time.time() + 10

        while time.time() < deadline and not (got_heartbeat and got_prices):
            timeout = max(deadline - time.time(), 0.1)
            message = await asyncio.wait_for(ws.recv(), timeout=timeout)
            print(message)
            data = json.loads(message)
            event_type = data.get("type")
            if event_type in ("heartbeat", "ping"):
                got_heartbeat = True
            if event_type == "prices_update":
                got_prices = True

        if not got_heartbeat or not got_prices:
            missing = []
            if not got_heartbeat:
                missing.append("heartbeat")
            if not got_prices:
                missing.append("prices_update")
            raise RuntimeError(f"Missing realtime events: {', '.join(missing)}")


try:
    asyncio.run(run())
except Exception as exc:
    print(f"WebSocket smoke test failed: {exc}")
    sys.exit(1)
PY

echo "✅ smoke_realtime.sh PASS"
