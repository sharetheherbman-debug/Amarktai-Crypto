#!/usr/bin/env bash
#
# install_backend.sh
#
# This script bootstraps the Python backend by creating a virtual
# environment, installing dependencies, seeding a default `.env` and
# performing a simple import test.  It should be idempotent and safe to
# run multiple times.  On a fresh server this can be executed after
# extracting the zip into `/var/amarktai/app`.

set -euo pipefail

PROJECT_ROOT=$(dirname "$(readlink -f "$0")")/..
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "📦 Installing backend dependencies in $BACKEND_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi

source "$BACKEND_DIR/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$BACKEND_DIR/requirements.txt"

# Copy example env if .env does not exist
if [ ! -f "$BACKEND_DIR/.env" ]; then
  if [ -f "$PROJECT_ROOT/.env.example" ]; then
    cp "$PROJECT_ROOT/.env.example" "$BACKEND_DIR/.env"
    echo "✅ Copied .env.example to backend/.env – update this file with production secrets"
  fi
fi

# Basic import test to ensure the app can start
python - <<'PY'
import importlib, sys
try:
    import backend.server  # noqa: F401
    print("✅ Backend import test passed")
except Exception as e:
    print("❌ Backend import test failed", e)
    sys.exit(1)
PY