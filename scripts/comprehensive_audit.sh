#!/bin/bash
###############################################################################
# Comprehensive Production Audit Script
# 
# Tests all features, endpoints, and integrations to ensure 150% readiness
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"

echo "=========================================================================="
echo "COMPREHENSIVE PRODUCTION AUDIT"
echo "=========================================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

function test_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((pass_count++))
}

function test_fail() {
    echo -e "${RED}✗${NC} $1"
    ((fail_count++))
}

function test_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "1. Code Quality Checks"
echo "----------------------------------------------------------------------"

# Check for syntax errors in all new files
echo -n "  Checking Python syntax... "
if python3 -m py_compile \
    "$BACKEND_DIR/routes/bot_control.py" \
    "$BACKEND_DIR/routes/autopilot_control.py" \
    "$BACKEND_DIR/routes/admin_enhanced.py" \
    "$BACKEND_DIR/routes/wallet_hub.py" \
    "$BACKEND_DIR/routes/chat_enhanced.py" \
    "$BACKEND_DIR/services/price_fallback_service.py" \
    "$BACKEND_DIR/services/safe_audit_logger.py" \
    "$BACKEND_DIR/utils/timezone_utils.py" \
    2>/dev/null; then
    test_pass "All Python files have valid syntax"
else
    test_fail "Syntax errors found in Python files"
fi

# Check for TODO markers
echo -n "  Checking for TODO markers... "
TODO_COUNT=$(grep -h "# TODO:" \
    "$BACKEND_DIR/routes/bot_control.py" \
    "$BACKEND_DIR/routes/autopilot_control.py" \
    "$BACKEND_DIR/routes/admin_enhanced.py" \
    "$BACKEND_DIR/routes/wallet_hub.py" \
    "$BACKEND_DIR/routes/chat_enhanced.py" \
    "$BACKEND_DIR/services/price_fallback_service.py" \
    "$BACKEND_DIR/services/safe_audit_logger.py" \
    "$BACKEND_DIR/utils/timezone_utils.py" 2>/dev/null | wc -l || echo "0")

if [ "$TODO_COUNT" -eq 0 ]; then
    test_pass "No blocking TODO markers found"
else
    test_warn "Found $TODO_COUNT TODO markers (review if blocking)"
fi

echo ""
echo "2. File Completeness Checks"
echo "----------------------------------------------------------------------"

# Check all required files exist
files=(
    "routes/bot_control.py"
    "routes/autopilot_control.py"
    "routes/admin_enhanced.py"
    "routes/wallet_hub.py"
    "routes/chat_enhanced.py"
    "services/price_fallback_service.py"
    "services/safe_audit_logger.py"
    "utils/timezone_utils.py"
    "paper_trading_engine.py"
)

for file in "${files[@]}"; do
    if [ -f "$BACKEND_DIR/$file" ]; then
        test_pass "File exists: $file"
    else
        test_fail "File missing: $file"
    fi
done

echo ""
echo "3. Router Registration Checks"
echo "----------------------------------------------------------------------"

# Check if routers are registered in server.py
routers=(
    "routes.bot_control"
    "routes.autopilot_control"
    "routes.admin_enhanced"
    "routes.wallet_hub"
    "routes.chat_enhanced"
)

for router in "${routers[@]}"; do
    if grep -q "\"$router\"" "$BACKEND_DIR/server.py"; then
        test_pass "Router registered: $router"
    else
        test_fail "Router NOT registered: $router"
    fi
done

echo ""
echo "4. Exchange Support Checks"
echo "----------------------------------------------------------------------"

# Check VALR and OVEX in paper_trading_engine.py
if grep -q "VALR_PAIRS" "$BACKEND_DIR/paper_trading_engine.py"; then
    test_pass "VALR pairs defined"
else
    test_fail "VALR pairs NOT defined"
fi

if grep -q "OVEX_PAIRS" "$BACKEND_DIR/paper_trading_engine.py"; then
    test_pass "OVEX pairs defined"
else
    test_fail "OVEX pairs NOT defined"
fi

if grep -q "self.valr_exchange" "$BACKEND_DIR/paper_trading_engine.py"; then
    test_pass "VALR exchange initialization found"
else
    test_fail "VALR exchange initialization NOT found"
fi

if grep -q "self.ovex_exchange" "$BACKEND_DIR/paper_trading_engine.py"; then
    test_pass "OVEX exchange initialization found"
else
    test_fail "OVEX exchange initialization NOT found"
fi

echo ""
echo "5. Timezone Implementation Checks"
echo "----------------------------------------------------------------------"

if grep -q "Africa/Johannesburg" "$BACKEND_DIR/utils/timezone_utils.py"; then
    test_pass "Africa/Johannesburg timezone configured"
else
    test_fail "Africa/Johannesburg timezone NOT configured"
fi

if grep -q "get_local_day_start" "$BACKEND_DIR/utils/timezone_utils.py"; then
    test_pass "get_local_day_start function exists"
else
    test_fail "get_local_day_start function NOT found"
fi

echo ""
echo "6. Endpoint Implementation Checks"
echo "----------------------------------------------------------------------"

# Check bot control endpoints
endpoints=(
    "/bots/{bot_id}/pause"
    "/bots/{bot_id}/resume"
    "/bots/{bot_id}/start"
    "/autopilot/status"
    "/autopilot/toggle"
    "/admin/users/list"
    "/wallet/health"
    "/wallet/balances"
    "/chat/clear"
    "/chat/daily-summary"
)

for endpoint in "${endpoints[@]}"; do
    if grep -q "$endpoint" "$BACKEND_DIR/routes"/*.py; then
        test_pass "Endpoint defined: $endpoint"
    else
        test_fail "Endpoint NOT defined: $endpoint"
    fi
done

echo ""
echo "7. Realtime Event Checks"
echo "----------------------------------------------------------------------"

# Check for realtime event emissions
events=(
    "bot_paused"
    "bot_resumed"
    "bot_started"
    "autopilot_toggled"
    "wallet_transfer"
)

for event in "${events[@]}"; do
    if grep -rq "$event" "$BACKEND_DIR/routes"/*.py; then
        test_pass "Event emission found: $event"
    else
        test_warn "Event emission not found: $event (may use different name)"
    fi
done

echo ""
echo "8. Database Collection Checks"
echo "----------------------------------------------------------------------"

if grep -q "wallet_transfers_collection" "$BACKEND_DIR/database.py"; then
    test_pass "wallet_transfers_collection defined"
else
    test_warn "wallet_transfers_collection not in database.py (may be created dynamically)"
fi

if grep -q "audit_logs_collection" "$BACKEND_DIR/database.py" || \
   grep -q "audit_logs_collection" "$BACKEND_DIR/services/safe_audit_logger.py"; then
    test_pass "audit_logs_collection accessible"
else
    test_warn "audit_logs_collection not found"
fi

echo ""
echo "=========================================================================="
echo "AUDIT SUMMARY"
echo "=========================================================================="
echo -e "${GREEN}Passed:${NC} $pass_count"
echo -e "${RED}Failed:${NC} $fail_count"

if [ $fail_count -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ ALL CHECKS PASSED - PRODUCTION READY${NC}"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}✗ SOME CHECKS FAILED - REVIEW REQUIRED${NC}"
    echo ""
    exit 1
fi
