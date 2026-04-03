#!/bin/bash
# Amarktai Network - Production Verification Script
# Standalone plug-and-play validation for deployment readiness
# MUST pass on a clean VPS before going live

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track overall pass/fail status
OVERALL_STATUS="PASS"
FAILED_TESTS=()

# Helper functions
log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    OVERALL_STATUS="FAIL"
    FAILED_TESTS+=("$1")
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Change to repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Amarktai Network - Verification    ║${NC}"
echo -e "${BLUE}║  Production Readiness Checks         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""
log_info "Repository: $REPO_ROOT"
echo ""

# ============================================================================
# 1. Python Compileall - Syntax Validation
# ============================================================================
log_section "1. Python Syntax Validation (compileall)"

log_info "Running python -m compileall backend/..."
if python3 -m compileall backend/ -q; then
    log_success "All Python files have valid syntax"
else
    log_error "Python syntax errors found - fix before deploying"
fi

# ============================================================================
# 2. Systemd Service Status Check
# ============================================================================
log_section "2. Systemd Service Status"

log_info "Checking amarktai-api.service status..."
if systemctl is-active --quiet amarktai-api.service 2>/dev/null; then
    log_success "amarktai-api.service is active and running"
    
    # Show service status details
    UPTIME=$(systemctl show amarktai-api.service -p ActiveEnterTimestamp --value)
    log_info "Service uptime: $UPTIME"
else
    log_warning "amarktai-api.service is not running"
    log_info "Start with: sudo systemctl start amarktai-api.service"
fi

# Check if service is enabled
if systemctl is-enabled --quiet amarktai-api.service 2>/dev/null; then
    log_success "Service is enabled (will start on boot)"
else
    log_warning "Service is not enabled - run: sudo systemctl enable amarktai-api.service"
fi

# ============================================================================
# 3. Port Binding Check
# ============================================================================
log_section "3. Port Binding Verification"

log_info "Checking if port 8000 is bound to 127.0.0.1..."
if command -v ss >/dev/null 2>&1; then
    if ss -lntp 2>/dev/null | grep -q ":8000.*127.0.0.1"; then
        log_success "Port 8000 is bound to 127.0.0.1 (localhost only)"
    elif ss -lntp 2>/dev/null | grep -q ":8000"; then
        PORT_INFO=$(ss -lntp 2>/dev/null | grep ":8000")
        log_warning "Port 8000 is bound but may not be restricted to localhost"
        log_info "Port details: $PORT_INFO"
    else
        log_warning "Port 8000 is not bound - service may not be running"
    fi
else
    log_warning "ss command not available - skipping port binding check"
fi

# ============================================================================
# 4. Health Endpoint Checks
# ============================================================================
log_section "4. Health Endpoint Checks"

log_info "Checking /api/health/ping endpoint..."
if curl -s -f http://127.0.0.1:8000/api/health/ping > /dev/null 2>&1; then
    log_success "/api/health/ping is responding"
elif curl -s -f http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    log_success "/api/health is responding"
else
    log_warning "Health endpoints not responding - service may not be started"
    log_info "Start service with: sudo systemctl start amarktai-api.service"
fi

# ============================================================================
# 5. OpenAPI Spec Download
# ============================================================================
log_section "5. OpenAPI Specification"

log_info "Downloading /openapi.json..."
if OPENAPI_JSON=$(curl -s -f http://127.0.0.1:8000/openapi.json 2>/dev/null); then
    log_success "OpenAPI spec downloaded successfully"
    
    # Verify it's valid JSON
    if echo "$OPENAPI_JSON" | python3 -m json.tool > /dev/null 2>&1; then
        log_success "OpenAPI spec is valid JSON"
    else
        log_error "OpenAPI spec is not valid JSON"
    fi
    
    # Check for critical endpoints
    CRITICAL_ENDPOINTS=(
        "/api/auth/login"
        "/api/health"
        "/api/bots"
    )
    
    for endpoint in "${CRITICAL_ENDPOINTS[@]}"; do
        if echo "$OPENAPI_JSON" | grep -q "\"$endpoint\""; then
            log_success "Endpoint found: $endpoint"
        else
            log_warning "Endpoint not found: $endpoint"
        fi
    done
else
    log_error "Failed to download OpenAPI spec"
    log_info "Check if service is running on http://127.0.0.1:8000"
fi

# ============================================================================
# 6. Deployment Readiness
# ============================================================================
log_section "6. Deployment Readiness"

# Check deployment scripts exist
if [ -f "deployment/install.sh" ]; then
    log_success "install.sh deployment script exists"
else
    log_error "install.sh not found"
fi

if [ -f "deployment/amarktai-api.service" ]; then
    log_success "Systemd service file exists"
else
    log_error "Systemd service file not found"
fi

if [ -f "deployment/nginx-amarktai.conf" ]; then
    log_success "Nginx config file exists"
else
    log_warning "Nginx config file not found"
fi

# ============================================================================
# FINAL REPORT
# ============================================================================
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}       VERIFICATION SUMMARY            ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ "$OVERALL_STATUS" == "PASS" ]; then
    echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          ✅ ALL CHECKS PASSED        ║${NC}"
    echo -e "${GREEN}║     System is production-ready       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔══════════════════════════════════════╗${NC}"
    echo -e "${RED}║        ❌ VERIFICATION FAILED         ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${RED}Failed checks:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo -e "${RED}  • $test${NC}"
    done
    echo ""
    exit 1
fi
