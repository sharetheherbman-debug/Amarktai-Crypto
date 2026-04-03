#!/usr/bin/env bash
#
# acceptance_tests.sh - Verify all critical fixes are working
#
# This script validates that the startup/shutdown hardening fixes
# eliminate all the critical errors observed in journalctl.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# ============================================================================
# Test 1: Service Restart (Multiple Times)
# ============================================================================
log_section "Test 1: Multiple Service Restarts"

if systemctl is-active --quiet amarktai-api; then
    log_info "Running 3 restart cycles..."
    for i in {1..3}; do
        log_info "Restart cycle $i/3..."
        sudo systemctl restart amarktai-api
        sleep 3
        
        if systemctl is-active --quiet amarktai-api; then
            log_success "Restart $i/3 successful"
        else
            log_error "Restart $i/3 failed - service not active"
            TESTS_FAILED=$((TESTS_FAILED + 1))
            FAILED_TESTS+=("Service restart $i/3")
        fi
    done
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    log_error "Service is not running - cannot test restarts"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Service not running")
fi

# ============================================================================
# Test 2: Health Endpoint
# ============================================================================
log_section "Test 2: Health Endpoint (/api/health/ping)"

HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://127.0.0.1:8000/api/health/ping 2>/dev/null || echo "000")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$HEALTH_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    log_success "Health endpoint returns HTTP 200"
    
    # Check if response is valid JSON with timestamp
    if echo "$RESPONSE_BODY" | jq -e '.timestamp' > /dev/null 2>&1; then
        log_success "Health response contains valid JSON with timestamp"
        TIMESTAMP=$(echo "$RESPONSE_BODY" | jq -r '.timestamp')
        log_info "Timestamp: $TIMESTAMP"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Health response is not valid JSON or missing timestamp"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("Health JSON format")
    fi
else
    log_error "Health endpoint returned HTTP $HTTP_CODE (expected 200)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Health endpoint")
fi

# ============================================================================
# Test 3: Check Journalctl for Critical Errors
# ============================================================================
log_section "Test 3: Journalctl Error Checks"

# Get recent logs
RECENT_LOGS=$(sudo journalctl -u amarktai-api -n 500 --no-pager 2>/dev/null || echo "")

# Test 3a: No "never awaited" warnings
if echo "$RECENT_LOGS" | grep -q "never awaited"; then
    log_error "Found 'never awaited' warnings in logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("never awaited warning")
else
    log_success "No 'never awaited' warnings found"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Test 3b: No SchedulerNotRunningError
if echo "$RECENT_LOGS" | grep -q "SchedulerNotRunningError"; then
    log_error "Found SchedulerNotRunningError in logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("SchedulerNotRunningError")
else
    log_success "No SchedulerNotRunningError found"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Test 3c: No "Unclosed client session" warnings
if echo "$RECENT_LOGS" | grep -q "Unclosed client session"; then
    log_error "Found 'Unclosed client session' warnings in logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Unclosed client session")
else
    log_success "No 'Unclosed client session' warnings found"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Test 3d: No "requires to release all resources" warnings
if echo "$RECENT_LOGS" | grep -q "requires.*release.*resources"; then
    log_error "Found 'requires to release all resources' warnings in logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Resource release warning")
else
    log_success "No resource release warnings found"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Test 3e: No "cannot import name 'is_admin'" errors
if echo "$RECENT_LOGS" | grep -q "cannot import name.*is_admin"; then
    log_error "Found 'cannot import is_admin' errors in logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("is_admin import error")
else
    log_success "No 'is_admin' import errors found"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# ============================================================================
# Test 4: Clean Service Stop
# ============================================================================
log_section "Test 4: Clean Service Stop"

log_info "Stopping service..."
sudo systemctl stop amarktai-api
sleep 2

if ! systemctl is-active --quiet amarktai-api; then
    log_success "Service stopped cleanly"
    
    # Check if shutdown had errors
    SHUTDOWN_LOGS=$(sudo journalctl -u amarktai-api -n 100 --no-pager | grep -A5 "Shutting down" || echo "")
    
    if echo "$SHUTDOWN_LOGS" | grep -q "Traceback\|Exception"; then
        log_error "Shutdown produced traceback/exception"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("Shutdown with errors")
    else
        log_success "Shutdown completed without traceback"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    fi
else
    log_error "Service did not stop"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Service stop")
fi

# Restart service for subsequent tests
log_info "Restarting service for subsequent tests..."
sudo systemctl start amarktai-api
sleep 5

# ============================================================================
# Test 5: Feature Flags
# ============================================================================
log_section "Test 5: Feature Flags Check"

log_info "Checking if feature flags are being logged..."
STARTUP_LOGS=$(sudo journalctl -u amarktai-api -n 200 --no-pager | grep "Feature flags" || echo "")

if [ -n "$STARTUP_LOGS" ]; then
    log_success "Feature flags are logged on startup"
    echo "$STARTUP_LOGS" | head -1
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    log_error "Feature flags not found in startup logs"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("Feature flags logging")
fi

# ============================================================================
# Final Report
# ============================================================================
log_section "Acceptance Test Results"

echo ""
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    log_success "🎉 ALL ACCEPTANCE TESTS PASSED!"
    echo ""
    echo "✅ No 'never awaited' warnings"
    echo "✅ No SchedulerNotRunningError"
    echo "✅ No 'Unclosed client session' warnings"
    echo "✅ No resource release warnings"
    echo "✅ No 'is_admin' import errors"
    echo "✅ Health endpoint returns valid JSON"
    echo "✅ Service restarts cleanly"
    echo "✅ Service stops without traceback"
    echo ""
    exit 0
else
    log_error "SOME TESTS FAILED"
    echo ""
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  ❌ $test"
    done
    echo ""
    log_info "Check logs with: sudo journalctl -u amarktai-api -n 200"
    exit 1
fi
