#!/bin/bash
# Comprehensive Repository Audit Runner

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=============================================================================="
echo "🔍 Amarktai Network - Repository Audit"
echo "=============================================================================="
echo ""
echo "Repository: $REPO_ROOT"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: python3 not found"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Run the audit script
echo "Running audit_repo.py..."
echo ""

cd "$REPO_ROOT"
python3 "$SCRIPT_DIR/audit_repo.py"

EXIT_CODE=$?

echo ""
echo "=============================================================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ AUDIT COMPLETED SUCCESSFULLY"
else
    echo "⚠️  AUDIT COMPLETED WITH WARNINGS/ERRORS"
fi
echo "=============================================================================="
echo ""
echo "Generated files:"
echo "  - audit_report.json"
echo "  - docs/CURRENT_STATE.md"
echo "  - docs/API_CONTRACT.md"
echo ""

exit $EXIT_CODE
