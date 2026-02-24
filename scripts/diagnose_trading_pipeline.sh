#!/usr/bin/env bash
# diagnose_trading_pipeline.sh — diagnose why trades are not appearing
# Usage: BASE_URL=https://your-backend TOKEN=<jwt> bash scripts/diagnose_trading_pipeline.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"

_hdr() { echo; echo "── $* ──"; }
_get() {
  curl -sf -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}$1" 2>/dev/null || echo "{}"
}
_jq() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null || echo "N/A"; }

echo "=== Trading Pipeline Diagnosis ==="
echo "Backend: ${BASE_URL}"
echo "Time:    $(date -u)"

_hdr "1. System ping"
_get /api/system/ping

_hdr "2. System gates"
GATES=$(_get /api/system/gates)
echo "$GATES" | python3 -c "
import sys, json
d = json.load(sys.stdin)
gates = d.get('gates', {})
for k, v in gates.items():
    icon = '✅' if v else '❌'
    print(f'  {icon} {k} = {v}')
print()
print('  safe_to_trade_paper:', d.get('safe_to_trade_paper'))
print('  safe_to_trade_live: ', d.get('safe_to_trade_live'))
" 2>/dev/null || echo "$GATES"

_hdr "3. Paper wallet"
WALLET=$(_get /api/wallet/paper)
echo "$WALLET" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  total          :', d.get('total', 0))
print('  available_zar  :', d.get('available_wallet_zar', 'N/A'))
print('  allocated_zar  :', d.get('allocated_funds_zar', 0))
print('  funded_status  :', d.get('funded_status', 'NOT IN RESPONSE'))
" 2>/dev/null || echo "$WALLET"

_hdr "4. Bots"
BOTS=$(_get /api/bots)
echo "$BOTS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
bots = d.get('bots', d) if isinstance(d, dict) else d
if not isinstance(bots, list): bots = []
print(f'  Total bots: {len(bots)}')
for b in bots[:10]:
    print(f'    [{b.get(\"status\",\"?\")}] {b.get(\"name\",\"?\")} ({b.get(\"exchange\",\"?\")} {b.get(\"trading_mode\",\"?\")})')
" 2>/dev/null || echo "$BOTS"

_hdr "5. Recent trades"
TRADES=$(_get /api/trades/recent)
echo "$TRADES" | python3 -c "
import sys, json
d = json.load(sys.stdin)
lst = d.get('trades', d) if isinstance(d, dict) else d
if not isinstance(lst, list): lst = []
print(f'  Recent trade count: {len(lst)}')
for t in lst[:5]:
    print(f'    [{t.get(\"status\",\"?\")}] {t.get(\"pair\",\"?\")} pnl={t.get(\"profit_loss\",\"?\")}')
" 2>/dev/null || echo "$TRADES"

_hdr "6. Learning status"
LEARN=$(_get /api/learning/status)
echo "$LEARN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  state          :', d.get('state'))
print('  trades_analyzed:', d.get('trades_analyzed', 0))
print('  enabled        :', d.get('enabled'))
print('  last_run_at    :', d.get('last_run_at'))
print('  last_error     :', d.get('last_error'))
" 2>/dev/null || echo "$LEARN"

_hdr "7. FLOKx status"
FLOKX=$(_get /api/flokx/status)
echo "$FLOKX" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  status            :', d.get('status'))
print('  dns_ok            :', d.get('dns_ok'))
print('  http_ok           :', d.get('http_ok'))
print('  reachability_error:', d.get('reachability_error'))
print('  configured        :', d.get('configured'))
" 2>/dev/null || echo "$FLOKX"

_hdr "8. Dashboard / equity summary"
DASH=$(_get /api/dashboard/overview 2>/dev/null || _get /api/dashboard 2>/dev/null || echo "{}")
echo "$DASH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k in ('equity','total_pnl','open_trades','total_trades','mode'):
    if k in d:
        print(f'  {k}: {d[k]}')
" 2>/dev/null || true

echo
echo "=== Diagnosis complete ==="
echo "If /api/trades/recent is empty:"
echo "  1. Check bots exist and are 'active' (step 4)"
echo "  2. Check paper wallet is FUNDED (step 3)"
echo "  3. Check safe_to_trade_paper=True (step 2)"
echo "  4. Check server logs for 'Paper tick' entries"
echo "  5. If bots are running but no trades: lower MIN_TRADE_INTERVAL or check pair prices"
