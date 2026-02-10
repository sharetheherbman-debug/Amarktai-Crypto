#!/bin/bash
# WebSocket Smoke Test
# Connects to /api/ws with auth token and verifies at least one message within 10 seconds.
#
# Usage: ./scripts/ws_smoke_test.sh [BASE_URL] [TOKEN]
# Example: ./scripts/ws_smoke_test.sh https://amarktai.com "your-jwt-token"

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
TOKEN="${2:-}"

# Strip trailing slash
BASE_URL="${BASE_URL%/}"

# Convert http(s) to ws(s)
WS_URL="${BASE_URL/http/ws}/api/ws"

echo "=== WebSocket Smoke Test ==="
echo "URL: $WS_URL"

if [ -z "$TOKEN" ]; then
    echo "⚠️  No token provided. Attempting to get one via /api/auth/login..."
    
    # Try to login with default test credentials
    LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"email": "test@test.com", "password": "test123"}' 2>/dev/null || echo "{}")
    
    TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
    
    if [ -z "$TOKEN" ]; then
        echo "❌ Could not obtain auth token. Provide TOKEN as second argument."
        echo "   Usage: $0 BASE_URL TOKEN"
        exit 1
    fi
    echo "✅ Got auth token"
fi

echo "Testing WebSocket connection..."

# Check if websocat is available
if command -v websocat &>/dev/null; then
    # Use websocat for WebSocket testing
    RESULT=$(echo "" | timeout 10 websocat -1 "${WS_URL}?token=${TOKEN}" 2>/dev/null || echo "")
    
    if [ -n "$RESULT" ]; then
        echo "✅ Received WebSocket message within 10 seconds:"
        echo "$RESULT" | head -5
        exit 0
    else
        echo "❌ No WebSocket message received within 10 seconds"
        exit 1
    fi
elif command -v python3 &>/dev/null; then
    # Use Python as fallback
    python3 -c "
import asyncio
import sys

async def test_ws():
    try:
        import websockets
    except ImportError:
        print('⚠️  websockets not installed, trying pip install...')
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'websockets', '-q'])
        import websockets
    
    url = '${WS_URL}?token=${TOKEN}'
    try:
        async with websockets.connect(url) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f'✅ Received WebSocket message: {msg[:200]}')
            return True
    except asyncio.TimeoutError:
        print('❌ No message received within 10 seconds')
        return False
    except Exception as e:
        print(f'❌ WebSocket connection error: {e}')
        return False

result = asyncio.run(test_ws())
sys.exit(0 if result else 1)
" 2>/dev/null
    exit $?
else
    echo "⚠️  Neither websocat nor python3 available. Falling back to curl health check."
    
    # At minimum, verify the WebSocket endpoint exists
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Upgrade: websocket" \
        -H "Connection: Upgrade" \
        "${BASE_URL}/api/ws" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" = "101" ] || [ "$HTTP_CODE" = "426" ] || [ "$HTTP_CODE" = "200" ]; then
        echo "✅ WebSocket endpoint responds (HTTP $HTTP_CODE)"
        exit 0
    else
        echo "❌ WebSocket endpoint returned HTTP $HTTP_CODE (expected 101 or 426)"
        exit 1
    fi
fi
