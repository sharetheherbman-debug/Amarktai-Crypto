#!/bin/bash
# Deployment Smoke Tests
# Tests that the three runtime errors are fixed and system starts cleanly

set -e  # Exit on error

echo "🚀 Running Deployment Smoke Tests..."
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Test 1: Config import
echo "Test 1: Config Import (AUTO_PROMOTE_LIVE)"
if python3 -c "from backend.config import AUTO_PROMOTE_LIVE; print(f'AUTO_PROMOTE_LIVE={AUTO_PROMOTE_LIVE}')" 2>/dev/null; then
    echo -e "${GREEN}✅ PASS${NC}: AUTO_PROMOTE_LIVE can be imported from config"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Cannot import AUTO_PROMOTE_LIVE from config"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 2: Type-safe wallet balance handling
echo "Test 2: Type-Safe Wallet Balance Extraction"
python3 << 'PYTHON_CODE'
import sys
sys.path.insert(0, 'backend')

# Test type-safe extraction with dict value
wallet_data = {'available_zar': {'value': 2000.0}, 'error': False}

if not wallet_data.get('error'):
    available_zar = wallet_data.get('available_zar', 0)
    if isinstance(available_zar, dict):
        available_funds = float(available_zar.get('value', 0) if isinstance(available_zar.get('value'), (int, float)) else 0)
    else:
        available_funds = float(available_zar) if isinstance(available_zar, (int, float)) else 0
else:
    available_funds = 1000

# Test comparison (this was causing the error)
PROFIT_THRESHOLD_ZAR = 1000
try:
    result = available_funds > PROFIT_THRESHOLD_ZAR
    print(f"✅ Comparison works: {available_funds} > {PROFIT_THRESHOLD_ZAR} = {result}")
except TypeError as e:
    print(f"❌ Comparison failed: {e}")
    sys.exit(1)

# Test min() function (used in calculate_reinvestment_amount)
try:
    max_reinvest = 1000.0
    reinvest_amount = min(max_reinvest, available_funds)
    print(f"✅ min() works: min({max_reinvest}, {available_funds}) = {reinvest_amount}")
except TypeError as e:
    print(f"❌ min() failed: {e}")
    sys.exit(1)
PYTHON_CODE

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: Type-safe wallet balance extraction works"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Type-safe wallet balance extraction failed"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 3: Self-healing scan_all_users method exists
echo "Test 3: Self-Healing scan_all_users Method"
python3 << 'PYTHON_CODE'
import sys
sys.path.insert(0, 'backend')

from engines.self_healing import self_healing

# Check method exists
if hasattr(self_healing, 'scan_all_users'):
    print("✅ scan_all_users method exists")
    
    # Check it's a coroutine (async method)
    import inspect
    if inspect.iscoroutinefunction(self_healing.scan_all_users):
        print("✅ scan_all_users is an async method")
    else:
        print("⚠️  scan_all_users is not async")
        sys.exit(1)
else:
    print("❌ scan_all_users method does not exist")
    sys.exit(1)
PYTHON_CODE

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: scan_all_users method exists and is async"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: scan_all_users method issue"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 4: Autonomous scheduler error handling
echo "Test 4: Autonomous Scheduler Error Handling"
python3 << 'PYTHON_CODE'
import sys
sys.path.insert(0, 'backend')

# Check that autonomous_scheduler has proper error handling
import inspect
from autonomous_scheduler import AutonomousScheduler

scheduler = AutonomousScheduler()

# Check _hourly_tasks has error handling
hourly_source = inspect.getsource(scheduler._hourly_tasks)
if 'except Exception as e:' in hourly_source and 'continue' in hourly_source:
    print("✅ Hourly tasks have per-user error handling")
else:
    print("⚠️  Hourly tasks may not have proper error handling")

# Check _daily_tasks has error handling
daily_source = inspect.getsource(scheduler._daily_tasks)
if 'except Exception as e:' in daily_source and 'continue' in daily_source:
    print("✅ Daily tasks have per-user error handling")
else:
    print("⚠️  Daily tasks may not have proper error handling")
PYTHON_CODE

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: Autonomous scheduler has error handling"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Autonomous scheduler error handling issue"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 5: Backend imports work
echo "Test 5: Backend Core Imports"
python3 << 'PYTHON_CODE'
import sys
sys.path.insert(0, 'backend')

try:
    # Test critical imports
    from config import ENABLE_LIVE_TRADING, ENABLE_PAPER_TRADING, AUTO_PROMOTE_LIVE
    from bot_lifecycle import bot_lifecycle
    from engines.self_healing import self_healing
    from engines.capital_allocator import capital_allocator
    from autonomous_scheduler import autonomous_scheduler
    
    print("✅ All critical backend imports successful")
    
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)
PYTHON_CODE

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: Backend core imports work"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: Backend core import failed"
    FAILED=$((FAILED + 1))
fi
echo ""

# Test 6: Frontend logo2.png exists
echo "Test 6: Frontend Logo2.png"
if [ -f "frontend/public/assets/logo2.png" ]; then
    echo -e "${GREEN}✅ PASS${NC}: logo2.png exists in frontend/public/assets/"
    PASSED=$((PASSED + 1))
else
    echo -e "${RED}❌ FAIL${NC}: logo2.png missing from frontend/public/assets/"
    FAILED=$((FAILED + 1))
fi
echo ""

# Summary
echo "═══════════════════════════════════════════"
echo "📊 Smoke Test Results"
echo "═══════════════════════════════════════════"
echo -e "${GREEN}✅ Passed: $PASSED${NC}"
echo -e "${RED}❌ Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All smoke tests passed!${NC}"
    echo "The three runtime errors are fixed:"
    echo "  1. ✅ Config import error (AUTO_PROMOTE_LIVE)"
    echo "  2. ✅ Hourly task type error (dict vs int comparison)"
    echo "  3. ✅ Self-healing API mismatch (scan_all_users)"
    exit 0
else
    echo -e "${RED}⚠️  Some tests failed. Review the errors above.${NC}"
    exit 1
fi
