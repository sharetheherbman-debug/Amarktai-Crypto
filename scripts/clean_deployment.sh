#!/bin/bash
# Clean deployment script - removes old compiled files and temporary artifacts
# Run before deployment to ensure a clean state

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🧹 Cleaning deployment artifacts..."

# Clean Python compiled files
echo "  Removing .pyc files..."
find "$PROJECT_ROOT/backend" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PROJECT_ROOT/backend" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Clean Python egg-info directories
echo "  Removing .egg-info directories..."
find "$PROJECT_ROOT" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Clean build directories
echo "  Removing build directories..."
rm -rf "$PROJECT_ROOT/build" 2>/dev/null || true
rm -rf "$PROJECT_ROOT/dist" 2>/dev/null || true
rm -rf "$PROJECT_ROOT/.pytest_cache" 2>/dev/null || true

# Clean temporary files
echo "  Removing temporary files..."
find "$PROJECT_ROOT" -type f -name "*.tmp" -delete 2>/dev/null || true
find "$PROJECT_ROOT" -type f -name "*.log" -path "*/tmp/*" -delete 2>/dev/null || true

# Clean frontend build artifacts (but not node_modules - that's intentional)
if [ -d "$PROJECT_ROOT/frontend/build" ]; then
    echo "  Removing frontend build directory..."
    rm -rf "$PROJECT_ROOT/frontend/build"
fi

# Clean coverage reports
echo "  Removing coverage reports..."
rm -rf "$PROJECT_ROOT/.coverage" 2>/dev/null || true
rm -rf "$PROJECT_ROOT/htmlcov" 2>/dev/null || true

echo "✅ Deployment cleaned successfully!"
echo ""
echo "Next steps:"
echo "  1. Verify .env file exists and has correct permissions (600)"
echo "  2. Check systemd service configuration"
echo "  3. Run preflight checks: ./scripts/preflight.sh"
