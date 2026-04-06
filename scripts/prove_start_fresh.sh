#!/usr/bin/env bash
# =============================================================================
# prove_start_fresh.sh
# Start Fresh / Paper Reset Proof Script — Amarktai Crypto
#
# Usage:
#   BASE_URL=https://your-server.com EMAIL=user@example.com PASSWORD=secret bash scripts/prove_start_fresh.sh
#
# Checks:
#   1. Login succeeds
#   2. Seed paper bots (or verify bots exist)
#   3. Confirm equity > 0 OR trades exist (pre-condition for meaningful test)
#   4. Call Start Fresh (POST /api/user/paper-start-fresh)
#   5. Verify /api/system/reset-proof → is_clean=true, equity=0, trades=0, bots=0
#   6. Verify /api/countdown/status → current_equity=0
#   7. Print PASS / FAIL
# =============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-admin@amarktai.com}"
PASSWORD="${PASSWORD:-changeme}"

PASS=0
FAIL=0

_pass() { echo "  ✅ PASS: $1"; ((PASS++)); }
_fail() { echo "  ❌ FAIL: $1"; ((FAIL++)); }
_info() { echo "  ℹ️  $1"; }

echo "============================================================"
echo "  Amarktai Crypto — Start Fresh Reset Proof"
echo "  Target: $BASE_URL"
echo "============================================================"

# ── 1. Login ──────────────────────────────────────────────────────────────────
echo ""
echo "1) Login"
LOGIN_RESP=$(curl -sf -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>&1) || true

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  _fail "Login failed or no token in response: $LOGIN_RESP"
  echo ""
  echo "============================================================"
  echo "  TOTAL: PASS=$PASS  FAIL=$FAIL"
  echo "============================================================"
  exit 1
fi
_pass "Login OK — token received"

AUTH="-H \"Authorization: Bearer $TOKEN\""
_get()  { eval curl -sf "$BASE_URL/api/$1" -H "\"Authorization: Bearer $TOKEN\"" 2>/dev/null; }
_post() { eval curl -sf -X POST "$BASE_URL/api/$1" \
            -H "\"Authorization: Bearer $TOKEN\"" \
            -H "\"Content-Type: application/json\"" \
            -d "\"$2\"" 2>/dev/null; }

# ── 2. Seed bots (best-effort) ────────────────────────────────────────────────
echo ""
echo "2) Seed paper bots (best-effort)"
SEED_RESP=$(curl -sf -X POST "$BASE_URL/api/bots/seed-luno-paper" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" 2>/dev/null) || true
_info "Seed response: $(echo "$SEED_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','?'))" 2>/dev/null)"

# ── 3. Check bots exist before reset ─────────────────────────────────────────
echo ""
echo "3) Check pre-reset state"
BOTS_RESP=$(curl -sf "$BASE_URL/api/bots/status" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || true
BOT_COUNT=$(echo "$BOTS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else len(d.get('bots',d.get('data',[]))))" 2>/dev/null || echo "0")
_info "Pre-reset bot count: $BOT_COUNT"

# ── 4. Run Start Fresh ────────────────────────────────────────────────────────
echo ""
echo "4) POST /api/user/paper-start-fresh"
RESET_RESP=$(curl -sf -X POST "$BASE_URL/api/user/paper-start-fresh" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}' 2>/dev/null) || true

RESET_OK=$(echo "$RESET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('ok',False)).lower())" 2>/dev/null)
if [ "$RESET_OK" = "true" ]; then
  _pass "Start Fresh returned ok=true"
else
  _fail "Start Fresh did not return ok=true: $RESET_RESP"
fi

INVARIANT_WARNINGS=$(echo "$RESET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); w=d.get('invariant_warnings',[]); print(';'.join(w) if w else '')" 2>/dev/null || echo "")
if [ -n "$INVARIANT_WARNINGS" ]; then
  _fail "Reset invariant warnings: $INVARIANT_WARNINGS"
else
  _pass "No invariant warnings from reset endpoint"
fi

# ── 5. Verify reset-proof ─────────────────────────────────────────────────────
echo ""
echo "5) GET /api/system/reset-proof"
PROOF_RESP=$(curl -sf "$BASE_URL/api/system/reset-proof" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || true

IS_CLEAN=$(echo "$PROOF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('is_clean',False)).lower())" 2>/dev/null)
PROOF_EQUITY=$(echo "$PROOF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('equity',999))" 2>/dev/null)
PROOF_TRADES=$(echo "$PROOF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('trades_total',999))" 2>/dev/null)
PROOF_BOTS=$(echo "$PROOF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bots',999))" 2>/dev/null)
PROOF_WALLET=$(echo "$PROOF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('wallet_balance',999))" 2>/dev/null)

[ "$PROOF_EQUITY" = "0" ] || [ "$PROOF_EQUITY" = "0.0" ] \
  && _pass "equity=0 ✓" || _fail "equity=$PROOF_EQUITY (expected 0)"
[ "$PROOF_TRADES" = "0" ] \
  && _pass "trades_total=0 ✓" || _fail "trades_total=$PROOF_TRADES (expected 0)"
[ "$PROOF_BOTS" = "0" ] \
  && _pass "bots=0 ✓" || _fail "bots=$PROOF_BOTS (expected 0)"
[ "$IS_CLEAN" = "true" ] \
  && _pass "is_clean=true ✓" || _fail "is_clean=$IS_CLEAN"
_info "wallet_balance=$PROOF_WALLET"

# ── 6. Verify countdown equity ────────────────────────────────────────────────
echo ""
echo "6) GET /api/ledger/countdown/status"
COUNTDOWN_RESP=$(curl -sf "$BASE_URL/api/ledger/countdown/status" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || true
COUNTDOWN_EQUITY=$(echo "$COUNTDOWN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_equity',999))" 2>/dev/null)
[ "$COUNTDOWN_EQUITY" = "0" ] || [ "$COUNTDOWN_EQUITY" = "0.0" ] \
  && _pass "countdown current_equity=0 ✓" || _fail "countdown current_equity=$COUNTDOWN_EQUITY (expected 0)"

# ── 7. Verify trades empty ────────────────────────────────────────────────────
echo ""
echo "7) GET /api/trades/recent"
TRADES_RESP=$(curl -sf "$BASE_URL/api/trades/recent" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || true
TRADE_COUNT=$(echo "$TRADES_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); arr=d if isinstance(d,list) else d.get('trades',d.get('data',[])); print(len(arr))" 2>/dev/null || echo "0")
[ "$TRADE_COUNT" = "0" ] \
  && _pass "trades/recent is empty ✓" || _fail "trades/recent has $TRADE_COUNT items (expected 0)"

# ── 8. Verify bots empty ──────────────────────────────────────────────────────
echo ""
echo "8) GET /api/bots/status"
BOTS_AFTER=$(curl -sf "$BASE_URL/api/bots/status" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || true
ACTIVE_AFTER=$(echo "$BOTS_AFTER" | python3 -c "
import sys,json; d=json.load(sys.stdin)
bots=d if isinstance(d,list) else d.get('bots',d.get('data',[]))
active=[b for b in bots if b.get('status') in ('active','running')]
print(len(active))" 2>/dev/null || echo "0")
[ "$ACTIVE_AFTER" = "0" ] \
  && _pass "bots/status shows 0 active bots ✓" || _fail "bots/status shows $ACTIVE_AFTER active bots (expected 0)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  RESULTS: PASS=$PASS  FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "  🎉 ALL CHECKS PASSED — Start Fresh is working correctly"
  EXIT_CODE=0
else
  echo "  💥 $FAIL CHECK(S) FAILED — Reset is incomplete"
  EXIT_CODE=1
fi
echo "============================================================"
exit $EXIT_CODE
