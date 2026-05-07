#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://amarktai.online}"
EMAIL="${EMAIL:?EMAIL is required}"
PASSWORD="${PASSWORD:?PASSWORD is required}"
RESET_PASSWORD="${RESET_PASSWORD:?RESET_PASSWORD is required}"

pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; exit 1; }

json_get() {
  local json="$1"
  local expr="$2"
  python3 - "$expr" <<'PY' <<<"$json"
import json,sys
expr=sys.argv[1]
data=json.load(sys.stdin)
cur=data
for part in expr.split('.'):
    if part=='':
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if isinstance(cur, bool):
    print("true" if cur else "false")
elif cur is None:
    print("")
else:
    print(cur)
PY
}

api_call() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sS -X "$method" "${BASE_URL}${path}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -sS -X "$method" "${BASE_URL}${path}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json"
  fi
}

echo "🔐 Login"
LOGIN_BODY=$(curl -sS -X POST "${BASE_URL}/api/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")
TOKEN=$(json_get "$LOGIN_BODY" "access_token")
[[ -n "$TOKEN" ]] || fail "login failed: token missing"
pass "login ok"

echo "📡 Verify frontend-used routes"
for path in \
  "/api/wallet/platform" \
  "/api/wallet/platform/summary" \
  "/api/wallet/paper" \
  "/api/radar/snapshot" \
  "/api/dashboard/snapshot" \
  "/api/overview/snapshot" \
  "/api/diagnostics/paper-trading-readiness" \
  "/api/diagnostics/live-trading-readiness" \
  "/api/diagnostics/trading-logic-version" \
  "/api/diagnostics/paper-execution-proof" \
  "/api/diagnostics/learning-last-run" \
  "/api/bots/status" \
  "/api/bots" \
  "/api/trades/recent?limit=20"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}${path}")
  [[ "$code" == "200" ]] || fail "route failed ${path} (HTTP ${code})"
done
pass "all required routes return 200"

echo "🧪 Reset validate"
VALIDATE_BODY=$(api_call POST "/api/system/paper-reset/validate" "{\"password\":\"${RESET_PASSWORD}\",\"resetPassword\":\"${RESET_PASSWORD}\",\"reset_password\":\"${RESET_PASSWORD}\",\"confirmation\":\"${RESET_PASSWORD}\",\"confirmation_phrase\":\"${RESET_PASSWORD}\",\"confirm\":\"${RESET_PASSWORD}\"}")
[[ "$(json_get "$VALIDATE_BODY" "valid")" == "true" ]] || fail "paper-reset validate failed: $VALIDATE_BODY"
pass "paper-reset validate ok"

echo "♻️ Reset execute"
RESET_BODY=$(api_call POST "/api/system/paper-reset" "{\"password\":\"${RESET_PASSWORD}\",\"resetPassword\":\"${RESET_PASSWORD}\",\"reset_password\":\"${RESET_PASSWORD}\",\"confirmation\":\"${RESET_PASSWORD}\",\"confirmation_phrase\":\"${RESET_PASSWORD}\",\"confirm\":\"${RESET_PASSWORD}\"}")
[[ "$(json_get "$RESET_BODY" "success")" == "true" ]] || fail "paper-reset failed: $RESET_BODY"
[[ "$(json_get "$RESET_BODY" "wallet_reset")" == "true" ]] || fail "wallet_reset=false"
[[ "$(json_get "$RESET_BODY" "remaining_paper_bots")" == "0" ]] || fail "remaining paper bots not zero"
[[ "$(json_get "$RESET_BODY" "remaining_paper_fills")" == "0" ]] || fail "remaining paper fills not zero"
BALANCE=$(json_get "$RESET_BODY" "paper_balance")
python3 - <<PY
import sys
bal=float("${BALANCE}" or 0)
sys.exit(0 if bal >= 30000 else 1)
PY
[[ $? -eq 0 ]] || fail "paper balance after reset is below 30000 (${BALANCE})"
pass "reset execute proof ok"

echo "💰 Wallet/platform truth"
PLATFORM_BODY=$(api_call GET "/api/wallet/platform")
SUMMARY_BODY=$(api_call GET "/api/wallet/platform/summary")
[[ "$(json_get "$PLATFORM_BODY" "success")" == "true" ]] || fail "wallet/platform failed"
[[ "$(json_get "$SUMMARY_BODY" "success")" == "true" ]] || fail "wallet/platform/summary failed"
[[ "$(json_get "$PLATFORM_BODY" "connectedExchangesCount")" == "$(json_get "$SUMMARY_BODY" "connectedExchangesCount")" ]] || fail "platform and summary connected counts differ"
[[ "$(json_get "$PLATFORM_BODY" "validApiKeysCount")" == "$(json_get "$SUMMARY_BODY" "validApiKeysCount")" ]] || fail "platform and summary validApiKeysCount differ"
pass "wallet/platform and summary truth consistent"

echo "📊 Diagnostics checks"
PAPER_READY=$(api_call GET "/api/diagnostics/paper-trading-readiness")
LOGIC_VER=$(api_call GET "/api/diagnostics/trading-logic-version")
EXEC_PROOF=$(api_call GET "/api/diagnostics/paper-execution-proof")
LEARNING=$(api_call GET "/api/diagnostics/learning-last-run")
LIVE_READY=$(api_call GET "/api/diagnostics/live-trading-readiness")
[[ "$(json_get "$LOGIC_VER" "live_enabled")" == "false" ]] || fail "live_enabled must remain false"
[[ -n "$(json_get "$LEARNING" "enabled")" ]] || fail "learning diagnostics missing enabled"
[[ -n "$(json_get "$EXEC_PROOF" "scheduler_running")" ]] || fail "execution proof missing scheduler_running"
[[ -n "$(json_get "$PAPER_READY" "status")" ]] || fail "paper readiness missing status"
[[ "$(json_get "$LIVE_READY" "status")" == "FAIL" || "$(json_get "$LIVE_READY" "checks.enable_live_trading")" == "false" ]] || fail "live readiness must remain blocked/fail while live disabled"
pass "diagnostics endpoints return expected contract fields"

echo "🤖 Seed fresh paper bots"
SEED_BODY=$(api_call POST "/api/bots/seed-paper" "{}")
[[ "$(json_get "$SEED_BODY" "success")" == "true" ]] || fail "seed-paper failed: $SEED_BODY"
created=$(json_get "$SEED_BODY" "created")
python3 - <<PY
import sys
sys.exit(0 if int(float("${created}" or 0)) >= 0 else 1)
PY
[[ $? -eq 0 ]] || fail "seed-paper created invalid value"
pass "seed-paper endpoint reachable"

echo "🔎 Post-seed consistency"
BOTS_STATUS=$(api_call GET "/api/bots/status")
TRADES_RECENT=$(api_call GET "/api/trades/recent?limit=20")
DASH=$(api_call GET "/api/dashboard/snapshot")
RADAR=$(api_call GET "/api/radar/snapshot")
WALLET=$(api_call GET "/api/wallet/paper")
[[ -n "$(json_get "$BOTS_STATUS" "bots")" ]] || fail "bots/status missing bots"
[[ -n "$(json_get "$DASH" "bots_summary.active")" ]] || fail "dashboard snapshot missing bots summary"
[[ -n "$(json_get "$RADAR" "bots.active")" ]] || fail "radar snapshot missing bots"
[[ -n "$(json_get "$WALLET" "total")" ]] || fail "wallet/paper missing total"
[[ -n "$(json_get "$TRADES_RECENT" "trades")" ]] || fail "trades/recent missing trades array"
pass "dashboard/radar/wallet/bots/trades contracts are all present"

echo "🎉 Full-stack paper trial smoke passed"
