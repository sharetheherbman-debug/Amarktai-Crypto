#!/usr/bin/env bash
###############################################################################
# /ops/deploy.sh – Amarktai Network idempotent deploy script
#
# DESIGN GOALS
#   • NEVER loses /etc/amarktai/backend.env  (external secret store)
#   • Idempotent – safe to run multiple times in a row
#   • Builds frontend, syncs to web root, restarts only if healthcheck passes
#   • Injects BUILD_SHA env var so the API can report it on /api/health/ping
#
# USAGE
#   sudo bash ops/deploy.sh [--skip-frontend] [--skip-backend]
#
# ENVIRONMENT (can be overridden)
#   REPO_ROOT        – absolute path to repo checkout  (default: dir of this script)
#   FRONTEND_WEBROOT – nginx static root               (default: /var/amarktai/app/Amarktai-Crypto/frontend/build)
#   ENV_FILE         – secrets env file                (default: /etc/amarktai/amarktai.env)
#   BACKEND_SERVICE  – systemd service name            (default: amarktai-api)
#   VENV_PATH        – Python venv path                (default: /var/amarktai/app/Amarktai-Crypto/backend/.venv)
#   BACKEND_DIR      – backend source directory        (default: $REPO_ROOT/backend)
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# ── Configurable paths ───────────────────────────────────────────────────────
# Nginx serves directly from the build output directory.  No rsync drift.
FRONTEND_WEBROOT="${FRONTEND_WEBROOT:-/var/amarktai/app/Amarktai-Crypto/frontend/build}"
ENV_FILE="${ENV_FILE:-/etc/amarktai/amarktai.env}"
BACKEND_SERVICE="${BACKEND_SERVICE:-amarktai-api}"
VENV_PATH="${VENV_PATH:-/var/amarktai/app/Amarktai-Crypto/backend/.venv}"
BACKEND_DIR="${BACKEND_DIR:-$REPO_ROOT/backend}"
FRONTEND_DIR="$REPO_ROOT/frontend"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
err()  { echo -e "${RED}✗ $*${NC}"; }
info() { echo -e "${CYAN}→ $*${NC}"; }

# ── Flags ─────────────────────────────────────────────────────────────────────
SKIP_FRONTEND=false
SKIP_BACKEND=false
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) SKIP_FRONTEND=true ;;
    --skip-backend)  SKIP_BACKEND=true  ;;
  esac
done

echo ""
echo "════════════════════════════════════════════════════════"
echo " 🚀  AMARKTAI NETWORK – DEPLOY"
echo "════════════════════════════════════════════════════════"
echo " Repo:    $REPO_ROOT"
echo " Web:     $FRONTEND_WEBROOT"
echo " Env:     $ENV_FILE"
echo " Service: $BACKEND_SERVICE"
echo "════════════════════════════════════════════════════════"
echo ""

# ── 0. Sanity: ensure .env file exists OUTSIDE the repo ───────────────────────
info "Checking env file..."
if [[ ! -f "$ENV_FILE" ]]; then
  err "Env file NOT FOUND: $ENV_FILE"
  echo ""
  echo "  To create it, run:"
  echo "    sudo mkdir -p $(dirname "$ENV_FILE")"
  echo "    sudo cp $REPO_ROOT/ops/etc-amarktai-env.template $ENV_FILE"
  echo "    sudo chmod 600 $ENV_FILE"
  echo "    sudo nano $ENV_FILE   # fill in real values"
  echo ""
  exit 1
fi
ok "Env file exists: $ENV_FILE"

# ── 1. Capture git hash before any changes ────────────────────────────────────
BUILD_SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
info "Build SHA: $BUILD_SHA  ($BUILD_DATE)"

# ── 2. Pull latest code ───────────────────────────────────────────────────────
info "Pulling latest code..."
git -C "$REPO_ROOT" pull --ff-only 2>&1 | tail -3
ok "Code updated"

# Recapture SHA after pull
BUILD_SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_TAG=$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || echo "unknown")

# ── 3. Frontend build ─────────────────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" == "false" ]]; then
  info "Building frontend..."
  cd "$FRONTEND_DIR"
  npm ci --prefer-offline --no-audit --quiet
  # Inject build metadata so frontend diagnostics can trace deployed bundle
  REACT_APP_BUILD_SHA="$BUILD_SHA" \
  REACT_APP_BUILD_TIMESTAMP="$BUILD_DATE" \
  REACT_APP_VERSION="$BUILD_SHA" \
  REACT_APP_VERSION_TAG="$BUILD_TAG" \
  npm run build
  ok "Frontend built"

  # Write build hash file
  echo "$BUILD_SHA" > "$FRONTEND_DIR/build/BUILD_SHA.txt"
  echo "$BUILD_DATE" > "$FRONTEND_DIR/build/BUILD_DATE.txt"

  # Nginx reads directly from the build output directory.
  # If FRONTEND_WEBROOT is different from the build output (legacy / custom
  # override), rsync the build there.  Otherwise just fix ownership.
  if [[ "$FRONTEND_WEBROOT" != "$FRONTEND_DIR/build" ]]; then
    # Legacy / custom webroot – sync build output
    if [[ -d "$FRONTEND_WEBROOT" ]]; then
      BACKUP="${FRONTEND_WEBROOT}_backup_$(date +%Y%m%d_%H%M%S)"
      info "Backing up current web root to $BACKUP"
      sudo cp -r "$FRONTEND_WEBROOT" "$BACKUP"
      ok "Web root backed up"
    fi
    sudo mkdir -p "$FRONTEND_WEBROOT"
    sudo rsync -a --delete "$FRONTEND_DIR/build/" "$FRONTEND_WEBROOT/"
    sudo chown -R www-data:www-data "$FRONTEND_WEBROOT"
    ok "Frontend deployed to $FRONTEND_WEBROOT"
  else
    # Canonical path – nginx reads build/ directly, just fix ownership
    sudo chown -R www-data:www-data "$FRONTEND_DIR/build"
    ok "Frontend build ready at $FRONTEND_DIR/build"
  fi

  # Reload nginx
  if sudo nginx -t 2>/dev/null; then
    sudo systemctl reload nginx || sudo systemctl restart nginx
    ok "Nginx reloaded"
  else
    err "Nginx config test failed – skipping reload"
  fi
  cd "$REPO_ROOT"
fi

# ── 4. Backend update ─────────────────────────────────────────────────────────
if [[ "$SKIP_BACKEND" == "false" ]]; then
  info "Updating backend dependencies..."
  if [[ -d "$VENV_PATH" ]]; then
    "$VENV_PATH/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt" --upgrade
    ok "Python deps updated"
  else
    warn "Venv not found at $VENV_PATH – skipping pip install"
  fi

  # Inject canonical backend build metadata for health/admin diagnostics
  info "Injecting build metadata into $ENV_FILE..."
  for key_value in \
    "BUILD_SHA=$BUILD_SHA" \
    "BUILD_TIMESTAMP=$BUILD_DATE" \
    "BUILD_VERSION=$BUILD_SHA" \
    "BUILD_VERSION_TAG=$BUILD_TAG"; do
    key="${key_value%%=*}"
    if grep -q "^${key}=" "$ENV_FILE"; then
      sudo sed -i "s|^${key}=.*|${key_value}|" "$ENV_FILE"
    else
      echo "$key_value" | sudo tee -a "$ENV_FILE" > /dev/null
    fi
  done
  ok "Build metadata updated in env file"

  # Restart service
  info "Restarting $BACKEND_SERVICE..."
  sudo systemctl restart "$BACKEND_SERVICE"
  sleep 5

  # Health check
  HEALTH=$(curl -sf http://127.0.0.1:8000/api/health/ping 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "unreachable")
  if [[ "$HEALTH" == "ok" ]]; then
    ok "Backend healthy: $HEALTH"
  else
    warn "Backend health returned: $HEALTH (may still be starting)"
    echo "  Check: sudo journalctl -u $BACKEND_SERVICE -n 50"
  fi
fi

# ── 5. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo -e "${GREEN} ✅  DEPLOY COMPLETE${NC}"
echo "════════════════════════════════════════════════════════"
echo " BUILD_SHA:  $BUILD_SHA"
echo " BUILD_DATE: $BUILD_DATE"
echo " Env file:   $ENV_FILE  (UNTOUCHED except BUILD_SHA line)"
echo ""
echo " Next: run ops/post_deploy_evidence_pack.sh to verify"
echo "════════════════════════════════════════════════════════"
echo ""
