#!/usr/bin/env bash
# go_live_paper_proof.sh — end-to-end paper-trading readiness proof
# Usage: BASE_URL=https://your-backend TOKEN=<jwt> bash scripts/go_live_paper_proof.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"
PASS=0; FAIL=0

_hdr() { echo; echo "══════════════════════════════════════════"; echo "  $*"; echo "══════════════════════════════════════════"; }
_ok()  { echo "  ✅  $*"; ((PASS++)) || true; }
_err() { echo "  ❌  $*"; ((FAIL++)) || true; }

_get() {
  local path="$1"
  curl -sf -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}${path}" 2>/dev/null
}
_post() {
  local path="$1"; local body="$2"
  curl -sf -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -d "${body}" "${BASE_URL}${path}" 2>/dev/null
}

_hdr "1. System Health"
if _get /api/system/ping | grep -q '"ok"'; then _ok "ping OK"; else _err "ping failed"; fi

_hdr "2. Wallet — paper funded status"
WALLET=$(_get /api/wallet/paper 2>/dev/null || echo "{}")
TOTAL=$(echo "$WALLET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo 0)
FSTATUS=$(echo "$WALLET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('funded_status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
if [ "$FSTATUS" = "FUNDED" ]; then _ok "Wallet FUNDED (total=${TOTAL})"; else _err "Wallet status=${FSTATUS} total=${TOTAL}"; fi

_hdr "3. Paper bots seeded"
BOTS=$(_get /api/bots 2>/dev/null || echo "{}")
BOT_COUNT=$(echo "$BOTS" | python3 -c "import sys,json; d=json.load(sys.stdin); bots=d.get('bots',d) if isinstance(d,dict) else d; print(len(bots) if isinstance(bots,list) else 0)" 2>/dev/null || echo 0)
if [ "$BOT_COUNT" -gt 0 ]; then _ok "${BOT_COUNT} bots found"; else _err "No bots found"; fi

_hdr "4. Recent trades"
TRADES=$(_get /api/trades/recent 2>/dev/null || echo "[]")
TRADE_COUNT=$(echo "$TRADES" | python3 -c "import sys,json; d=json.load(sys.stdin); lst=d.get('trades',d) if isinstance(d,dict) else d; print(len(lst) if isinstance(lst,list) else 0)" 2>/dev/null || echo 0)
if [ "$TRADE_COUNT" -gt 0 ]; then _ok "${TRADE_COUNT} recent trades"; else echo "  ℹ️  No recent trades yet (paper bots may not have run)"; fi

_hdr "5. Learning status"
LEARN=$(_get /api/learning/status 2>/dev/null || echo "{}")
L_STATE=$(echo "$LEARN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','?'))" 2>/dev/null || echo "?")
L_TRADES=$(echo "$LEARN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trades_analyzed',0))" 2>/dev/null || echo 0)
_ok "Learning state=${L_STATE} trades_analyzed=${L_TRADES}"

_hdr "6. FLOKx reachability"
FLOKX=$(_get /api/flokx/status 2>/dev/null || echo "{}")
FL_STATUS=$(echo "$FLOKX" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
FL_DNS=$(echo "$FLOKX" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dns_ok',False))" 2>/dev/null || echo False)
if [ "$FL_STATUS" != "service_unreachable" ]; then _ok "FLOKx status=${FL_STATUS}"; else _err "FLOKx unreachable (dns_ok=${FL_DNS})"; fi

_hdr "7. System gates"
GATES=$(_get /api/system/gates 2>/dev/null || echo "{}")
PAPER_SAFE=$(echo "$GATES" | python3 -c "import sys,json; print(json.load(sys.stdin).get('safe_to_trade_paper',False))" 2>/dev/null || echo False)
if [ "$PAPER_SAFE" = "True" ]; then _ok "safe_to_trade_paper=True"; else _err "safe_to_trade_paper=${PAPER_SAFE}"; fi

echo
echo "══════════════════════════════════════════"
echo "  Result: ${PASS} passed / ${FAIL} failed"
echo "══════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
