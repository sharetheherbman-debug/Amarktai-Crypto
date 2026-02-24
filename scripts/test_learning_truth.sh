#!/usr/bin/env bash
# =============================================================================
# TEST LEARNING TRUTH — Amarktai Network
# Validates /api/learning/status returns truthful data (never claims 'complete'
# when trades_analyzed == 0).
# Usage: BASE_URL=http://localhost:8000 TOKEN=<jwt> bash scripts/test_learning_truth.sh
# Exit code 0 = PASS, nonzero = FAIL
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0

_TMPFILE=$(mktemp /tmp/test_learning_truth.XXXXXX)
trap 'rm -f "$_TMPFILE"' EXIT

http_get() {
  local url="$1"
  if [ -n "$TOKEN" ]; then
    curl -s -o "$_TMPFILE" -w "%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      "$url"
  else
    curl -s -o "$_TMPFILE" -w "%{http_code}" "$url"
  fi
}

echo ""
echo "============================================================"
echo " TEST: LEARNING TRUTH — $BASE_URL"
echo " Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
echo ""

# --- Test 1: endpoint returns 200 ---
echo "[1] /api/learning/status must return HTTP 200"
HTTP=$(http_get "$BASE_URL/api/learning/status")
if [ "$HTTP" -eq 200 ]; then
  PASS=$((PASS + 1))
  echo "  ✅  PASS  HTTP 200"
else
  FAIL=$((FAIL + 1))
  echo "  ❌  FAIL  HTTP ${HTTP} (expected 200)"
  echo "  Body: $(cat "$_TMPFILE" | head -c 400)"
  echo ""
  echo "FAIL: ${FAIL} test(s) failed."
  exit 1
fi

BODY=$(cat "$_TMPFILE")

# --- Test 2: response has required fields ---
echo "[2] Response must include all required fields"
REQUIRED_FIELDS="state trades_analyzed bots_evolved strategy_updates last_run_at last_error last_changes"
MISSING=""
for f in $REQUIRED_FIELDS; do
  if ! echo "$BODY" | FIELD="$f" python3 -c "import sys,json,os; d=json.load(sys.stdin); assert os.environ['FIELD'] in d" 2>/dev/null; then
    MISSING="$MISSING $f"
  fi
done
if [ -z "$MISSING" ]; then
  PASS=$((PASS + 1))
  echo "  ✅  PASS  All required fields present"
else
  FAIL=$((FAIL + 1))
  echo "  ❌  FAIL  Missing fields:$MISSING"
fi

# --- Test 3: state is a valid value ---
echo "[3] state must be one of: disabled|no_data|idle|running|complete|error|insufficient_data"
STATE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null)
VALID_STATES="disabled no_data idle running complete error insufficient_data"
STATE_OK=false
for vs in $VALID_STATES; do
  if [ "$STATE" = "$vs" ]; then
    STATE_OK=true
    break
  fi
done
if $STATE_OK; then
  PASS=$((PASS + 1))
  echo "  ✅  PASS  state='$STATE' is valid"
else
  FAIL=$((FAIL + 1))
  echo "  ❌  FAIL  state='$STATE' is not a valid state"
fi

# --- Test 4: trades_analyzed is a non-negative integer ---
echo "[4] trades_analyzed must be a non-negative integer"
TRADES=$(echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d.get('trades_analyzed', -1)
assert isinstance(t, int) and t >= 0, f'bad trades_analyzed: {t}'
print(t)
" 2>/dev/null)
if [ $? -eq 0 ]; then
  PASS=$((PASS + 1))
  echo "  ✅  PASS  trades_analyzed=$TRADES"
else
  FAIL=$((FAIL + 1))
  echo "  ❌  FAIL  trades_analyzed is not a valid non-negative int"
fi

# --- Test 5: truth gate — no 'complete' with zero trades ---
echo "[5] Truth gate: must not return state=complete when trades_analyzed=0"
echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
state = d.get('state', '')
trades = int(d.get('trades_analyzed', 0) or 0)
if trades == 0 and state == 'complete':
    print('FAIL: state=complete but trades_analyzed=0')
    sys.exit(1)
print(f'OK: state={state!r} trades_analyzed={trades}')
" 2>&1
if [ $? -eq 0 ]; then
  PASS=$((PASS + 1))
  echo "  ✅  PASS  Truth gate passed"
else
  FAIL=$((FAIL + 1))
  echo "  ❌  FAIL  Truth gate failed: state=complete with 0 trades"
fi

# --- Summary ---
echo ""
echo "------------------------------------------------------------"
echo "  PASS: $PASS   FAIL: $FAIL"
echo "------------------------------------------------------------"

if [ "$FAIL" -gt 0 ]; then
  echo "❌  $FAIL test(s) FAILED"
  exit 1
else
  echo "✅  ALL LEARNING TRUTH TESTS PASSED"
  exit 0
fi
