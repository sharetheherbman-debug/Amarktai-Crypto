#!/bin/bash
set -e

# verify_repo.sh - Verify repository Python files compile without errors
# This script validates that all Python files in the repo are syntactically correct
# Excludes: .venv, _archive, __pycache__, node_modules

echo "============================================"
echo "Repository Verification Script"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL=0
PASSED=0
FAILED=0

# Get the repository root
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "📁 Repository: $REPO_ROOT"
echo ""

# Find all Python files, excluding .venv, _archive, __pycache__, and node_modules
echo "🔍 Finding Python files (excluding .venv, _archive, __pycache__)..."
FILES=$(find . -name "*.py" \
    -not -path "./.venv/*" \
    -not -path "*/.venv/*" \
    -not -path "./_archive/*" \
    -not -path "*/_archive/*" \
    -not -path "*/__pycache__/*" \
    -not -path "./node_modules/*" \
    -not -path "*/node_modules/*" \
    2>/dev/null)

if [ -z "$FILES" ]; then
    echo -e "${YELLOW}⚠️  No Python files found${NC}"
    exit 0
fi

FILE_COUNT=$(echo "$FILES" | wc -l)
echo "Found $FILE_COUNT Python files to check"
echo ""

echo "🐍 Checking Python syntax with py_compile..."
echo ""

# Check each file
while IFS= read -r file; do
    TOTAL=$((TOTAL + 1))
    
    # Show progress every 10 files
    if [ $((TOTAL % 10)) -eq 0 ]; then
        echo "  Progress: $TOTAL/$FILE_COUNT files checked..."
    fi
    
    # Attempt to compile
    if python3 -m py_compile "$file" 2>/dev/null; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        echo -e "${RED}❌ FAIL: $file${NC}"
        # Show the actual error
        python3 -m py_compile "$file" 2>&1 | head -5
        echo ""
    fi
done <<< "$FILES"

echo ""
echo "============================================"
echo "Verification Results"
echo "============================================"
echo "Total files checked: $TOTAL"
echo -e "${GREEN}✅ Passed: $PASSED${NC}"

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}❌ Failed: $FAILED${NC}"
    echo ""
    echo -e "${RED}Repository verification FAILED${NC}"
    echo "Fix the syntax errors above before deploying."
    exit 1
else
    echo -e "${RED}❌ Failed: $FAILED${NC}"
    echo ""
    echo -e "${GREEN}✅ Repository verification PASSED${NC}"
    echo "All Python files compile successfully."
fi

echo ""
echo "Optional: Run full compileall check"
echo "  python3 -m compileall -q backend/ -x '(.venv|_archive|__pycache__)'"
echo ""

exit 0
