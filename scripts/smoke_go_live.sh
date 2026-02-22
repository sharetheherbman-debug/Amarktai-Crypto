#!/bin/bash
# smoke_go_live.sh — GO LIVE TODAY smoke test
# Run on VPS: bash scripts/smoke_go_live.sh
# Requires: curl, python3, bash 4+

set -euo pipefail

BASE=${BASE_URL:-http://127.0.0.1:8000}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@amarktai.com}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-}
PASS=0
FAIL=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "${YELLOW}WARN${NC} $1"; }

check_http() {
  local label="$1" url="$2" method="${3:-GET}" body="${4:-}" token="${5:-}"
  local args=(-s -o /tmp/go_live_body.txt -w "%{http_code}" -X "$method")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  [ -n "$body"  ] && args+=(-H "Content-Type: application/json" -d "$body")
  local status
  status=$(curl "${args[@]}" "$url")
  echo "$status"
}

echo "==============================="
echo " Amarktai GO LIVE smoke test"
echo " Base: $BASE"
echo "==============================="
echo ""

# ── 1. Health ping ──────────────────────────────────────────────────────────
echo "1) /api/health/ping"
STATUS=$(check_http "health/ping" "$BASE/api/health/ping")
if [ "$STATUS" = "200" ]; then pass "health/ping → 200"
else fail "health/ping → $STATUS (expected 200)"; fi

# ── 2. Login ────────────────────────────────────────────────────────────────
echo ""
echo "2) POST /api/auth/login"
if [ -z "$ADMIN_PASSWORD" ]; then
  warn "ADMIN_PASSWORD not set — skipping auth-dependent tests"
  TOKEN=""
else
  LOGIN_BODY="{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}"
  LOGIN_STATUS=$(check_http "login" "$BASE/api/auth/login" POST "$LOGIN_BODY")
  LOGIN_RESP=$(cat /tmp/go_live_body.txt)

  if [ "$LOGIN_STATUS" = "200" ]; then
    TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token',''))" 2>/dev/null || echo "")
    if [ -z "$TOKEN" ]; then
      fail "login returned 200 but no access_token in response"
    else
      # Print token metadata
      EXP=$(echo "$TOKEN" | python3 -c "
import sys,base64,json
parts=sys.stdin.read().strip().split('.')
if len(parts)==3:
    pad=parts[1]+'=='
    try:
        payload=json.loads(base64.urlsafe_b64decode(pad))
        print(payload.get('exp','?'))
    except:
        print('?')
else:
    print('?')
" 2>/dev/null || echo "?")
      NOW=$(date +%s)
      if [ "$EXP" != "?" ] && [ "$EXP" -gt "$NOW" ] 2>/dev/null; then
        REMAIN=$(( EXP - NOW ))
        REMAIN_HRS=$(( REMAIN / 3600 ))
        pass "login → 200 | token length=${#TOKEN} | exp=$(date -d @$EXP 2>/dev/null || date -r $EXP 2>/dev/null || echo $EXP) | remaining=${REMAIN}s (~${REMAIN_HRS}h)"
        if [ "$REMAIN" -lt 3600 ]; then
          warn "Token expires in less than 1 hour — check ACCESS_TOKEN_EXPIRE_HOURS"
        fi
      else
        pass "login → 200 | token length=${#TOKEN} | exp=$EXP (could not parse expiry)"
      fi
    fi
  else
    fail "login → $LOGIN_STATUS (expected 200)"
    TOKEN=""
  fi
fi

# ── 3. /api/auth/me ─────────────────────────────────────────────────────────
echo ""
echo "3) GET /api/auth/me"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  STATUS=$(check_http "auth/me" "$BASE/api/auth/me" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ]; then pass "auth/me → 200"
  else fail "auth/me → $STATUS (expected 200)"; fi
fi

# ── 4. /api/system/status ───────────────────────────────────────────────────
echo ""
echo "4) GET /api/system/status"
STATUS=$(check_http "system/status" "$BASE/api/system/status" GET "" "${TOKEN:-}")
if [ "$STATUS" = "200" ]; then pass "system/status → 200"
else fail "system/status → $STATUS (expected 200)"; fi

# ── 5. /api/prices/live ─────────────────────────────────────────────────────
echo ""
echo "5) GET /api/prices/live"
STATUS=$(check_http "prices/live" "$BASE/api/prices/live")
BODY=$(cat /tmp/go_live_body.txt)
if [ "$STATUS" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else (len(d.get('prices',[])) if isinstance(d,dict) else 0))" 2>/dev/null || echo "?")
  if [ "$COUNT" != "0" ] && [ "$COUNT" != "?" ]; then
    pass "prices/live → 200 | $COUNT entries"
  else
    fail "prices/live → 200 but response is empty or unreadable"
  fi
else
  fail "prices/live → $STATUS (expected 200)"
fi

# ── 6. /api/bots ────────────────────────────────────────────────────────────
echo ""
echo "6) GET /api/bots"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  STATUS=$(check_http "bots" "$BASE/api/bots" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ]; then pass "bots → 200"
  else fail "bots → $STATUS (expected 200)"; fi
fi

# ── 7. /api/bots/status ─────────────────────────────────────────────────────
echo ""
echo "7) GET /api/bots/status"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  STATUS=$(check_http "bots/status" "$BASE/api/bots/status" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ]; then pass "bots/status → 200"
  else fail "bots/status → $STATUS (expected 200)"; fi
fi

# ── 8. /api/trades/recent ───────────────────────────────────────────────────
echo ""
echo "8) GET /api/trades/recent"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  STATUS=$(check_http "trades/recent" "$BASE/api/trades/recent" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ]; then pass "trades/recent → 200"
  else fail "trades/recent → $STATUS (expected 200)"; fi
fi

# ── 9. /api/wallet/deposit-address (no keys → 400/422, keys → 200) ──────────
echo ""
echo "9) GET /api/wallet/deposit-address"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  STATUS=$(check_http "wallet/deposit-address" "$BASE/api/wallet/deposit-address?exchange=luno&currency=BTC" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ] || [ "$STATUS" = "400" ] || [ "$STATUS" = "422" ] || [ "$STATUS" = "400" ]; then
    pass "wallet/deposit-address → $STATUS (200 if keys present, 400/422 if missing — both valid)"
  elif [ "$STATUS" = "401" ]; then
    fail "wallet/deposit-address → 401 (WRONG: should be 400/422 for missing keys, not 401)"
  else
    fail "wallet/deposit-address → $STATUS (expected 200 or 400/422)"
  fi
fi

# ── 10. WebSocket smoke ──────────────────────────────────────────────────────
echo ""
echo "10) WebSocket heartbeat + prices_update (15s timeout)"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  WS_URL="ws://127.0.0.1:8000/api/ws?token=${TOKEN}"
  WS_RESULT=$(python3 - <<PYEOF 2>&1
import asyncio, sys
try:
    import websockets
except ImportError:
    print("SKIP: websockets not installed (pip install websockets)")
    sys.exit(0)

async def run():
    uri = "$WS_URL"
    got_heartbeat = False
    got_prices = False
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            for _ in range(30):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1)
                    import json
                    data = json.loads(msg)
                    t = data.get("type","")
                    if t in ("heartbeat","ping","pong"):
                        got_heartbeat = True
                    if t in ("prices_update","price","prices"):
                        got_prices = True
                    if got_heartbeat and got_prices:
                        break
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        print(f"WS_ERROR: {e}")
        return
    if got_heartbeat and got_prices:
        print("WS_OK")
    elif got_heartbeat:
        print("WS_PARTIAL: heartbeat only (no prices_update)")
    else:
        print("WS_PARTIAL: no heartbeat received")

asyncio.run(run())
PYEOF
)
  if echo "$WS_RESULT" | grep -q "^SKIP"; then
    warn "WebSocket test skipped: $WS_RESULT"
  elif echo "$WS_RESULT" | grep -q "^WS_OK"; then
    pass "WebSocket → heartbeat + prices_update received"
  elif echo "$WS_RESULT" | grep -q "^WS_PARTIAL"; then
    warn "WebSocket partial: $WS_RESULT (non-blocking)"
  else
    fail "WebSocket → $WS_RESULT"
  fi
fi

# ── 11. Session stability: call /api/auth/me again after 15s ────────────────
echo ""
echo "11) Session stability: wait 15s then re-check /api/auth/me"
if [ -z "$TOKEN" ]; then warn "Skipped (no token)"; else
  echo "    (waiting 15 seconds...)"
  sleep 15
  STATUS=$(check_http "auth/me (stability)" "$BASE/api/auth/me" GET "" "$TOKEN")
  if [ "$STATUS" = "200" ]; then pass "Session stable after 15s → /api/auth/me still 200"
  elif [ "$STATUS" = "401" ]; then
    DETAIL=$(cat /tmp/go_live_body.txt | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',''))" 2>/dev/null || echo "")
    fail "Session broken after 15s → 401 detail='$DETAIL'"
  else
    fail "Session stability → $STATUS (expected 200)"
  fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "==============================="
echo " Results: ${PASS} passed, ${FAIL} failed"
echo "==============================="
[ "$FAIL" -eq 0 ]
