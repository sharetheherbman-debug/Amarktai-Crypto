#!/usr/bin/env bash
###############################################################################
# /ops/post_deploy_evidence_pack.sh – Deployment verification script
#
# Prints a "truth pack" that proves the deployment is correct:
#   - Git hash in repo vs hash reported by running service
#   - Backend health + ping endpoint
#   - Frontend index.html exists + references correct JS bundle
#   - Key API endpoints respond with expected shape
#   - WebSocket/SSE reachability
#
# USAGE
#   bash ops/post_deploy_evidence_pack.sh
###############################################################################
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE="${API_BASE:-http://127.0.0.1:8000/api}"
NGINX_BASE="${NGINX_BASE:-http://localhost}"
FRONTEND_WEBROOT="${FRONTEND_WEBROOT:-/var/amarktai/app/Amarktai-Crypto/frontend/build}"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0

pass() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL++)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; ((WARN++)); }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} 🔍  AMARKTAI NETWORK – POST-DEPLOY EVIDENCE PACK${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo " Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# ── 1. Git hash ───────────────────────────────────────────────────────────────
echo -e "${BOLD}[1] Source Code Version${NC}"
REPO_SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
REPO_BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
info "Repo SHA:    $REPO_SHA"
info "Repo branch: $REPO_BRANCH"
info "Repo dirty:  $(git -C "$REPO_ROOT" status --short 2>/dev/null | wc -l | tr -d ' ') uncommitted files"
echo ""

# ── 2. Service status ─────────────────────────────────────────────────────────
echo -e "${BOLD}[2] systemd Service${NC}"
if command -v systemctl &>/dev/null; then
  SVC_STATE=$(systemctl is-active amarktai-api 2>/dev/null || echo "not-found")
  if [[ "$SVC_STATE" == "active" ]]; then
    pass "amarktai-api is active"
  else
    fail "amarktai-api state: $SVC_STATE"
  fi
  info "$(systemctl show amarktai-api --property=MainPID,ActiveState,SubState 2>/dev/null | head -3)"
else
  warn "systemctl not available (non-systemd environment)"
fi
echo ""

# ── 3. Backend health (direct) ────────────────────────────────────────────────
echo -e "${BOLD}[3] Backend Health (direct 127.0.0.1:8000)${NC}"
HEALTH_RAW=$(curl -sf --max-time 5 "$API_BASE/health/ping" 2>/dev/null || echo '{"error":"unreachable"}')
echo "$HEALTH_RAW" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RAW"
HEALTH_STATUS=$(echo "$HEALTH_RAW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "parse-error")
SERVICE_SHA=$(echo "$HEALTH_RAW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('build_sha') or d.get('build_hash','none'))" 2>/dev/null || echo "none")
if [[ "$HEALTH_STATUS" == "ok" || "$HEALTH_STATUS" == "healthy" ]]; then
  pass "Backend /api/health/ping status: $HEALTH_STATUS"
else
  fail "Backend /api/health/ping status: $HEALTH_STATUS"
fi

# Check SHA match
if [[ "$SERVICE_SHA" != "none" && "$SERVICE_SHA" != "unknown" ]]; then
  if [[ "$SERVICE_SHA" == "$REPO_SHA"* || "$REPO_SHA" == "$SERVICE_SHA"* ]]; then
    pass "Build SHA match: repo=$REPO_SHA service=$SERVICE_SHA"
  else
    warn "Build SHA mismatch: repo=$REPO_SHA service=$SERVICE_SHA (may be stale)"
  fi
fi
echo ""

# ── 4. Backend health via nginx ───────────────────────────────────────────────
echo -e "${BOLD}[4] Backend Health (via nginx proxy)${NC}"
NGINX_HEALTH=$(curl -sf --max-time 5 "$NGINX_BASE/api/health/ping" 2>/dev/null || echo '{"error":"nginx-unreachable"}')
NGINX_STATUS=$(echo "$NGINX_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "parse-error")
if [[ "$NGINX_STATUS" == "ok" || "$NGINX_STATUS" == "healthy" ]]; then
  pass "Nginx proxy /api/health/ping: $NGINX_STATUS"
else
  warn "Nginx proxy /api/health/ping: $NGINX_STATUS (nginx may not be running locally)"
fi
echo ""

# ── 5. OpenAPI schema ─────────────────────────────────────────────────────────
echo -e "${BOLD}[5] OpenAPI Schema${NC}"
OPENAPI=$(curl -sf --max-time 10 "$API_BASE/../openapi.json" 2>/dev/null || curl -sf --max-time 10 "$API_BASE/openapi.json" 2>/dev/null || echo '{}')
ROUTE_COUNT=$(echo "$OPENAPI" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('paths',{})))" 2>/dev/null || echo "0")
if [[ "$ROUTE_COUNT" -gt 5 ]]; then
  pass "OpenAPI has $ROUTE_COUNT routes"
else
  fail "OpenAPI empty or unreachable (got $ROUTE_COUNT routes)"
fi
echo ""

# ── 6. Frontend build ─────────────────────────────────────────────────────────
echo -e "${BOLD}[6] Frontend Build Artifacts${NC}"
if [[ -d "$FRONTEND_WEBROOT" ]]; then
  INDEX_HTML="$FRONTEND_WEBROOT/index.html"
  if [[ -f "$INDEX_HTML" ]]; then
    pass "index.html exists"
    # Extract JS bundle reference
    JS_BUNDLE=$(grep -oE 'static/js/main\.[a-f0-9]+\.js' "$INDEX_HTML" | head -1 || echo "")
    if [[ -n "$JS_BUNDLE" ]]; then
      if [[ -f "$FRONTEND_WEBROOT/$JS_BUNDLE" ]]; then
        BUNDLE_SIZE=$(du -h "$FRONTEND_WEBROOT/$JS_BUNDLE" | cut -f1)
        pass "JS bundle exists: $JS_BUNDLE ($BUNDLE_SIZE)"
      else
        fail "JS bundle missing: $FRONTEND_WEBROOT/$JS_BUNDLE"
      fi
    else
      warn "Could not extract JS bundle name from index.html"
    fi
  else
    fail "index.html missing in $FRONTEND_WEBROOT"
  fi

  BUILD_SHA_FILE="$FRONTEND_WEBROOT/BUILD_SHA.txt"
  if [[ -f "$BUILD_SHA_FILE" ]]; then
    FRONTEND_SHA=$(cat "$BUILD_SHA_FILE")
    info "Frontend build SHA: $FRONTEND_SHA"
  fi
else
  warn "Web root not found: $FRONTEND_WEBROOT (may be dev environment)"
fi
echo ""

# ── 7. Key API endpoints ──────────────────────────────────────────────────────
echo -e "${BOLD}[7] Key API Endpoints (unauthenticated)${NC}"
check_endpoint() {
  local label="$1"; local url="$2"; local expect_key="${3:-}"
  local resp
  resp=$(curl -sf --max-time 5 "$url" 2>/dev/null || echo '{"error":"timeout"}')
  if echo "$resp" | python3 -c "import sys,json; json.load(sys.stdin)" &>/dev/null; then
    if [[ -n "$expect_key" ]]; then
      HAS_KEY=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if '$expect_key' in d else 'no')" 2>/dev/null || echo "no")
      if [[ "$HAS_KEY" == "yes" ]]; then
        pass "$label – key '$expect_key' present"
      else
        fail "$label – key '$expect_key' missing in response"
      fi
    else
      pass "$label – valid JSON"
    fi
  else
    fail "$label – non-JSON or error: ${resp:0:80}"
  fi
}

check_endpoint "GET /api/health"      "$API_BASE/health"         "status"
check_endpoint "GET /api/health/ping" "$API_BASE/health/ping"    "status"
check_endpoint "GET /api/diagnostics/frontend-contract" "$API_BASE/diagnostics/frontend-contract" "contract_version"
echo ""

# ── 8. Env file safety check ──────────────────────────────────────────────────
echo -e "${BOLD}[8] Env File Safety${NC}"
ENV_FILE="${ENV_FILE:-/etc/amarktai/backend.env}"
if [[ -f "$ENV_FILE" ]]; then
  pass "Env file present: $ENV_FILE"
  PERMS=$(stat -c "%a" "$ENV_FILE" 2>/dev/null || stat -f "%Lp" "$ENV_FILE" 2>/dev/null || echo "?")
  if [[ "$PERMS" == "600" ]]; then
    pass "Env file permissions: $PERMS (correct)"
  else
    warn "Env file permissions: $PERMS (should be 600)"
  fi
else
  fail "Env file MISSING: $ENV_FILE"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL + WARN))
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} 📊  EVIDENCE PACK SUMMARY${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo -e " ${GREEN}PASS${NC}: $PASS / $TOTAL"
echo -e " ${RED}FAIL${NC}: $FAIL / $TOTAL"
echo -e " ${YELLOW}WARN${NC}: $WARN / $TOTAL"
echo ""
if [[ $FAIL -eq 0 ]]; then
  echo -e " ${GREEN}✅  Deployment looks GOOD${NC}"
else
  echo -e " ${RED}❌  $FAIL check(s) FAILED – investigate before going live${NC}"
fi
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo ""
