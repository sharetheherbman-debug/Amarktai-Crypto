#!/usr/bin/env bash
###############################################################################
# ops/redeploy_production.sh – Amarktai Crypto ONE-COMMAND Production Deploy
#
# USAGE
#   sudo bash ops/redeploy_production.sh
#
# WHAT IT DOES
#   1. Verifies repo path and git state (deploys the currently checked-out commit)
#   2. Records current commit SHA and branch
#   3. Runs backend preflight (env file, paths, venv, python import)
#   4. Installs locked backend dependencies from requirements.production.lock.txt
#   5. Installs canonical systemd unit (amarktai-api.service)
#   6. Installs canonical nginx config (amarktai)
#   7. Removes stale nginx sites and old systemd services
#   8. Rebuilds frontend (npm ci + npm run build)
#   9. Reloads systemd daemon, restarts backend and nginx
#  10. Compares built JS filename vs live-served JS filename (fails if mismatch)
#  11. Runs /api/health and /api/health/ping checks
#  12. Prints PASS / FAIL summary
#
# CANONICAL PATHS (single source of truth)
APP_ROOT_CANONICAL=/var/amarktai/app/Amarktai-Crypto
#   Backend:  $APP_ROOT_CANONICAL/backend
#   Venv:     $APP_ROOT_CANONICAL/backend/.venv
#   Frontend: $APP_ROOT_CANONICAL/frontend/build  (nginx root)
#   Env file: /etc/amarktai/amarktai.env
#   Service:  amarktai-api
#   Nginx:    amarktai
###############################################################################
set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
err()  { echo -e "${RED}✗ $*${NC}"; }
info() { echo -e "${CYAN}→ $*${NC}"; }
head() { echo -e "\n${BOLD}${CYAN}══ $* ══${NC}"; }

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ROOT=/var/amarktai/app/Amarktai-Crypto
BACKEND_DIR="$APP_ROOT/backend"
VENV="$BACKEND_DIR/.venv"
FRONTEND_DIR="$APP_ROOT/frontend"
FRONTEND_BUILD="$FRONTEND_DIR/build"
ENV_FILE=/etc/amarktai/amarktai.env
SERVICE=amarktai-api
NGINX_SITE=amarktai
NGINX_AVAIL=/etc/nginx/sites-available/$NGINX_SITE
NGINX_ENABLED=/etc/nginx/sites-enabled/$NGINX_SITE
SYSTEMD_UNIT=/etc/systemd/system/$SERVICE.service
LOG_DIR=/var/log/amarktai

# Track overall pass/fail
PASS_COUNT=0
FAIL_COUNT=0
FAILURES=()

pass() { ok "$1"; PASS_COUNT=$(( PASS_COUNT + 1 )); }
fail() { err "$1"; FAIL_COUNT=$(( FAIL_COUNT + 1 )); FAILURES+=("$1"); }

###############################################################################
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║        AMARKTAI CRYPTO – PRODUCTION REDEPLOY                ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo " Repo root:  $REPO_ROOT"
echo " App root:   $APP_ROOT"
echo " Env file:   $ENV_FILE"
echo " Service:    $SERVICE"
echo " Nginx site: $NGINX_SITE"
echo ""

###############################################################################
head "STEP 1 – Verify repo path"
###############################################################################
if [[ "$REPO_ROOT" != "$APP_ROOT" ]]; then
  warn "Script running from $REPO_ROOT (not $APP_ROOT)"
  warn "Ensure production clone is at $APP_ROOT"
fi

if [[ ! -f "$REPO_ROOT/backend/server.py" ]]; then
  fail "backend/server.py not found – wrong repo root"
  echo "Expected repo at: $APP_ROOT"
  exit 1
fi
pass "Repo path valid"

GIT_BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
GIT_SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
info "Branch: $GIT_BRANCH  SHA: $GIT_SHA"

###############################################################################
head "STEP 2 – Record checked-out commit"
###############################################################################
# Deploys the CURRENTLY CHECKED-OUT commit only.
# To update code before deploying, run: sudo git -C "$APP_ROOT" pull
# or: sudo git -C "$APP_ROOT" reset --hard <sha>
# This script will then deploy whatever is currently checked out.
GIT_TAG=$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || echo "")
pass "Deploying checked-out commit: $GIT_SHA ${GIT_TAG:+(tag: $GIT_TAG)} on branch $GIT_BRANCH"

###############################################################################
head "STEP 3 – Backend preflight checks"
###############################################################################
info "Checking env file..."
if [[ ! -f "$ENV_FILE" ]]; then
  fail "Env file missing: $ENV_FILE"
  echo ""
  echo "  To create it:"
  echo "    sudo mkdir -p /etc/amarktai"
  echo "    sudo cp $REPO_ROOT/ops/etc-amarktai-env.template $ENV_FILE"
  echo "    sudo chmod 600 $ENV_FILE"
  echo "    sudo chown root:www-data $ENV_FILE"
  echo "    sudo nano $ENV_FILE   # fill in real secrets"
  echo ""
  exit 1
fi
pass "Env file exists: $ENV_FILE"

info "Checking log directory..."
mkdir -p "$LOG_DIR"
chown www-data:www-data "$LOG_DIR" 2>/dev/null || true
if [[ -w "$LOG_DIR" ]] || sudo -u www-data test -w "$LOG_DIR" 2>/dev/null; then
  pass "Log directory writable: $LOG_DIR"
else
  warn "Log directory may not be writable by www-data – fixing..."
  chown -R www-data:www-data "$LOG_DIR"
fi

###############################################################################
head "STEP 4 – Backend venv and locked dependency install"
###############################################################################
if [[ ! -d "$VENV" ]]; then
  info "Creating Python venv at $VENV..."
  sudo -u www-data python3 -m venv "$VENV"
  pass "Venv created"
else
  pass "Venv exists: $VENV"
fi

info "Upgrading pip in venv..."
sudo -u www-data "$VENV/bin/pip" install --quiet --upgrade pip

LOCK_FILE="$REPO_ROOT/backend/requirements.production.lock.txt"
if [[ ! -f "$LOCK_FILE" ]]; then
  fail "Production lock file missing: $LOCK_FILE"
  exit 1
fi
# Using the locked file (not requirements.txt) eliminates live pip resolver
# backtracking and the numpy/langchain-chroma/pandas-ta ResolutionImpossible.
# numpy==1.26.4  satisfies: langchain-chroma==0.1.4 (numpy<2.0) AND
#                           pandas-ta==0.3.14b0 (numpy 1.x era release).
info "Installing from locked requirements: $LOCK_FILE"
sudo -u www-data "$VENV/bin/pip" install --quiet -r "$LOCK_FILE"
pass "Backend dependencies installed from locked file"

###############################################################################
head "STEP 5 – Python import preflight"
###############################################################################
info "Checking python can import server module..."
if sudo -u www-data bash -c "cd '$BACKEND_DIR' && '$VENV/bin/python3' -c 'import server' 2>&1"; then
  pass "Python import server: OK"
else
  fail "Python cannot import server – check backend dependencies"
  echo "  Run: sudo -u www-data bash -c \"cd $BACKEND_DIR && $VENV/bin/python3 -c 'import server'\""
  exit 1
fi

###############################################################################
head "STEP 6 – Install canonical systemd unit"
###############################################################################
UNIT_SRC="$REPO_ROOT/ops/systemd/amarktai-api.service"
if [[ ! -f "$UNIT_SRC" ]]; then
  fail "Systemd unit source not found: $UNIT_SRC"
  exit 1
fi
cp "$UNIT_SRC" "$SYSTEMD_UNIT"
pass "Systemd unit installed: $SYSTEMD_UNIT"

# Install nightly XGBoost retrain timer (optional — only runs when ENABLE_LEARNING_LOOP=true)
RETRAIN_SVC_SRC="$REPO_ROOT/ops/systemd/amarktai-retrain.service"
RETRAIN_TMR_SRC="$REPO_ROOT/ops/systemd/amarktai-retrain.timer"
if [[ -f "$RETRAIN_SVC_SRC" && -f "$RETRAIN_TMR_SRC" ]]; then
  cp "$RETRAIN_SVC_SRC" /etc/systemd/system/amarktai-retrain.service
  cp "$RETRAIN_TMR_SRC" /etc/systemd/system/amarktai-retrain.timer
  systemctl enable amarktai-retrain.timer 2>/dev/null || true
  systemctl start amarktai-retrain.timer 2>/dev/null || true
  pass "Nightly retrain timer installed and enabled (amarktai-retrain.timer)"
else
  warn "Retrain timer not found — skipping (ops/systemd/amarktai-retrain.{service,timer})"
fi

# Create model directories required by XGBoost retrain and River learner.
# These must exist before the backend starts; River will mkdir on init but
# XGBoost retrain fails silently if models/ is absent.
MODEL_DIR="$BACKEND_DIR/models"
mkdir -p "$MODEL_DIR/river"
chown -R www-data:www-data "$MODEL_DIR" 2>/dev/null || true
pass "Model directories ready: $MODEL_DIR  (xgb + river)"

###############################################################################
head "STEP 7 – Disable stale systemd services"
###############################################################################
for stale_service in amarktai.service amarktai-spa.service; do
  unit_name="${stale_service%.service}"
  if systemctl list-unit-files "$stale_service" 2>/dev/null | grep -q "$stale_service"; then
    info "Disabling stale service: $stale_service"
    systemctl disable --now "$stale_service" 2>/dev/null || true
    if [[ -f "/etc/systemd/system/$stale_service" ]]; then
      mv "/etc/systemd/system/$stale_service" "/etc/systemd/system/${stale_service}.disabled"
      info "Renamed to: ${stale_service}.disabled"
    fi
    pass "Stale service disabled: $stale_service"
  else
    pass "No stale service: $stale_service"
  fi
done

systemctl daemon-reload
pass "Systemd daemon reloaded"

###############################################################################
head "STEP 8 – Install canonical nginx config"
###############################################################################
NGINX_SRC="$REPO_ROOT/ops/nginx/amarktai.conf"
if [[ ! -f "$NGINX_SRC" ]]; then
  fail "Nginx config source not found: $NGINX_SRC"
  exit 1
fi
cp "$NGINX_SRC" "$NGINX_AVAIL"
pass "Nginx config installed: $NGINX_AVAIL"

###############################################################################
head "STEP 9 – Remove stale nginx sites"
###############################################################################
for stale_link in default amarktai-spa amarktai-websocket; do
  link="/etc/nginx/sites-enabled/$stale_link"
  if [[ -e "$link" || -L "$link" ]]; then
    rm -f "$link"
    pass "Removed stale nginx link: $link"
  else
    pass "No stale nginx link: $link"
  fi
done

# Ensure canonical symlink exists
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
pass "Nginx symlink: $NGINX_ENABLED → $NGINX_AVAIL"

###############################################################################
head "STEP 10 – Rebuild frontend"
###############################################################################
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
info "Installing npm dependencies (ci)..."
cd "$FRONTEND_DIR"
sudo -u www-data npm ci --legacy-peer-deps --prefer-offline --quiet

info "Building frontend..."
sudo -u www-data bash -c "
  export CI=false
  export REACT_APP_BUILD_SHA='$GIT_SHA'
  export REACT_APP_BUILD_TIMESTAMP='$BUILD_DATE'
  export REACT_APP_VERSION='$GIT_SHA'
  cd '$FRONTEND_DIR'
  npm run build
"
cd "$REPO_ROOT"

# Write build metadata files
echo "$GIT_SHA" > "$FRONTEND_BUILD/BUILD_SHA.txt"
echo "$BUILD_DATE" > "$FRONTEND_BUILD/BUILD_DATE.txt"

# Fix ownership
chown -R www-data:www-data "$FRONTEND_BUILD"
pass "Frontend built and ownership fixed"

###############################################################################
head "STEP 11 – Nginx config test and reload"
###############################################################################
if nginx -t 2>&1; then
  pass "Nginx config test: OK"
else
  fail "Nginx config test FAILED"
  exit 1
fi

###############################################################################
head "STEP 12 – Restart backend service"
###############################################################################
info "Enabling and restarting $SERVICE..."
systemctl enable "$SERVICE" 2>/dev/null || true
systemctl restart "$SERVICE"
sleep 8
pass "Service restarted: $SERVICE"

# Reload nginx (after backend is up)
systemctl reload nginx || systemctl restart nginx
pass "Nginx reloaded"

###############################################################################
head "STEP 13 – Compare built JS vs live-served JS"
###############################################################################
info "Checking built JS filename..."
BUILT_JS=$(ls "$FRONTEND_BUILD/static/js/main."*.js 2>/dev/null | xargs -I{} basename {} 2>/dev/null | head -1)
if [[ -z "$BUILT_JS" ]]; then
  fail "No built JS file found in $FRONTEND_BUILD/static/js/"
else
  pass "Built JS: $BUILT_JS"
fi

info "Checking live-served JS filename..."
SERVED_JS=$(grep -oP 'static/js/main\.[a-f0-9]+\.js' "$FRONTEND_BUILD/index.html" 2>/dev/null | head -1 | xargs basename 2>/dev/null || true)
if [[ -z "$SERVED_JS" ]]; then
  fail "Could not read JS filename from $FRONTEND_BUILD/index.html"
else
  pass "Served JS: $SERVED_JS"
fi

if [[ -n "$BUILT_JS" && -n "$SERVED_JS" ]]; then
  if [[ "$BUILT_JS" == "$SERVED_JS" ]]; then
    pass "Built JS matches served JS: $BUILT_JS ✓"
  else
    fail "JS MISMATCH: built=$BUILT_JS  served=$SERVED_JS"
  fi
fi

###############################################################################
head "STEP 14 – Backend health checks"
###############################################################################
info "Waiting for backend to be ready..."
sleep 3

HEALTH_URL="http://127.0.0.1:8000/api/health"
PING_URL="http://127.0.0.1:8000/api/health/ping"

HEALTH_STATUS=$(curl -sf "$HEALTH_URL" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "unreachable")
if [[ "$HEALTH_STATUS" == "ok" || "$HEALTH_STATUS" == "healthy" ]]; then
  pass "/api/health: $HEALTH_STATUS"
else
  fail "/api/health: $HEALTH_STATUS"
  echo "  Check: sudo journalctl -u $SERVICE -n 50 --no-pager"
fi

PING_STATUS=$(curl -sf "$PING_URL" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "unreachable")
if [[ "$PING_STATUS" == "ok" ]]; then
  pass "/api/health/ping: $PING_STATUS"
else
  fail "/api/health/ping: $PING_STATUS"
fi

###############################################################################
head "STEP 15 – Verify ExecStart path in live unit"
###############################################################################
EXEC_START=$(systemctl show "$SERVICE" --property=ExecStart 2>/dev/null | grep -oP '(?<=path=)[^ ;]+' | head -1 || true)
EXPECTED_EXEC="$VENV/bin/uvicorn"
if [[ "$EXEC_START" == "$EXPECTED_EXEC" ]]; then
  pass "ExecStart path correct: $EXEC_START"
else
  fail "ExecStart mismatch: got=$EXEC_START expected=$EXPECTED_EXEC"
fi

# Check no stale amarktai.service running
if systemctl is-active amarktai.service &>/dev/null; then
  fail "Stale amarktai.service is still active – run ops/cleanup_stale_deployment.sh"
else
  pass "No stale amarktai.service running"
fi

###############################################################################
head "FINAL SUMMARY"
###############################################################################
echo ""
if [[ $FAIL_COUNT -eq 0 ]]; then
  echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${GREEN}║  ✅  DEPLOY COMPLETE – ALL $PASS_COUNT CHECKS PASSED              ║${NC}"
  echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
else
  echo -e "${BOLD}${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${RED}║  ❌  DEPLOY FINISHED WITH $FAIL_COUNT FAILURE(S)                   ║${NC}"
  echo -e "${BOLD}${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "${RED}Failures:${NC}"
  for f in "${FAILURES[@]}"; do
    echo -e "  ${RED}• $f${NC}"
  done
fi

echo ""
echo "  Built:    $BUILT_JS"
echo "  Served:   $SERVED_JS"
echo "  SHA:      $GIT_SHA"
echo "  Date:     $BUILD_DATE"
echo "  Service:  $(systemctl is-active $SERVICE 2>/dev/null || echo unknown)"
echo "  Nginx:    $(systemctl is-active nginx 2>/dev/null || echo unknown)"
echo ""
echo "  Verify:   sudo bash ops/verify_production.sh"
echo "  Logs:     sudo journalctl -u $SERVICE -n 50 --no-pager"
echo ""

[[ $FAIL_COUNT -eq 0 ]]
