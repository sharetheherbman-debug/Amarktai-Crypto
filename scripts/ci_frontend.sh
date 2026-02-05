#!/bin/bash
# CI Frontend Build Check
# This script ensures the frontend builds successfully from a clean state
# Run this before merging to catch lockfile mismatches early

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "================================================"
echo "Frontend CI Build Check"
echo "================================================"
echo ""

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ Error: Frontend directory not found at $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

echo "📂 Working directory: $(pwd)"
echo ""

# Check for required files
echo "🔍 Checking for required files..."
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found"
    exit 1
fi

if [ ! -f "package-lock.json" ]; then
    echo "❌ Error: package-lock.json not found"
    exit 1
fi

echo "✅ Required files present"
echo ""

# Check Node.js version
echo "🔍 Checking Node.js version..."
NODE_VERSION=$(node --version)
echo "   Node.js: $NODE_VERSION"
NPM_VERSION=$(npm --version)
echo "   npm: $NPM_VERSION"
echo ""

# Clean install
echo "📦 Running npm ci (clean install)..."
npm ci --no-audit

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ npm ci failed!"
    echo "   This usually means package.json and package-lock.json are out of sync."
    echo "   To fix: cd frontend && npm install && git add package-lock.json"
    exit 1
fi

echo "✅ Dependencies installed successfully"
echo ""

# Verify lockfile integrity
echo "🔍 Verifying lockfile integrity..."
npm list > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: npm list found dependency issues"
    echo "   Running npm list to show details:"
    npm list || true
    echo ""
fi

# Build
echo "🏗️  Building frontend..."
npm run build

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Build completed successfully"
echo ""

# Verify build output
echo "🔍 Verifying build artifacts..."
if [ ! -d "build" ]; then
    echo "❌ Error: build directory not created"
    exit 1
fi

if [ ! -f "build/index.html" ]; then
    echo "❌ Error: build/index.html not found"
    exit 1
fi

if [ ! -d "build/static" ]; then
    echo "❌ Error: build/static directory not found"
    exit 1
fi

echo "✅ Build artifacts verified"
echo ""

echo "================================================"
echo "✅ All frontend CI checks passed!"
echo "================================================"
