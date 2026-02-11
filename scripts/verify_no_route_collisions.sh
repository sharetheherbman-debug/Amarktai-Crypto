#!/bin/bash
# Verify No Route Collisions - Pre-Deployment Check
# Ensures server boots without route collision errors

set -euo pipefail  # Exit on error

echo "🔍 Amarktai Network - Route Collision Check"
echo "============================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

cd "$PROJECT_ROOT"

VENV_DIR="$BACKEND_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "✅ Using backend virtual environment: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
elif [ -d "$PROJECT_ROOT/.venv" ]; then
    VENV_DIR="$PROJECT_ROOT/.venv"
    echo "✅ Using virtual environment: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
else
    echo -e "${YELLOW}⚠️  No virtual environment found.${NC}"
    echo "Create backend/.venv first:" >&2
    echo "  cd $BACKEND_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# Test 1: Import server.py without crashes
echo ""
echo "📋 Test 1: Import server.py (detect collisions at import time)"
echo "---------------------------------------------------------------"

cd "$BACKEND_DIR"
if python - <<'PY'
import sys
import traceback
sys.path.insert(0, '.')
try:
    import server
    print("✅ Server imported successfully")
except ModuleNotFoundError as exc:
    print(f"❌ Missing dependency: {exc.name}. Install backend requirements.", file=sys.stderr)
    sys.exit(2)
except Exception as exc:
    print(f"❌ Server import failed: {exc}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
PY
then
    echo -e "${GREEN}✅ PASSED: Server imports without collision errors${NC}"
else
    exit_code=$?
    if [ "$exit_code" -eq 2 ]; then
        echo -e "${RED}❌ FAILED: Missing dependency (install backend requirements)${NC}"
    else
        echo -e "${RED}❌ FAILED: Server import failed${NC}"
    fi
    exit 1
fi

# Test 2: Run route collision regression tests
echo ""
echo "📋 Test 2: Route collision regression tests"
echo "---------------------------------------------"

cd "$PROJECT_ROOT"
if [ -f "$BACKEND_DIR/tests/test_route_collisions.py" ]; then
    # Disable pytest plugin autoloading to avoid web3 conflicts
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    if pytest -xvs "$BACKEND_DIR/tests/test_route_collisions.py" -p no:warnings 2>&1; then
        echo -e "${GREEN}✅ PASSED: No route collisions detected${NC}"
    else
        echo -e "${RED}❌ FAILED: Route collision tests failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  SKIPPED: test_route_collisions.py not found${NC}"
fi

# Test 3: Verify critical /api/prices/live route exists exactly once
echo ""
echo "📋 Test 3: Verify GET /api/prices/live uniqueness"
echo "---------------------------------------------------"

cd "$BACKEND_DIR"
ROUTE_COUNT=$(python -c "
import sys
sys.path.insert(0, '.')
import server

count = 0
for route in server.app.routes:
    if hasattr(route, 'methods') and hasattr(route, 'path'):
        if 'GET' in route.methods and route.path == '/api/prices/live':
            count += 1
print(count)
" 2>/dev/null)

if [ "$ROUTE_COUNT" = "1" ]; then
    echo -e "${GREEN}✅ PASSED: GET /api/prices/live registered exactly once${NC}"
elif [ "$ROUTE_COUNT" = "0" ]; then
    echo -e "${RED}❌ FAILED: GET /api/prices/live not found (missing critical endpoint)${NC}"
    exit 1
else
    echo -e "${RED}❌ FAILED: GET /api/prices/live registered $ROUTE_COUNT times (collision!)${NC}"
    exit 1
fi

# Summary
echo ""
echo "============================================"
echo -e "${GREEN}✅ All route collision checks passed!${NC}"
echo "============================================"
echo ""
echo "Server is safe to deploy - no route collisions detected."
echo ""

exit 0
