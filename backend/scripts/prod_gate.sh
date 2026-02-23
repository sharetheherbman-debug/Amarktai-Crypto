#!/usr/bin/env bash
# prod_gate.sh — Backend Production Go-Live Gate
#
# Runs all pre-flight checks before going live:
#   1. pytest (with third-party plugin auto-load disabled)
#   2. go_live_smoke.sh (API contract checks)
#   3. smoke_bodyguard_loop.sh (bodyguard lock-loop check)
#
# Usage:
#   ./backend/scripts/prod_gate.sh [BASE_URL]
#   AMK_EMAIL=admin@example.com AMK_PASSWORD=secret ./backend/scripts/prod_gate.sh
#
# Exit codes: 0 = PASS, non-zero = FAIL
#
# Environment variables:
#   BASE_URL        — Backend URL (default: http://127.0.0.1:8000)
#   VENV_DIR        — Path to virtualenv (default: ./venv)
#   AMK_EMAIL       — Admin email for smoke tests
#   AMK_PASSWORD    — Admin password for smoke tests

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/venv}"

echo "╔══════════════════════════════════════════════╗"
echo "║      BACKEND PRODUCTION GATE                 ║"
echo "╚══════════════════════════════════════════════╝"
echo "  REPO_ROOT : $REPO_ROOT"
echo "  BASE_URL  : $BASE_URL"
echo "  VENV_DIR  : $VENV_DIR"
echo ""

FAILURES=0

# ── Step 0: Activate venv if it exists ──────────────────────────────────────
if [ -f "${VENV_DIR}/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    echo "[0] venv activated: $VENV_DIR"
else
    echo "[0] No venv found at $VENV_DIR – using system Python"
fi
echo ""

# ── Step 1: pytest ───────────────────────────────────────────────────────────
echo "[1] Running pytest..."
# PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 prevents third-party pytest11 entry-points
# (e.g. web3's pytest-ethereum plugin) from being auto-loaded, which would
# otherwise crash the test session with an ImportError before any test runs.
# The -p no:ethereum flag in pytest.ini is a belt-and-suspenders companion.
if PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
        --tb=short \
        -ra \
        2>&1; then
    echo "    [1] PASS — pytest"
else
    echo "    [1] FAIL — pytest returned non-zero"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# ── Step 2: go_live_smoke.sh ─────────────────────────────────────────────────
echo "[2] Running go_live_smoke.sh..."
SMOKE_SCRIPT="${REPO_ROOT}/scripts/go_live_smoke.sh"
if [ -f "$SMOKE_SCRIPT" ]; then
    if BASE_URL="$BASE_URL" bash "$SMOKE_SCRIPT" 2>&1; then
        echo "    [2] PASS — go_live_smoke.sh"
    else
        echo "    [2] FAIL — go_live_smoke.sh returned non-zero"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "    [2] SKIP — $SMOKE_SCRIPT not found"
fi
echo ""

# ── Step 3: smoke_bodyguard_loop.sh ─────────────────────────────────────────
echo "[3] Running smoke_bodyguard_loop.sh..."
BODYGUARD_SCRIPT="${REPO_ROOT}/backend/scripts/smoke_bodyguard_loop.sh"
if [ -f "$BODYGUARD_SCRIPT" ]; then
    if BASE_URL="$BASE_URL" bash "$BODYGUARD_SCRIPT" 2>&1; then
        echo "    [3] PASS — smoke_bodyguard_loop.sh"
    else
        echo "    [3] FAIL — smoke_bodyguard_loop.sh returned non-zero"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "    [3] SKIP — $BODYGUARD_SCRIPT not found"
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════╗"
if [ "$FAILURES" -eq 0 ]; then
    echo "║  PRODUCTION GATE: PASS ✅                    ║"
    echo "╚══════════════════════════════════════════════╝"
    exit 0
else
    echo "║  PRODUCTION GATE: FAIL ❌  ($FAILURES failure(s))  ║"
    echo "╚══════════════════════════════════════════════╝"
    exit 1
fi
