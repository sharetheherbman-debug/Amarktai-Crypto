#!/usr/bin/env bash
# =============================================================================
# GO-LIVE TRUTH PACK — Amarktai Network
# Hits every critical endpoint and prints a PASS/FAIL summary.
# Usage: BASE_URL=http://localhost:8000 TOKEN=<jwt> bash scripts/go_live_truth_pack.sh
# =============================================================================

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0
RESULTS=()

# Create a unique temp file to avoid races in concurrent executions
_TMPFILE=$(mktemp /tmp/go_live_truth_pack.XXXXXX)
trap 'rm -f "$_TMPFILE"' EXIT

check() {
  local label="$1"
  local url="$2"
  local expected_field="${3:-}"

  local http_code
  local body

  if [ -n "$TOKEN" ]; then
    body=$(curl -s -o "$_TMPFILE" -w "%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      "$url")
  else
    body=$(curl -s -o "$_TMPFILE" -w "%{http_code}" "$url")
  fi

  http_code="$body"
  resp=$(cat "$_TMPFILE" 2>/dev/null)

  if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    if [ -n "$expected_field" ]; then
      if echo "$resp" | grep -q "\"$expected_field\""; then
        PASS=$((PASS + 1))
        RESULTS+=("  ✅  PASS  $label")
      else
        FAIL=$((FAIL + 1))
        RESULTS+=("  ❌  FAIL  $label  (HTTP $http_code but missing field '$expected_field')")
      fi
    else
      PASS=$((PASS + 1))
      RESULTS+=("  ✅  PASS  $label")
    fi
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ❌  FAIL  $label  (HTTP $http_code)")
  fi
}

echo ""
echo "============================================================"
echo "  AMARKTAI NETWORK — GO-LIVE TRUTH PACK"
echo "  BASE_URL: $BASE_URL"
echo "============================================================"
echo ""

check "Health ping"                  "$BASE_URL/api/health/ping"
check "Bot status"                   "$BASE_URL/api/bots/status"
check "Recent trades"                "$BASE_URL/api/trades/recent"
check "Ledger fills"                 "$BASE_URL/api/ledger/fills"
check "Paper wallet"                 "$BASE_URL/api/wallet/paper"
check "Ledger invariants"            "$BASE_URL/api/ledger/invariants/check"          "invariant_ok"
check "HuggingFace test-connection"  "$BASE_URL/api/huggingface/test-connection"
check "AI status"                    "$BASE_URL/api/ai/status"
check "Learning status"              "$BASE_URL/api/learning/status"                  "enabled"

echo "Results:"
for r in "${RESULTS[@]}"; do
  echo "$r"
done

echo ""
echo "------------------------------------------------------------"
echo "  PASS: $PASS   FAIL: $FAIL"
echo "------------------------------------------------------------"

if [ "$FAIL" -eq 0 ]; then
  echo "  ✅  ALL CHECKS PASSED — system is GO-LIVE ready"
  echo "============================================================"
  exit 0
else
  echo "  ❌  $FAIL CHECK(S) FAILED — review output above"
  echo "============================================================"
  exit 1
fi
