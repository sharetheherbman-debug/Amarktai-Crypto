#!/usr/bin/env bash
# frontend/scripts/prod_gate.sh — Frontend Production Build Gate
#
# Runs a deterministic CI-equivalent pipeline:
#   1. npm ci  (clean, reproducible install from package-lock.json)
#   2. ESLint  (if eslint config present)
#   3. npm run build
#   4. verify-build.js  (asserts built index.html references only files that exist)
#
# Usage:
#   cd frontend && ./scripts/prod_gate.sh
#   ./frontend/scripts/prod_gate.sh  (from repo root, sets FRONTEND_DIR automatically)
#
# Exit codes: 0 = PASS, non-zero = FAIL

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "╔══════════════════════════════════════════════╗"
echo "║   FRONTEND PRODUCTION GATE                   ║"
echo "╚══════════════════════════════════════════════╝"
echo "  FRONTEND_DIR : $FRONTEND_DIR"
echo "  Node         : $(node --version 2>/dev/null || echo 'NOT FOUND')"
echo "  npm          : $(npm --version 2>/dev/null || echo 'NOT FOUND')"
echo ""

cd "$FRONTEND_DIR"

FAILURES=0

# ── Step 1: Clean install ────────────────────────────────────────────────────
echo "[1] Installing dependencies (npm ci)..."
if npm ci --prefer-offline 2>&1; then
    echo "    [1] PASS — npm ci"
else
    echo "    [1] FAIL — npm ci returned non-zero"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# ── Step 2: Lint (ESLint) ────────────────────────────────────────────────────
echo "[2] Running ESLint..."
# ESLint is present if eslint.config.js or .eslintrc* exists
ESLINT_CONFIG_PRESENT=false
for f in eslint.config.js eslint.config.mjs .eslintrc .eslintrc.js .eslintrc.json .eslintrc.yml; do
    if [ -f "$FRONTEND_DIR/$f" ]; then
        ESLINT_CONFIG_PRESENT=true
        break
    fi
done

if $ESLINT_CONFIG_PRESENT; then
    if npx eslint src --ext .js,.jsx --max-warnings=0 2>&1; then
        echo "    [2] PASS — ESLint (zero warnings)"
    else
        echo "    [2] FAIL — ESLint reported errors/warnings"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "    [2] SKIP — No ESLint config found"
fi
echo ""

# ── Step 3: Build ────────────────────────────────────────────────────────────
echo "[3] Building (npm run build)..."
# DISABLE_ESLINT_PLUGIN prevents duplicate lint, CI=false avoids treating warnings as errors
if CI=false DISABLE_ESLINT_PLUGIN=true npm run build 2>&1; then
    echo "    [3] PASS — build succeeded"
else
    echo "    [3] FAIL — build returned non-zero"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# ── Step 4: Verify built assets ─────────────────────────────────────────────
echo "[4] Verifying built assets..."
VERIFY_SCRIPT="${SCRIPT_DIR}/verify-build.js"
if [ -f "$VERIFY_SCRIPT" ] && [ -d "${FRONTEND_DIR}/build" ]; then
    if node "$VERIFY_SCRIPT" "${FRONTEND_DIR}/build" 2>&1; then
        echo "    [4] PASS — build assets verified"
    else
        echo "    [4] FAIL — build asset verification failed"
        FAILURES=$((FAILURES + 1))
    fi
else
    if [ ! -d "${FRONTEND_DIR}/build" ]; then
        echo "    [4] SKIP — No build/ directory (build step may have failed)"
    else
        echo "    [4] SKIP — verify-build.js not found"
    fi
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════╗"
if [ "$FAILURES" -eq 0 ]; then
    echo "║  FRONTEND GATE: PASS ✅                      ║"
    echo "╚══════════════════════════════════════════════╝"
    exit 0
else
    printf "║  FRONTEND GATE: FAIL ❌  (%d failure(s))        ║\n" "$FAILURES"
    echo "╚══════════════════════════════════════════════╝"
    exit 1
fi
