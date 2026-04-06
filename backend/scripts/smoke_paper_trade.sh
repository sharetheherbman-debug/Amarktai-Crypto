#!/usr/bin/env bash
# smoke_paper_trade.sh — confirm paper trading produces trades OR clear skip_reasons
#
# Usage:
#   ./smoke_paper_trade.sh [BASE_URL]
#   Env vars: BASE_URL (default http://127.0.0.1:8000)
#             ADMIN_EMAIL + ADMIN_PASS   — auto-login to obtain a bearer token (preferred)
#             AMK_EMAIL + AMK_PASSWORD   — alternate login env vars (backward compat)
#             ADMIN_TOKEN                — use a pre-existing bearer token (fallback)
#             WAIT_SECONDS               — how long to wait for trades (default 180)
#
# Examples:
#   ADMIN_EMAIL=admin@example.com ADMIN_PASS=secret ./smoke_paper_trade.sh
#   BASE_URL=http://127.0.0.1:8000 ADMIN_EMAIL=admin@example.com ADMIN_PASS=secret ./smoke_paper_trade.sh

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

# ---------------------------------------------------------------------------
# Acquire bearer token: prefer ADMIN_EMAIL/ADMIN_PASS login, fall back to
# AMK_EMAIL/AMK_PASSWORD (backward compat), then to a pre-set ADMIN_TOKEN.
# ---------------------------------------------------------------------------
_acquire_token() {
    local email="${ADMIN_EMAIL:-${AMK_EMAIL:-}}"
    local password="${ADMIN_PASS:-${AMK_PASSWORD:-}}"
    local static_token="${ADMIN_TOKEN:-}"

    if [ -n "$email" ] && [ -n "$password" ]; then
        local resp
        resp=$(curl -sf --max-time 15 -X POST \
            -H "Content-Type: application/json" \
            -d "{\"email\":\"${email}\",\"password\":\"${password}\"}" \
            "${BASE_URL}/api/auth/login" 2>/dev/null) || {
            echo "ERROR: Login request to ${BASE_URL}/api/auth/login failed" >&2
            return 1
        }
        local token
        token=$(python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" <<< "$resp" 2>/dev/null) || {
            echo "ERROR: Could not extract access_token from login response" >&2
            return 1
        }
        if [ -z "$token" ]; then
            echo "ERROR: access_token is empty in login response" >&2
            return 1
        fi
        echo "$token"
        return 0
    fi

    if [ -n "$static_token" ]; then
        echo "$static_token"
        return 0
    fi

    echo "ERROR: Set ADMIN_EMAIL+ADMIN_PASS (or AMK_EMAIL+AMK_PASSWORD) or ADMIN_TOKEN to authenticate" >&2
    return 1
}

ADMIN_TOKEN="$(_acquire_token)"
AUTH_HEADER="Authorization: Bearer ${ADMIN_TOKEN}"

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

# 2. Get an active paper bot via /api/bots/status (verified correct endpoint)
bots_json=$(get_json "$BASE_URL/api/bots/status")
bot_id=$(python3 - <<'EOF'
import sys, json
raw = open('/dev/stdin').read()
try:
    data = json.loads(raw)
    # /api/bots/status returns {"bots": [...], ...} or a list directly
    bots = data.get('bots', data) if isinstance(data, dict) else data
    if not isinstance(bots, list):
        sys.exit(0)
    for b in bots:
        bmode = b.get('trading_mode') or b.get('mode', 'paper')
        status = b.get('status', '') or b.get('state', '')
        if str(bmode).lower().startswith('paper') and status == 'active':
            print(b['id'])
            sys.exit(0)
except Exception as e:
    sys.stderr.write(f"Bot parse error: {e}\n")
EOF
<<< "$bots_json")

if [ -z "$bot_id" ]; then
    echo "FAIL — no active paper bot found via /api/bots/status (raw response below):"
    echo "$bots_json" | head -c 500
    echo ""
    echo "  => Ensure at least one active paper bot exists before running this smoke test."
    exit 1
fi

echo "[2] Target paper bot_id: $bot_id"

# 3. Capture baseline trade count
bot_json=$(get_json "$BASE_URL/api/bots/$bot_id/status" 2>/dev/null || \
           get_json "$BASE_URL/api/admin/bots/$bot_id" 2>/dev/null || echo "{}")
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
    bot_json=$(get_json "$BASE_URL/api/bots/$bot_id/status" 2>/dev/null || \
               get_json "$BASE_URL/api/admin/bots/$bot_id" 2>/dev/null || echo "{}")
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
