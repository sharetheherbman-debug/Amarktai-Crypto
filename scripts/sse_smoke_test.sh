#!/bin/bash
# SSE Smoke Test
# Connects to /api/realtime/events with auth token and verifies at least one event within 10 seconds.
#
# Usage: ./scripts/sse_smoke_test.sh [BASE_URL] [TOKEN]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
TOKEN="${2:-}"

BASE_URL="${BASE_URL%/}"

if [ -z "$TOKEN" ]; then
  EMAIL="${AMARKTAI_EMAIL:-}"
  PASSWORD="${AMARKTAI_PASSWORD:-}"

  if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    echo "❌ Provide TOKEN or set AMARKTAI_EMAIL/AMARKTAI_PASSWORD for login."
    exit 1
  fi

  LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")

  TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
  if [ -z "$TOKEN" ]; then
    echo "❌ Unable to obtain auth token from login."
    exit 1
  fi
fi

python3 - <<PY
import sys
import time
import urllib.request

base_url = "${BASE_URL}"
token = "${TOKEN}"
url = f"{base_url}/api/realtime/events?token={token}"

req = urllib.request.Request(url)
start = time.time()
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        while time.time() - start < 10:
            line = resp.readline()
            if not line:
                continue
            if line.startswith(b"data:"):
                print("✅ SSE event received:", line.decode().strip()[:200])
                sys.exit(0)
except Exception as exc:
    print(f"❌ SSE connection error: {exc}")
    sys.exit(1)

print("❌ No SSE event received within 10 seconds")
sys.exit(1)
PY
