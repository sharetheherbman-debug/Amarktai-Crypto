#!/bin/bash
###############################################################################
# GO-LIVE VERIFICATION SCRIPT
# Validates all requirements for production deployment
###############################################################################

# Don't exit on grep failures, but exit on other errors
set +e  # Allow commands to fail (we check return codes manually)

echo "=========================================="
echo "🚀 AMARKTAI NETWORK - GO-LIVE VERIFICATION"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track pass/fail
PASSED=0
FAILED=0

# Helper functions
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
}

# Get API base URL from environment or use default
API_BASE="${API_BASE:-http://localhost:8000}"
echo "Testing API at: $API_BASE"
echo ""

###############################################################################

# Check frontend exchanges configuration
else
fi

# Check backend exchange_limits.py
    if ! grep -q '"kraken"' backend/exchange_limits.py; then
    else
        fail "Backend exchange_limits.py: Kraken still present"
    fi
else
fi

# Check backend config.py
    if ! grep -q "'kraken'" backend/config.py; then
    else
        fail "Backend config.py: Kraken still present"
    fi
else
fi

# Verify bot limits: Luno(5), Binance(10), KuCoin(10), Bybit(10), Kraken(10), Bitget(10), Gateio(10) = 65
echo ""
echo "Checking platform bot limits..."
if grep -A5 "BOT_ALLOCATION" backend/exchange_limits.py | grep -q '"luno": 5' && \
   grep -A5 "BOT_ALLOCATION" backend/exchange_limits.py | grep -q '"binance": 10' && \
   grep -A5 "BOT_ALLOCATION" backend/exchange_limits.py | grep -q '"kucoin": 10' && \
    if grep -q "MAX_BOTS_GLOBAL = 45" backend/exchange_limits.py; then
        pass "Platform bot limits correct: Total 45 bots (5+10+10+10+10)"
    else
        fail "MAX_BOTS_GLOBAL should be 45"
    fi
else
    fail "Platform bot limits incorrect"
fi

echo ""

###############################################################################
# TEST 2: Admin Unlock Endpoint
###############################################################################
echo "🔐 Test 2: Admin Unlock Endpoint"
echo "---------------------------------"

# Note: We can't test with actual password in CI/CD, but we can verify endpoint exists
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_BASE/api/admin/unlock" 2>/dev/null || echo "000")
if [ "$response" = "405" ] || [ "$response" = "422" ] || [ "$response" = "401" ]; then
    # These codes mean endpoint exists (405=method not allowed, 422=validation error, 401=unauthorized)
    pass "Admin unlock endpoint exists at /api/admin/unlock"
else
    if [ "$response" = "404" ]; then
        fail "Admin unlock endpoint not found (404)"
    else
        warn "Admin unlock endpoint returned unexpected code: $response (may not be running)"
    fi
fi

# Check if admin endpoints file has required functions
if grep -q "def unlock_admin_panel" backend/routes/admin_endpoints.py; then
    pass "Admin unlock function defined"
else
    fail "Admin unlock function not found"
fi

if grep -q "def get_system_resources" backend/routes/admin_endpoints.py; then
    pass "System resources monitoring endpoint defined"
else
    fail "System resources monitoring not found"
fi

if grep -q "def get_process_health" backend/routes/admin_endpoints.py; then
    pass "Process health monitoring endpoint defined"
else
    fail "Process health monitoring not found"
fi

if grep -q "def get_system_logs" backend/routes/admin_endpoints.py; then
    pass "System logs viewing endpoint defined"
else
    fail "System logs viewing not found"
fi

if grep -q "def get_user_api_keys_status" backend/routes/admin_endpoints.py; then
    pass "User API keys status endpoint defined"
else
    fail "User API keys status not found"
fi

echo ""

###############################################################################
# TEST 3: API Keys Save/Test Endpoints
###############################################################################
echo "🔑 Test 3: API Keys Endpoints"
echo "-----------------------------"

# Check save endpoint
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_BASE/api/keys/save" 2>/dev/null || echo "000")
if [ "$response" = "405" ] || [ "$response" = "422" ] || [ "$response" = "401" ]; then
    pass "API keys save endpoint exists"
else
    if [ "$response" = "404" ]; then
        fail "API keys save endpoint not found (404)"
    else
        warn "API keys save endpoint returned: $response (may not be running)"
    fi
fi

# Check test endpoint
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_BASE/api/keys/test" 2>/dev/null || echo "000")
if [ "$response" = "405" ] || [ "$response" = "422" ] || [ "$response" = "401" ]; then
    pass "API keys test endpoint exists"
else
    if [ "$response" = "404" ]; then
        fail "API keys test endpoint not found (404)"
    else
        warn "API keys test endpoint returned: $response (may not be running)"
    fi
fi

# NOTE: OVEX is NOT a supported exchange (removed)
# Supported exchanges: luno, binance, kucoin, bybit, kraken, bitget, gate

echo ""

###############################################################################
# TEST 4: Paper Trading Status Endpoint
###############################################################################
echo "📊 Test 4: Paper Trading Status"
echo "--------------------------------"

# Check endpoint exists
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_BASE/api/health/paper-trading" 2>/dev/null || echo "000")
if [ "$response" = "200" ]; then
    pass "Paper trading status endpoint responds (200)"
    
    # Try to fetch actual status
    status_json=$(curl -s --max-time 5 "$API_BASE/api/health/paper-trading" 2>/dev/null || echo "{}")
    if echo "$status_json" | grep -q "is_running"; then
        pass "Paper trading status returns expected fields"
    else
        warn "Paper trading status may not have all expected fields"
    fi
else
    if [ "$response" = "404" ]; then
        fail "Paper trading status endpoint not found (404)"
    else
        warn "Paper trading status returned: $response (may not be running)"
    fi
fi

# Check if status tracking is in paper_trading_engine.py
if grep -q "self.is_running" backend/paper_trading_engine.py && \
   grep -q "self.last_tick_time" backend/paper_trading_engine.py && \
   grep -q "self.last_trade_simulation" backend/paper_trading_engine.py && \
   grep -q "self.last_error" backend/paper_trading_engine.py; then
    pass "Paper trading engine has status tracking variables"
else
    fail "Paper trading engine missing status tracking"
fi

if grep -q "def get_status" backend/paper_trading_engine.py; then
    pass "Paper trading engine has get_status() method"
else
    fail "Paper trading engine missing get_status() method"
fi

echo ""

###############################################################################
# TEST 5: WebSocket Typed Messages
###############################################################################
echo "🔌 Test 5: WebSocket Typed Messages"
echo "-----------------------------------"

# Check websocket manager sends connection message
if grep -q '"type": "connection"' backend/websocket_manager.py; then
    pass "WebSocket sends 'connection' type message"
else
    fail "WebSocket missing 'connection' type"
fi

# Check websocket sends ping
if grep -q '"type": "ping"' backend/websocket_manager.py; then
    pass "WebSocket sends 'ping' type message"
else
    fail "WebSocket missing 'ping' type"
fi

# Check realtime_events uses typed messages
if grep -q '"type":' backend/realtime_events.py; then
    pass "Realtime events use typed messages"
else
    warn "Realtime events may not be using typed messages"
fi

# Check if trade_update, bot_update types exist
if grep -q '"type": "trade_executed"' backend/realtime_events.py || \
   grep -q '"type": "bot_created"' backend/realtime_events.py; then
    pass "Realtime events have trade/bot update types"
else
    warn "Realtime events missing some update types"
fi

echo ""

###############################################################################
# TEST 6: No Kraken References in Current Files (case-insensitive)
###############################################################################
echo "🔍 Test 6: Kraken Reference Check"
echo "----------------------------------"

# Check for kraken references in key files (excluding git history, comments about removal)
kraken_found=0

# Frontend JS files
if grep -ri "kraken" frontend/src/ --include="*.js" --include="*.jsx" 2>/dev/null | grep -v "Removed\|removed\|Replace" | grep -q .; then
    fail "Found 'Kraken' references in frontend/src/"
    kraken_found=1
else
    pass "No Kraken references in frontend/src/"
fi

# Backend Python files (excluding migrations/docs about the change)
if grep -ri "kraken" backend/ --include="*.py" 2>/dev/null | grep -v "Removed\|removed\|Replace\|#.*kraken" | grep -q .; then
    fail "Found 'Kraken' references in backend/"
    kraken_found=1
else
    pass "No Kraken references in backend/"
fi

# Platform constants check
if [ -f "backend/platform_constants.py" ]; then
    if grep -qi "kraken" backend/platform_constants.py; then
        fail "Kraken found in platform_constants.py"
        kraken_found=1
    else
        pass "Platform constants clean (no Kraken)"
    fi
else
    warn "platform_constants.py not found"
fi

if [ -f "frontend/src/constants/platforms.js" ]; then
    if grep -qi "kraken" frontend/src/constants/platforms.js; then
        fail "Kraken found in frontend constants/platforms.js"
        kraken_found=1
    else
        pass "Frontend platform constants clean (no Kraken)"
    fi
else
    warn "frontend constants/platforms.js not found"
fi

echo ""

###############################################################################
# TEST 7: Platform Constants Validation
###############################################################################
echo "📐 Test 7: Platform Constants Validation"
echo "----------------------------------------"

# Check backend constants exist and have correct platforms
if [ -f "backend/platform_constants.py" ]; then
    # Check all 5 platforms present
    if grep -q "'luno'" backend/platform_constants.py && \
       grep -q "'binance'" backend/platform_constants.py && \
       grep -q "'kucoin'" backend/platform_constants.py && \
        pass "Backend constants: All 5 platforms defined"
    else
        fail "Backend constants: Missing one or more platforms"
    fi
    
    # Check total capacity is 45
    if grep -q "45" backend/platform_constants.py; then
        pass "Backend constants: Total capacity appears correct"
    else
        warn "Backend constants: Could not verify total capacity of 45"
    fi
else
    fail "Backend platform_constants.py not found"
fi

# Check frontend constants exist and have correct platforms
if [ -f "frontend/src/constants/platforms.js" ]; then
    if grep -q "'luno'" frontend/src/constants/platforms.js && \
       grep -q "'binance'" frontend/src/constants/platforms.js && \
       grep -q "'kucoin'" frontend/src/constants/platforms.js && \
        pass "Frontend constants: All 5 platforms defined"
    else
        fail "Frontend constants: Missing one or more platforms"
    fi
    
    # Check maxBots are correct
    if grep -q "maxBots: 5" frontend/src/constants/platforms.js && \
       grep -q "maxBots: 10" frontend/src/constants/platforms.js; then
        pass "Frontend constants: Bot limits appear correct"
    else
        warn "Frontend constants: Could not verify bot limits"
    fi
else
    fail "Frontend constants/platforms.js not found"
fi

echo ""

###############################################################################
# TEST 8: Dashboard PlatformSelector Check
###############################################################################
echo "🔍 Test 8: Dashboard PlatformSelector Duplication"
echo "--------------------------------------------------"

# Count PlatformSelector usages in Dashboard.js
PLATFORM_SELECTOR_COUNT=$(grep -c "PlatformSelector" frontend/src/pages/Dashboard.js || echo "0")
echo "Found $PLATFORM_SELECTOR_COUNT PlatformSelector references in Dashboard.js"

# Should be exactly 3: 1 import and 2 usage (Bot Management + Live Trades)
if [ "$PLATFORM_SELECTOR_COUNT" -eq "3" ]; then
    pass "Dashboard has no duplicate PlatformSelector (1 import + 2 usage)"
elif [ "$PLATFORM_SELECTOR_COUNT" -lt "3" ]; then
    fail "Dashboard is missing PlatformSelector"
else
    fail "Dashboard has duplicate PlatformSelector instances (found $PLATFORM_SELECTOR_COUNT, expected 3)"
fi

echo ""

###############################################################################
# TEST 9: Kraken References Check
###############################################################################
echo "🔎 Test 9: Kraken References (Should be 0)"
echo "-------------------------------------------"

# Check entire repo for Kraken references (case insensitive)
KRAKEN_COUNT=$(grep -ri "kraken" . --include="*.js" --include="*.py" --include="*.jsx" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=build --exclude-dir=dist --exclude="verify_go_live.sh" 2>/dev/null | wc -l || echo "0")

if [ "$KRAKEN_COUNT" -eq "0" ]; then
    pass "No Kraken references found in codebase"
else
    echo ""
    echo "Found Kraken references:"
    grep -ri "kraken" . --include="*.js" --include="*.py" --include="*.jsx" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=build --exclude-dir=dist --exclude="verify_go_live.sh" 2>/dev/null | head -10
    echo ""
    fail "Found $KRAKEN_COUNT Kraken references - should be 0"
fi

echo ""

###############################################################################
# TEST 10: Hardcoded Platform Arrays Check
###############################################################################
echo "📝 Test 10: Hardcoded Platform Arrays in Dashboard"
echo "---------------------------------------------------"

# Check for hardcoded platform arrays (not sourced from constants)
if grep -q "const allPlatforms = \[" frontend/src/pages/Dashboard.js 2>/dev/null; then
    # Check if it's using the constants properly
    if grep -q "SUPPORTED_PLATFORMS.map" frontend/src/pages/Dashboard.js 2>/dev/null; then
        pass "Dashboard uses platform constants (SUPPORTED_PLATFORMS.map)"
    else
        fail "Dashboard has hardcoded platform array not sourced from constants"
    fi
else
    pass "No hardcoded platform arrays found in Dashboard"
fi

echo ""

###############################################################################
# TEST 11: Frontend Build and Bundle Verification (Optional)
###############################################################################
echo "🏗️ Test 11: Frontend Build & Bundle Verification (Optional)"
echo "-------------------------------------------------------------"

# Check if BUILD_FRONTEND env var is set
if [ "${BUILD_FRONTEND}" = "true" ]; then
    # Check if node_modules exists
    if [ ! -d "frontend/node_modules" ]; then
        warn "node_modules not found, running npm ci..."
        cd frontend && npm ci --silent && cd ..
    fi

    # Build frontend
    echo "Building frontend..."
    cd frontend
    if npm run build > /tmp/build.log 2>&1; then
        pass "Frontend build successful"
    
    # Check if build directory exists
    if [ -d "build" ]; then
        pass "Build directory created"
        
        # Find main JS bundle
        MAIN_JS=$(find build/static/js -name "main.*.js" 2>/dev/null | head -1)
        
        if [ -n "$MAIN_JS" ]; then
            pass "Found main JS bundle: $(basename $MAIN_JS)"
            
            # Check for required strings in bundle
            echo "Checking bundle for required strings..."
            
            # NOTE: OVEX is NOT a supported exchange (removed)
            # Supported exchanges: luno, binance, kucoin, bybit, kraken, bitget, gate
            
            if grep -q "Win Rate\|WIN RATE" "$MAIN_JS"; then
                pass "Bundle contains 'Win Rate'"
            else
                fail "Bundle missing 'Win Rate' string"
            fi
            
            if grep -q "Trade Count\|TRADES" "$MAIN_JS"; then
                pass "Bundle contains 'Trade Count/TRADES'"
            else
                fail "Bundle missing 'Trade Count' string"
            fi
            
            if grep -q "Platform Comparison\|Platform Performance" "$MAIN_JS"; then
                pass "Bundle contains platform comparison text"
            else
                warn "Bundle might be missing platform comparison text"
            fi
            
            # Verify Kraken is NOT in bundle
            if grep -qi "kraken" "$MAIN_JS"; then
                fail "Bundle contains 'Kraken' - should be removed"
            else
                pass "Bundle does not contain Kraken"
            fi
            
        else
            fail "Main JS bundle not found in build/static/js"
        fi
    else
        fail "Build directory not created"
    fi
    else
        fail "Frontend build failed - check /tmp/build.log for details"
        cat /tmp/build.log | tail -20
    fi

    cd ..
else
    warn "Skipping frontend build (set BUILD_FRONTEND=true to enable)"
    warn "Bundle verification checks will be skipped"
fi

echo ""

###############################################################################
# TEST 12: Platform Constants Validation
###############################################################################
echo "⚙️ Test 12: Platform Constants Validation"
echo "------------------------------------------"

# Check frontend constants
if [ -f "frontend/src/constants/platforms.js" ]; then
    PLATFORM_COUNT=$(grep -o "'luno'\|'binance'\|'kucoin'\|'ovex'\|'valr'" frontend/src/constants/platforms.js | sort -u | wc -l)
    if [ "$PLATFORM_COUNT" -eq "5" ]; then
        pass "Frontend constants have exactly 5 platforms"
    else
        fail "Frontend constants have $PLATFORM_COUNT platforms (expected 5)"
    fi
    
    # Check TOTAL_BOT_CAPACITY
    if grep -q "TOTAL_BOT_CAPACITY.*45" frontend/src/constants/platforms.js; then
        pass "Frontend TOTAL_BOT_CAPACITY is 45"
    else
        fail "Frontend TOTAL_BOT_CAPACITY is not 45"
    fi
fi

# Check backend constants
if [ -f "backend/platform_constants.py" ]; then
    BACKEND_PLATFORM_COUNT=$(grep -o "'luno'\|'binance'\|'kucoin'\|'ovex'\|'valr'" backend/platform_constants.py | sort -u | wc -l)
    if [ "$BACKEND_PLATFORM_COUNT" -eq "5" ]; then
        pass "Backend constants have exactly 5 platforms"
    else
        fail "Backend constants have $BACKEND_PLATFORM_COUNT platforms (expected 5)"
    fi
    
    # Check total bot capacity
    if grep -q "TOTAL_BOT_CAPACITY.*45" backend/platform_constants.py; then
        pass "Backend TOTAL_BOT_CAPACITY is 45"
    else
        fail "Backend TOTAL_BOT_CAPACITY is not 45"
    fi
fi

echo ""

###############################################################################
# TEST 13: File Structure Check
###############################################################################
echo "📁 Test 13: File Structure"
echo "--------------------------"

required_files=(
    "backend/exchange_limits.py"
    "backend/config.py"
    "backend/paper_trading_engine.py"
    "backend/platform_constants.py"
    "backend/routes/admin_endpoints.py"
    "backend/routes/api_key_management.py"
    "backend/routes/system_health_endpoints.py"
    "backend/websocket_manager.py"
    "backend/realtime_events.py"
    "frontend/src/config/exchanges.js"
    "frontend/src/lib/platforms.js"
    "frontend/src/constants/platforms.js"
    "frontend/src/components/Dashboard/CreateBotSection.js"
    "frontend/src/components/Dashboard/APISetupSection.js"
)

# Note: LiveTradesView.js should NOT exist (it was removed as unused)

# Note: LiveTradesView.js should NOT exist (it was removed as unused)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        pass "File exists: $file"
    else
        fail "File missing: $file"
    fi
done

# Verify LiveTradesView was removed
if [ -f "frontend/src/components/LiveTradesView.js" ]; then
    fail "LiveTradesView.js still exists - should be removed (unused component)"
else
    pass "LiveTradesView.js correctly removed (was unused)"
fi

echo ""

###############################################################################
# TEST 14: ErrorBoundary Component Check
###############################################################################
echo "🛡️ Test 14: ErrorBoundary Component"
echo "------------------------------------"

if [ -f "frontend/src/components/ErrorBoundary.js" ]; then
    pass "ErrorBoundary component exists"
    
    # Check if it has key methods
    if grep -q "componentDidCatch" frontend/src/components/ErrorBoundary.js && \
       grep -q "getDerivedStateFromError" frontend/src/components/ErrorBoundary.js; then
        pass "ErrorBoundary has required error handling methods"
    else
        fail "ErrorBoundary missing required error handling methods"
    fi
    
    # Check if Dashboard uses ErrorBoundary
    if grep -q "import.*ErrorBoundary" frontend/src/pages/Dashboard.js && \
       grep -q "<ErrorBoundary" frontend/src/pages/Dashboard.js; then
        pass "Dashboard uses ErrorBoundary component"
    else
        fail "Dashboard does not use ErrorBoundary"
    fi
else
    fail "ErrorBoundary component not found"
fi

echo ""

###############################################################################
# TEST 15: UI Layout Verification (50/50 splits)
###############################################################################
echo "📐 Test 15: UI Layout Verification"
echo "-----------------------------------"

# Check for 50/50 split patterns in Dashboard
if grep -q "flex: '0 0 50%'" frontend/src/pages/Dashboard.js || \
   grep -q "flex: 0 0 50%" frontend/src/pages/Dashboard.js; then
    pass "Dashboard has 50/50 split layouts"
else
    warn "Could not verify 50/50 split layouts in Dashboard"
fi

# Check that PlatformSelector is only used in correct locations
# Count actual JSX usage (not import statement)
SELECTOR_COUNT=$(grep -c "<PlatformSelector" frontend/src/pages/Dashboard.js || echo "0")
# Should be exactly 2 usage instances: Bot Management right panel + Live Trades right panel
if [ "$SELECTOR_COUNT" -eq "2" ]; then
    pass "PlatformSelector usage count correct (2 usage: Bot Management + Live Trades)"
else
    fail "PlatformSelector usage count: $SELECTOR_COUNT (expected 2: Bot Management + Live Trades)"
fi

echo ""

###############################################################################
# TEST 16: Graph Height Verification
###############################################################################
echo "📊 Test 16: Profit Graph Height"
echo "--------------------------------"

# Check if graph height is 310px
if grep -q "height: '310px'" frontend/src/pages/Dashboard.js; then
    pass "Profit graph height increased to 310px"
elif grep -q "height: '280px'" frontend/src/pages/Dashboard.js; then
    fail "Profit graph still at old height (280px)"
else
    warn "Could not verify profit graph height"
fi

echo ""

###############################################################################
# TEST 17: Deployment Script Verification
###############################################################################
echo "🚀 Test 17: Deployment Script"
echo "------------------------------"

if [ -f "scripts/deploy.sh" ]; then
    pass "Deployment script exists"
    
    # Check if executable
    if [ -x "scripts/deploy.sh" ]; then
        pass "Deployment script is executable"
    else
        warn "Deployment script is not executable (run: chmod +x scripts/deploy.sh)"
    fi
    
    # Check for key deployment steps
    if grep -q "npm ci" scripts/deploy.sh && \
       grep -q "npm run build" scripts/deploy.sh && \
       grep -q "rsync" scripts/deploy.sh; then
        pass "Deployment script has required build and sync steps"
    else
        fail "Deployment script missing required steps"
    fi
else
    fail "Deployment script not found at scripts/deploy.sh"
fi

echo ""

###############################################################################
# TEST 18: GO_LIVE.md Documentation
###############################################################################
echo "📖 Test 18: GO_LIVE Documentation"
echo "----------------------------------"

if [ -f "docs/GO_LIVE.md" ]; then
    pass "GO_LIVE.md documentation exists"
    
    # Check for key sections
    if grep -q "VPS" docs/GO_LIVE.md && \
       grep -q "nginx" docs/GO_LIVE.md && \
       grep -q "deployment" docs/GO_LIVE.md; then
        pass "GO_LIVE.md has required deployment sections"
    else
        warn "GO_LIVE.md may be missing some sections"
    fi
else
    fail "GO_LIVE.md documentation not found"
fi

echo ""

###############################################################################
# TEST 19: Paper Trading Onboarding Note
###############################################################################
echo "📝 Test 19: Paper Trading Onboarding Removal"
echo "--------------------------------------------"

# Per production blocker fixes, this block was intentionally removed
if ! grep -q "Getting Started with Paper Trading" frontend/src/pages/Dashboard.js; then
    pass "Paper trading onboarding note correctly removed (per production blocker fixes)"
else
    fail "Paper trading onboarding note should be removed"
fi

echo ""

###############################################################################
# SUMMARY
###############################################################################
echo "=========================================="
echo "📊 VERIFICATION SUMMARY"
echo "=========================================="
echo ""

###############################################################################
# TEST: PRODUCTION BLOCKER FIXES
###############################################################################
echo "🚨 Production Blocker Fixes Verification"
echo "----------------------------------------"

# Test 1: Show/Hide Admin Command
echo "Checking show/hide admin command handler..."
if grep -q "msgLower === 'show admin'" frontend/src/pages/Dashboard.js && \
   grep -q "msgLower === 'hide admin'" frontend/src/pages/Dashboard.js; then
    pass "Show/hide admin commands exist"
else
    fail "Show/hide admin commands not found"
fi

if grep -q "originalInput.toLowerCase().trim()" frontend/src/pages/Dashboard.js || \
   grep -q "msgLower = originalInput.toLowerCase().trim()" frontend/src/pages/Dashboard.js; then
    pass "Admin command parsing is case-insensitive and trims whitespace"
else
    fail "Admin command parsing not properly implemented"
fi

if grep -q "/admin/unlock" frontend/src/pages/Dashboard.js; then
    pass "Admin unlock endpoint is called"
else
    fail "Admin unlock endpoint not called"
fi

# Test 2: Welcome Block Removed
echo "Checking welcome block removal..."
if ! grep -q "Getting Started with Paper Trading" frontend/src/pages/Dashboard.js; then
    pass "Unwanted welcome block removed"
else
    fail "Welcome block still present - should be deleted"
fi

# Test 3: API Keys Authorization Header
echo "Checking API keys authorization header..."
if grep -q 'Authorization: `Bearer \${token}`' frontend/src/components/Dashboard/APISetupSection.js; then
    pass "APISetupSection Authorization header is correct"
else
    fail "APISetupSection Authorization header is corrupted or incorrect"
fi

# Test 4: DecisionTrace filteredDecisions Fix
echo "Checking DecisionTrace component..."
if grep -q "useMemo" frontend/src/components/DecisionTrace.js; then
    if grep -A5 "const filteredDecisions = useMemo" frontend/src/components/DecisionTrace.js | grep -q "decisions.filter"; then
        pass "DecisionTrace uses useMemo for filteredDecisions"
    else
        fail "DecisionTrace useMemo implementation incorrect"
    fi
else
    fail "DecisionTrace does not use useMemo"
fi

# Test 5: Profit Graph Height
echo "Checking profit graph height..."
if grep -q "minHeight: '350px'" frontend/src/pages/Dashboard.js || \
   grep -q "height: '350px'" frontend/src/pages/Dashboard.js; then
    pass "Profit graph height increased to 350px"
else
    warn "Profit graph height may not be properly increased (looking for 350px)"
fi

# Test 6: Live Trades Single Selector
echo "Checking Live Trades platform selector..."
selector_count=$(grep -c "PlatformSelector" frontend/src/pages/Dashboard.js | head -1)
if [ "$selector_count" -le 3 ]; then
    pass "Live Trades section has controlled platform selectors"
else
    warn "Multiple PlatformSelector instances found ($selector_count) - verify no duplicates in Live Trades"
fi

# Test 7: Admin Endpoints
echo "Checking admin panel endpoints..."
if grep -q "def get_system_stats_extended" backend/routes/admin_endpoints.py || \
   grep -q "/api/admin/system-stats" backend/routes/admin_endpoints.py; then
    pass "Admin system-stats endpoint exists"
else
    fail "Admin system-stats endpoint not found"
fi

if grep -q "def get_user_storage_usage" backend/routes/admin_endpoints.py || \
   grep -q "/api/admin/user-storage" backend/routes/admin_endpoints.py; then
    pass "Admin user-storage endpoint exists"
else
    fail "Admin user-storage endpoint not found"
fi

# Test 8: Bot Override Endpoint
echo "Checking bot override endpoint..."
if grep -q "def override_bot_to_live" backend/routes/admin_endpoints.py || \
   grep -q "/api/admin/bots/{bot_id}/override-live" backend/routes/admin_endpoints.py; then
    pass "Admin bot override endpoint exists"
else
    fail "Admin bot override endpoint not found"
fi

if grep -q "handleBotOverrideLive" frontend/src/pages/Dashboard.js; then
    pass "Frontend bot override handler exists"
else
    fail "Frontend bot override handler not found"
fi

# Test 9: ErrorBoundary Wrapping
echo "Checking ErrorBoundary usage in metrics..."
if grep -A10 "metricsTab === 'decision-trace'" frontend/src/pages/Dashboard.js | grep -q "ErrorBoundary"; then
    pass "Decision Trace wrapped in ErrorBoundary"
else
    fail "Decision Trace not wrapped in ErrorBoundary"
fi

echo ""
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED - READY FOR GO-LIVE! 🎉${NC}"
    exit 0
else
    echo -e "${RED}✗ $FAILED CHECK(S) FAILED - REVIEW REQUIRED${NC}"
    exit 1
fi
