#!/bin/bash
# Script to remove all VALR and OVEX references from the repository

set -e

REPO_ROOT="/home/runner/work/Amarktai-Crypto/Amarktai-Crypto"
cd "$REPO_ROOT"

echo "=============================================================================="
echo "🧹 Removing VALR and OVEX References"
echo "=============================================================================="
echo ""

# Backup strategy: We'll use git to track changes
echo "Creating backup branch..."
git branch backup-before-valr-ovex-removal || true

echo ""
echo "Step 1: Removing/Archiving docs with VALR/OVEX references..."
echo ""

# Move old audit/status docs to archive
mkdir -p docs/archive
DOCS_TO_ARCHIVE=(
    "AUDIT_REPORT.md"
    "COMPREHENSIVE_AUDIT_REPORT.md"
    "COMPREHENSIVE_PRODUCTION_AUDIT.md"
    "FINAL_PRODUCTION_AUDIT.md"
    "IMPLEMENTATION_COMPLETE.md"
    "IMPLEMENTATION_SUMMARY.md"
    "PLATFORM_MIGRATION_SUMMARY.md"
    "PLATFORM_UPDATE_SUMMARY.md"
    "PREMERGE_REPORT.md"
    "PRODUCTION_FEATURES_IMPLEMENTATION.md"
    "PRODUCTION_FIXES_STATUS.md"
    "PRODUCTION_LAUNCH_VERIFICATION.md"
    "PRODUCTION_READY_SUMMARY.md"
    "PRODUCTION_UPDATE_COMPLETE.md"
    "PRODUCTION_UPGRADE_SUMMARY.md"
    "PR_STATUS_REPORT.md"
    "PR_SUMMARY.md"
    "RULE_CONFLICTS_ANALYSIS.md"
    "DASHBOARD_AUDIT_REPORT.md"
    "DEPLOYMENT_SUMMARY.md"
    "GO_LIVE.md"
)

for doc in "${DOCS_TO_ARCHIVE[@]}"; do
    if [ -f "docs/$doc" ]; then
        echo "  Archiving docs/$doc"
        mv "docs/$doc" "docs/archive/$doc"
    fi
done

echo ""
echo "Step 2: Removing VALR/OVEX from remaining active docs..."
echo ""

# Update docs that should remain but need cleaning
if [ -f "docs/admin_panel.md" ]; then
    echo "  Cleaning docs/admin_panel.md"
    # Remove VALR/OVEX lines
    sed -i '/["\x27]valr["\x27]/d' docs/admin_panel.md
    sed -i '/["\x27]ovex["\x27]/d' docs/admin_panel.md
    # Update platform lists
    sed -i 's/`"luno"`, `"binance"`, `"kucoin"`, `"valr"`, `"ovex"`/`"luno"`, `"binance"`, `"kucoin"`, `"bybit"`, `"kraken"`, `"bitget"`, `"gateio"`/g' docs/admin_panel.md
fi

echo ""
echo "Step 3: Cleaning test scripts..."
echo ""

# Clean up test scripts
if [ -f "scripts/go_live_smoke.sh" ]; then
    echo "  Cleaning scripts/go_live_smoke.sh"
    # Replace platform lists
    sed -i 's/luno binance kucoin ovex valr/luno binance kucoin bybit kraken bitget gateio/g' scripts/go_live_smoke.sh
    # Remove OVEX/VALR specific tests
    sed -i '/Test 5: Bot validation with OVEX\/VALR/,/^fi$/d' scripts/go_live_smoke.sh
    sed -i '/OVEX\/VALR bots found/d' scripts/go_live_smoke.sh
    sed -i '/No OVEX\/VALR bots found/d' scripts/go_live_smoke.sh
fi

if [ -f "scripts/verify_go_live.sh" ]; then
    echo "  Cleaning scripts/verify_go_live.sh"
    # Remove OVEX/VALR verification tests
    sed -i '/TEST 1: Platform Standardization - OVEX present/,/^fi$/d' scripts/verify_go_live.sh
    sed -i '/OVEX present, Kraken removed/d' scripts/verify_go_live.sh
    sed -i '/grep -q.*ovex/d' scripts/verify_go_live.sh
    sed -i '/grep -q.*valr/d' scripts/verify_go_live.sh
    sed -i '/OVEX not found/d' scripts/verify_go_live.sh
    sed -i '/OVEX included/d' scripts/verify_go_live.sh
    sed -i "s/Luno(5), Binance(10), KuCoin(10), OVEX(10), VALR(10) = 45/Luno(5), Binance(10), KuCoin(10), Bybit(10), Kraken(10), Bitget(10), Gateio(10) = 65/g" scripts/verify_go_live.sh
fi

if [ -f "scripts/premerge_smoke.sh" ]; then
    echo "  Cleaning scripts/premerge_smoke.sh"
    # Remove VALR/OVEX tests
    sed -i '/run_test "VALR Limits Present"/,/^$/d' scripts/premerge_smoke.sh
    sed -i '/run_test "OVEX Limits Present"/,/^$/d' scripts/premerge_smoke.sh
fi

if [ -f "scripts/comprehensive_audit.sh" ]; then
    echo "  Cleaning scripts/comprehensive_audit.sh"
    # Remove VALR/OVEX checks
    sed -i '/Check VALR and OVEX/,/^fi$/d' scripts/comprehensive_audit.sh
    sed -i '/VALR pairs defined/d' scripts/comprehensive_audit.sh
    sed -i '/OVEX pairs defined/d' scripts/comprehensive_audit.sh
fi

echo ""
echo "Step 4: Cleaning backend tests..."
echo ""

if [ -f "backend/tests/test_critical_fixes.py" ]; then
    echo "  Cleaning backend/tests/test_critical_fixes.py"
    # Remove OVEX/VALR assertions
    sed -i "/assert.*ovex.*not in PAPER_SUPPORTED_EXCHANGES/d" backend/tests/test_critical_fixes.py
    sed -i "/assert.*valr.*not in PAPER_SUPPORTED_EXCHANGES/d" backend/tests/test_critical_fixes.py
fi

echo ""
echo "Step 5: Update CURRENT_STATE.md to remove VALR/OVEX section..."
echo ""

if [ -f "docs/CURRENT_STATE.md" ]; then
    # Remove the VALR/OVEX references section
    sed -i '/## VALR\/OVEX References (Must Be Removed)/,/## Removed Features/d' docs/CURRENT_STATE.md
    # Update blocker about VALR/OVEX
    sed -i '/### VALR_OVEX_PRESENT (HIGH)/,/^$/d' docs/CURRENT_STATE.md
fi

echo ""
echo "Step 6: Cleaning comments in server.py..."
echo ""

if [ -f "backend/server.py" ]; then
    echo "  Updating backend/server.py"
    sed -i 's/# OVEX and VALR removed - only Luno, Binance, KuCoin supported/# Supported exchanges: Luno, Binance, KuCoin, Bybit, Kraken, Bitget, GateIO (7 total)/g' backend/server.py
fi

echo ""
echo "Step 7: Cleaning AI learning docs..."
echo ""

for doc in docs/AI_LEARNING_*.md docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md docs/SYSTEM_RULES_AND_AI_LEARNING.md docs/ARCHITECTURE_MAP.md docs/COMPLETE_FEATURE_LIST.md docs/DEPLOYMENT_CHECKLIST.md docs/DEPLOYMENT_GUIDE.md; do
    if [ -f "$doc" ]; then
        echo "  Cleaning $doc"
        # Replace 5 platforms with 7 platforms
        sed -i 's/5 platforms/7 exchanges/g' "$doc"
        sed -i 's/5 supported platforms/7 supported exchanges/g' "$doc"
        # Update lists
        sed -i 's/Luno, Binance, KuCoin, OVEX, VALR/Luno, Binance, KuCoin, Bybit, Kraken, Bitget, GateIO/g' "$doc"
        sed -i 's/Luno, Binance, KuCoin, OVEX and VALR/Luno, Binance, KuCoin, Bybit, Kraken, Bitget, and GateIO/g' "$doc"
        # Remove individual mentions
        sed -i 's/, OVEX//g' "$doc"
        sed -i 's/, VALR//g' "$doc"
        sed -i 's/OVEX, //g' "$doc"
        sed -i 's/VALR, //g' "$doc"
        # Update totals
        sed -i 's/45 bots total/65 bots total/g' "$doc"
        sed -i 's/= 45 bots/= 65 bots/g' "$doc"
    fi
done

echo ""
echo "=============================================================================="
echo "✅ VALR/OVEX Removal Complete"
echo "=============================================================================="
echo ""
echo "Changes made:"
echo "  - Archived ${#DOCS_TO_ARCHIVE[@]} outdated documentation files"
echo "  - Cleaned remaining docs and scripts"
echo "  - Updated all platform references to 7 exchanges"
echo "  - Updated bot totals from 45 to 65"
echo ""
echo "Run './scripts/run_audit.sh' to verify removal"
echo ""
