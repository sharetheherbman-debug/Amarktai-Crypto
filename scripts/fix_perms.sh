#!/usr/bin/env bash
set -e

# ============================================================================
# Fix Permissions Script
# ============================================================================
# Fixes file permissions after recursive chmod/chown operations.
# This script ensures:
# - Code directories: 755
# - Code files: 644
# - .venv/bin/* executables: 755
# - Owner: www-data (or admin + group www-data)
#
# Usage:
#   sudo ./scripts/fix_perms.sh
#   OR
#   ./scripts/fix_perms.sh  # If you have write access
# ============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_DIR="${BACKEND_DIR}/.venv"

echo "============================================"
echo "Permission Hardening for Amarktai Backend"
echo "============================================"
echo "Repository root: ${REPO_ROOT}"
echo "Backend directory: ${BACKEND_DIR}"
echo "Virtual environment: ${VENV_DIR}"
echo ""

# Check if running as root (for chown)
RUNNING_AS_ROOT=false
if [ "$EUID" -eq 0 ]; then
    RUNNING_AS_ROOT=true
    echo "✅ Running as root - will set ownership"
else
    echo "⚠️  Not running as root - skipping ownership changes"
    echo "   Run with sudo to change ownership to www-data"
fi
echo ""

# ============================================================================
# Fix Code Directory Permissions
# ============================================================================
echo "📁 Fixing code directory permissions..."

# Directories should be 755 (rwxr-xr-x)
find "${BACKEND_DIR}" -type d \
    ! -path "${VENV_DIR}/*" \
    ! -path "${BACKEND_DIR}/.venv" \
    -exec chmod 755 {} + 2>/dev/null || true

# Files should be 644 (rw-r--r--)
find "${BACKEND_DIR}" -type f \
    ! -path "${VENV_DIR}/*" \
    ! -name "*.sh" \
    -exec chmod 644 {} + 2>/dev/null || true

# Shell scripts should be executable (755)
find "${BACKEND_DIR}" -type f -name "*.sh" \
    ! -path "${VENV_DIR}/*" \
    -exec chmod 755 {} + 2>/dev/null || true

echo "✅ Code permissions fixed"

# ============================================================================
# Fix Virtual Environment Permissions
# ============================================================================
if [ -d "${VENV_DIR}" ]; then
    echo ""
    echo "🐍 Fixing virtual environment permissions..."
    
    # Fix .venv/bin/* executables
    if [ -d "${VENV_DIR}/bin" ]; then
        chmod 755 "${VENV_DIR}/bin" 2>/dev/null || true
        
        # All executables in bin should be 755
        find "${VENV_DIR}/bin" -type f -exec chmod 755 {} + 2>/dev/null || true
        
        echo "✅ Virtual environment executables fixed"
        echo "   pip, python, pytest, etc. are now executable"
    else
        echo "⚠️  No .venv/bin directory found"
    fi
    
    # Fix .venv directory structure
    find "${VENV_DIR}" -type d -exec chmod 755 {} + 2>/dev/null || true
    
    # Most .venv files should be 644
    find "${VENV_DIR}" -type f \
        ! -path "${VENV_DIR}/bin/*" \
        -exec chmod 644 {} + 2>/dev/null || true
    
    echo "✅ Virtual environment permissions fixed"
else
    echo ""
    echo "⚠️  No virtual environment found at ${VENV_DIR}"
    echo "   Run scripts/bootstrap_backend.sh to create one"
fi

# ============================================================================
# Fix Ownership (requires root)
# ============================================================================
if [ "$RUNNING_AS_ROOT" = true ]; then
    echo ""
    echo "👤 Setting ownership to www-data..."
    
    # Check if www-data user exists
    if id "www-data" &>/dev/null; then
        chown -R www-data:www-data "${BACKEND_DIR}" 2>/dev/null || true
        echo "✅ Ownership set to www-data:www-data"
    else
        echo "⚠️  www-data user not found, skipping ownership change"
        echo "   Keeping current ownership"
    fi
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "============================================"
echo "✅ Permission hardening complete!"
echo "============================================"
echo ""
echo "Permissions set:"
echo "  - Directories: 755 (rwxr-xr-x)"
echo "  - Code files: 644 (rw-r--r--)"
echo "  - Shell scripts: 755 (rwxr-xr-x)"
echo "  - .venv/bin/*: 755 (rwxr-xr-x)"
echo ""

if [ "$RUNNING_AS_ROOT" = true ]; then
    echo "Ownership: www-data:www-data"
else
    echo "Ownership: unchanged (run with sudo to change)"
fi

echo ""
echo "Next steps:"
echo "  1. Run: scripts/bootstrap_backend.sh"
echo "  2. Test: pytest -q backend/tests/test_route_collisions.py"
echo "  3. Start: systemctl restart amarktai-api"
echo ""
