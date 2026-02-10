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

if [ "${AMARKTAI_WS_INSECURE:-}" = "1" ]; then
  echo "Warning: AMARKTAI_WS_INSECURE=1 disables TLS verification for tests only."
fi

python3 - "$WS_URL" <<'PY'
import asyncio
import os
import ssl
import sys

import websockets

uri = sys.argv[1]
ssl_context = None
if uri.startswith("wss://") and os.getenv("AMARKTAI_WS_INSECURE") == "1":
    ssl_context = ssl._create_unverified_context()


async def run():
    async with websockets.connect(uri, open_timeout=10, ssl=ssl_context) as ws:
        message = await asyncio.wait_for(ws.recv(), timeout=10)
        print(message)


try:
    asyncio.run(run())
except Exception as exc:
    print(f"WebSocket smoke test failed: {exc}")
    sys.exit(1)
PY

echo "✅ smoke_realtime.sh PASS"
