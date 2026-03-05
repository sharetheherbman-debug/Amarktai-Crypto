#!/usr/bin/env bash
# ============================================================================
# Go-Live Evidence Pack — Automated verification for Amarktai Network
# ============================================================================
# Usage:
#   export BASE_URL=http://localhost:8000   # or https://yourdomain.com
#   export TOKEN=<admin-jwt>
#   bash scripts/go_live_evidence_pack.sh
# ============================================================================
set -euo pipefail

BASE=${BASE_URL:-http://localhost:8000}
TOKEN=${TOKEN:-${AUTH_TOKEN:-""}}
AUTH="Authorization: Bearer $TOKEN"
PASS=0
FAIL=0
SKIP=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { PASS=$((PASS+1)); printf "  ${GREEN}✅ PASS${NC}  %s\n" "$1"; }
fail() { FAIL=$((FAIL+1)); printf "  ${RED}❌ FAIL${NC}  %s\n" "$1"; }
skip() { SKIP=$((SKIP+1)); printf "  ${YELLOW}⏭  SKIP${NC}  %s\n" "$1"; }

check() {
  local desc="$1" url="$2" expect="${3:-200}"
  local code
  code=$(curl -sf -o /dev/null -w "%{http_code}" -H "$AUTH" "$url" 2>/dev/null || echo "000")
  if [ "$code" = "$expect" ]; then pass "$desc (HTTP $code)"; else fail "$desc (HTTP $code, expected $expect)"; fi
}

echo "=============================================="
echo " Amarktai Go-Live Evidence Pack"
echo " Target: $BASE"
echo "=============================================="

# 1. Health / Ping
echo ""
echo "--- 1. Health & Ping ---"
check "Public health ping" "$BASE/api/health/ping"
check "System status (auth)" "$BASE/api/system/status"

# 2. Build SHA not unknown
echo ""
echo "--- 2. Build SHA ---"
SHA=$(curl -sf -H "$AUTH" "$BASE/api/health/ping" 2>/dev/null | grep -o '"build_hash":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
if [ "$SHA" != "unknown" ] && [ -n "$SHA" ]; then pass "Build SHA: $SHA"; else fail "Build SHA is unknown"; fi

# 3. WebSocket connect
echo ""
echo "--- 3. WebSocket ---"
if command -v wscat &>/dev/null; then
  timeout 5 wscat -c "ws://${BASE#http*://}/api/ws?token=$TOKEN" --execute 'process.exit(0)' 2>/dev/null && pass "WebSocket connect" || fail "WebSocket connect"
else
  skip "WebSocket (wscat not installed)"
fi

# 4. CoinStats
echo ""
echo "--- 4. CoinStats ---"
check "CoinStats status" "$BASE/api/coinstats/status"
check "CoinStats news" "$BASE/api/coinstats/news"
check "CoinStats markets" "$BASE/api/coinstats/markets"

# 5. HuggingFace
echo ""
echo "--- 5. HuggingFace ---"
check "HuggingFace status" "$BASE/api/huggingface/status"
HF_TEST=$(curl -sf -X POST -H "$AUTH" -H "Content-Type: application/json" -d '{}' "$BASE/api/huggingface/test-connection" 2>/dev/null)
if echo "$HF_TEST" | grep -q '"connected"'; then pass "HuggingFace test-connection"; else fail "HuggingFace test-connection"; fi

# 6. List bots (normal + scalper)
echo ""
echo "--- 6. Bot Listing ---"
check "List all bots" "$BASE/api/bots"
check "Trades recent (normal)" "$BASE/api/trades/recent?bot_type=normal"
check "Trades recent (scalper)" "$BASE/api/trades/recent?bot_type=scalper"

# 7. Scalper endpoints
echo ""
echo "--- 7. Scalper ---"
check "Scalper summary" "$BASE/api/scalper/summary"
check "Scalper caps" "$BASE/api/scalper/caps"

# 8. Radar timeseries
echo ""
echo "--- 8. Bot Radar ---"
check "Radar snapshot" "$BASE/api/radar/snapshot"
check "Radar timeseries" "$BASE/api/radar/timeseries"

# 9. Ledger fills
echo ""
echo "--- 9. Ledger & Fills ---"
check "Ledger fills" "$BASE/api/ledger/fills"
check "Portfolio summary" "$BASE/api/portfolio/summary"

# 10. Paper reset
echo ""
echo "--- 10. Paper Reset ---"
RESET_RESULT=$(curl -sf -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"confirmation":"RESET_PAPER_TRADING"}' "$BASE/api/system/paper-reset" 2>/dev/null || echo "error")
if echo "$RESET_RESULT" | grep -q '"success":true\|"success": true'; then
  pass "Paper reset clears locks"
else
  fail "Paper reset: $RESET_RESULT"
fi

# 11. Risk endpoints
echo ""
echo "--- 11. Risk Management ---"
check "Daily loss lock status" "$BASE/api/risk/daily-loss-lock/status"
check "Bodyguard status" "$BASE/api/risk/bodyguard/status"

# 12. Truth Console
echo ""
echo "--- 12. Truth Console ---"
check "Truth console" "$BASE/api/admin/truth"

# 13. Build info
echo ""
echo "--- 13. Build Info ---"
check "Build info endpoint" "$BASE/api/build/info"

# Summary
echo ""
echo "=============================================="
echo " RESULTS: ${GREEN}$PASS PASS${NC} / ${RED}$FAIL FAIL${NC} / ${YELLOW}$SKIP SKIP${NC}"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}❌ EVIDENCE PACK: NOT READY${NC}"
  exit 1
else
  echo -e "${GREEN}✅ EVIDENCE PACK: GO-LIVE READY${NC}"
  exit 0
fi
