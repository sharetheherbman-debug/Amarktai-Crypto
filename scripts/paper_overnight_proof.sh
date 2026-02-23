#!/usr/bin/env bash
# paper_overnight_proof.sh
# Smoke-test script for overnight paper trading proof.
#
# Usage:
#   export LOGIN_EMAIL="your@email.com"
#   export LOGIN_PASSWORD="yourpassword"
#   bash scripts/paper_overnight_proof.sh
#
# Override API base:  API_BASE=http://127.0.0.1:8000  (default)
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
EMAIL="${LOGIN_EMAIL:-admin@amarktai.online}"
PASSWORD="${LOGIN_PASSWORD:-}"
LOGFILE="/tmp/paper_overnight_proof_$(date +%Y%m%d_%H%M%S).log"

info()  { echo "[INFO]  $*" | tee -a "$LOGFILE"; }
ok()    { echo "[OK]    $*" | tee -a "$LOGFILE"; }
warn()  { echo "[WARN]  $*" | tee -a "$LOGFILE"; }
fail()  { echo "[FAIL]  $*" | tee -a "$LOGFILE"; exit 1; }

info "=== Amarktai Paper Overnight Proof ==="
info "API_BASE=$API_BASE"
info "Log file: $LOGFILE"

# ---- Step 1: Login ----
info "Step 1: Login..."
if [ -z "$PASSWORD" ]; then
  fail "Set LOGIN_PASSWORD environment variable before running this script."
fi

LOGIN_RESP=$(curl -sf -X POST "$API_BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" || echo "CURL_ERROR")

if [ "$LOGIN_RESP" = "CURL_ERROR" ]; then
  fail "Login request failed (curl error)."
fi

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token') or d.get('access_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  fail "Could not extract token from login response: $LOGIN_RESP"
fi
ok "Logged in. Token obtained."

AUTH="-H \"Authorization: Bearer $TOKEN\""

_get() {
  curl -sf -H "Authorization: Bearer $TOKEN" "$API_BASE$1" 2>/dev/null || echo "{}"
}
_post() {
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$2" "$API_BASE$1" 2>/dev/null || echo "{}"
}

# ---- Step 2: Ensure paper mode ----
info "Step 2: Check system mode..."
MODE=$(_get "/api/system/mode")
PAPER=$(echo "$MODE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('paperTrading', False))" 2>/dev/null || echo "false")
LIVE=$(echo "$MODE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('liveTrading', False))" 2>/dev/null || echo "false")
info "  paperTrading=$PAPER  liveTrading=$LIVE"
if [ "$LIVE" = "True" ]; then
  warn "Live trading is ON – paper reset may be blocked. Continuing anyway."
fi
ok "Mode check done."

# ---- Step 3: Reset paper runtime ----
info "Step 3: Reset paper runtime (start-fresh)..."
RESET_RESP=$(_post "/api/admin/start-fresh" \
  '{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}')
RESET_OK=$(echo "$RESET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok', False))" 2>/dev/null || echo "false")
if [ "$RESET_OK" = "True" ]; then
  ok "Paper reset successful."
  echo "$RESET_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  deleted_counts:', json.dumps(d.get('deleted_counts', d.get('deleted', {}))))
print('  wallet_before:', d.get('wallet_before', 'n/a'))
print('  wallet_after:', d.get('wallet_after', 'n/a'))
" 2>/dev/null | tee -a "$LOGFILE" || true
else
  warn "Paper reset returned non-OK: $RESET_RESP"
fi

# ---- Step 4: Seed 5 Luno bots ----
info "Step 4: Seed 5 Luno paper bots (Gbot1..Gbot5)..."
SEED_RESP=$(_post "/api/bots/seed-luno-paper" '{}')
SEED_OK=$(echo "$SEED_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "false")
if [ "$SEED_OK" = "True" ]; then
  ok "Bots seeded."
  echo "$SEED_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  created:', d.get('created', 0), '  existing:', d.get('existing', 0), '  skipped:', d.get('skipped', 0))
for b in d.get('bots', []):
    print('   ', b.get('name'), '->', b.get('status'), b.get('bot_id',''))
" 2>/dev/null | tee -a "$LOGFILE" || true
else
  warn "Seed returned non-OK: $SEED_RESP"
fi

# ---- Step 5: Sample counts NOW ----
info "Step 5: Sample trading activity (T=0)..."
ACT0=$(_get "/api/trades/activity")
echo "$ACT0" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  active_bots:', d.get('active_bots'))
print('  queued_trades:', d.get('queued_trades'))
print('  last_trade_at:', d.get('last_trade_at'))
print('  last_fill_at:', d.get('last_fill_at'))
" 2>/dev/null | tee -a "$LOGFILE" || warn "Could not parse activity response."

# ---- Step 6: Wait 60s ----
info "Step 6: Waiting 60 seconds for trading activity..."
sleep 60

# ---- Step 7: Sample counts AFTER ----
info "Step 7: Sample trading activity (T=60s)..."
ACT1=$(_get "/api/trades/activity")
echo "$ACT1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  active_bots:', d.get('active_bots'))
print('  queued_trades:', d.get('queued_trades'))
print('  last_trade_at:', d.get('last_trade_at'))
print('  last_fill_at:', d.get('last_fill_at'))
print('  last_tick_at:', d.get('last_tick_at'))
" 2>/dev/null | tee -a "$LOGFILE" || warn "Could not parse activity response."

# ---- Step 8: Print last 2 minutes of proof log lines ----
info "Step 8: Checking logs for paper trading proof lines..."
JOURNAL_LINES=$(journalctl -u amarktai-api --since "2 minutes ago" --no-pager -q 2>/dev/null \
  | grep -E "Paper tick start|Bots scanned|Queued trade|Filled|EXECUTED" \
  | tail -20 || true)

if [ -n "$JOURNAL_LINES" ]; then
  ok "Found paper trading proof lines in logs:"
  echo "$JOURNAL_LINES" | tee -a "$LOGFILE"
else
  warn "No paper trading proof lines found in last 2 minutes of logs."
  warn "(Service may need time to run first tick. Check: journalctl -u amarktai-api -n 50)"
fi

info "=== Proof complete. Full log: $LOGFILE ==="
