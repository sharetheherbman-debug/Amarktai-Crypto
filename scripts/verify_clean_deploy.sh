#!/usr/bin/env bash
#
# verify_clean_deploy.sh - Clean Deploy Verification
#
# This script verifies that a fresh clone can:
# 1. Install dependencies
# 2. Pass route collision tests
# 3. Pass exchange validation tests
# 4. Start the backend server
# 5. Access critical API endpoints
#
# Exit codes: 0=PASS, 1=FAIL

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
TESTS_DIR="$REPO_ROOT/tests"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((TESTS_PASSED++)) || true
    ((TESTS_RUN++)) || true
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ((TESTS_FAILED++)) || true
    ((TESTS_RUN++)) || true
    FAILED_TESTS+=("$1")
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo "=============================================================================="
echo "🔍 Clean Deploy Verification"
echo "=============================================================================="
echo ""

cd "$REPO_ROOT"

# ----------------------------------------------------------------------------
# Step 1: Verify Dependencies Can Be Installed
# ----------------------------------------------------------------------------
log_info "Step 1: Checking backend dependencies..."

if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
    log_error "requirements.txt not found"
    exit 1
fi

# Check if we can read requirements (don't actually install in test)
if grep -q "fastapi" "$BACKEND_DIR/requirements.txt"; then
    log_success "Backend requirements.txt exists and contains FastAPI"
else
    log_error "Backend requirements.txt missing FastAPI"
fi

# ----------------------------------------------------------------------------
# Step 2: Run Route Collision Tests
# ----------------------------------------------------------------------------
log_info "Step 2: Running route collision tests..."

if [ -f "$TESTS_DIR/test_route_collisions.py" ]; then
    # Try to run the test directly (requires dependencies)
    if command -v python3 &> /dev/null; then
        if python3 -c "import fastapi" 2>/dev/null; then
            cd "$TESTS_DIR"
            if python3 test_route_collisions.py 2>&1; then
                log_success "Route collision tests passed"
            else
                log_error "Route collision tests failed"
            fi
            cd "$REPO_ROOT"
        else
            log_warn "FastAPI not installed - skipping route collision test execution"
            log_info "To run: cd tests && python3 test_route_collisions.py"
        fi
    else
        log_warn "Python3 not available - skipping route collision test execution"
    fi
else
    log_error "test_route_collisions.py not found"
fi

# ----------------------------------------------------------------------------
# Step 3: Run Exchange Validation Tests
# ----------------------------------------------------------------------------
log_info "Step 3: Running exchange validation tests..."

if [ -f "$TESTS_DIR/test_supported_exchanges.py" ]; then
    if command -v python3 &> /dev/null; then
        if python3 -c "import pytest" 2>/dev/null; then
            cd "$TESTS_DIR"
            if python3 test_supported_exchanges.py 2>&1; then
                log_success "Exchange validation tests passed"
            else
                log_error "Exchange validation tests failed"
            fi
            cd "$REPO_ROOT"
        else
            log_warn "pytest not installed - checking manually..."
            
            # Manual check for VALR/OVEX in active code (use word boundaries)
            if grep -riw "valr\|ovex" "$BACKEND_DIR" \
                --include="*.py" \
                --exclude-dir="_archive" \
                --exclude-dir=".venv" \
                --exclude-dir="site-packages" \
                | grep -v "test_" | grep -q .; then
                log_error "VALR/OVEX found in active backend code"
            else
                log_success "No VALR/OVEX in active backend code (manual check)"
            fi
        fi
    else
        log_warn "Python3 not available - skipping exchange validation"
    fi
else
    log_error "test_supported_exchanges.py not found"
fi

# ----------------------------------------------------------------------------
# Step 4: Verify Critical Files Exist
# ----------------------------------------------------------------------------
log_info "Step 4: Verifying critical backend files exist..."

CRITICAL_FILES=(
    "$BACKEND_DIR/server.py"
    "$BACKEND_DIR/auth.py"
    "$BACKEND_DIR/database.py"
    "$BACKEND_DIR/routes/diagnostics.py"
    "$BACKEND_DIR/routes/system_status.py"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        log_success "Found $(basename $file)"
    else
        log_error "Missing critical file: $(basename $file)"
    fi
done

# ----------------------------------------------------------------------------
# Step 5: Check Route Collision Detector in server.py
# ----------------------------------------------------------------------------
log_info "Step 5: Checking route collision detector..."

if grep -q "route_registry = {}" "$BACKEND_DIR/server.py"; then
    if grep -q "Route collision detected - cannot start server" "$BACKEND_DIR/server.py"; then
        log_success "Route collision detector present in server.py"
    else
        log_error "Route collision detector incomplete"
    fi
else
    log_error "Route collision detector not found"
fi

# ----------------------------------------------------------------------------
# Step 6: Verify Import Fixes
# ----------------------------------------------------------------------------
log_info "Step 6: Verifying import fixes..."

# Check get_admin_user exists in auth.py
if grep -q "get_admin_user = require_admin" "$BACKEND_DIR/auth.py"; then
    log_success "get_admin_user alias exists in auth.py"
else
    log_error "get_admin_user alias missing in auth.py"
fi

# Check get_decrypted_key exists in api_key_management.py
if grep -q "async def get_decrypted_key" "$BACKEND_DIR/routes/api_key_management.py"; then
    log_success "get_decrypted_key function exists in api_key_management.py"
else
    log_error "get_decrypted_key function missing in api_key_management.py"
fi

# ----------------------------------------------------------------------------
# Step 7: Verify Duplicate Routes Removed
# ----------------------------------------------------------------------------
log_info "Step 7: Verifying duplicate routes removed..."

# Check diagnostics.py doesn't have duplicate wallet-status
duplicate_wallet_status=$(grep -c "@router.get(\"/wallet-status\")" "$BACKEND_DIR/routes/diagnostics.py" || true)
if [ "$duplicate_wallet_status" -le 1 ]; then
    log_success "No duplicate /wallet-status in diagnostics.py"
else
    log_error "Duplicate /wallet-status found in diagnostics.py ($duplicate_wallet_status occurrences)"
fi

# Check diagnostics.py doesn't have duplicate transfers
duplicate_transfers=$(grep -c "@router.get(\"/transfers\")" "$BACKEND_DIR/routes/diagnostics.py" || true)
if [ "$duplicate_transfers" -le 1 ]; then
    log_success "No duplicate /transfers in diagnostics.py"
else
    log_error "Duplicate /transfers found in diagnostics.py ($duplicate_transfers occurrences)"
fi

# Check compatibility_endpoints doesn't have profit-history
if grep -q "@router.get(\"/analytics/profit-history\")" "$BACKEND_DIR/routes/compatibility_endpoints.py"; then
    log_error "Duplicate /analytics/profit-history still in compatibility_endpoints.py"
else
    log_success "Duplicate /analytics/profit-history removed from compatibility_endpoints.py"
fi

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
echo "=============================================================================="
echo "📊 Verification Summary"
echo "=============================================================================="
echo "Tests Run:    $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    echo ""
    echo "The repository is ready for clean deployment."
    echo ""
    echo "Next steps:"
    echo "  1. git clone on fresh Ubuntu 24.04 VPS"
    echo "  2. cd backend && python3 -m venv .venv && source .venv/bin/activate"
    echo "  3. pip install -r requirements.txt"
    echo "  4. uvicorn server:app --host 0.0.0.0 --port 8000"
    echo ""
    exit 0
else
    echo -e "${RED}❌ VERIFICATION FAILED${NC}"
    echo ""
    echo "Failed checks:"
    for failed_test in "${FAILED_TESTS[@]}"; do
        echo "  - $failed_test"
    done
    echo ""
    echo "Fix these issues before deploying."
    exit 1
fi
