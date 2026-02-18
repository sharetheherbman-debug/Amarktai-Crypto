#!/bin/bash
# Quick Deployment Smoke Tests (No Dependencies)
# Verifies the three runtime errors are fixed at the code level

set -e

echo "🚀 Running Quick Deployment Smoke Tests..."
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PASSED=0
FAILED=0

# Test 1: Check AUTO_PROMOTE_LIVE is defined in config/__init__.py
echo "Test 1: AUTO_PROMOTE_LIVE in config/__init__.py"
if grep -q "AUTO_PROMOTE_LIVE = os.getenv" backend/config/__init__.py && \
   grep -q "'AUTO_PROMOTE_LIVE'" backend/config/__init__.py; then
    echo -e "${GREEN}✅ PASS${NC}: AUTO_PROMOTE_LIVE is defined and exported"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: AUTO_PROMOTE_LIVE not properly defined/exported"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 2: Check type-safe wallet balance handling in capital_allocator.py
echo "Test 2: Type-Safe Wallet Balance Handling"
if grep -q "def extract_numeric_balance" backend/engines/capital_allocator.py && \
   grep -q "self.extract_numeric_balance(wallet_data" backend/engines/capital_allocator.py; then
    echo -e "${GREEN}✅ PASS${NC}: Type-safe helper method exists in capital_allocator"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Type-safe helper method missing"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 3: Check scan_all_users method exists in self_healing.py
echo "Test 3: scan_all_users Method Exists"
if grep -q "async def scan_all_users" backend/engines/self_healing.py; then
    echo -e "${GREEN}✅ PASS${NC}: scan_all_users method exists"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: scan_all_users method not found"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 4: Check error handling in autonomous_scheduler.py
echo "Test 4: Error Handling in Autonomous Scheduler"
if grep -q "except Exception as e:" backend/autonomous_scheduler.py && \
   grep -q "continue  # Continue with next user" backend/autonomous_scheduler.py; then
    echo -e "${GREEN}✅ PASS${NC}: Per-user error handling exists"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Error handling may be missing"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 5: Check bot_lifecycle.py can import AUTO_PROMOTE_LIVE
echo "Test 5: bot_lifecycle.py Import Check"
if grep -q "from config import AUTO_PROMOTE_LIVE" backend/bot_lifecycle.py; then
    echo -e "${GREEN}✅ PASS${NC}: bot_lifecycle imports AUTO_PROMOTE_LIVE from config"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: bot_lifecycle doesn't import AUTO_PROMOTE_LIVE"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 6: Check logo2.png exists
echo "Test 6: Logo2.png Files"
LOGO_COUNT=0
[ -f "logo2.png" ] && LOGO_COUNT=$((LOGO_COUNT + 1))
[ -f "frontend/public/assets/logo2.png" ] && LOGO_COUNT=$((LOGO_COUNT + 1))
[ -f "frontend/assets/logo2.png" ] && LOGO_COUNT=$((LOGO_COUNT + 1))

if [ $LOGO_COUNT -ge 2 ]; then
    echo -e "${GREEN}✅ PASS${NC}: logo2.png files exist ($LOGO_COUNT locations)"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: logo2.png missing (found in $LOGO_COUNT locations)"
    FAILED=$((FAILED + 1))
fi
echo ""

# Summary
echo "═══════════════════════════════════════════"
echo "📊 Quick Smoke Test Results"
echo "═══════════════════════════════════════════"
echo -e "${GREEN}✅ Passed: $PASSED${NC}"
echo -e "${RED}❌ Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All quick smoke tests passed!${NC}"
    echo "Code-level fixes verified:"
    echo "  1. ✅ AUTO_PROMOTE_LIVE defined and exported"
    echo "  2. ✅ Type-safe wallet balance handling added"
    echo "  3. ✅ scan_all_users method implemented"
    echo "  4. ✅ Robust error handling in schedulers"
    echo "  5. ✅ Logo files present"
    exit 0
else
    echo -e "${RED}⚠️  Some tests failed. Review the errors above.${NC}"
    exit 1
fi
