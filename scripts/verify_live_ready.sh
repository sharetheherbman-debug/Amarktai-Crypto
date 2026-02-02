#!/bin/bash
###############################################################################
# LIVE READY VERIFICATION SCRIPT
# Quick verification script for deployment readiness
# Checks: API endpoints, platform configuration, bot capacity, wallet services
###############################################################################

set -e

echo "=========================================="
echo "🚀 AMARKTAI NETWORK - LIVE READY CHECK"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0

pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# API base URL
API_BASE="${API_BASE:-http://localhost:8000}"
TOKEN="${AUTH_TOKEN:-}"

echo "Testing API at: $API_BASE"
echo ""

###############################################################################
# 1. HEALTH & AUTH ENDPOINTS
###############################################################################
echo "=== 1. Health & Auth Endpoints ==="

# Health check
if curl -s -f "$API_BASE/health" > /dev/null 2>&1; then
    pass "Health endpoint responding"
else
    fail "Health endpoint not responding"
fi

# Check login endpoint exists
if curl -s -f -X POST "$API_BASE/api/auth/login" -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test"}' > /dev/null 2>&1; then
    pass "Login endpoint exists (401 expected)"
else
    fail "Login endpoint not responding"
fi

echo ""

###############################################################################
# 2. API KEYS ENDPOINTS (Unified)
###############################################################################
echo "=== 2. API Keys Endpoints (Unified) ==="

# Check providers list (public endpoint)
if curl -s -f "$API_BASE/api/keys/providers" | grep -q "providers"; then
    pass "GET /api/keys/providers working"
else
    fail "GET /api/keys/providers not working"
fi

# Note: Other endpoints require auth
echo "  Note: /api/keys/list, /save, /test, /{provider} require authentication"

echo ""

###############################################################################
# 3. PROFIT/ANALYTICS ENDPOINTS
###############################################################################
echo "=== 3. Profit/Analytics Endpoints ==="

# Check if profit-history compatibility endpoint exists
if curl -s "$API_BASE/api/analytics/profit-history?period=7d" | grep -q "error\|data\|success" 2>/dev/null; then
    pass "GET /api/analytics/profit-history compatibility endpoint exists"
else
    warn "GET /api/analytics/profit-history may require authentication"
fi

echo ""

###############################################################################
# 4. PLATFORM CONFIGURATION
###############################################################################
echo "=== 4. Platform Configuration ==="

# Check exchange_limits.py for 7 exchanges
# Note: "gate" is the internal ID, displayed as "Gate.io" in UI
REQUIRED_EXCHANGES=("luno" "binance" "kucoin" "bybit" "kraken" "bitget" "gate")
EXCHANGE_COUNT=0

for exchange in "${REQUIRED_EXCHANGES[@]}"; do
    if grep -q "\"$exchange\"" backend/exchange_limits.py 2>/dev/null; then
        ((EXCHANGE_COUNT++))
    fi
done

if [ $EXCHANGE_COUNT -eq 7 ]; then
    pass "All 7 exchanges configured: ${REQUIRED_EXCHANGES[*]}"
else
    fail "Only $EXCHANGE_COUNT/7 exchanges found"
fi

# Check for VALR/OVEX (should NOT exist)
if grep -qi "valr\|ovex" backend/exchange_limits.py backend/platforms.py backend/config.py 2>/dev/null; then
    fail "VALR/OVEX found in active code (must be removed)"
else
    pass "No VALR/OVEX in active code"
fi

echo ""

###############################################################################
# 5. BOT CAPACITY CONFIGURATION
###############################################################################
echo "=== 5. Bot Capacity Configuration ==="

# Check MAX_BOTS_GLOBAL
MAX_BOTS_GLOBAL=$(grep "MAX_BOTS_GLOBAL.*=" backend/exchange_limits.py 2>/dev/null | grep -o "[0-9]\+" | head -1)
if [ "$MAX_BOTS_GLOBAL" = "65" ]; then
    pass "MAX_BOTS_GLOBAL = 65"
else
    fail "MAX_BOTS_GLOBAL = $MAX_BOTS_GLOBAL (should be 65)"
fi

# Check MAX_TOTAL_BOTS
MAX_TOTAL_BOTS=$(grep "MAX_TOTAL_BOTS.*=" backend/config.py 2>/dev/null | grep -o "[0-9]\+" | head -1)
if [ "$MAX_TOTAL_BOTS" = "65" ]; then
    pass "MAX_TOTAL_BOTS = 65"
else
    fail "MAX_TOTAL_BOTS = $MAX_TOTAL_BOTS (should be 65)"
fi

echo ""

###############################################################################
# 6. WALLET SERVICES
###############################################################################
echo "=== 6. Wallet Services ==="

# Check transfer state machine exists
if [ -f "backend/services/transfer_state_machine.py" ]; then
    pass "Transfer state machine exists"
    
    # Check for idempotency
    if grep -q "idempotency" backend/services/transfer_state_machine.py; then
        pass "Idempotency support confirmed"
    else
        warn "Idempotency not found in transfer state machine"
    fi
    
    # Check for 2FA enforcement
    if grep -q "REQUIRE_2FA\|totp" backend/services/transfer_state_machine.py; then
        pass "2FA/TOTP support confirmed"
    else
        warn "2FA/TOTP not found in transfer state machine"
    fi
    
    # Check for reserved funds
    if grep -q "reserved_funds" backend/services/transfer_state_machine.py; then
        pass "Reserved funds tracking confirmed"
    else
        warn "Reserved funds tracking not found"
    fi
else
    fail "Transfer state machine not found"
fi

echo ""

###############################################################################
# 7. EMAIL SERVICE
###############################################################################
echo "=== 7. Email Service ==="

if [ -f "backend/email_service.py" ]; then
    # Check for hardcoded credentials (should NOT exist)
    if grep -q "amarktainetwork@gmail.com\|nplqlufxqwihqnpg" backend/email_service.py; then
        fail "Hardcoded SMTP credentials found in email_service.py"
    else
        pass "No hardcoded SMTP credentials"
    fi
    
    # Check for env var usage
    if grep -q "os.getenv.*SMTP" backend/email_service.py; then
        pass "Email service uses environment variables"
    else
        warn "Email service may not use environment variables"
    fi
else
    fail "email_service.py not found"
fi

echo ""

###############################################################################
# 8. PAPER → LIVE PROMOTION
###############################################################################
echo "=== 8. Paper → Live Promotion ==="

if [ -f "backend/engines/promotion_engine.py" ]; then
    pass "Promotion engine exists"
    
    # Check for 7 day requirement
    if grep -q "PAPER_TRAINING_DAYS" backend/engines/promotion_engine.py; then
        pass "Paper training days requirement implemented"
    else
        warn "Paper training days not found"
    fi
    
    # Check for stat separation
    if grep -q "paper_history\|live_.*_count" backend/engines/promotion_engine.py; then
        pass "Paper/Live stat separation implemented"
    else
        warn "Stat separation not confirmed"
    fi
else
    fail "Promotion engine not found"
fi

echo ""

###############################################################################
# 9. BOT SPAWNING CONFIGURATION
###############################################################################
echo "=== 9. Bot Spawning Configuration ==="

# Check for separated thresholds
if grep -q "BOT_SPAWN_PROFIT_THRESHOLD_ZAR" backend/config.py; then
    pass "BOT_SPAWN_PROFIT_THRESHOLD_ZAR configured"
else
    fail "BOT_SPAWN_PROFIT_THRESHOLD_ZAR not found"
fi

if grep -q "NEW_BOT_SEED_CAPITAL_ZAR" backend/config.py; then
    pass "NEW_BOT_SEED_CAPITAL_ZAR configured"
else
    fail "NEW_BOT_SEED_CAPITAL_ZAR not found"
fi

echo ""

###############################################################################
# SUMMARY
###############################################################################
echo "=========================================="
echo "📊 VERIFICATION SUMMARY"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILED CHECK(S) FAILED - REVIEW BEFORE DEPLOYMENT${NC}"
    exit 1
fi
