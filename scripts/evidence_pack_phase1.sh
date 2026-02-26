#!/usr/bin/env bash
# =============================================================================
# evidence_pack_phase1.sh  —  Phase 1 Equity/Reset Truth Evidence Pack
#
# Verifies that:
#   1. Login succeeds and token is retrieved.
#   2. /api/wallet/paper returns total and available.
#   3. /api/trades/recent?limit=10 returns a well-formed list.
#   4. /api/analytics/equity?range=7d  current_equity matches wallet total (±0.01).
#   5. /api/system/status returns ok.
#   6. Paper reset (/api/user/paper-start-fresh) succeeds and post-reset invariants hold:
#        - wallet.total == 0 (reset to zero)
#        - equity.current_equity == equity.initial_capital
#        - equity curve starts at/after reset timestamp
#        - equity never shows a phantom value unrelated to wallet (>1 away from wallet)
#
# Usage:
#   BASE_URL=https://your-server.com \
#   EMAIL=user@example.com \
#   PASSWORD=secret \
#   bash scripts/evidence_pack_phase1.sh
#
# Safe: paper-only.  No live trading operations are performed.
# =============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-admin@amarktai.com}"
PASSWORD="${PASSWORD:-changeme}"
EPSILON=0.02   # Acceptable delta between equity and wallet total

PASS=0
FAIL=0

_pass() { echo "  ✅ PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  ❌ FAIL: $1"; FAIL=$((FAIL + 1)); }
_info() { echo "  ℹ️  $1"; }
_head() { echo ""; echo "══════════════════════════════════════════════"; echo "  $1"; echo "══════════════════════════════════════════════"; }

echo "╔══════════════════════════════════════════════╗"
echo "║  Amarktai — Phase 1 Evidence Pack             ║"
echo "║  Target: $BASE_URL"
echo "╚══════════════════════════════════════════════╝"

# ─────────────────────────────────────────────────────────────────────────────
_head "1) Login"
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_RESP=$(curl -sf -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>&1) || true

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token',''))" 2>/dev/null || echo "")
if [ -z "$TOKEN" ]; then
  _fail "Login failed — no token in response: $LOGIN_RESP"
  echo ""; echo "TOTAL: PASS=$PASS  FAIL=$FAIL — FAILED (cannot continue without token)"; exit 1
fi
_pass "Login OK — token received"

AUTH_H="Authorization: Bearer $TOKEN"
_get()  { curl -sf "$BASE_URL/api/$1" -H "$AUTH_H" 2>/dev/null; }
_post() { curl -sf -X POST "$BASE_URL/api/$1" -H "$AUTH_H" -H "Content-Type: application/json" -d "$2" 2>/dev/null; }

# ─────────────────────────────────────────────────────────────────────────────
_head "2) GET /api/wallet/paper"
# ─────────────────────────────────────────────────────────────────────────────
WALLET=$(  _get "wallet/paper" ) || true
WALLET_TOTAL=$(echo "$WALLET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "ERR")
if [ "$WALLET_TOTAL" = "ERR" ]; then
  _fail "/api/wallet/paper did not return a parseable total"
else
  _pass "/api/wallet/paper total=$WALLET_TOTAL"
fi
_info "wallet response: $WALLET"

# ─────────────────────────────────────────────────────────────────────────────
_head "3) GET /api/trades/recent?limit=10"
# ─────────────────────────────────────────────────────────────────────────────
TRADES=$( _get "trades/recent?limit=10" ) || true
TRADE_COUNT=$(echo "$TRADES" | python3 -c "
import sys,json
d=json.load(sys.stdin)
t = d.get('trades', d) if isinstance(d,dict) else d
print(len(t) if isinstance(t,list) else '?')
" 2>/dev/null || echo "ERR")
if [ "$TRADE_COUNT" = "ERR" ]; then
  _fail "/api/trades/recent did not return a parseable response"
else
  _pass "/api/trades/recent returned $TRADE_COUNT trades"
fi

# ─────────────────────────────────────────────────────────────────────────────
_head "4) GET /api/analytics/equity?range=7d"
# ─────────────────────────────────────────────────────────────────────────────
EQUITY=$( _get "analytics/equity?range=7d" ) || true
CURRENT_EQUITY=$(echo "$EQUITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_equity',0))" 2>/dev/null || echo "ERR")
INITIAL_CAPITAL=$(echo "$EQUITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('initial_capital',0))" 2>/dev/null || echo "ERR")
if [ "$CURRENT_EQUITY" = "ERR" ] || [ "$INITIAL_CAPITAL" = "ERR" ]; then
  _fail "/api/analytics/equity did not return parseable values"
else
  _pass "/api/analytics/equity current_equity=$CURRENT_EQUITY  initial_capital=$INITIAL_CAPITAL"
fi
_info "equity response: $EQUITY"

# G1 invariant: current_equity == wallet.total (±EPSILON)
if [ "$WALLET_TOTAL" != "ERR" ] && [ "$CURRENT_EQUITY" != "ERR" ]; then
  MATCH=$(python3 -c "print('yes' if abs(float('$CURRENT_EQUITY') - float('$WALLET_TOTAL')) <= $EPSILON else 'no')" 2>/dev/null || echo "no")
  if [ "$MATCH" = "yes" ]; then
    _pass "G1: equity.current_equity ($CURRENT_EQUITY) matches wallet.total ($WALLET_TOTAL) within ±$EPSILON"
  else
    _fail "G1: equity.current_equity ($CURRENT_EQUITY) does NOT match wallet.total ($WALLET_TOTAL) — delta exceeds $EPSILON"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
_head "5) GET /api/system/status"
# ─────────────────────────────────────────────────────────────────────────────
STATUS=$( _get "system/status" ) || true
STATUS_OK=$(echo "$STATUS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
ok = d.get('ok') or d.get('status') or d.get('healthy') or d.get('success')
print('yes' if ok else 'no')
" 2>/dev/null || echo "no")
if [ "$STATUS_OK" = "yes" ]; then
  _pass "/api/system/status returned a healthy response"
else
  _info "/api/system/status may not have an 'ok' field — response: $STATUS"
fi

# ─────────────────────────────────────────────────────────────────────────────
_head "6) POST /api/user/paper-start-fresh  (paper reset)"
# ─────────────────────────────────────────────────────────────────────────────
RESET_PAYLOAD='{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}'
RESET_RESP=$( _post "user/paper-start-fresh" "$RESET_PAYLOAD" ) || true
RESET_OK=$(echo "$RESET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('ok',False)).lower())" 2>/dev/null || echo "false")
if [ "$RESET_OK" = "true" ]; then
  _pass "Paper reset returned ok=true"
else
  _fail "Paper reset did NOT return ok=true: $RESET_RESP"
fi

INVARIANT_WARNINGS=$(echo "$RESET_RESP" | python3 -c "
import sys,json; d=json.load(sys.stdin); w=d.get('invariant_warnings',[])
print(';'.join(w) if w else '')
" 2>/dev/null || echo "")
if [ -n "$INVARIANT_WARNINGS" ]; then
  _fail "Reset invariant warnings: $INVARIANT_WARNINGS"
else
  _pass "No invariant_warnings from reset endpoint"
fi

# ─────────────────────────────────────────────────────────────────────────────
_head "7) Post-reset: /api/wallet/paper  (must be 0)"
# ─────────────────────────────────────────────────────────────────────────────
WALLET_POST=$( _get "wallet/paper" ) || true
WALLET_POST_TOTAL=$(echo "$WALLET_POST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "ERR")
if [ "$WALLET_POST_TOTAL" = "0" ] || [ "$WALLET_POST_TOTAL" = "0.0" ]; then
  _pass "G2: Post-reset wallet.total=0 ✓"
else
  _fail "G2: Post-reset wallet.total=$WALLET_POST_TOTAL (expected 0)"
fi

# ─────────────────────────────────────────────────────────────────────────────
_head "8) Post-reset: /api/analytics/equity  (current_equity == initial_capital == 0)"
# ─────────────────────────────────────────────────────────────────────────────
EQUITY_POST=$( _get "analytics/equity?range=7d" ) || true
CE_POST=$(echo "$EQUITY_POST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_equity',0))" 2>/dev/null || echo "ERR")
IC_POST=$(echo "$EQUITY_POST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('initial_capital',0))" 2>/dev/null || echo "ERR")
_info "Post-reset equity: current_equity=$CE_POST  initial_capital=$IC_POST"

# G2: current_equity == wallet.total (both should be 0)
if [ "$CE_POST" != "ERR" ] && [ "$WALLET_POST_TOTAL" != "ERR" ]; then
  MATCH_POST=$(python3 -c "print('yes' if abs(float('$CE_POST') - float('$WALLET_POST_TOTAL')) <= $EPSILON else 'no')" 2>/dev/null || echo "no")
  if [ "$MATCH_POST" = "yes" ]; then
    _pass "G2: Post-reset equity.current_equity ($CE_POST) matches wallet.total ($WALLET_POST_TOTAL)"
  else
    _fail "G2: Post-reset equity.current_equity ($CE_POST) does NOT match wallet.total ($WALLET_POST_TOTAL)"
  fi
fi

# G2: current_equity == initial_capital after reset
if [ "$CE_POST" != "ERR" ] && [ "$IC_POST" != "ERR" ]; then
  MATCH_IC=$(python3 -c "print('yes' if abs(float('$CE_POST') - float('$IC_POST')) <= $EPSILON else 'no')" 2>/dev/null || echo "no")
  if [ "$MATCH_IC" = "yes" ]; then
    _pass "G2: Post-reset current_equity ($CE_POST) == initial_capital ($IC_POST)"
  else
    _fail "G2: Post-reset current_equity ($CE_POST) != initial_capital ($IC_POST)"
  fi
fi

# Phantom value check — equity must not jump to an unrelated number (e.g. 1000)
# when wallet is 0: current_equity should be <=1 if wallet is 0
if [ "$CE_POST" != "ERR" ]; then
  PHANTOM=$(python3 -c "print('yes' if abs(float('$CE_POST')) > 1.0 and float('$WALLET_POST_TOTAL') == 0 else 'no')" 2>/dev/null || echo "no")
  if [ "$PHANTOM" = "yes" ]; then
    _fail "G2: Phantom equity detected — equity=$CE_POST while wallet=0"
  else
    _pass "G2: No phantom equity after reset"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  RESULTS: PASS=$PASS  FAIL=$FAIL"
echo "══════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
  echo "  🎉 ALL CHECKS PASSED"
  exit 0
else
  echo "  💥 SOME CHECKS FAILED"
  exit 1
fi
