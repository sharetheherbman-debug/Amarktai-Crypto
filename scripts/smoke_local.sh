#!/bin/bash
###############################################################################
# SMOKE TEST - Local API Validation
# Starts API server and validates /api/health/ping returns 200
###############################################################################

set -euo pipefail

echo "=========================================="
echo "🔥 SMOKE TEST - LOCAL API VALIDATION"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
HOST="127.0.0.1"
PORT="8000"
HEALTH_ENDPOINT="http://${HOST}:${PORT}/api/health/ping"
STARTUP_TIMEOUT=30
HEALTH_CHECK_RETRIES=10
UVICORN_PID=""

# Cleanup function
cleanup() {
    if [ -n "$UVICORN_PID" ]; then
        echo "Stopping uvicorn (PID: $UVICORN_PID)..."
        kill "$UVICORN_PID" 2>/dev/null || true
        # Give it time to shut down gracefully
        sleep 2
        # Force kill if still running
        kill -9 "$UVICORN_PID" 2>/dev/null || true
        echo -e "${GREEN}✓ Uvicorn stopped${NC}"
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

echo "🔍 Pre-flight checks..."
echo "-----------------------------------"

# Check if port is already in use
if command -v lsof >/dev/null 2>&1; then
    if lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}✗ FAIL${NC}: Port ${PORT} is already in use"
        echo "Process: $(lsof -Pi :${PORT} -sTCP:LISTEN | tail -n1)"
        exit 1
    fi
fi

# Find Python and activate venv if present
PYTHON_CMD="python3"
if [ -d "backend/.venv" ]; then
    echo "Activating venv at backend/.venv..."
    source backend/.venv/bin/activate
    PYTHON_CMD="python3"
elif [ -d ".venv" ]; then
    echo "Activating venv at .venv..."
    source .venv/bin/activate
    PYTHON_CMD="python3"
fi

# Verify Python can import server module
cd backend || exit 1
if ! $PYTHON_CMD -c "import server" 2>/dev/null; then
    echo -e "${RED}✗ FAIL${NC}: Cannot import server module"
    echo "Run: pip install -r requirements.txt"
    exit 1
fi
echo -e "${GREEN}✓ Server module importable${NC}"

echo ""
echo "🚀 Starting uvicorn server..."
echo "-----------------------------------"

# Start uvicorn in background
$PYTHON_CMD -m uvicorn server:app --host ${HOST} --port ${PORT} --log-level warning > /tmp/uvicorn.log 2>&1 &
UVICORN_PID=$!

echo "Uvicorn started (PID: $UVICORN_PID)"
echo "Waiting for server to be ready (max ${STARTUP_TIMEOUT}s)..."

# Wait for server to start
for i in $(seq 1 ${STARTUP_TIMEOUT}); do
    if curl -sf ${HEALTH_ENDPOINT} >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Server is ready after ${i}s${NC}"
        break
    fi
    
    # Check if process is still running
    if ! kill -0 $UVICORN_PID 2>/dev/null; then
        echo -e "${RED}✗ FAIL${NC}: Uvicorn process died during startup"
        echo "Last 20 lines of log:"
        tail -n 20 /tmp/uvicorn.log
        exit 1
    fi
    
    sleep 1
    
    if [ $i -eq ${STARTUP_TIMEOUT} ]; then
        echo -e "${RED}✗ FAIL${NC}: Server did not start within ${STARTUP_TIMEOUT}s"
        echo "Last 20 lines of log:"
        tail -n 20 /tmp/uvicorn.log
        exit 1
    fi
done

echo ""
echo "🏥 Testing health endpoint..."
echo "-----------------------------------"

# Test /api/health/ping endpoint
HTTP_CODE=$(curl -s -o /tmp/health_response.json -w "%{http_code}" ${HEALTH_ENDPOINT})

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ PASS${NC}: /api/health/ping returned HTTP 200"
    echo "Response: $(cat /tmp/health_response.json)"
else
    echo -e "${RED}✗ FAIL${NC}: /api/health/ping returned HTTP $HTTP_CODE"
    echo "Response: $(cat /tmp/health_response.json)"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ SMOKE TEST PASSED${NC}"
echo "=========================================="
echo ""
echo "Server successfully:"
echo "  - Started and bound to ${HOST}:${PORT}"
echo "  - Responded to health check with HTTP 200"
echo ""

exit 0
