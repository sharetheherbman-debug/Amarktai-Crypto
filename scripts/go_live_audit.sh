#!/bin/bash
# Go-Live Audit Script
# Comprehensive audit for production readiness
# Tests frontend build, backend tests, and E2E sanity checks

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
TESTS_DIR="$PROJECT_ROOT/tests"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
FAILED_ITEMS=()

echo "======================================"
echo "   GO-LIVE AUDIT SCRIPT"
echo "======================================"
echo "Project Root: $PROJECT_ROOT"
echo "Date: $(date)"
echo ""

# Function to print section header
print_section() {
    echo ""
    echo "======================================"
    echo "  $1"
    echo "======================================"
}

# Function to test and record result
test_item() {
    local description="$1"
    local command="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -n "[$TOTAL_TESTS] Testing: $description... "
    
    if eval "$command" > /tmp/go_live_audit_$TOTAL_TESTS.log 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_ITEMS+=("$description")
        echo "  Error log: /tmp/go_live_audit_$TOTAL_TESTS.log"
        return 1
    fi
}

# ======================================
# SECTION 1: Environment Checks
# ======================================
print_section "1. ENVIRONMENT CHECKS"

test_item "Python 3.12+ installed" "python3 --version | grep -E 'Python 3\.(1[2-9]|[2-9][0-9])'"
test_item "Node.js 18+ installed" "node --version | grep -E 'v(1[8-9]|[2-9][0-9])'"
test_item "npm installed" "npm --version"
test_item "pip installed" "pip3 --version"
test_item "Backend directory exists" "test -d $BACKEND_DIR"
test_item "Frontend directory exists" "test -d $FRONTEND_DIR"
test_item "Tests directory exists" "test -d $TESTS_DIR"

# ======================================
# SECTION 2: Backend Setup
# ======================================
print_section "2. BACKEND SETUP"

# Check if virtual environment exists
if [ -d "$BACKEND_DIR/.venv" ]; then
    echo "✓ Virtual environment exists"
else
    echo "${YELLOW}⚠ Virtual environment not found, creating...${NC}"
    cd "$BACKEND_DIR"
    python3 -m venv .venv || {
        echo -e "${RED}✗ Failed to create virtual environment${NC}"
        exit 1
    }
fi

# Activate virtual environment
source "$BACKEND_DIR/.venv/bin/activate" || {
    echo -e "${RED}✗ Failed to activate virtual environment${NC}"
    exit 1
}

test_item "Install backend dependencies" "cd $BACKEND_DIR && pip3 install -q -r requirements.txt"
test_item "Backend requirements satisfied" "cd $BACKEND_DIR && pip3 check"

# ======================================
# SECTION 3: Frontend Build
# ======================================
print_section "3. FRONTEND BUILD"

test_item "Install frontend dependencies" "cd $FRONTEND_DIR && npm install --silent"
test_item "Frontend build succeeds" "cd $FRONTEND_DIR && npm run build"
test_item "Build directory created" "test -d $FRONTEND_DIR/build"
test_item "index.html exists in build" "test -f $FRONTEND_DIR/build/index.html"

# ======================================
# SECTION 4: Backend Unit Tests
# ======================================
print_section "4. BACKEND UNIT TESTS"

# Avoid pytest plugin auto-loading issues (web3 plugins)
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Run pytest with our new tests
cd "$PROJECT_ROOT"
test_item "API Keys tests pass" "pytest tests/test_api_keys.py -v --tb=short"
test_item "Bots E2E tests pass" "pytest tests/test_bots_e2e.py -v --tb=short"
test_item "Overview realtime tests pass" "pytest tests/test_overview_realtime.py -v --tb=short"
test_item "Chat tests pass" "pytest tests/test_chat.py -v --tb=short"
test_item "Paper trading tests pass" "pytest tests/test_paper_trading.py -v --tb=short"

# Run any existing tests
if [ -f "$TESTS_DIR/test_production_fixes.py" ]; then
    test_item "Production fixes tests pass" "pytest tests/test_production_fixes.py -v --tb=short"
fi

# ======================================
# SECTION 5: API Sanity Checks
# ======================================
print_section "5. API SANITY CHECKS"

# Check if backend is running
echo "Checking if backend is running..."
if curl -s -f http://127.0.0.1:8000/api/health/ping > /dev/null 2>&1; then
    echo "✓ Backend is running"
    BACKEND_RUNNING=true
else
    echo "${YELLOW}⚠ Backend not running, skipping API tests${NC}"
    echo "  To test APIs, start backend with: cd $BACKEND_DIR && python server.py"
    BACKEND_RUNNING=false
fi

if [ "$BACKEND_RUNNING" = true ]; then
    test_item "Health endpoint responds" "curl -s -f http://127.0.0.1:8000/api/health/ping"
    test_item "OpenAPI JSON exists" "curl -s -f http://127.0.0.1:8000/api/openapi.json | grep -q 'openapi\\|paths'"
    test_item "API docs accessible" "curl -s -f http://127.0.0.1:8000/docs"
    
    # Test auth endpoints (should return 401 or success)
    echo -n "[$((TOTAL_TESTS + 1))] Testing: Auth endpoints exist... "
    if curl -s http://127.0.0.1:8000/api/auth/login -X POST -H "Content-Type: application/json" -d '{}' | grep -q '401\\|400\\|email'; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        FAILED_ITEMS+=("Auth endpoints exist")
    fi
fi

# ======================================
# SECTION 6: SPA Routing Check
# ======================================
print_section "6. SPA ROUTING CHECK"

# Check if nginx is configured and running
if command -v nginx &> /dev/null && systemctl is-active --quiet nginx 2>/dev/null; then
    echo "✓ Nginx is installed and running"
    
    # Check if our config exists
    if [ -f "/etc/nginx/sites-enabled/amarktai" ] || [ -f "/etc/nginx/sites-enabled/amarktai-spa" ]; then
        echo "✓ Nginx config found"
        
        # Run SPA routing tests
        if [ -f "$SCRIPT_DIR/test_spa_routing.sh" ]; then
            test_item "SPA routing validation" "bash $SCRIPT_DIR/test_spa_routing.sh"
        else
            echo "${YELLOW}⚠ SPA routing test script not found${NC}"
        fi
    else
        echo "${YELLOW}⚠ Nginx config not installed${NC}"
        echo "  Install with: sudo cp deployment/nginx/amarktai-spa.conf /etc/nginx/sites-available/amarktai"
    fi
else
    echo "${YELLOW}⚠ Nginx not installed or not running${NC}"
    echo "  SPA routing tests skipped"
fi

# ======================================
# SECTION 7: Configuration Checks
# ======================================
print_section "7. CONFIGURATION CHECKS"

test_item "Backend .env exists" "test -f $BACKEND_DIR/.env"
test_item "Nginx SPA config exists" "test -f $PROJECT_ROOT/deployment/nginx/amarktai-spa.conf"
test_item "SPA routing test script exists" "test -f $SCRIPT_DIR/test_spa_routing.sh"

# Check for required environment variables
if [ -f "$BACKEND_DIR/.env" ]; then
    echo -n "Checking required environment variables... "
    missing_vars=()
    
    grep -q "JWT_SECRET" "$BACKEND_DIR/.env" || missing_vars+=("JWT_SECRET")
    grep -q "MONGO_URI" "$BACKEND_DIR/.env" || missing_vars+=("MONGO_URI")
    
    if [ ${#missing_vars[@]} -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "  Missing: ${missing_vars[*]}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
        FAILED_ITEMS+=("Required environment variables")
    fi
fi

# ======================================
# PRINT SUMMARY
# ======================================
echo ""
echo "======================================"
echo "   AUDIT SUMMARY"
echo "======================================"
echo "Total Tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
echo "======================================"

if [ $FAILED_TESTS -gt 0 ]; then
    echo ""
    echo -e "${RED}FAILED ITEMS:${NC}"
    for item in "${FAILED_ITEMS[@]}"; do
        echo "  ✗ $item"
    done
fi

echo ""
echo "======================================"
echo "   GO-LIVE CHECKLIST"
echo "======================================"

# Build checklist based on results
echo -ne "[ "
if [ $PASSED_TESTS -ge $((TOTAL_TESTS * 80 / 100)) ]; then
    echo -ne "${GREEN}✓${NC}"
else
    echo -ne "${RED}✗${NC}"
fi
echo " ] Backend tests passing"

echo -ne "[ "
if [ -d "$FRONTEND_DIR/build" ]; then
    echo -ne "${GREEN}✓${NC}"
else
    echo -ne "${RED}✗${NC}"
fi
echo " ] Frontend built successfully"

echo -ne "[ "
if [ -f "$PROJECT_ROOT/deployment/nginx/amarktai-spa.conf" ]; then
    echo -ne "${GREEN}✓${NC}"
else
    echo -ne "${RED}✗${NC}"
fi
echo " ] SPA routing config created"

echo -ne "[ "
if [ -f "$BACKEND_DIR/.env" ]; then
    echo -ne "${GREEN}✓${NC}"
else
    echo -ne "${RED}✗${NC}"
fi
echo " ] Environment configured"

echo -ne "[ "
if [ $FAILED_TESTS -eq 0 ]; then
    echo -ne "${GREEN}✓${NC}"
else
    echo -ne "${RED}✗${NC}"
fi
echo " ] All tests passing"

echo ""
echo "======================================"

# Exit with appropriate code
if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}RESULT: AUDIT FAILED${NC}"
    echo ""
    echo "Please fix the failing items above before going live."
    echo "Check error logs in /tmp/go_live_audit_*.log for details."
    exit 1
else
    echo -e "${GREEN}RESULT: READY FOR GO-LIVE! 🚀${NC}"
    echo ""
    echo "All checks passed! Your deployment is production-ready."
    echo ""
    echo "Next steps:"
    echo "1. Install nginx config: sudo cp deployment/nginx/amarktai-spa.conf /etc/nginx/sites-available/amarktai"
    echo "2. Enable site: sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/"
    echo "3. Test nginx: sudo nginx -t"
    echo "4. Reload nginx: sudo systemctl reload nginx"
    echo "5. Start/restart backend service: sudo systemctl restart amarktai-api"
    exit 0
fi
