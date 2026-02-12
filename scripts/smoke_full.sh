#!/bin/bash
# ============================================================================
# Amarktai Network - Full Smoke Test
# ============================================================================
# Runs login, bot lifecycle, AI pause, learning dry-run, countdown checks.
#
# Usage:
#   ./scripts/smoke_full.sh [API_URL] [INVITE_CODE]
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

API_URL="${1:-http://localhost:8000}"
INVITE_CODE="${2:-AMARKTAI2024}"
TEST_EMAIL="${EMAIL:-smoke-full-$(date +%s)@example.com}"
TEST_PASSWORD="${PASSWORD:-SmokeFull123!}"
TEST_USERNAME="smokefull$(date +%s)"
BOT_NAME="SmokeBot-$(date +%s)"

TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

print_test() { echo -e "${BLUE}[TEST]${NC} $1"; }
print_pass() { echo -e "${GREEN}[PASS]${NC} $1"; TESTS_PASSED=$((TESTS_PASSED + 1)); }
print_fail() { echo -e "${RED}[FAIL]${NC} $1"; TESTS_FAILED=$((TESTS_FAILED + 1)); FAILED_TESTS+=("$1"); }
print_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

cleanup() {
  echo ""
  echo -e "${BLUE}============================================================================${NC}"
  echo -e "${BLUE}Test Summary${NC}"
  echo -e "${BLUE}============================================================================${NC}"
  echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
  echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
  if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}❌ SMOKE TEST FAILED${NC}"
    exit 1
  else
    echo -e "${GREEN}✅ ALL SMOKE TESTS PASSED${NC}"
    exit 0
  fi
}

trap cleanup EXIT

print_test "Register test user (invite header)"
REGISTER_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Invite-Code: $INVITE_CODE" \
  -d "{
    \"username\": \"$TEST_USERNAME\",
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }" || echo '{"error": "curl_failed"}')
if echo "$REGISTER_RESPONSE" | grep -q "token\|success\|already exists"; then
  print_pass "Registration step completed"
else
  print_info "Registration skipped: $REGISTER_RESPONSE"
fi

print_test "Login"
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }" || echo '{"error": "curl_failed"}')
TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//' || echo "")
if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
  print_pass "Login succeeded"
else
  print_fail "Login failed: $LOGIN_RESPONSE"
  TOKEN=""
fi

print_test "Bots status"
if [ -n "$TOKEN" ]; then
  STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/bots/status" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$STATUS_CODE" = "200" ]; then
    print_pass "Bots status returned 200"
  else
    print_fail "Bots status failed (HTTP $STATUS_CODE)"
  fi
else
  print_fail "Skipping bots status (no token)"
fi

print_test "Create paper bot"
BOT_ID=""
if [ -n "$TOKEN" ]; then
  BOT_RESPONSE=$(curl -s -X POST "$API_URL/api/bots" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"$BOT_NAME\",
      \"exchange\": \"luno\",
      \"risk_mode\": \"safe\",
      \"trading_mode\": \"paper\",
      \"initial_capital\": 1000
    }" || echo '{"error": "curl_failed"}')
  BOT_ID=$(echo "$BOT_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"//;s/"$//' || echo "")
  if [ -n "$BOT_ID" ]; then
    print_pass "Bot created ($BOT_ID)"
  else
    print_fail "Bot creation failed: $BOT_RESPONSE"
  fi
fi

print_test "Start bot"
if [ -n "$TOKEN" ] && [ -n "$BOT_ID" ]; then
  START_RESPONSE=$(curl -s -X POST "$API_URL/api/bots/$BOT_ID/start" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" || echo '{"error": "curl_failed"}')
  if echo "$START_RESPONSE" | grep -q '"success":true\|success'; then
    print_pass "Bot start requested"
  else
    print_fail "Bot start failed: $START_RESPONSE"
  fi
fi

print_test "Confirm at least 1 trade"
if [ -n "$TOKEN" ] && [ -n "$BOT_ID" ]; then
  TRADE_FOUND=false
  for attempt in $(seq 1 12); do
    TRADES_RESPONSE=$(curl -s "$API_URL/api/trades/recent?limit=20" \
      -H "Authorization: Bearer $TOKEN" || echo '{"trades":[]}')
    if echo "$TRADES_RESPONSE" | grep -q "$BOT_ID"; then
      TRADE_FOUND=true
      break
    fi
    print_info "Waiting for trade... attempt $attempt/12"
    sleep 10
  done
  if [ "$TRADE_FOUND" = true ]; then
    print_pass "Trade detected for bot"
  else
    print_fail "No trades detected for bot within timeout"
  fi
fi

print_test "Pause bot via AI chat tool call"
if [ -n "$TOKEN" ] && [ -n "$BOT_ID" ]; then
  AI_RESPONSE=$(curl -s -X POST "$API_URL/api/ai/chat" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"content\": \"pause bot $BOT_NAME\",
      \"request_action\": true
    }" || echo '{"error": "curl_failed"}')
  if echo "$AI_RESPONSE" | grep -q '"success":true\|"action_results"'; then
    print_pass "AI pause request sent"
  else
    print_fail "AI pause failed: $AI_RESPONSE"
  fi
fi

print_test "Verify bot paused"
if [ -n "$TOKEN" ] && [ -n "$BOT_ID" ]; then
  STATUS_RESPONSE=$(curl -s "$API_URL/api/bots/status" \
    -H "Authorization: Bearer $TOKEN" || echo '{}')
  if echo "$STATUS_RESPONSE" | grep -q "$BOT_ID" && echo "$STATUS_RESPONSE" | grep -q "paused"; then
    print_pass "Bot shows paused state"
  else
    print_fail "Bot not paused: $STATUS_RESPONSE"
  fi
fi

print_test "Run learning dry-run"
if [ -n "$TOKEN" ]; then
  LEARNING_RESPONSE=$(curl -s -X POST "$API_URL/api/learning/nightly-run?dry_run=true" \
    -H "Authorization: Bearer $TOKEN" || echo '{"error": "curl_failed"}')
  if echo "$LEARNING_RESPONSE" | grep -q '"success":true'; then
    print_pass "Learning dry-run triggered"
  else
    print_fail "Learning dry-run failed: $LEARNING_RESPONSE"
  fi
fi

print_test "Countdown endpoint"
if [ -n "$TOKEN" ]; then
  COUNTDOWN_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/countdown/status" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$COUNTDOWN_CODE" = "200" ]; then
    print_pass "Countdown endpoint OK"
  else
    print_fail "Countdown endpoint failed (HTTP $COUNTDOWN_CODE)"
  fi
fi
