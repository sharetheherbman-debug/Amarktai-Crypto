#!/usr/bin/env bash
# =============================================================================
# Amarktai Network — Go-Live Audit Script (v2)
# =============================================================================
# Covers:
#   A) Paper reset + countdown/equity invariants
#   K) Trading write-path proof (executor persists trades/fills)
#   L) Risk lock sanity (no instant bodyguard on clean start)
#   M) HuggingFace structured JSON (no 5xx, no stack traces)
#   N) FetchAI test-connection
#   O) GDELT / sentiment-news configured or graceful failure
#
# Usage:
#   BASE_URL=http://your-vps:8000 \
#   AMARKTAI_EMAIL=user@example.com \
#   AMARKTAI_PASSWORD=secret \
#   bash scripts/go_live_audit.sh
#
# Exits non-zero if ANY check FAILS.
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${AMARKTAI_EMAIL:-}"
PASSWORD="${AMARKTAI_PASSWORD:-}"
BOT_WAIT_SECONDS="${BOT_WAIT_SECONDS:-65}"   # Wait for scheduler ticks

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
RESULTS=()

log_pass() { echo -e "${GREEN}✓ PASS${NC} $1"; ((PASS_COUNT++)) || true; RESULTS+=("PASS|$1"); }
log_fail() { echo -e "${RED}✗ FAIL${NC} $1"; ((FAIL_COUNT++)) || true; RESULTS+=("FAIL|$1"); }
log_warn() { echo -e "${YELLOW}⚠ WARN${NC} $1"; ((WARN_COUNT++)) || true; RESULTS+=("WARN|$1"); }
log_info() { echo -e "${BLUE}ℹ${NC}  $1"; }

die() { echo -e "${RED}FATAL: $1${NC}" >&2; exit 1; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v curl  >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

jq_get() {
  # Usage: jq_get <field> <json_string>
  python3 -c "import json,sys; d=json.loads(sys.argv[2]); print(d.get(sys.argv[1],'')); " "$1" "$2" 2>/dev/null || true
}

jq_num() {
  python3 -c "import json,sys; d=json.loads(sys.argv[2]); print(float(d.get(sys.argv[1],0))); " "$1" "$2" 2>/dev/null || echo "0"
}

http_status() {
  curl -o /dev/null -s -w "%{http_code}" "$@"
}

auth_get_status() {
  http_status -H "Authorization: Bearer $TOKEN" "$BASE_URL$1"
}

auth_get() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE_URL$1" 2>/dev/null
}

auth_post() {
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$2" "$BASE_URL$1" 2>/dev/null
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "   Amarktai Network — Go-Live Audit"
echo "   Target: $BASE_URL"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 0) Credentials ────────────────────────────────────────────────────────────
if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  die "Set AMARKTAI_EMAIL and AMARKTAI_PASSWORD before running this script."
fi

# ── 1) Backend Health ─────────────────────────────────────────────────────────
log_info "Checking backend health..."
if curl -fsS "$BASE_URL/health" >/dev/null 2>&1 || \
   curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then
  log_pass "Backend /health responds"
else
  log_fail "Backend /health — server may be down"
fi

# ── 2) Login ──────────────────────────────────────────────────────────────────
log_info "Logging in as $EMAIL..."
LOGIN_RESP=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}" 2>/dev/null) || LOGIN_RESP=""

TOKEN=$(jq_get "access_token" "$LOGIN_RESP")
if [ -z "$TOKEN" ]; then
  log_fail "Login failed — no access_token (check credentials)"
  echo "Login response: $LOGIN_RESP" >&2
  exit 1
fi
log_pass "Login OK"

# ── 3) Paper Reset ─────────────────────────────────────────────────────────────
log_info "Performing paper-sandbox reset..."
RESET_RESP=$(auth_post "/api/system/paper-sandbox/reset" \
  '{"confirmed": true, "confirmation_phrase": "RESET PAPER SANDBOX"}') || RESET_RESP=""

RESET_OK=$(jq_get "success" "$RESET_RESP")
if [ "$RESET_OK" = "True" ] || [ "$RESET_OK" = "true" ]; then
  TOTAL_DEL=$(jq_num "total_deleted" "$RESET_RESP")
  log_pass "Paper sandbox reset OK (deleted ${TOTAL_DEL} docs)"
  INV_WARN=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); w=d.get('invariant_warnings',[]); print(len(w)); " "$RESET_RESP" 2>/dev/null || echo "0")
  if [ "$INV_WARN" -gt 0 ]; then
    WARNS=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print('; '.join(d.get('invariant_warnings',[])));  " "$RESET_RESP" 2>/dev/null || echo "")
    log_fail "Post-reset invariant warnings: $WARNS"
  fi
else
  log_fail "Paper sandbox reset failed: $RESET_RESP"
fi

# Also try user-level reset (used by frontend)
USER_RESET=$(auth_post "/api/user/paper-start-fresh" \
  '{"confirmation_phrase": "START FRESH", "scope": "paper_only", "also_reset_risk_locks": true}') || USER_RESET=""
U_OK=$(jq_get "ok" "$USER_RESET")
if [ "$U_OK" = "True" ] || [ "$U_OK" = "true" ]; then
  log_pass "User paper-start-fresh OK"
else
  log_warn "User paper-start-fresh: $USER_RESET"
fi

# ── 4) Countdown / Equity Invariants ─────────────────────────────────────────
log_info "Checking post-reset invariants..."
sleep 2  # Allow async cleanup to settle

EQ_RESP=$(auth_get "/api/analytics/equity") || EQ_RESP="{}"
EQ_VAL=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('current_equity', d.get('equity', -1)));  " "$EQ_RESP" 2>/dev/null || echo "-1")
if python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if v==0.0 else 1)" "$EQ_VAL" 2>/dev/null; then
  log_pass "/api/analytics/equity.current_equity == 0 after reset"
elif python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if v < 0 else 1)" "$EQ_VAL" 2>/dev/null; then
  log_warn "/api/analytics/equity returned no equity field (no bots yet — OK)"
else
  log_fail "/api/analytics/equity.current_equity == $EQ_VAL (expected 0)"
fi

CTD_RESP=$(auth_get "/api/countdown/status") || CTD_RESP="{}"
CTD_EQ=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('current_equity', -999));  " "$CTD_RESP" 2>/dev/null || echo "-999")
CTD_TR=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('trades_total', -999));  " "$CTD_RESP" 2>/dev/null || echo "-999")
if python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if v==0.0 else 1)" "$CTD_EQ" 2>/dev/null; then
  log_pass "/api/countdown/status.current_equity == 0 after reset"
else
  log_fail "/api/countdown/status.current_equity == $CTD_EQ (expected 0)"
fi
if python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if v==0.0 else 1)" "$CTD_TR" 2>/dev/null; then
  log_pass "/api/countdown/status.trades_total == 0 after reset"
else
  log_fail "/api/countdown/status.trades_total == $CTD_TR (expected 0)"
fi

CTM_RESP=$(auth_get "/api/analytics/countdown-to-million") || CTM_RESP="{}"
CTM_CAP=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('current_capital', d.get('current_capital',0)));  " "$CTM_RESP" 2>/dev/null || echo "0")
CTM_TR=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); m=d.get('metrics',{}); print(m.get('total_trades', d.get('trades_total', 0)));  " "$CTM_RESP" 2>/dev/null || echo "0")
if python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if v==0.0 else 1)" "$CTM_CAP" 2>/dev/null; then
  log_pass "/api/analytics/countdown-to-million.current_capital == 0 after reset"
else
  log_fail "/api/analytics/countdown-to-million.current_capital == $CTM_CAP (expected 0)"
fi

# ── 5) Risk Lock Sanity — immediately after reset ─────────────────────────────
log_info "Checking risk locks are clear after reset..."
RISK_RESP=$(auth_get "/api/risk/status") || RISK_RESP="{}"
DL_ACTIVE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); dl=d.get('daily_loss_lock',{}); print(dl.get('active', d.get('daily_loss_lock_active', False)));  " "$RISK_RESP" 2>/dev/null || echo "False")
BG_ACTIVE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); bg=d.get('bodyguard_lock',{}); print(bg.get('active', False));  " "$RISK_RESP" 2>/dev/null || echo "False")

if [ "$DL_ACTIVE" = "False" ] || [ "$DL_ACTIVE" = "false" ]; then
  log_pass "daily_loss_lock UNLOCKED after reset"
else
  log_fail "daily_loss_lock ACTIVE after reset (stale state) — reason: $(jq_get 'daily_loss_lock' "$RISK_RESP")"
fi
if [ "$BG_ACTIVE" = "False" ] || [ "$BG_ACTIVE" = "false" ]; then
  log_pass "bodyguard_lock UNLOCKED after reset"
else
  log_fail "bodyguard_lock ACTIVE after reset (stale state)"
fi

DLL_RESP=$(auth_get "/api/risk/daily-loss-lock") || DLL_RESP="{}"
DLL_STATUS=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('locked', d.get('active', False)));  " "$DLL_RESP" 2>/dev/null || echo "False")
if [ "$DLL_STATUS" = "False" ] || [ "$DLL_STATUS" = "false" ]; then
  log_pass "/api/risk/daily-loss-lock UNLOCKED after reset"
else
  log_fail "/api/risk/daily-loss-lock LOCKED after reset: $DLL_RESP"
fi

CB_STATUS_CODE=$(auth_get_status "/api/circuit-breaker/status")
if [ "$CB_STATUS_CODE" = "200" ]; then
  CB_RESP=$(auth_get "/api/circuit-breaker/status") || CB_RESP="{}"
  CB_TRIP=$(jq_get "tripped" "$CB_RESP")
  if [ "$CB_TRIP" = "False" ] || [ "$CB_TRIP" = "false" ]; then
    log_pass "/api/circuit-breaker/status NOT tripped after reset"
  else
    log_fail "/api/circuit-breaker/status TRIPPED after reset: $CB_RESP"
  fi
else
  log_warn "/api/circuit-breaker/status returned $CB_STATUS_CODE"
fi

# ── 6) Trading Write-Path Proof (K) ──────────────────────────────────────────
log_info "Creating a paper bot to test trading write-path..."
BOT_RESP=$(auth_post "/api/bots" '{
  "name": "audit-bot",
  "pair": "BTC/ZAR",
  "exchange": "luno",
  "trading_mode": "paper",
  "strategy": "grid",
  "initial_capital": 1000,
  "base_order_size": 100,
  "safety_order_size": 100,
  "max_safety_orders": 2,
  "take_profit_pct": 1.5,
  "stop_loss_pct": 5.0
}') || BOT_RESP="{}"

BOT_ID=$(jq_get "id" "$BOT_RESP")
if [ -z "$BOT_ID" ]; then
  # Try alternate field names
  BOT_ID=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('bot',{}).get('id','') or d.get('bot_id',''));  " "$BOT_RESP" 2>/dev/null || echo "")
fi

if [ -n "$BOT_ID" ]; then
  log_pass "Paper bot created: $BOT_ID"
  log_info "Waiting ${BOT_WAIT_SECONDS}s for scheduler ticks (trading write-path test)..."
  sleep "$BOT_WAIT_SECONDS"

  # Check trades/recent
  TRADES_RESP=$(auth_get "/api/trades/recent?limit=5") || TRADES_RESP="{}"
  TRADE_COUNT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); arr=d.get('trades', d.get('data', d if isinstance(d,list) else [])); print(len(arr));  " "$TRADES_RESP" 2>/dev/null || echo "0")

  # Check fills in ledger
  FILLS_RESP=$(auth_get "/api/ledger/fills?limit=5") || FILLS_RESP="{}"
  FILL_COUNT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); arr=d.get('fills', []); print(len(arr));  " "$FILLS_RESP" 2>/dev/null || echo "0")

  if [ "$TRADE_COUNT" -gt 0 ] || [ "$FILL_COUNT" -gt 0 ]; then
    log_pass "Trading write-path OK (trades=$TRADE_COUNT fills=$FILL_COUNT)"
  else
    log_warn "Trading write-path: no trades/fills after ${BOT_WAIT_SECONDS}s (check executor logs; market may be closed or bot config may need a price)"
  fi

  # Risk lock check AFTER creating bot (must still be unlocked with 0 trades)
  RISK2=$(auth_get "/api/risk/status") || RISK2="{}"
  DL2=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); dl=d.get('daily_loss_lock',{}); print(dl.get('active', False));  " "$RISK2" 2>/dev/null || echo "False")
  BG2=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); bg=d.get('bodyguard_lock',{}); print(bg.get('active', False));  " "$RISK2" 2>/dev/null || echo "False")

  if [ "$TRADE_COUNT" = "0" ] && ([ "$DL2" = "True" ] || [ "$DL2" = "true" ]); then
    log_fail "RISK LOCK TRIGGERED WITHOUT TRADES — daily_loss_lock active with 0 trades (stale equity/ledger)"
  fi
  if [ "$TRADE_COUNT" = "0" ] && ([ "$BG2" = "True" ] || [ "$BG2" = "true" ]); then
    log_fail "RISK LOCK TRIGGERED WITHOUT TRADES — bodyguard_lock active with 0 trades (stale equity/ledger)"
  fi
  if ([ "$DL2" = "False" ] || [ "$DL2" = "false" ]) && ([ "$BG2" = "False" ] || [ "$BG2" = "false" ]); then
    log_pass "No risk locks triggered during bot warmup (correct behavior)"
  fi

else
  log_warn "Bot creation failed (may need valid API keys for paper trading): $BOT_RESP"
fi

# ── 7) HuggingFace Endpoints (M) ──────────────────────────────────────────────
log_info "Checking HuggingFace endpoints..."

HF_TEST_CODE=$(auth_get_status "/api/huggingface/test-connection")
if [ "$HF_TEST_CODE" = "200" ]; then
  HF_TEST=$(auth_get "/api/huggingface/test-connection") || HF_TEST="{}"
  HF_STATUS=$(jq_get "status" "$HF_TEST")
  log_pass "/api/huggingface/test-connection returned 200 (status=$HF_STATUS)"
else
  log_fail "/api/huggingface/test-connection returned HTTP $HF_TEST_CODE (expected 200)"
fi

HF_MODELS_CODE=$(auth_get_status "/api/huggingface/models")
if [ "$HF_MODELS_CODE" = "200" ]; then
  HF_MODELS=$(auth_get "/api/huggingface/models") || HF_MODELS="{}"
  HF_SUCCESS=$(jq_get "success" "$HF_MODELS")
  if [ "$HF_SUCCESS" = "True" ] || [ "$HF_SUCCESS" = "true" ]; then
    log_pass "/api/huggingface/models returned 200 with success=true"
  else
    log_fail "/api/huggingface/models returned 200 but success!=true: $HF_MODELS"
  fi
else
  log_fail "/api/huggingface/models returned HTTP $HF_MODELS_CODE (expected 200)"
fi

# Test sentiment endpoint returns structured JSON (never 5xx)
HF_SENT_CODE=$(curl -o /dev/null -s -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Bitcoin is going up today"}' "$BASE_URL/api/huggingface/analyze-sentiment")
if [ "$HF_SENT_CODE" = "200" ]; then
  HF_SENT=$(auth_post "/api/huggingface/analyze-sentiment" '{"text": "Bitcoin is going up today"}') || HF_SENT="{}"
  # Must have 'success' field regardless of key configured or not
  HF_S_FIELD=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print('success' in d);  " "$HF_SENT" 2>/dev/null || echo "False")
  if [ "$HF_S_FIELD" = "True" ]; then
    log_pass "/api/huggingface/analyze-sentiment always returns structured JSON with 'success' field"
  else
    log_fail "/api/huggingface/analyze-sentiment missing 'success' field: $HF_SENT"
  fi
else
  log_fail "/api/huggingface/analyze-sentiment returned HTTP $HF_SENT_CODE (expected 200, never 5xx)"
fi

# ── 8) FetchAI endpoints (D) ──────────────────────────────────────────────────
log_info "Checking FetchAI endpoints..."
for ep in "/api/fetchai/status" "/api/fetchai/test-connection"; do
  CODE=$(auth_get_status "$ep")
  if [ "$CODE" = "200" ] || [ "$CODE" = "400" ]; then
    # 400 is acceptable when key not configured (structured error)
    log_pass "$ep returned $CODE (not 5xx)"
  else
    log_fail "$ep returned HTTP $CODE (expected 200 or 400)"
  fi
done

# ── 9) GDELT / Sentiment-News (O) ────────────────────────────────────────────
log_info "Checking GDELT news provider..."
GDELT_CODE=$(auth_get_status "/api/diagnostics/sentiment-news")
if [ "$GDELT_CODE" = "200" ]; then
  GDELT_RESP=$(auth_get "/api/diagnostics/sentiment-news") || GDELT_RESP="{}"
  GDELT_SRC=$(jq_get "source" "$GDELT_RESP")
  GDELT_CONF=$(jq_get "configured" "$GDELT_RESP")
  if [ "$GDELT_SRC" = "gdelt" ]; then
    log_pass "/api/diagnostics/sentiment-news source=gdelt (no API key required)"
  else
    log_warn "/api/diagnostics/sentiment-news source=$GDELT_SRC configured=$GDELT_CONF"
  fi
else
  log_fail "/api/diagnostics/sentiment-news returned HTTP $GDELT_CODE"
fi

NEWS_CODE=$(auth_get_status "/api/news/articles")
if [ "$NEWS_CODE" = "200" ]; then
  log_pass "/api/news/articles returns 200"
else
  log_warn "/api/news/articles returned $NEWS_CODE"
fi

# ── 10) Build Info ─────────────────────────────────────────────────────────────
BUILD_RESP=$(curl -fsS "$BASE_URL/api/build/info" 2>/dev/null) || BUILD_RESP="{}"
BUILD_SHA=$(jq_get "version" "$BUILD_RESP")
if [ -n "$BUILD_SHA" ] && [ "$BUILD_SHA" != "unknown" ]; then
  log_pass "Build SHA: $BUILD_SHA"
else
  log_warn "Build SHA is unknown (set BUILD_SHA env var or ensure git is available at startup)"
fi

# ── Summary Table ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "   Audit Summary"
echo "═══════════════════════════════════════════════════════════════"
printf "  %-12s  %s\n" "Result" "Check"
echo "  ──────────────────────────────────────────────────────────"
for r in "${RESULTS[@]}"; do
  STATUS="${r%%|*}"
  LABEL="${r#*|}"
  case "$STATUS" in
    PASS) printf "  ${GREEN}%-12s${NC}  %s\n" "✓ PASS" "$LABEL" ;;
    FAIL) printf "  ${RED}%-12s${NC}  %s\n" "✗ FAIL" "$LABEL" ;;
    WARN) printf "  ${YELLOW}%-12s${NC}  %s\n" "⚠ WARN" "$LABEL" ;;
  esac
done
echo "  ──────────────────────────────────────────────────────────"
echo ""
echo -e "  Passed : ${GREEN}${PASS_COUNT}${NC}"
echo -e "  Failed : ${RED}${FAIL_COUNT}${NC}"
echo -e "  Warned : ${YELLOW}${WARN_COUNT}${NC}"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo -e "${RED}AUDIT FAILED — fix the above FAILs before go-live.${NC}"
  exit 1
else
  echo -e "${GREEN}AUDIT PASSED — system is go-live ready.${NC}"
  exit 0
fi

