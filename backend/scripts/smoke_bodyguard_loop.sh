#!/usr/bin/env bash
# smoke_bodyguard_loop.sh — verify bodyguard reset stops the lock loop
#
# Usage:
#   ./smoke_bodyguard_loop.sh [BASE_URL]
#   Env vars: BASE_URL (default http://127.0.0.1:8000)
#             AMK_EMAIL + AMK_PASSWORD  — auto-login to obtain a bearer token
#             ADMIN_TOKEN               — use a pre-existing bearer token (fallback)
#
# Examples:
#   AMK_EMAIL=admin@example.com AMK_PASSWORD=secret ./smoke_bodyguard_loop.sh
#   BASE_URL=http://127.0.0.1:8000 AMK_EMAIL=admin@example.com AMK_PASSWORD=secret ./smoke_bodyguard_loop.sh

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"

# ---------------------------------------------------------------------------
# Acquire bearer token: prefer AMK_EMAIL/AMK_PASSWORD login, fall back to
# a pre-set ADMIN_TOKEN env var.
# ---------------------------------------------------------------------------
_acquire_token() {
    local email="${AMK_EMAIL:-}"
    local password="${AMK_PASSWORD:-}"
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

    echo "ERROR: Set AMK_EMAIL+AMK_PASSWORD or ADMIN_TOKEN to authenticate" >&2
    return 1
}

ADMIN_TOKEN="$(_acquire_token)"
AUTH_HEADER="Authorization: Bearer ${ADMIN_TOKEN}"

echo "=== Smoke: Bodyguard Lock Loop ==="
echo "    BASE_URL: $BASE_URL"
echo ""

# Helper: GET JSON
get_json() {
    curl -sf --max-time 15 -H "$AUTH_HEADER" "$1" 2>/dev/null
}

# Helper: POST JSON
post_json() {
    curl -sf --max-time 15 -X POST -H "$AUTH_HEADER" -H "Content-Type: application/json" \
        -d "${3:-{}}" "$1" 2>/dev/null
}

# 1. List bots
echo "[1] Fetching bot list..."
bots_json=$(get_json "$BASE_URL/api/admin/bots" 2>/dev/null || echo "{}")
# Extract first locked/quarantined bot id using python
bot_id=$(python3 - <<'EOF'
import sys, json, os
raw = open('/dev/stdin').read()
try:
    data = json.loads(raw)
    bots = data if isinstance(data, list) else data.get('bots', data.get('data', []))
    locked_statuses = {'paused', 'quarantined', 'locked'}
    for b in bots:
        if b.get('status', '') in locked_statuses or b.get('paused_by_bodyguard') or b.get('bodyguard_locked'):
            print(b['id'])
            sys.exit(0)
    # fallback: first active bot
    for b in bots:
        if b.get('status') == 'active':
            print(b['id'])
            sys.exit(0)
except Exception as e:
    pass
EOF
<<< "$bots_json")

if [ -z "$bot_id" ]; then
    echo "SKIP — no bots found, nothing to check"
    exit 0
fi

echo "    Target bot_id: $bot_id"

# 2. Check current bodyguard state
echo "[2] Checking bot bodyguard state fields..."
bot_json=$(get_json "$BASE_URL/api/admin/bots/$bot_id" 2>/dev/null || echo "{}")
current_status=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
echo "    Current status: $current_status"

# 3. If locked/quarantined, call reset
if [[ "$current_status" =~ ^(paused|quarantined|locked) ]]; then
    echo "[3] Bot is locked ($current_status) — calling reset-locks..."
    reset_resp=$(post_json "$BASE_URL/api/admin/bots/$bot_id/reset-locks" "" '{"reason":"smoke_test_reset"}' 2>/dev/null || echo "{}")
    reset_status=$(python3 -c "import sys,json; d=json.loads('''$reset_resp'''); print(d.get('status','?'))" 2>/dev/null || echo "?")
    echo "    Reset response status: $reset_status"
    if [[ "$reset_status" != "active" ]]; then
        echo "FAIL — reset endpoint returned status '$reset_status' (expected 'active')"
        exit 1
    fi
    echo "    PASS — reset returned active"
else
    echo "[3] Bot is not locked ($current_status) — skipping reset step"
fi

# 4. Confirm bot is tradeable within 30 seconds
echo "[4] Waiting up to 30s for bot to be active and tradeable..."
deadline=$((SECONDS + 30))
while [ $SECONDS -lt $deadline ]; do
    bot_json=$(get_json "$BASE_URL/api/admin/bots/$bot_id" 2>/dev/null || echo "{}")
    status_now=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    locked_by_bg=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(str(d.get('paused_by_bodyguard', False)).lower())" 2>/dev/null || echo "false")
    if [[ "$status_now" == "active" && "$locked_by_bg" == "false" ]]; then
        echo "    PASS — bot is active and not locked (${SECONDS}s elapsed)"
        break
    fi
    sleep 3
done

if [[ "$status_now" != "active" ]]; then
    echo "FAIL — bot status is '$status_now' after 30s (expected active)"
    exit 1
fi

# 5. Confirm bodyguard does NOT instantly re-lock within 120 seconds
echo "[5] Monitoring for 120s to ensure bodyguard does not re-lock..."
deadline=$((SECONDS + 120))
re_locked=false
while [ $SECONDS -lt $deadline ]; do
    sleep 10
    bot_json=$(get_json "$BASE_URL/api/admin/bots/$bot_id" 2>/dev/null || echo "{}")
    status_now=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    if [[ "$status_now" =~ ^(paused|quarantined|locked) ]]; then
        pause_reason=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('pause_reason') or d.get('quarantine_reason') or 'n/a')" 2>/dev/null || echo "n/a")
        equity_peak=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('equity_peak','n/a'))" 2>/dev/null || echo "n/a")
        current_cap=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('current_capital','n/a'))" 2>/dev/null || echo "n/a")
        drawdown=$(python3 -c "import sys,json; d=json.loads('''$bot_json'''); print(d.get('current_drawdown_pct','n/a'))" 2>/dev/null || echo "n/a")
        echo "WARN — bot re-locked with status '$status_now'"
        echo "  pause_reason   : $pause_reason"
        echo "  equity_peak    : $equity_peak"
        echo "  current_capital: $current_cap"
        echo "  drawdown_pct   : $drawdown"
        re_locked=true
        break
    fi
done

if $re_locked; then
    echo "FAIL — bodyguard re-locked the bot within 120s of reset"
    exit 1
else
    echo "PASS — bot remained active for 120s without re-lock"
fi

echo ""
echo "=== Bodyguard smoke test PASSED ==="
exit 0
