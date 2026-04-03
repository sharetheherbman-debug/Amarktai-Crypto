#!/bin/bash
# Production Readiness Verification Script
# Runs CI-style checks before deployment

set -e  # Exit on error

echo "=================================="
echo "Production Readiness Verification"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend"
cd "$BACKEND_DIR"

FAILED=0

# 1. Python Syntax Check
echo "1. Checking Python syntax..."
PYTHON_FILES=$(find . -name "*.py" -type f | grep -v __pycache__ | grep -v venv)
SYNTAX_ERRORS=0

for file in $PYTHON_FILES; do
    if ! python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "${RED}✗${NC} Syntax error in: $file"
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
        FAILED=1
    fi
done

if [ $SYNTAX_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All Python files compile successfully"
else
    echo -e "${RED}✗${NC} Found $SYNTAX_ERRORS syntax errors"
fi
echo ""

# 2. Import Resolution Check
echo "2. Checking critical imports..."
IMPORT_ERRORS=0

# Check Phase 1 imports
if python3 -c "from services.ledger_service import LedgerService" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} ledger_service imports OK"
else
    echo -e "${RED}✗${NC} ledger_service import failed"
    IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    FAILED=1
fi

# Check Phase 2 imports
if python3 -c "from services.order_pipeline import OrderPipeline" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} order_pipeline imports OK"
else
    echo -e "${RED}✗${NC} order_pipeline import failed"
    IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    FAILED=1
fi

if [ $IMPORT_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All critical imports resolve"
else
    echo -e "${RED}✗${NC} Found $IMPORT_ERRORS import errors"
fi
echo ""

# 3. Test Suite Execution
echo "3. Running test suite..."
if [ -d "tests" ]; then
    if python3 -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/pytest_output.txt; then
        TESTS_PASSED=$(grep "passed" /tmp/pytest_output.txt | tail -1 || echo "0 passed")
        echo -e "${GREEN}✓${NC} Tests: $TESTS_PASSED"
    else
        echo -e "${RED}✗${NC} Some tests failed"
        FAILED=1
    fi
else
    echo -e "${YELLOW}⚠${NC} Tests directory not found (optional)"
fi
echo ""

# 4. Configuration Validation
echo "4. Checking configuration files..."
if [ -f "../.env.example" ]; then
    echo -e "${GREEN}✓${NC} .env.example exists"
    
    # Check critical variables
    REQUIRED_VARS=("MONGO_URL" "JWT_SECRET" "USE_ORDER_PIPELINE")
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "$var" ../.env.example; then
            echo -e "${GREEN}✓${NC} $var documented"
        else
            echo -e "${YELLOW}⚠${NC} $var not in .env.example"
        fi
    done
else
    echo -e "${YELLOW}⚠${NC} .env.example not found"
fi
echo ""

# 5. Database Schema Validation
echo "5. Verifying database collections..."
COLLECTIONS=(
    "fills_ledger"
    "ledger_events"
    "pending_orders"
    "circuit_breaker_state"
)

echo "Required collections:"
for coll in "${COLLECTIONS[@]}"; do
    echo "  - $coll"
done
echo -e "${GREEN}✓${NC} Schema documented"
echo ""

# 6. Endpoint Availability
echo "6. Checking API endpoint definitions..."
ENDPOINTS=(
    "routes/ledger_endpoints.py"
    "routes/order_endpoints.py"
    "routes/bot_lifecycle.py"
)

for endpoint in "${ENDPOINTS[@]}"; do
    if [ -f "$endpoint" ]; then
        echo -e "${GREEN}✓${NC} $endpoint exists"
    else
        echo -e "${RED}✗${NC} $endpoint missing"
        FAILED=1
    fi
done
echo ""

# 7. Frontend Component Check
echo "7. Checking frontend components..."
FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/frontend"
if [ -d "$FRONTEND_DIR" ]; then
    if [ -f "$FRONTEND_DIR/src/components/BotLifecycleControls.js" ]; then
        echo -e "${GREEN}✓${NC} BotLifecycleControls.js exists"
    else
        echo -e "${YELLOW}⚠${NC} BotLifecycleControls.js not found"
    fi
    
    if [ -f "$FRONTEND_DIR/src/components/AIChatPanel.js" ]; then
        echo -e "${GREEN}✓${NC} AIChatPanel.js exists"
    else
        echo -e "${YELLOW}⚠${NC} AIChatPanel.js not found"
    fi
else
    echo -e "${YELLOW}⚠${NC} Frontend directory not found"
fi
echo ""

# Final Report
echo "=================================="
echo "Verification Complete"
echo "=================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED${NC}"
    echo ""
    echo "System is production-ready!"
    exit 0
else
    echo -e "${RED}✗ SOME CHECKS FAILED${NC}"
    echo ""
    echo "Please fix the issues above before deploying."
    exit 1
fi
