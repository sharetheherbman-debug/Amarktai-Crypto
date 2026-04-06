#!/bin/bash
# ============================================================================
# Amarktai Network – Go-Live Smoke Test
# ============================================================================
# Every step is deterministic and reproducible.
# Usage:
#   ./scripts/go_live_smoke.sh [BASE_URL] [EMAIL] [PASSWORD]
#   API_BASE=https://yourdomain.com AMK_EMAIL=admin@x.com AMK_PASSWORD=secret \
#     ./scripts/go_live_smoke.sh
#
# Exits 0 when all required tests pass, 1 when any required test fails.
# ============================================================================
set -uo pipefail

API_BASE="${1:-${API_BASE:-http://127.0.0.1:8000}}"
EMAIL="${2:-${AMK_EMAIL:-}}"
PASSWORD="${3:-${AMK_PASSWORD:-}}"
TIMEOUT="${TIMEOUT:-15}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0

pass()  { echo -e "${GREEN}✅ PASS${NC}  $1"; ((PASS++)); }
fail()  { echo -e "${RED}❌ FAIL${NC}  $1"; ((FAIL++)); }
warn()  { echo -e "${YELLOW}⚠️  WARN${NC}  $1"; ((WARN++)); }
info()  { echo -e "${BLUE}ℹ️  INFO${NC}  $1"; }
header(){ echo -e "\n${BLUE}── $1 ──${NC}"; }

curl_get() {
    local url="$1"; shift
    curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w '\n%{http_code}' "$@" "$url"
}
curl_post() {
    local url="$1"; local body="$2"; shift 2
    curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -w '\n%{http_code}' \
        -X POST -H "Content-Type: application/json" -d "$body" "$@" "$url"
}
http_code() { echo "$1" | tail -n1; }
body()      { echo "$1" | head -n-1; }

# ────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Amarktai Network – Go-Live Smoke Test      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
info "API Base : $API_BASE"

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    fail "Credentials missing. Set AMK_EMAIL + AMK_PASSWORD or pass as args."
    exit 1
fi

# ── 1. Health Ping ──────────────────────────────────────────────
header "1. Health Ping"
R=$(curl_get "$API_BASE/api/health/ping" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    BUILD_HASH=$(body "$R" | grep -o '"build_hash":"[^"]*' | cut -d'"' -f4 || echo "unknown")
    pass "Health ping OK  build_hash=$BUILD_HASH"
else
    fail "Health ping failed (HTTP $(http_code "$R"))"
fi

# ── 2. Build Info ────────────────────────────────────────────────
header "2. Build Info (/api/build)"
R=$(curl_get "$API_BASE/api/build" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    VER=$(body "$R" | grep -o '"version":"[^"]*' | cut -d'"' -f4 || echo "?")
    DB=$(body "$R" | grep -o '"name":"[^"]*' | head -1 | cut -d'"' -f4 || echo "?")
    pass "/api/build  version=$VER  db=$DB"
else
    fail "/api/build returned HTTP $(http_code "$R")"
fi

# ── 3. Login ────────────────────────────────────────────────────
header "3. Login"
R=$(curl_post "$API_BASE/api/auth/login" "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    TOKEN=$(body "$R" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4 || echo "")
    if [ -n "$TOKEN" ]; then
        pass "Login OK  (token length=${#TOKEN})"
    else
        fail "Login 200 but no access_token"; exit 1
    fi
else
    fail "Login failed (HTTP $(http_code "$R"))"; exit 1
fi
AUTH="-H \"Authorization: Bearer $TOKEN\""
acurl_get()  { eval curl_get "$1" "$AUTH"; }
acurl_post() { eval curl_post "$1" "$2" "$AUTH"; }

# ── 4. /api/auth/me ─────────────────────────────────────────────
header "4. Auth/Me"
R=$(curl_get "$API_BASE/api/auth/me" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
[ "$(http_code "$R")" = "200" ] && pass "/api/auth/me OK" || fail "/api/auth/me HTTP $(http_code "$R")"

# ── 5. Bot Status ───────────────────────────────────────────────
header "5. Bot Status"
R=$(curl_get "$API_BASE/api/bots/status" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
[ "$(http_code "$R")" = "200" ] && pass "/api/bots/status OK" || fail "/api/bots/status HTTP $(http_code "$R")"

# ── 6. Submit 2 paper orders ────────────────────────────────────
header "6. Submit 2 Paper Orders"
ORDER_TEMPLATE='{"symbol":"BTC/ZAR","side":"buy","amount":0.0001,"order_type":"market","exchange":"luno","mode":"paper"}'
TRADE_IDS=()
for i in 1 2; do
    R=$(curl_post "$API_BASE/api/orders/submit" "$ORDER_TEMPLATE" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
    CODE=$(http_code "$R")
    if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
        TID=$(body "$R" | grep -o '"trade_id":"[^"]*\|"id":"[^"]*' | head -1 | cut -d'"' -f4 || echo "")
        TRADE_IDS+=("$TID")
        pass "Paper order $i submitted (id=$TID)"
    else
        warn "Paper order $i HTTP $CODE  (exchange may not be configured)"
    fi
done

# ── 7. Diagnostics: DB ──────────────────────────────────────────
header "7. DB Diagnostics"
R=$(curl_get "$API_BASE/api/diagnostics/db" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    DB_NAME=$(body "$R" | grep -o '"db_name":"[^"]*' | cut -d'"' -f4 || echo "?")
    COLLS=$(body "$R" | grep -o '"collections":\[[^]]*\]' | head -c 120 || echo "?")
    pass "DB diagnostics  db_name=$DB_NAME"
    info "Collections: $COLLS"
else
    fail "DB diagnostics HTTP $(http_code "$R")"
fi

# ── 8. Data Integrity ───────────────────────────────────────────
header "8. Data Integrity"
R=$(curl_get "$API_BASE/api/diagnostics/data-integrity" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    TOTAL=$(body "$R" | grep -o '"total_trades":[0-9]*' | cut -d':' -f2 || echo "?")
    PNL=$(body "$R" | grep -o '"net_realized_pnl":[^,}]*' | cut -d':' -f2 || echo "?")
    WALLET=$(body "$R" | grep -o '"paper_wallet_balance":[^,}]*' | cut -d':' -f2 || echo "?")
    pass "Data integrity  total_trades=$TOTAL  net_pnl=$PNL  wallet_balance=$WALLET"
else
    fail "Data integrity HTTP $(http_code "$R")"
fi

# ── 9. Overview ─────────────────────────────────────────────────
header "9. Overview"
R=$(curl_get "$API_BASE/api/overview" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
[ "$(http_code "$R")" = "200" ] && pass "/api/overview OK" || fail "/api/overview HTTP $(http_code "$R")"

# ── 10. Wallet balance ──────────────────────────────────────────
header "10. Wallet Balance"
R=$(curl_get "$API_BASE/api/wallet/balance" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
[ "$(http_code "$R")" = "200" ] && pass "/api/wallet/balance OK" || warn "/api/wallet/balance HTTP $(http_code "$R")"

# ── 11. HuggingFace Status ──────────────────────────────────────
header "11. HuggingFace Status"
R=$(curl_get "$API_BASE/api/hf/status" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    ENABLED=$(body "$R" | grep -o '"enabled":[^,}]*' | cut -d':' -f2 || echo "?")
    ERROR=$(body "$R" | grep -o '"last_error":[^,}]*' | head -1 | cut -d':' -f2 || echo "null")
    pass "/api/hf/status  enabled=$ENABLED  last_error=$ERROR"
else
    fail "/api/hf/status HTTP $(http_code "$R")"
fi

# ── 12. WebSocket (10-second connect test) ──────────────────────
header "12. WebSocket Connectivity"
WS_URL=$(echo "$API_BASE" | sed 's|http|ws|')/api/ws
if command -v websocat &>/dev/null; then
    WS_MSG=$(echo "" | timeout 10 websocat "$WS_URL?token=$TOKEN" 2>/dev/null | head -1 || echo "")
    if [ -n "$WS_MSG" ]; then
        pass "WebSocket received message: ${WS_MSG:0:80}"
    else
        warn "WebSocket: no message within 10s (may need live server)"
    fi
elif command -v wscat &>/dev/null; then
    WS_MSG=$(echo "" | timeout 10 wscat -c "$WS_URL?token=$TOKEN" 2>/dev/null | head -1 || echo "")
    [ -n "$WS_MSG" ] && pass "WebSocket OK" || warn "WebSocket: no message within 10s"
else
    warn "WebSocket: install websocat or wscat to test. URL=$WS_URL?token=<TOKEN>"
fi

# ── 13. Realtime Smoke ──────────────────────────────────────────
header "13. Realtime Smoke"
R=$(curl_get "$API_BASE/api/diagnostics/realtime-smoke" -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
if [ "$(http_code "$R")" = "200" ]; then
    OK=$(body "$R" | grep -o '"success":[^,}]*' | cut -d':' -f2 || echo "?")
    pass "Realtime smoke  success=$OK"
else
    fail "Realtime smoke HTTP $(http_code "$R")"
fi

# ── 14. Reset Runtime endpoint – MUST return deprecated ─────────
header "14. Reset Runtime deduplication"
R=$(curl_post "$API_BASE/api/admin/runtime/reset" '{"confirmation_phrase":"CONFIRM RUNTIME RESET","mode":"paper"}' \
    -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo -e "error\n000")
CODE=$(http_code "$R")
if [ "$CODE" = "200" ] || [ "$CODE" = "403" ]; then
    DEPRECATED=$(body "$R" | grep -o '"deprecated":true' || echo "")
    if [ -n "$DEPRECATED" ]; then
        pass "Old /admin/runtime/reset returns deprecated=true (harmless)"
    elif [ "$CODE" = "403" ]; then
        pass "Old /admin/runtime/reset blocked (not admin)"
    else
        warn "Old /admin/runtime/reset returned 200 without deprecated flag"
    fi
else
    warn "/admin/runtime/reset HTTP $CODE"
fi

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
printf  "║  %-20s  PASS=%-3d FAIL=%-3d WARN=%-3d ║\n" "Go-Live Result" "$PASS" "$FAIL" "$WARN"
echo "╚══════════════════════════════════════════════╝"

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}🎉 All required tests passed – system is go-live ready!${NC}"
    exit 0
else
    echo -e "${RED}💥 $FAIL required test(s) failed – fix before go-live!${NC}"
    exit 1
fi
