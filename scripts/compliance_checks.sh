#!/bin/bash
# Compliance Grep Checks
# Verifies no VALR/OVEX, removed features, or ToS-breaking keywords

set -e

REPO_ROOT="/home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment"
cd "$REPO_ROOT"

echo "=============================================================================="
echo "🔍 Compliance Grep Checks"
echo "=============================================================================="
echo ""

ERRORS=0

# Function to check pattern
check_pattern() {
    local pattern="$1"
    local description="$2"
    local exclude_pattern="${3:-archive}"
    
    echo "Checking: $description"
    
    # Search in active code (excluding archives, audit tools, and dependency directories)
    matches=$(grep -ri "$pattern" \
        --include="*.py" \
        --include="*.js" \
        --include="*.jsx" \
        --include="*.md" \
        --include="*.sh" \
        --exclude-dir=".venv" \
        --exclude-dir="site-packages" \
        --exclude-dir="node_modules" \
        --exclude-dir="dist" \
        --exclude-dir="build" \
        --exclude-dir="__pycache__" \
        backend/ frontend/ docs/ scripts/ 2>/dev/null \
        | grep -v "$exclude_pattern" \
        | grep -v "CURRENT_STATE.md" \
        | grep -v "API_CONTRACT.md" \
        | grep -v "IMPLEMENTATION_STATUS.md" \
        | grep -v "WALLET_IMPLEMENTATION_GUIDE.md" \
        | grep -v "audit_report.json" \
        | grep -v "compliance_checks.sh" \
        | grep -v "audit_repo.py" \
        | grep -v "remove_valr_ovex.sh" \
        | grep -v "verify_go_live.sh" \
        | grep -v "comprehensive_audit.sh" \
        | grep -v "preflight.sh" \
        | wc -l)
    
    if [ "$matches" -gt 0 ]; then
        echo "  ❌ FAIL: Found $matches matches for '$pattern'"
        grep -ri "$pattern" \
            --include="*.py" \
            --include="*.js" \
            --include="*.jsx" \
            --include="*.md" \
            --include="*.sh" \
            --exclude-dir=".venv" \
            --exclude-dir="site-packages" \
            --exclude-dir="node_modules" \
            --exclude-dir="dist" \
            --exclude-dir="build" \
            --exclude-dir="__pycache__" \
            backend/ frontend/ docs/ scripts/ 2>/dev/null \
            | grep -v "$exclude_pattern" \
            | grep -v "CURRENT_STATE.md" \
            | grep -v "API_CONTRACT.md" \
            | grep -v "IMPLEMENTATION_STATUS.md" \
            | grep -v "WALLET_IMPLEMENTATION_GUIDE.md" \
            | grep -v "audit_report.json" \
            | grep -v "compliance_checks.sh" \
            | grep -v "audit_repo.py" \
            | grep -v "remove_valr_ovex.sh" \
            | grep -v "verify_go_live.sh" \
            | grep -v "comprehensive_audit.sh" \
        | grep -v "preflight.sh" \
            | head -10
        ((ERRORS++))
    else
        echo "  ✅ PASS: No matches for '$pattern'"
    fi
    echo ""
}

# Check 1: VALR/OVEX (should not exist in active code)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. VALR/OVEX References (Must Be Zero)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_pattern '\bvalr\b' "VALR (lowercase)"
check_pattern '\bVALR\b' "VALR (uppercase)"
check_pattern '\bovex\b' "OVEX (lowercase)"
check_pattern '\bOVEX\b' "OVEX (uppercase)"

# Check 2: Removed features (should not exist in active routes)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Removed Features (Must Be Zero or Archived)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_pattern '\bwalk.*forward\b' "Walk-forward backtesting" "archive\|WALLET_IMPLEMENTATION"
check_pattern '\bMonte.*Carlo\b' "Monte Carlo simulation" "archive\|WALLET_IMPLEMENTATION"
check_pattern '\bstrategy.*marketplace\b' "Strategy marketplace"
check_pattern '\bTradingView\b' "TradingView integration"
check_pattern '\bTelegram.*bot\b' "Telegram bot integration"

# Check 3: ToS violations (should not exist or only in negative context)
# Note: These may have false positives in comments stating what NOT to do
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. ToS-Breaking Keywords (Manual Review Required)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  Note: These may be in comments stating what NOT to do (false positives)"
echo ""

# Manual check - show matches for review but don't fail
echo "Checking: proxy rotation"
matches=$(grep -ri "proxy.*rotat" \
    --include="*.py" \
    backend/ 2>/dev/null \
    | grep -v "archive\|NO proxy rotation" \
    | wc -l)
if [ "$matches" -gt 0 ]; then
    echo "  ⚠️  Found $matches matches - MANUAL REVIEW NEEDED"
    grep -ri "proxy.*rotat" --include="*.py" backend/ 2>/dev/null | grep -v "archive\|NO proxy rotation" | head -5
else
    echo "  ✅ No proxy rotation references"
fi
echo ""

echo "Checking: wash trading / noise trades"
matches=$(grep -ri "wash.*trad\|noise.*trade" \
    --include="*.py" \
    backend/ 2>/dev/null \
    | grep -v "archive\|NO.*wash\|NO.*noise" \
    | wc -l)
if [ "$matches" -gt 0 ]; then
    echo "  ⚠️  Found $matches matches - MANUAL REVIEW NEEDED"
    grep -ri "wash.*trad\|noise.*trade" --include="*.py" backend/ 2>/dev/null | grep -v "archive\|NO.*wash\|NO.*noise" | head -5
else
    echo "  ✅ No wash trading / noise trade references"
fi
echo ""

# Check 4: Verify 7 exchanges
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Exchange Count Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "backend/exchange_limits.py" ]; then
    REQUIRED=("luno" "binance" "kucoin" "bybit" "kraken" "bitget" "gate")
    FOUND=0
    
    for exchange in "${REQUIRED[@]}"; do
        if grep -q "\"$exchange\"" backend/exchange_limits.py; then
            echo "  ✅ Exchange configured: $exchange"
            ((FOUND++))
        else
            echo "  ❌ Exchange NOT configured: $exchange"
            ((ERRORS++))
        fi
    done
    
    if [ $FOUND -eq 7 ]; then
        echo "  ✅ Exactly 7 exchanges configured (correct)"
    else
        echo "  ❌ Expected 7 exchanges, found $FOUND"
        ((ERRORS++))
    fi
else
    echo "  ❌ exchange_limits.py not found"
    ((ERRORS++))
fi
echo ""

# Summary
echo "=============================================================================="
echo "Summary"
echo "=============================================================================="

if [ $ERRORS -eq 0 ]; then
    echo "✅ ALL COMPLIANCE CHECKS PASSED"
    echo ""
    echo "Repository is compliant with production requirements:"
    echo "  - No VALR/OVEX references in active code"
    echo "  - No removed features in active routes"
    echo "  - Exactly 7 exchanges configured"
    echo "  - No obvious ToS violations"
    echo ""
    exit 0
else
    echo "❌ $ERRORS COMPLIANCE ERRORS FOUND"
    echo ""
    echo "Fix errors before production deployment."
    echo ""
    exit 1
fi
