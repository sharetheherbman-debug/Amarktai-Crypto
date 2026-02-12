#!/usr/bin/env bash
#
# build_frontend.sh
#
# This script installs Node dependencies and builds the production
# frontend bundle.  It attempts to use Yarn if a lockfile is present
# and falls back to npm.  A minimum Node version of 20 is required.

set -euo pipefail

PROJECT_ROOT=$(dirname "$(readlink -f "$0")")/..
FRONTEND_DIR="$PROJECT_ROOT/frontend"
RUN_USER="${SUDO_USER:-$(whoami)}"
NODE_CMD_PREFIX=""
if [ "$(id -u)" = "0" ] && [ -n "${SUDO_USER:-}" ]; then
  NODE_CMD_PREFIX="sudo -u ${RUN_USER}"
fi

echo "⚛️ Building frontend in $FRONTEND_DIR"

# Ensure correct Node version (>=20)
NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 20 ]; then
  echo "❌ Node v20 or higher is required.  Current version: $(node -v)"
  exit 1
fi

cd "$FRONTEND_DIR"
rm -rf build

# Install dependencies using Yarn or npm
if [ -f yarn.lock ]; then
  echo "📦 Installing dependencies with Yarn..."
  $NODE_CMD_PREFIX yarn install --frozen-lockfile
else
  echo "📦 Installing dependencies with npm..."
  $NODE_CMD_PREFIX npm ci --legacy-peer-deps || $NODE_CMD_PREFIX npm install --legacy-peer-deps
fi

# Build the project
if [ -f yarn.lock ]; then
  $NODE_CMD_PREFIX yarn build
else
  $NODE_CMD_PREFIX npm run build
fi

echo "✅ Frontend build complete"
