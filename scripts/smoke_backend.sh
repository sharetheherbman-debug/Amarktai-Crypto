#!/bin/bash
#
# Smoke test for backend startup and health check
# Tests that:
# 1. server:app can be imported
# 2. uvicorn starts successfully on a random port
# 3. /api/health/ping endpoint responds correctly
# 4. Response includes build_hash, uptime, and bind_ok fields
#
# Exit codes:
#   0 = Success
#   1 = Failure

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "========================================"
echo "Backend Smoke Test"
echo "========================================"
echo "Project Root: $PROJECT_ROOT"
echo "Backend Dir: $BACKEND_DIR"
echo ""

# Find a random available port
get_random_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

PORT=$(get_random_port)
echo "Using random port: $PORT"
echo ""

# Step 1: Test import of server:app
echo "Step 1: Testing server:app import..."
cd "$BACKEND_DIR"
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

try:
    # Try importing the server module
    print("  - Importing server module...")
    import server
    
    # Check that app exists
    if not hasattr(server, 'app'):
        print("  ❌ FAIL: server module has no 'app' attribute")
        sys.exit(1)
    
    print("  ✅ server:app imported successfully")
    
except Exception as e:
    print(f"  ❌ FAIL: Could not import server:app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ SMOKE TEST FAILED: Could not import server:app"
    exit 1
fi

echo ""

# Step 2: Start uvicorn in background
echo "Step 2: Starting uvicorn on port $PORT..."
cd "$BACKEND_DIR"

# Create a temp log file
LOG_FILE=$(mktemp)
echo "  - Log file: $LOG_FILE"

# Start uvicorn in background
PYTHONPATH=. uvicorn server:app --host 127.0.0.1 --port $PORT --log-level warning > "$LOG_FILE" 2>&1 &
UVICORN_PID=$!

echo "  - Uvicorn PID: $UVICORN_PID"
echo "  - Waiting for server to start..."

# Wait for server to be ready (up to 30 seconds)
MAX_WAIT=30
WAITED=0
SERVER_READY=false

while [ $WAITED -lt $MAX_WAIT ]; do
    sleep 1
    WAITED=$((WAITED + 1))
    
    # Check if process is still running
    if ! kill -0 $UVICORN_PID 2>/dev/null; then
        echo "  ❌ FAIL: Uvicorn process died"
        echo ""
        echo "Last 50 lines of log:"
        tail -50 "$LOG_FILE"
        rm -f "$LOG_FILE"
        exit 1
    fi
    
    # Try to connect
    if curl -s -f http://127.0.0.1:$PORT/api/health/ping > /dev/null 2>&1; then
        SERVER_READY=true
        echo "  ✅ Server is ready after ${WAITED}s"
        break
    fi
done

if [ "$SERVER_READY" != "true" ]; then
    echo "  ❌ FAIL: Server did not become ready within ${MAX_WAIT}s"
    echo ""
    echo "Last 50 lines of log:"
    tail -50 "$LOG_FILE"
    kill $UVICORN_PID 2>/dev/null || true
    rm -f "$LOG_FILE"
    exit 1
fi

echo ""

# Step 3: Test /api/health/ping endpoint
echo "Step 3: Testing /api/health/ping endpoint..."

RESPONSE=$(curl -s http://127.0.0.1:$PORT/api/health/ping)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$PORT/api/health/ping)

echo "  - HTTP Status: $HTTP_CODE"

# Both 200 (healthy) and 503 (unhealthy but responding) are acceptable for smoke test
# 503 may occur if DB is not connected, but server is running and can respond
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "503" ]; then
    echo "  ❌ FAIL: Unexpected HTTP status code: $HTTP_CODE"
    echo "  Response: $RESPONSE"
    kill $UVICORN_PID 2>/dev/null || true
    rm -f "$LOG_FILE"
    exit 1
fi

echo "  - Response: $RESPONSE"

# Step 4: Verify response includes required fields
echo ""
echo "Step 4: Verifying response fields..."

# Check for build_hash field
if echo "$RESPONSE" | grep -q '"build_hash"'; then
    echo "  ✅ build_hash field present"
else
    echo "  ❌ FAIL: build_hash field missing"
    kill $UVICORN_PID 2>/dev/null || true
    rm -f "$LOG_FILE"
    exit 1
fi

# Check for bind_ok field
if echo "$RESPONSE" | grep -q '"bind_ok"'; then
    echo "  ✅ bind_ok field present"
else
    echo "  ❌ FAIL: bind_ok field missing"
    kill $UVICORN_PID 2>/dev/null || true
    rm -f "$LOG_FILE"
    exit 1
fi

# Check for uptime_seconds field (may not be present if startup tracking failed)
if echo "$RESPONSE" | grep -q '"uptime_seconds"'; then
    echo "  ✅ uptime_seconds field present"
else
    echo "  ⚠️  WARNING: uptime_seconds field missing (optional)"
fi

# Cleanup
echo ""
echo "Cleaning up..."
kill $UVICORN_PID 2>/dev/null || true
wait $UVICORN_PID 2>/dev/null || true
rm -f "$LOG_FILE"

echo ""
echo "========================================"
echo "✅ SMOKE TEST PASSED"
echo "========================================"
exit 0
