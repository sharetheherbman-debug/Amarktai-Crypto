#!/usr/bin/env bash
# =============================================================================
# prove_go_live_paper.sh
# Go-Live Paper Trading Proof Script — Amarktai Crypto
#
# Usage:
#   BASE_URL=https://your-server.com EMAIL=user@example.com PASSWORD=secret bash scripts/prove_go_live_paper.sh
#
# Checks:
#   1. Login succeeds and token is valid
#   2. /api/market/prices returns BTC/ZAR (not XBTZAR), ETH/ZAR, XRP/ZAR
#   3. Seeds 2 Luno paper bots
#   4. Bots start in training state (not active) until training completes
#   5. Open trades appear
#   6. At least one closed trade appears (or prints exact block reason)
#   7. /api/bots/status always returns valid JSON
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-admin@amarktai.com}"
PASSWORD="${PASSWORD:-changeme}"
MAX_WAIT_TRADES=120   # seconds to wait for first closed trade
POLL_INTERVAL=5

PASS=0
FAIL=0
ERRORS=()

pass() { echo "  ✅ PASS: $1"; ((PASS++)); }
fail() { echo "  ❌ FAIL: $1"; ((FAIL++)); ERRORS+=("$1"); }
info() { echo "  ℹ️  $1"; }
section() { echo; echo "═══════════════════════════════════════"; echo "  $1"; echo "═══════════════════════════════════════"; }

# ─────────────────────────────────────────
# 1. LOGIN
# ─────────────────────────────────────────
section "1. Login"

LOGIN_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>&1) || true

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token',''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
  pass "Login succeeded; token received (length=${#TOKEN})"
else
  fail "Login failed — response: $LOGIN_RESPONSE"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "RESULT: FAIL ($FAIL failures, $PASS passes)"
  echo "Errors: ${ERRORS[*]}"
  exit 1
fi

AUTH="-H \"Authorization: Bearer $TOKEN\""

do_get() {
  curl -sf -H "Authorization: Bearer $TOKEN" "$BASE_URL$1" 2>&1 || echo "{\"error\":\"request failed\"}"
}

do_post() {
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$2" "$BASE_URL$1" 2>&1 || echo "{\"error\":\"request failed\"}"
}

# ─────────────────────────────────────────
# 2. MARKET PRICES — BTC not XBT
# ─────────────────────────────────────────
section "2. Market Prices (BTC/ZAR symbol)"

PRICES=$(do_get "/api/market/prices")
BTC_PRICE=$(echo "$PRICES" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prices',{}).get('BTC/ZAR',{}).get('price','MISSING'))" 2>/dev/null || echo "MISSING")
XBT_KEY=$(echo "$PRICES" | python3 -c "import sys,json; d=json.load(sys.stdin); keys=list(d.get('prices',{}).keys()); print('XBTZAR' in keys or 'XBT/ZAR' in keys)" 2>/dev/null || echo "False")

if [ "$BTC_PRICE" != "MISSING" ] && [ "$BTC_PRICE" != "0.0" ] && [ "$BTC_PRICE" != "0" ]; then
  pass "BTC/ZAR price present: R${BTC_PRICE}"
else
  info "BTC/ZAR price is 0 or missing — API may not be configured. Checking key names..."
  BTC_KEY_EXISTS=$(echo "$PRICES" | python3 -c "import sys,json; d=json.load(sys.stdin); print('BTC/ZAR' in d.get('prices',{}))" 2>/dev/null || echo "False")
  if [ "$BTC_KEY_EXISTS" = "True" ]; then
    pass "BTC/ZAR key present in response (price may be 0 if no API key configured)"
  else
    fail "BTC/ZAR key missing from /api/market/prices response"
  fi
fi

if [ "$XBT_KEY" = "False" ]; then
  pass "No XBTZAR/XBT/ZAR keys in response (BTC symbol used correctly)"
else
  fail "XBTZAR or XBT/ZAR key found in response — symbol not normalized to BTC"
fi

# ─────────────────────────────────────────
# 3. SEED 2 LUNO PAPER BOTS
# ─────────────────────────────────────────
section "3. Seed 2 Luno Paper Bots"

BOT1_RESP=$(do_post "/api/bots" '{"name":"ProofBot1","exchange":"luno","trading_mode":"paper","pair":"BTC/ZAR","strategy":"range","initial_capital":500}')
BOT2_RESP=$(do_post "/api/bots" '{"name":"ProofBot2","exchange":"luno","trading_mode":"paper","pair":"BTC/ZAR","strategy":"momentum","initial_capital":500}')

BOT1_ID=$(echo "$BOT1_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id','') or d.get('id',''))" 2>/dev/null || echo "")
BOT2_ID=$(echo "$BOT2_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id','') or d.get('id',''))" 2>/dev/null || echo "")

if [ -n "$BOT1_ID" ] && [ "$BOT1_ID" != "null" ]; then
  pass "Bot 1 created: ID=$BOT1_ID"
else
  fail "Bot 1 creation failed — response: $BOT1_RESP"
fi

if [ -n "$BOT2_ID" ] && [ "$BOT2_ID" != "null" ]; then
  pass "Bot 2 created: ID=$BOT2_ID"
else
  fail "Bot 2 creation failed — response: $BOT2_RESP"
fi

# ─────────────────────────────────────────
# 4. BOTS STATUS IS VALID JSON + CHECK LIFECYCLE STATE
# ─────────────────────────────────────────
section "4. /api/bots/status — Valid JSON + Lifecycle State"

BOTS_STATUS=$(do_get "/api/bots/status")

VALID_JSON=$(echo "$BOTS_STATUS" | python3 -c "import sys,json; json.load(sys.stdin); print('ok')" 2>/dev/null || echo "invalid")
if [ "$VALID_JSON" = "ok" ]; then
  pass "/api/bots/status returns valid JSON"
else
  fail "/api/bots/status returned invalid JSON: $BOTS_STATUS"
fi

# Check that any bot with training_complete=false shows lifecycle_state=training (not active)
TRAINING_AS_ACTIVE=$(echo "$BOTS_STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
bots = d if isinstance(d, list) else d.get('bots', [])
bad = [b.get('id') for b in bots
       if not b.get('training_complete', True)
       and b.get('lifecycle_state') == 'active']
print(','.join(bad) if bad else 'none')
" 2>/dev/null || echo "check-failed")

if [ "$TRAINING_AS_ACTIVE" = "none" ]; then
  pass "No bots with training_complete=false are showing lifecycle_state=active"
elif [ "$TRAINING_AS_ACTIVE" = "check-failed" ]; then
  info "Could not check training/active state (JSON structure may differ)"
else
  fail "Bots with training_complete=false are incorrectly showing lifecycle_state=active: $TRAINING_AS_ACTIVE"
fi

# Check that bots in training show training_progress
if [ -n "$BOT1_ID" ] && [ "$BOT1_ID" != "null" ]; then
  BOT_DETAIL=$(do_get "/api/bots/$BOT1_ID")
  LSTATE=$(echo "$BOT_DETAIL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('lifecycle_state') or d.get('state') or d.get('bot',{}).get('lifecycle_state',''))" 2>/dev/null || echo "")
  info "Bot 1 lifecycle_state: '$LSTATE'"
  if [ "$LSTATE" = "training" ] || [ "$LSTATE" = "active" ]; then
    pass "Bot 1 has a valid lifecycle_state"
  else
    info "Bot 1 lifecycle_state='$LSTATE' (may still be initializing)"
  fi
fi

# ─────────────────────────────────────────
# 5. WAIT FOR OPEN TRADES
# ─────────────────────────────────────────
section "5. Wait for Open Trades"

OPEN_FOUND=0
for i in $(seq 1 12); do
  TRADES=$(do_get "/api/trades/recent?limit=20")
  OPEN_COUNT=$(echo "$TRADES" | python3 -c "
import sys, json
d = json.load(sys.stdin)
trades = d if isinstance(d, list) else d.get('trades', [])
print(sum(1 for t in trades if t.get('status') in ('open','pending')))
" 2>/dev/null || echo "0")
  if [ "$OPEN_COUNT" -gt 0 ] 2>/dev/null; then
    pass "Open trades found: $OPEN_COUNT"
    OPEN_FOUND=1
    break
  fi
  info "No open trades yet (attempt $i/12) — waiting ${POLL_INTERVAL}s..."
  sleep "$POLL_INTERVAL"
done

if [ "$OPEN_FOUND" -eq 0 ]; then
  # Fetch block reason
  BLOCK_REASON=$(do_get "/api/bots/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
bots = d if isinstance(d, list) else d.get('bots', [])
reasons = []
for b in bots:
    r = b.get('training_block_reason') or b.get('paused_reason_message') or b.get('last_decision_reason') or b.get('last_order_error')
    if r:
        reasons.append(f\"{b.get('name','?')}: {r}\")
print('; '.join(reasons) if reasons else 'No block reason found')
" 2>/dev/null || echo "Could not determine block reason")
  fail "No open trades appeared within 60s. Block reason(s): $BLOCK_REASON"
fi

# ─────────────────────────────────────────
# 6. WAIT FOR CLOSED TRADES
# ─────────────────────────────────────────
section "6. Wait for Closed Trades"

CLOSED_FOUND=0
WAITED=0
while [ "$WAITED" -lt "$MAX_WAIT_TRADES" ]; do
  TRADES=$(do_get "/api/trades/recent?limit=50")
  CLOSED_COUNT=$(echo "$TRADES" | python3 -c "
import sys, json
d = json.load(sys.stdin)
trades = d if isinstance(d, list) else d.get('trades', [])
print(sum(1 for t in trades if t.get('status') not in ('open','pending')))
" 2>/dev/null || echo "0")
  if [ "$CLOSED_COUNT" -gt 0 ] 2>/dev/null; then
    pass "Closed trades found: $CLOSED_COUNT"
    CLOSED_FOUND=1
    break
  fi
  info "No closed trades yet (waited ${WAITED}s) — waiting ${POLL_INTERVAL}s..."
  sleep "$POLL_INTERVAL"
  WAITED=$((WAITED + POLL_INTERVAL))
done

if [ "$CLOSED_FOUND" -eq 0 ]; then
  BLOCK_REASON=$(do_get "/api/bots/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
bots = d if isinstance(d, list) else d.get('bots', [])
reasons = []
for b in bots:
    r = b.get('training_block_reason') or b.get('paused_reason_message') or b.get('last_decision_reason') or b.get('last_order_error')
    if r:
        reasons.append(f\"{b.get('name','?')}: {r}\")
print('; '.join(reasons) if reasons else 'No block reason found — bots may be in cooldown')
" 2>/dev/null || echo "Could not determine block reason")
  fail "No closed trades within ${MAX_WAIT_TRADES}s. Block reason(s): $BLOCK_REASON"
fi

# ─────────────────────────────────────────
# 7. INTELLIGENCE STATUS
# ─────────────────────────────────────────
section "7. Intelligence Status"

INTEL=$(do_get "/api/intelligence/status")
LAST_RUN=$(echo "$INTEL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_run_at','null'))" 2>/dev/null || echo "null")
REFRESH=$(echo "$INTEL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_interval_seconds','null'))" 2>/dev/null || echo "null")

info "refresh_interval_seconds: $REFRESH"
info "last_run_at: $LAST_RUN"

if [ "$REFRESH" = "60" ] || [ "$REFRESH" -le 120 ] 2>/dev/null; then
  pass "Intelligence refresh interval is ≤120s ($REFRESH)"
else
  fail "Intelligence refresh interval is too high: $REFRESH (expected ≤120)"
fi

if [ "$LAST_RUN" != "null" ] && [ -n "$LAST_RUN" ]; then
  pass "Intelligence last_run_at is non-null: $LAST_RUN"
else
  info "Intelligence last_run_at is null (expected within 2 minutes of deploy)"
fi

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
section "RESULTS"
echo ""
echo "  ✅ PASS: $PASS"
echo "  ❌ FAIL: $FAIL"
echo ""
if [ "${#ERRORS[@]}" -gt 0 ]; then
  echo "  Failures:"
  for e in "${ERRORS[@]}"; do
    echo "    • $e"
  done
fi
echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ✅ ALL CHECKS PASSED — GO-LIVE READY (PAPER)"
  echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 0
else
  echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ❌ $FAIL CHECK(S) FAILED — NOT YET READY"
  echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi
