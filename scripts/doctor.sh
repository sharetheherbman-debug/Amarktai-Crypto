#!/bin/bash
###############################################################################
# DOCTOR SCRIPT - Go-Live Readiness Check
# Comprehensive validation of all deployment requirements
###############################################################################

set +e  # Don't exit on first error, we want to report all issues

echo "=========================================="
echo "🏥 AMARKTAI DOCTOR - GO-LIVE READINESS"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNINGS=0

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARNINGS++))
}

info() {
    echo -e "${BLUE}ℹ INFO${NC}: $1"
}

###############################################################################
# CHECK 1: Repository Structure
###############################################################################
echo "📁 Check 1: Repository Structure"
echo "-----------------------------------"

if [ -d "backend" ]; then
    pass "backend/ directory exists"
else
    fail "backend/ directory missing"
fi

if [ -d "frontend" ]; then
    pass "frontend/ directory exists"
else
    fail "frontend/ directory missing"
fi

if [ -d "scripts" ]; then
    pass "scripts/ directory exists"
else
    fail "scripts/ directory missing"
fi

if [ -d "docs" ]; then
    pass "docs/ directory exists"
else
    fail "docs/ directory missing"
fi

echo ""

###############################################################################
# CHECK 2: Critical Files
###############################################################################
echo "📄 Check 2: Critical Files"
echo "-----------------------------------"

REQUIRED_FILES=(
    "backend/server.py"
    "backend/routes/auth.py"
    "backend/routes/realtime.py"
    "backend/routes/bot_lifecycle.py"
    "backend/validators/bot_validator.py"
    "frontend/package.json"
    "frontend/src/pages/Dashboard.js"
    ".env.example"
    "docs/ARCHITECTURE_MAP.md"
    "docs/DEPLOYMENT_GUIDE.md"
    "scripts/test_sse.sh"
    "scripts/test_bots.sh"
    "scripts/verify_go_live.sh"
    ".github/workflows/ci.yml"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        pass "$file exists"
    else
        fail "$file missing"
    fi
done

echo ""

###############################################################################
# CHECK 3: Backend Endpoint Verification
###############################################################################
echo "🔌 Check 3: Backend Endpoint Verification"
echo "-----------------------------------"

# Check for GET /api/auth/profile
if grep -q '@router.get.*"/auth/profile"' backend/routes/auth.py; then
    pass "GET /api/auth/profile endpoint defined"
else
    fail "GET /api/auth/profile endpoint missing"
fi

# Check for PUT /api/auth/profile
if grep -q '@router.put.*"/auth/profile"' backend/routes/auth.py; then
    pass "PUT /api/auth/profile endpoint defined"
else
    fail "PUT /api/auth/profile endpoint missing"
fi

# Check for SSE endpoint
if grep -q '@router.get.*"/events"' backend/routes/realtime.py; then
    pass "SSE /events endpoint defined"
else
    fail "SSE /events endpoint missing"
fi

# Check SSE has auth requirement
if grep -q 'Depends(get_current_user)' backend/routes/realtime.py; then
    pass "SSE endpoint requires authentication"
else
    fail "SSE endpoint missing auth requirement"
fi

# Check for bot creation endpoint
if grep -q 'async def create_bot' backend/server.py; then
    pass "Bot creation endpoint defined"
else
    fail "Bot creation endpoint missing"
fi

echo ""

###############################################################################
# CHECK 4: Backend Python Syntax
###############################################################################
echo "🐍 Check 4: Backend Python Syntax"
echo "-----------------------------------"

PYTHON_FILES=(
    "backend/server.py"
    "backend/routes/auth.py"
    "backend/routes/realtime.py"
    "backend/routes/bot_lifecycle.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        pass "$file syntax valid"
    else
        fail "$file syntax error"
    fi
done

echo ""

###############################################################################
# CHECK 5: Trading Gates Configuration
###############################################################################
echo "🚦 Check 5: Trading Gates Configuration"
echo "-----------------------------------"

ENV_FILE=".env.example"
if [ -f "backend/.env.example" ]; then
    ENV_FILE="backend/.env.example"
fi

if grep -q "PAPER_TRADING" "$ENV_FILE"; then
    pass "PAPER_TRADING flag in .env.example"
else
    fail "PAPER_TRADING flag missing from .env.example"
fi

if grep -q "LIVE_TRADING" "$ENV_FILE"; then
    pass "LIVE_TRADING flag in .env.example"
else
    fail "LIVE_TRADING flag missing from .env.example"
fi

if grep -q "AUTOPILOT_ENABLED" "$ENV_FILE"; then
    pass "AUTOPILOT_ENABLED flag in .env.example"
else
    fail "AUTOPILOT_ENABLED flag missing from .env.example"
fi

# Check for system gate implementation
if [ -f "backend/services/system_gate.py" ]; then
    pass "System gate service exists"
else
    warn "System gate service not found (may be in different location)"
fi

echo ""

###############################################################################
# CHECK 6: Bot Validation
###############################################################################
echo "🤖 Check 6: Bot Validation"
echo "-----------------------------------"

if [ -f "backend/validators/bot_validator.py" ]; then
    if grep -q "validate_bot_creation" backend/validators/bot_validator.py; then
        pass "Bot validator with validation method exists"
    else
        fail "Bot validator missing validation method"
    fi
    
    if grep -q "capital" backend/validators/bot_validator.py; then
        pass "Bot validator checks capital"
    else
        warn "Bot validator may not check capital"
    fi
    
    if grep -q "exchange\|platform" backend/validators/bot_validator.py; then
        pass "Bot validator checks exchange/platform"
    else
        warn "Bot validator may not check exchange"
    fi
else
    fail "Bot validator missing"
fi

echo ""

###############################################################################
# CHECK 7: Frontend Build
###############################################################################
echo "⚛️  Check 7: Frontend Build"
echo "-----------------------------------"

if [ -f "frontend/package.json" ]; then
    pass "package.json exists"
    
    # Check if build script exists
    if grep -q '"build"' frontend/package.json; then
        pass "Build script defined in package.json"
    else
        fail "Build script missing from package.json"
    fi
    
    # Check if dependencies exist
    if [ -d "frontend/node_modules" ]; then
        info "node_modules already installed"
        
        # Try to build
        echo "  Building frontend..."
        cd frontend
        if npm run build >/dev/null 2>&1; then
            pass "Frontend build succeeds"
            
            if [ -d "build" ]; then
                pass "Build directory created"
                
                if [ -f "build/index.html" ]; then
                    pass "index.html in build output"
                else
                    fail "index.html missing from build"
                fi
                
                if [ -d "build/static" ]; then
                    pass "static/ directory in build output"
                else
                    fail "static/ directory missing from build"
                fi
            else
                fail "Build directory not created"
            fi
        else
            fail "Frontend build fails"
        fi
        cd ..
    else
        warn "node_modules not installed (run: cd frontend && npm ci)"
    fi
else
    fail "package.json missing"
fi

echo ""

###############################################################################
# CHECK 8: CI/CD Configuration
###############################################################################
echo "🔄 Check 8: CI/CD Configuration"
echo "-----------------------------------"

if [ -f ".github/workflows/ci.yml" ]; then
    pass "GitHub Actions workflow exists"
    
    if grep -q "backend-checks" .github/workflows/ci.yml; then
        pass "Backend checks job defined"
    else
        warn "Backend checks job missing"
    fi
    
    if grep -q "frontend-build" .github/workflows/ci.yml; then
        pass "Frontend build job defined"
    else
        warn "Frontend build job missing"
    fi
    
    if grep -q "deployment-readiness" .github/workflows/ci.yml; then
        pass "Deployment readiness job defined"
    else
        warn "Deployment readiness job missing"
    fi
else
    fail "GitHub Actions workflow missing"
fi

echo ""

###############################################################################
# CHECK 9: Documentation
###############################################################################
echo "📚 Check 9: Documentation"
echo "-----------------------------------"

if [ -f "docs/ARCHITECTURE_MAP.md" ]; then
    pass "ARCHITECTURE_MAP.md exists"
    
    if grep -q "Canonical" docs/ARCHITECTURE_MAP.md; then
        pass "Documents canonical modules"
    else
        warn "May not document canonical modules"
    fi
else
    fail "ARCHITECTURE_MAP.md missing"
fi

if [ -f "docs/DEPLOYMENT_GUIDE.md" ]; then
    pass "DEPLOYMENT_GUIDE.md exists"
    
    if grep -q "Quick Deployment" docs/DEPLOYMENT_GUIDE.md; then
        pass "Contains deployment instructions"
    else
        warn "May not contain deployment instructions"
    fi
else
    fail "DEPLOYMENT_GUIDE.md missing"
fi

if [ -f "README.md" ]; then
    pass "README.md exists"
else
    warn "README.md missing"
fi

echo ""

###############################################################################
# CHECK 10: Test Scripts
###############################################################################
echo "🧪 Check 10: Test Scripts"
echo "-----------------------------------"

if [ -f "scripts/test_sse.sh" ]; then
    pass "test_sse.sh exists"
    if [ -x "scripts/test_sse.sh" ]; then
        pass "test_sse.sh is executable"
    else
        warn "test_sse.sh not executable (chmod +x needed)"
    fi
else
    fail "test_sse.sh missing"
fi

if [ -f "scripts/test_bots.sh" ]; then
    pass "test_bots.sh exists"
    if [ -x "scripts/test_bots.sh" ]; then
        pass "test_bots.sh is executable"
    else
        warn "test_bots.sh not executable (chmod +x needed)"
    fi
else
    fail "test_bots.sh missing"
fi

if [ -f "scripts/verify_go_live.sh" ]; then
    pass "verify_go_live.sh exists"
    if [ -x "scripts/verify_go_live.sh" ]; then
        pass "verify_go_live.sh is executable"
    else
        warn "verify_go_live.sh not executable (chmod +x needed)"
    fi
else
    fail "verify_go_live.sh missing"
fi

echo ""

###############################################################################
# CHECK 11: Deployment Scripts
###############################################################################
echo "🚀 Check 11: Deployment Scripts"
echo "-----------------------------------"

if [ -f "deployment/install_backend.sh" ]; then
    pass "Backend install script exists"
else
    warn "Backend install script missing"
fi

if [ -f "scripts/deploy.sh" ]; then
    pass "Frontend deploy script exists"
else
    warn "Frontend deploy script missing"
fi

if [ -d "deployment/nginx" ] || [ -f "deployment/nginx-amarktai.conf" ]; then
    pass "Nginx configuration exists"
else
    warn "Nginx configuration missing"
fi

echo ""

###############################################################################
# CHECK 13: DEPLOYMENT BLOCKER CHECKS - CRITICAL
###############################################################################
echo "🚨 Check 13: Deployment Blockers (CRITICAL)"
echo "-----------------------------------"

# Check if we can find the venv or Python environment
PYTHON_CMD="python3"
VENV_PATH=""

# Try to find venv
if [ -d "backend/.venv" ]; then
    VENV_PATH="backend/.venv"
    PYTHON_CMD="backend/.venv/bin/python3"
    pass "Virtual environment found at backend/.venv"
elif [ -d ".venv" ]; then
    VENV_PATH=".venv"
    PYTHON_CMD=".venv/bin/python3"
    pass "Virtual environment found at .venv"
else
    warn "No virtual environment found (backend/.venv or .venv)"
fi

# Check if Python can import critical dependencies
if $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
    pass "FastAPI importable"
else
    fail "FastAPI not importable - run: pip install -r backend/requirements.txt"
fi

if $PYTHON_CMD -c "import uvicorn" 2>/dev/null; then
    pass "Uvicorn importable"
else
    fail "Uvicorn not importable - run: pip install uvicorn"
fi

# Check routes.keys import (CRITICAL BLOCKER)
cd backend 2>/dev/null || true
if $PYTHON_CMD -c "import routes.keys" 2>/dev/null; then
    pass "routes.keys importable (CRITICAL)"
else
    fail "routes.keys import FAILED - API will not start!"
fi

# Check api_key_management module exports (CRITICAL BLOCKER)
if $PYTHON_CMD -c "from routes.api_key_management import encrypt_api_key, decrypt_api_key" 2>/dev/null; then
    pass "routes.api_key_management exports encrypt_api_key, decrypt_api_key (CRITICAL)"
else
    fail "routes.api_key_management imports FAILED - routes.keys will fail!"
fi
cd - >/dev/null 2>&1 || true

# Check for Fernet encryption key environment variables
if [ -n "$AMARKTAI_FERNET_KEY" ]; then
    pass "AMARKTAI_FERNET_KEY is set"
elif [ -n "$FERNET_KEY" ]; then
    pass "FERNET_KEY is set"
else
    warn "Neither AMARKTAI_FERNET_KEY nor FERNET_KEY is set - will derive from JWT_SECRET (not recommended for production)"
    info "Generate a key with: python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
fi

# Check MongoDB directories (deployment responsibility, not repo)
if [ -d "/var/lib/mongodb" ]; then
    pass "/var/lib/mongodb directory exists"
    
    # Check ownership if running as root/sudo
    if [ "$(id -u)" -eq 0 ] || command -v stat >/dev/null 2>&1; then
        OWNER=$(stat -c '%U' /var/lib/mongodb 2>/dev/null || stat -f '%Su' /var/lib/mongodb 2>/dev/null || echo "unknown")
        if [ "$OWNER" = "mongodb" ]; then
            pass "/var/lib/mongodb owned by mongodb user"
        else
            warn "/var/lib/mongodb owner is $OWNER (expected: mongodb)"
            info "Run: sudo chown -R mongodb:mongodb /var/lib/mongodb"
        fi
    fi
else
    fail "/var/lib/mongodb directory does not exist"
    info "Create with: sudo mkdir -p /var/lib/mongodb /var/log/mongodb"
    info "Set ownership: sudo chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb"
    info "Set permissions: sudo chmod 755 /var/lib/mongodb /var/log/mongodb"
fi

if [ -d "/var/log/mongodb" ]; then
    pass "/var/log/mongodb directory exists"
else
    fail "/var/log/mongodb directory does not exist"
    info "Create with: sudo mkdir -p /var/log/mongodb"
    info "Set ownership: sudo chown -R mongodb:mongodb /var/log/mongodb"
fi

# Check port 8000 availability (optional but helpful)
if command -v lsof >/dev/null 2>&1; then
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        warn "Port 8000 is already in use"
        info "Process using port 8000: $(lsof -Pi :8000 -sTCP:LISTEN | tail -n1)"
    else
        pass "Port 8000 is available"
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ':8000 '; then
        warn "Port 8000 appears to be in use"
    else
        pass "Port 8000 is available"
    fi
else
    info "Cannot check port 8000 (lsof/netstat not available)"
fi

echo ""

###############################################################################
# SUMMARY
###############################################################################
echo "=========================================="
echo "📊 DIAGNOSTIC SUMMARY"
echo "=========================================="
echo ""
echo -e "${GREEN}Passed:${NC}   $PASSED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Failed:${NC}   $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✅ PERFECT HEALTH - GO-LIVE READY!${NC}"
        echo ""
        echo "All checks passed with no warnings."
        echo "Repository is production-ready."
        exit 0
    else
        echo -e "${YELLOW}⚠️  GOOD HEALTH - MINOR WARNINGS${NC}"
        echo ""
        echo "All critical checks passed, but $WARNINGS warning(s) found."
        echo "Review warnings above. Most are non-critical."
        exit 0
    fi
else
    echo -e "${RED}❌ HEALTH ISSUES DETECTED${NC}"
    echo ""
    echo "Found $FAILED critical issue(s) that must be fixed."
    echo "Review failures above before deploying."
    exit 1
fi
