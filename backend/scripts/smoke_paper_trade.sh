#!/usr/bin/env bash
# smoke_paper_trade.sh — confirm paper trading produces trades OR clear skip_reasons
#
# Usage:
#   ./smoke_paper_trade.sh [BASE_URL] [ADMIN_TOKEN]
#   Env vars: BASE_URL, ADMIN_TOKEN
#
# On VPS:
#   BASE_URL=http://localhost:8000 ADMIN_TOKEN=<token> ./smoke_paper_trade.sh

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
ADMIN_TOKEN="${2:-${ADMIN_TOKEN:-}}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

if [ -z "$ADMIN_TOKEN" ]; then
    echo "ERROR: ADMIN_TOKEN must be set (env or second argument)"
    exit 2
fi

AUTH_HEADER="Authorization: Bearer $ADMIN_TOKEN"

echo "=== Smoke: Paper Trading ==="
echo "    BASE_URL   : $BASE_URL"
echo "    Timeout    : ${WAIT_SECONDS}s"
echo ""

get_json() {
    curl -sf --max-time 15 -H "$AUTH_HEADER" "$1" 2>/dev/null || echo "{}"
}

# 1. Confirm system is in paper mode
echo "[1] Checking system trading mode..."
mode_json=$(get_json "$BASE_URL/api/system/mode" 2>/dev/null || get_json "$BASE_URL/api/admin/system-status")
mode=$(python3 -c "
import sys, json
try:
    d = json.loads('''$mode_json''')
    live = d.get('liveTrading', d.get('live_trading', False))
    print('live' if live else 'paper')
except:
    print('unknown')
" 2>/dev/null || echo "unknown")
echo "    System mode: $mode"

# 2. Get an active paper bot
bots_json=$(get_json "$BASE_URL/api/admin/bots")
bot_id=$(python3 - <<'EOF'
import sys, json
raw = open('/dev/stdin').read()
try:
    data = json.loads(raw)
    bots = data if isinstance(data, list) else data.get('bots', data.get('data', []))
    for b in bots:
        bmode = b.get('trading_mode') or b.get('mode', 'paper')
        if str(bmode).lower().startswith('paper') and b.get('status') == 'active':
            print(b['id'])
            sys.exit(0)
except Exception as e:
    pass
EOF
<<< "$bots_json")

if [ -z "$bot_id" ]; then
    echo "SKIP — no active paper bot found"
    exit 0
fi

echo "[2] Target paper bot_id: $bot_id"

# 3. Capture baseline trade count
bot_json=$(get_json "$BASE_URL/api/admin/bots/$bot_id")
baseline_count=$(python3 -c "
import sys, json
try:
    d = json.loads('''$bot_json''')
    print(int(d.get('trades_count', 0)))
except:
    print(0)
" 2>/dev/null || echo "0")
echo "[3] Baseline trades_count: $baseline_count"

# 4. Wait up to WAIT_SECONDS for at least 1 new trade OR a deterministic skip_reason
echo "[4] Waiting up to ${WAIT_SECONDS}s for trade or deterministic skip_reason..."
deadline=$((SECONDS + WAIT_SECONDS))
success=false
final_error=""
final_trades_count="$baseline_count"

while [ $SECONDS -lt $deadline ]; do
    sleep 10
    bot_json=$(get_json "$BASE_URL/api/admin/bots/$bot_id")
    current_count=$(python3 -c "
import sys, json
try:
    d = json.loads('''$bot_json''')
    print(int(d.get('trades_count', 0)))
except:
    print(0)
" 2>/dev/null || echo "0")
    last_error=$(python3 -c "
import sys, json
try:
    d = json.loads('''$bot_json''')
    print(d.get('last_order_error') or '')
except:
    print('')
" 2>/dev/null || echo "")

    final_trades_count="$current_count"
    final_error="$last_error"

    if [ "$current_count" -gt "$baseline_count" ]; then
        echo "    PASS — new trade detected! trades_count went from $baseline_count to $current_count"
        success=true
        break
    fi

    if [ -n "$last_error" ] && [ "$last_error" != "No trade result" ] && [ "$last_error" != "null" ] && [ "$last_error" != "None" ]; then
        echo "    PASS — deterministic skip_reason: $last_error"
        success=true
        break
    fi

    elapsed=$((SECONDS - (deadline - WAIT_SECONDS)))
    echo "    ${elapsed}s — trades_count=$current_count, last_error='$last_error'"
done

echo ""
echo "Final state:"
echo "  trades_count  : $final_trades_count (baseline was $baseline_count)"
echo "  last_order_error: $final_error"

if $success; then
    echo ""
    echo "=== Paper trade smoke test PASSED ==="
    exit 0
fi

# Check for the problematic "No trade result" generic error
if [ "$final_error" = "No trade result" ] || [ -z "$final_error" ]; then
    echo "FAIL — no trades and last_order_error is generic ('$final_error') after ${WAIT_SECONDS}s"
    exit 1
else
    echo "WARN — no new trades but last_order_error is '$final_error' — may be a legitimate block"
    exit 0
fi
