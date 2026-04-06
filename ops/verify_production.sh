#!/usr/bin/env bash
###############################################################################
# ops/verify_production.sh – Amarktai Crypto Production Verification
#
# USAGE
#   sudo bash ops/verify_production.sh
#
# Verifies:
#   • amarktai-api.service is active
#   • ExecStart path is the canonical venv uvicorn
#   • uvicorn process is running from the correct path
#   • Nginx root is the canonical frontend build path
#   • Built JS filename matches live-served JS filename
#   • /api/health and /api/health/ping return ok
#   • No stale amarktai.service remains
#   • No stale nginx sites remain enabled
#   • Public domain responds over HTTPS (if DOMAIN is set)
###############################################################################
set -uo pipefail

# ── Canonical constants ────────────────────────────────────────────────────────
APP_ROOT=/var/amarktai/app/Amarktai-Crypto
BACKEND_DIR="$APP_ROOT/backend"
VENV="$BACKEND_DIR/.venv"
FRONTEND_BUILD="$APP_ROOT/frontend/build"
ENV_FILE=/etc/amarktai/amarktai.env
SERVICE=amarktai-api
NGINX_SITE=amarktai
DOMAIN="${DOMAIN:-amarktai.online}"
EXPECTED_NGINX_ROOT="$FRONTEND_BUILD"
EXPECTED_EXEC="$VENV/bin/uvicorn"

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; PASS=$(( PASS + 1 )); }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; FAIL=$(( FAIL + 1 )); FAILURES+=("$*"); }
info() { echo -e "${CYAN}  → $*${NC}"; }

PASS=0; FAIL=0; FAILURES=()

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  AMARKTAI CRYPTO – PRODUCTION VERIFICATION${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

###############################################################################
echo -e "${BOLD}[ Service checks ]${NC}"
###############################################################################

# 1. Service active?
SVC_STATE=$(systemctl is-active "$SERVICE" 2>/dev/null || echo "inactive")
if [[ "$SVC_STATE" == "active" ]]; then
  ok "$SERVICE is active"
else
  fail "$SERVICE is $SVC_STATE (expected: active)"
fi

# 2. Service enabled?
SVC_ENABLED=$(systemctl is-enabled "$SERVICE" 2>/dev/null || echo "disabled")
if [[ "$SVC_ENABLED" == "enabled" ]]; then
  ok "$SERVICE is enabled (survives reboot)"
else
  warn "$SERVICE is $SVC_ENABLED – run: sudo systemctl enable $SERVICE"
fi

# 3. ExecStart path
EXEC_START=$(systemctl show "$SERVICE" --property=ExecStart 2>/dev/null | grep -oP '(?<=path=)[^ ;]+' | head -1 || true)
if [[ "$EXEC_START" == "$EXPECTED_EXEC" ]]; then
  ok "ExecStart correct: $EXEC_START"
else
  fail "ExecStart wrong: got='$EXEC_START' expected='$EXPECTED_EXEC'"
fi

# 4. Unit file path
UNIT_FILE=$(systemctl show "$SERVICE" --property=FragmentPath 2>/dev/null | cut -d= -f2 || true)
if [[ "$UNIT_FILE" == "/etc/systemd/system/$SERVICE.service" ]]; then
  ok "Unit file path: $UNIT_FILE"
else
  warn "Unit file path: $UNIT_FILE"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Process checks ]${NC}"
###############################################################################

# 5. Uvicorn process from correct venv path?
UVICORN_PROC=$(pgrep -a uvicorn 2>/dev/null | head -3 || true)
if echo "$UVICORN_PROC" | grep -q "$VENV/bin/uvicorn"; then
  ok "uvicorn process from canonical venv: $VENV/bin/uvicorn"
else
  if echo "$UVICORN_PROC" | grep -q "uvicorn"; then
    ACTUAL_UVICORN=$(echo "$UVICORN_PROC" | grep uvicorn | awk '{print $2}' | head -1)
    fail "uvicorn running from wrong path: $ACTUAL_UVICORN (expected: $EXPECTED_EXEC)"
  else
    fail "No uvicorn process found"
  fi
fi

# 6. No stale amarktai.service
if systemctl is-active "amarktai.service" &>/dev/null; then
  fail "Stale amarktai.service is active – run ops/cleanup_stale_deployment.sh"
else
  ok "No stale amarktai.service running"
fi

if [[ -f "/etc/systemd/system/amarktai.service" ]]; then
  fail "Stale /etc/systemd/system/amarktai.service file exists – remove it"
else
  ok "No stale amarktai.service unit file"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Nginx checks ]${NC}"
###############################################################################

# 7. Nginx active?
NGINX_STATE=$(systemctl is-active nginx 2>/dev/null || echo "inactive")
if [[ "$NGINX_STATE" == "active" ]]; then
  ok "nginx is active"
else
  fail "nginx is $NGINX_STATE"
fi

# 8. Canonical nginx site enabled?
if [[ -L "/etc/nginx/sites-enabled/$NGINX_SITE" ]]; then
  ok "nginx site enabled: /etc/nginx/sites-enabled/$NGINX_SITE"
else
  fail "nginx site NOT enabled: /etc/nginx/sites-enabled/$NGINX_SITE"
fi

# 9. Nginx config root is canonical path?
NGINX_ROOT=$(grep -oP '(?<=root\s{1,10})/.+(?=;)' "/etc/nginx/sites-available/$NGINX_SITE" 2>/dev/null | head -1 | tr -d ' ' || true)
if [[ "$NGINX_ROOT" == "$EXPECTED_NGINX_ROOT" ]]; then
  ok "Nginx root correct: $NGINX_ROOT"
else
  fail "Nginx root wrong: got='$NGINX_ROOT' expected='$EXPECTED_NGINX_ROOT'"
fi

# 10. No stale nginx sites enabled
for stale in default amarktai-spa amarktai-websocket; do
  if [[ -e "/etc/nginx/sites-enabled/$stale" || -L "/etc/nginx/sites-enabled/$stale" ]]; then
    fail "Stale nginx site still enabled: /etc/nginx/sites-enabled/$stale"
  else
    ok "No stale nginx site: $stale"
  fi
done

###############################################################################
echo ""
echo -e "${BOLD}[ Frontend build checks ]${NC}"
###############################################################################

# 11. Frontend build directory exists?
if [[ -d "$FRONTEND_BUILD" ]]; then
  ok "Frontend build directory exists: $FRONTEND_BUILD"
else
  fail "Frontend build directory missing: $FRONTEND_BUILD"
fi

# 12. Built JS filename
BUILT_JS=$(ls "$FRONTEND_BUILD/static/js/main."*.js 2>/dev/null | xargs -I{} basename {} 2>/dev/null | head -1 || true)
if [[ -n "$BUILT_JS" ]]; then
  ok "Built JS: $BUILT_JS"
else
  fail "No built JS file in $FRONTEND_BUILD/static/js/"
fi

# 13. index.html JS filename
SERVED_JS=$(grep -oP 'static/js/main\.[a-f0-9]+\.js' "$FRONTEND_BUILD/index.html" 2>/dev/null | head -1 | xargs basename 2>/dev/null || true)
if [[ -n "$SERVED_JS" ]]; then
  ok "Served JS (from index.html): $SERVED_JS"
else
  fail "Cannot read JS filename from $FRONTEND_BUILD/index.html"
fi

# 14. Do they match?
if [[ -n "$BUILT_JS" && -n "$SERVED_JS" ]]; then
  if [[ "$BUILT_JS" == "$SERVED_JS" ]]; then
    ok "Built JS == Served JS: $BUILT_JS ✓"
  else
    fail "JS MISMATCH: built=$BUILT_JS  served=$SERVED_JS  (stale build – rerun redeploy)"
  fi
fi

###############################################################################
echo ""
echo -e "${BOLD}[ API health checks ]${NC}"
###############################################################################

# 15. /api/health
HEALTH=$(curl -sf --max-time 5 "http://127.0.0.1:8000/api/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "unreachable")
if [[ "$HEALTH" == "ok" || "$HEALTH" == "healthy" ]]; then
  ok "/api/health: $HEALTH"
else
  fail "/api/health: $HEALTH"
fi

# 16. /api/health/ping
PING=$(curl -sf --max-time 5 "http://127.0.0.1:8000/api/health/ping" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "unreachable")
if [[ "$PING" == "ok" ]]; then
  ok "/api/health/ping: $PING"
else
  fail "/api/health/ping: $PING"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Env file checks ]${NC}"
###############################################################################

# 17. Env file exists and has correct permissions
if [[ -f "$ENV_FILE" ]]; then
  ok "Env file exists: $ENV_FILE"
  ENV_PERMS=$(stat -c %a "$ENV_FILE" 2>/dev/null || echo "?")
  if [[ "$ENV_PERMS" == "600" || "$ENV_PERMS" == "640" ]]; then
    ok "Env file permissions: $ENV_PERMS"
  else
    warn "Env file permissions: $ENV_PERMS (recommend 600)"
  fi
else
  fail "Env file missing: $ENV_FILE"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Nightly retrain timer checks ]${NC}"
###############################################################################

# 19. Timer unit file installed
if [[ -f "/etc/systemd/system/amarktai-retrain.timer" ]]; then
  ok "amarktai-retrain.timer unit file present"
else
  fail "amarktai-retrain.timer unit file missing – run redeploy"
fi

# 20. Timer active
TIMER_STATE=$(systemctl is-active amarktai-retrain.timer 2>/dev/null || echo "inactive")
if [[ "$TIMER_STATE" == "active" ]]; then
  ok "amarktai-retrain.timer is active"
else
  fail "amarktai-retrain.timer is $TIMER_STATE – run: sudo systemctl start amarktai-retrain.timer"
fi

# 21. Timer enabled (survives reboots)
TIMER_ENABLED=$(systemctl is-enabled amarktai-retrain.timer 2>/dev/null || echo "disabled")
if [[ "$TIMER_ENABLED" == "enabled" ]]; then
  ok "amarktai-retrain.timer is enabled"
else
  fail "amarktai-retrain.timer is $TIMER_ENABLED – run: sudo systemctl enable amarktai-retrain.timer"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Learning / model artifact checks ]${NC}"
###############################################################################

MODEL_DIR="$BACKEND_DIR/models"
RIVER_DIR="$MODEL_DIR/river"
XGB_MODEL="$MODEL_DIR/xgb_predictor.json"

# 22. Model directory
if [[ -d "$MODEL_DIR" ]]; then
  ok "Model directory exists: $MODEL_DIR"
else
  fail "Model directory missing: $MODEL_DIR – run redeploy"
fi

# 23. River model directory
if [[ -d "$RIVER_DIR" ]]; then
  ok "River model dir exists: $RIVER_DIR"
else
  fail "River model dir missing: $RIVER_DIR – run redeploy"
fi

# 24. XGBoost model (warn only – expected missing on fresh install)
if [[ -f "$XGB_MODEL" ]]; then
  ok "XGBoost model present: $XGB_MODEL"
else
  warn "XGBoost model not yet trained: $XGB_MODEL (normal on fresh install – trains at 02:00 UTC once ENABLE_LEARNING_LOOP=true)"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ SMTP configuration check ]${NC}"
###############################################################################

# 25. SMTP config sanity (reads from env file, does NOT send email)
SMTP_USER_VAL=$(grep -oP '(?<=^SMTP_USER=)\S+' "$ENV_FILE" 2>/dev/null | head -1 || echo "")
SMTP_PASS_VAL=$(grep -oP '(?<=^SMTP_PASSWORD=)\S+' "$ENV_FILE" 2>/dev/null | head -1 || echo "")
SMTP_HOST_VAL=$(grep -oP '(?<=^SMTP_HOST=)\S+' "$ENV_FILE" 2>/dev/null | head -1 || echo "smtp.gmail.com")
if [[ -n "$SMTP_USER_VAL" && -n "$SMTP_PASS_VAL" ]]; then
  ok "SMTP configured: SMTP_HOST=$SMTP_HOST_VAL  SMTP_USER=$SMTP_USER_VAL"
  info "Tip: live SMTP probe → curl -sH 'Authorization: Bearer \$TOKEN' http://127.0.0.1:8000/api/diagnostics/smtp-test | python3 -m json.tool"
else
  warn "SMTP not configured (SMTP_USER or SMTP_PASSWORD blank in $ENV_FILE) – daily emails disabled"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Learning readiness API check ]${NC}"
###############################################################################

# 26. /api/diagnostics/learning-readiness (unauthenticated)
LR_JSON=$(curl -sf --max-time 5 "http://127.0.0.1:8000/api/diagnostics/learning-readiness" 2>/dev/null || echo "{}")
LR_XGB=$(echo "$LR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print('present' if d.get('xgb_model_present') else 'missing')" 2>/dev/null || echo "unknown")
LR_RIVER=$(echo "$LR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print('present' if d.get('river_dir_present') else 'missing')" 2>/dev/null || echo "unknown")
LR_TIMER=$(echo "$LR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timer_active','unknown'))" 2>/dev/null || echo "unknown")
if [[ "$LR_JSON" != "{}" ]]; then
  ok "Learning readiness API: xgb=$LR_XGB  river=$LR_RIVER  timer=$LR_TIMER"
else
  warn "Learning readiness API: backend not reachable (check /api/health)"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ Public domain check ]${NC}"
###############################################################################

# 27. Public HTTPS (non-fatal)
HTTPS_CODE=$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" "https://$DOMAIN/" 2>/dev/null || echo "000")
if [[ "$HTTPS_CODE" == "200" || "$HTTPS_CODE" == "301" || "$HTTPS_CODE" == "302" ]]; then
  ok "https://$DOMAIN/ responds: HTTP $HTTPS_CODE"
else
  warn "https://$DOMAIN/ HTTP $HTTPS_CODE (may be DNS / cert issue or non-public VPS)"
fi

# 19. XGBoost model artifact (non-fatal)
if [[ -f "$BACKEND_DIR/models/xgb_predictor.json" ]]; then
  ok "XGBoost model present: $BACKEND_DIR/models/xgb_predictor.json"
else
  warn "XGBoost model missing – run: cd $BACKEND_DIR && $VENV/bin/python3 scripts/bootstrap_xgboost_model.py"
fi

# 20. Retraining timer (non-fatal)
if systemctl is-enabled amarktai-retrain.timer &>/dev/null 2>&1; then
  ok "Retraining timer enabled"
else
  warn "Retraining timer not enabled (optional)"
fi

###############################################################################
echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
if [[ $FAIL -eq 0 ]]; then
  echo -e "${BOLD}${GREEN}  ✅  VERIFICATION PASSED – all $PASS checks OK${NC}"
else
  echo -e "${BOLD}${RED}  ❌  VERIFICATION FAILED – $FAIL failure(s) / $PASS passed${NC}"
  echo ""
  echo -e "${RED}  Failures:${NC}"
  for f in "${FAILURES[@]}"; do
    echo -e "${RED}    • $f${NC}"
  done
  echo ""
  echo "  Run: sudo bash ops/redeploy_production.sh  to fix"
fi
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

[[ $FAIL -eq 0 ]]
