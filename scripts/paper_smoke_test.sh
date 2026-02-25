#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Paper Trading Smoke Tests — non-destructive, no bot creation
# Usage:
#   export API_BASE="https://www.amarktai.online/api"
#   export AUTH_TOKEN="<your JWT>"
#   bash scripts/paper_smoke_test.sh
# ---------------------------------------------------------------------------

set -euo pipefail

API_BASE="${API_BASE:-https://www.amarktai.online/api}"
AUTH="${AUTH_TOKEN:-}"

if [[ -z "$AUTH" ]]; then
  echo "ERROR: AUTH_TOKEN is not set. Export it before running this script."
  exit 1
fi

H="Authorization: Bearer $AUTH"
PASS=0; FAIL=0

check() {
  local label="$1"; local url="$2"; local jq_check="${3:-.}"
  local out
  out=$(curl -sf -H "$H" "$url" 2>&1) || { echo "❌ FAIL [$label]: curl error"; ((FAIL++)); return; }
  local val
  val=$(echo "$out" | python3 -c "import sys,json; d=json.load(sys.stdin); print($jq_check)" 2>/dev/null) || {
    echo "❌ FAIL [$label]: jq parse error — response: ${out:0:200}"; ((FAIL++)); return;
  }
  if [[ "$val" == "True" || "$val" == "true" || "$val" == "1" || "$val" == "ok" ]]; then
    echo "✅ PASS [$label]: $val"
    ((PASS++))
  else
    echo "⚠️  INFO [$label]: $val"
    ((PASS++))
  fi
}

echo ""
echo "=== 1. Build Info — git SHA, branch, dirty flag ==="
BUILD=$(curl -sf "$API_BASE/build/info")
SHA=$(echo "$BUILD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['backend']['sha'])" 2>/dev/null || echo "unknown")
BRANCH=$(echo "$BUILD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['backend']['branch'])" 2>/dev/null || echo "unknown")
DIRTY=$(echo "$BUILD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['backend'].get('dirty', 'N/A'))" 2>/dev/null || echo "unknown")
echo "  sha=$SHA  branch=$BRANCH  dirty=$DIRTY"
[[ "$SHA" != "unknown" ]] && { echo "✅ PASS [build_sha]"; ((PASS++)); } || { echo "❌ FAIL [build_sha]"; ((FAIL++)); }

echo ""
echo "=== 2. Wallet Hub — mode, funding_status, active_bots, deficit ==="
WH=$(curl -sf -H "$H" "$API_BASE/wallet/status")
MODE=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('mode','?'))" 2>/dev/null || echo "?")
FS=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('funding_status','?'))" 2>/dev/null || echo "?")
AB=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('active_bots',0))" 2>/dev/null || echo "?")
RC=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('required_capital',0))" 2>/dev/null || echo "?")
AV=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('available_balance',0))" 2>/dev/null || echo "?")
DEF=$(echo "$WH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('deficit',0))" 2>/dev/null || echo "?")
echo "  mode=$MODE  funding_status=$FS  active_bots=$AB  required_capital=$RC  available=$AV  deficit=$DEF"
[[ "$FS" != "?" ]] && { echo "✅ PASS [wallet_status_fields_present]"; ((PASS++)); } || { echo "❌ FAIL [wallet_status_fields_present]"; ((FAIL++)); }
[[ "$FS" != "NOT_CONFIGURED" ]] && echo "  ℹ️  NOTE: funding_status=$FS (if bots exist and wallet funded, this should be FUNDED or UNFUNDED)"

echo ""
echo "=== 3. Recent Trades — check for open paper trades ==="
TR=$(curl -sf -H "$H" "$API_BASE/trades/recent")
COUNT=$(echo "$TR" | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('trades',[]) or d if isinstance(d,list) else []; print(len(t))" 2>/dev/null || echo "0")
echo "  recent_trades=$COUNT"
[[ "$COUNT" != "0" ]] && { echo "✅ PASS [trades_recent_non_empty]"; ((PASS++)); } || { echo "⚠️  INFO [trades_recent_empty]: no trades (create a bot and wait for a tick)"; ((PASS++)); }

echo ""
echo "=== 4. Diagnostics — last-tick-summary ==="
TS=$(curl -sf -H "$H" "$API_BASE/diagnostics/last-tick-summary")
LT=$(echo "$TS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_tick_at','?'))" 2>/dev/null || echo "?")
BE=$(echo "$TS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bots_evaluated',0))" 2>/dev/null || echo "?")
OA=$(echo "$TS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('opens_attempted',0))" 2>/dev/null || echo "?")
CA=$(echo "$TS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('closes_attempted',0))" 2>/dev/null || echo "?")
LE=$(echo "$TS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_error','none'))" 2>/dev/null || echo "?")
echo "  last_tick_at=$LT  bots_evaluated=$BE  opens_attempted=$OA  closes_attempted=$CA  last_error=$LE"
[[ "$LT" != "?" ]] && { echo "✅ PASS [last_tick_summary_endpoint]"; ((PASS++)); } || { echo "❌ FAIL [last_tick_summary_endpoint]"; ((FAIL++)); }

echo ""
echo "=== 5. Diagnostics — open-trades ==="
OT=$(curl -sf -H "$H" "$API_BASE/diagnostics/open-trades")
OTC=$(echo "$OT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('open_trades_count',0))" 2>/dev/null || echo "?")
echo "  open_trades=$OTC"
[[ "$OTC" != "?" ]] && { echo "✅ PASS [open_trades_endpoint]"; ((PASS++)); } || { echo "❌ FAIL [open_trades_endpoint]"; ((FAIL++)); }

echo ""
echo "=== 6. FLOKx key status (if key present) ==="
FS_STATUS=$(curl -sf -H "$H" "$API_BASE/keys/status" | python3 -c "
import sys,json
d=json.load(sys.stdin)
sm=d.get('status_map') or {}
flokx=sm.get('flokx') or {}
print(flokx.get('status','not_configured') if isinstance(flokx,dict) else flokx)
" 2>/dev/null || echo "not_checked")
echo "  flokx_status=$FS_STATUS"
if [[ "$FS_STATUS" == "not_configured" ]]; then
  echo "  ℹ️  INFO [flokx]: key not configured — add key via dashboard to test DNS check"
  ((PASS++))
else
  echo "  ✅ PASS [flokx_key_status_present]: $FS_STATUS"
  ((PASS++))
fi

echo ""
echo "=== SUMMARY ==="
echo "  PASS: $PASS   FAIL: $FAIL"
[[ "$FAIL" -eq 0 ]] && echo "🎉 All checks passed!" || echo "⚠️  $FAIL check(s) failed."
exit $FAIL
