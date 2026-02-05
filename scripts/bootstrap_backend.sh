#!/usr/bin/env bash
set -e

# ============================================================================
# Backend Bootstrap Script
# ============================================================================
# Creates virtual environment, installs dependencies, and runs tests.
# Safe to run multiple times (idempotent).
#
# Usage:
#   ./scripts/bootstrap_backend.sh
# ============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_DIR="${BACKEND_DIR}/.venv"

echo "============================================"
echo "Bootstrap Amarktai Backend"
echo "============================================"
echo "Repository root: ${REPO_ROOT}"
echo "Backend directory: ${BACKEND_DIR}"
echo ""

# ============================================================================
# Check Python
# ============================================================================
echo "🐍 Checking Python installation..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found!"
    echo "   Install Python 3.8+ and try again"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python ${PYTHON_VERSION} found"

# Check minimum version (3.8+)
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]; }; then
    echo "❌ Python 3.8+ required (found ${PYTHON_VERSION})"
    exit 1
fi

# ============================================================================
# Create Virtual Environment
# ============================================================================
echo ""
echo "📦 Setting up virtual environment..."

if [ -d "${VENV_DIR}" ]; then
    echo "✅ Virtual environment already exists at ${VENV_DIR}"
else
    echo "Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip --quiet

# ============================================================================
# Install Dependencies
# ============================================================================
echo ""
echo "📥 Installing dependencies..."

cd "${BACKEND_DIR}"

# Install main requirements
if [ -f "requirements.txt" ]; then
    echo "Installing requirements.txt..."
    pip install -r requirements.txt --quiet
    echo "✅ Main requirements installed"
else
    echo "⚠️  No requirements.txt found"
fi

# Install AI requirements if they exist
if [ -f "requirements-ai.txt" ]; then
    echo "Installing requirements-ai.txt..."
    pip install -r requirements-ai.txt --quiet
    echo "✅ AI requirements installed"
fi

# ============================================================================
# Syntax Check
# ============================================================================
echo ""
echo "🔍 Running syntax check..."

if python -m py_compile server.py 2>/dev/null; then
    echo "✅ server.py syntax check passed"
else
    echo "❌ server.py syntax check failed!"
    echo "   Fix syntax errors before proceeding"
    exit 1
fi

# Check a few more critical files
for file in models.py database.py auth.py; do
    if [ -f "$file" ]; then
        if python -m py_compile "$file" 2>/dev/null; then
            echo "✅ $file syntax check passed"
        else
            echo "❌ $file syntax check failed!"
            exit 1
        fi
    fi
done

# ============================================================================
# Run Route Collision Test
# ============================================================================
echo ""
echo "🧪 Running route collision test..."

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "⚠️  pytest not found in virtual environment"
    echo "   Installing pytest..."
    pip install pytest --quiet
fi

cd "${REPO_ROOT}"

# Run only the route collision test
if pytest -q tests/test_route_collisions.py::test_no_route_collisions 2>&1 | tee /tmp/test_output.txt; then
    echo "✅ Route collision test passed"
else
    echo "❌ Route collision test failed!"
    echo ""
    cat /tmp/test_output.txt
    echo ""
    echo "Fix route collisions before deploying"
    exit 1
fi

# ============================================================================
# Fix Permissions
# ============================================================================
echo ""
echo "🔒 Fixing permissions..."

if [ -f "${REPO_ROOT}/scripts/fix_perms.sh" ]; then
    bash "${REPO_ROOT}/scripts/fix_perms.sh"
else
    echo "⚠️  fix_perms.sh not found, skipping permission fix"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "============================================"
echo "✅ Backend bootstrap complete!"
echo "============================================"
echo ""
echo "Virtual environment: ${VENV_DIR}"
echo "Python version: ${PYTHON_VERSION}"
echo ""
echo "To activate the virtual environment:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "To start the server:"
echo "  cd ${BACKEND_DIR}"
echo "  source .venv/bin/activate"
echo "  python server.py"
echo ""
echo "Or with systemd:"
echo "  sudo systemctl restart amarktai-api"
echo ""
