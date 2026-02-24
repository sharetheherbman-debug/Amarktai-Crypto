#!/usr/bin/env bash
# =============================================================================
# GO-LIVE EVIDENCE PACK — Amarktai Network
# Validates all critical go-live endpoints and exits nonzero if any blocker remains.
# Usage: BASE_URL=http://localhost:8000 TOKEN=<jwt> bash scripts/go_live_evidence_pack.sh
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0
BLOCKER=0
RESULTS=()

_TMPFILE=$(mktemp /tmp/go_live_evidence_pack.XXXXXX)
trap 'rm -f "$_TMPFILE"' EXIT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

check() {
  local label="$1"
  local url="$2"
  local expected_field="${3:-}"
  local is_blocker="${4:-true}"

  local http_code resp
  http_code=$(http_get "$url")
  resp=$(cat "$_TMPFILE" 2>/dev/null)

  if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    if [ -n "$expected_field" ]; then
      if echo "$resp" | grep -q "\"${expected_field}\""; then
        PASS=$((PASS + 1))
        RESULTS+=("  ✅  PASS  $label")
      else
        FAIL=$((FAIL + 1))
        [ "$is_blocker" = "true" ] && BLOCKER=$((BLOCKER + 1))
        RESULTS+=("  ❌  FAIL  $label  (HTTP $http_code but missing field '${expected_field}')")
        RESULTS+=("           Body: $(echo "$resp" | head -c 300)")
      fi
    else
      PASS=$((PASS + 1))
      RESULTS+=("  ✅  PASS  $label")
    fi
  else
    FAIL=$((FAIL + 1))
    [ "$is_blocker" = "true" ] && BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  $label  (HTTP $http_code)")
    RESULTS+=("           Body: $(echo "$resp" | head -c 300)")
  fi
}

check_field_value() {
  # check that field == expected_value
  local label="$1"
  local url="$2"
  local field="$3"
  local expected_value="$4"
  local is_blocker="${5:-true}"

  local http_code resp
  http_code=$(http_get "$url")
  resp=$(cat "$_TMPFILE" 2>/dev/null)

  if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    if echo "$resp" | FIELD="$field" EXPECTED="$expected_value" python3 -c "
import sys, json, os
try:
    d = json.load(sys.stdin)
    # Navigate nested keys e.g. trading_mode_flags.paper_trading
    keys = os.environ['FIELD'].split('.')
    v = d
    for k in keys:
        v = v[k]
    expected = os.environ['EXPECTED']
    # Handle booleans
    if expected.lower() == 'true': expected = True
    elif expected.lower() == 'false': expected = False
    sys.exit(0 if str(v) == str(expected) or v == expected else 1)
except Exception as e:
    sys.stderr.write(str(e)+'\n')
    sys.exit(1)
" 2>/dev/null; then
      PASS=$((PASS + 1))
      RESULTS+=("  ✅  PASS  $label  (${field}=${expected_value})")
    else
      FAIL=$((FAIL + 1))
      [ "$is_blocker" = "true" ] && BLOCKER=$((BLOCKER + 1))
      actual=$(echo "$resp" | FIELD="$field" python3 -c "
import sys, json, os
try:
    d = json.load(sys.stdin)
    keys = os.environ['FIELD'].split('.')
    v = d
    for k in keys:
        v = v.get(k, '<missing>') if isinstance(v, dict) else '<missing>'
    print(v)
except: print('<parse error>')
" 2>/dev/null)
      RESULTS+=("  ❌  FAIL  $label  (${field} expected='${expected_value}' actual='${actual}')")
    fi
  else
    FAIL=$((FAIL + 1))
    [ "$is_blocker" = "true" ] && BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  $label  (HTTP $http_code)")
  fi
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " AMARKTAI GO-LIVE EVIDENCE PACK"
echo " Target: $BASE_URL"
echo " Time:   $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
echo ""

# 1. Health / system
echo "[1] Health & System"
check "system health"       "$BASE_URL/api/health"         "status"
check "system status"       "$BASE_URL/api/system/status"  "feature_flags"
check "system status has trading_mode_flags" "$BASE_URL/api/system/status" "trading_mode_flags"

# 2. Learning status — BLOCKER if missing
echo ""
echo "[2] Learning Status (A)"
check "learning/status exists (200)" "$BASE_URL/api/learning/status" "state"
check "learning/status has trades_analyzed" "$BASE_URL/api/learning/status" "trades_analyzed"

# Compound truth check: state=complete with 0 trades is a blocker
_learning_resp=$(http_get "$BASE_URL/api/learning/status"; cat "$_TMPFILE" 2>/dev/null)
_learning_body=$(cat "$_TMPFILE" 2>/dev/null)
_trades=$(echo "$_learning_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(int(d.get('trades_analyzed', 0)))
except: print(0)
" 2>/dev/null)
_state=$(echo "$_learning_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('state',''))
except: print('')
" 2>/dev/null)

if [ "$_trades" = "0" ] && [ "$_state" = "complete" ]; then
  FAIL=$((FAIL + 1))
  BLOCKER=$((BLOCKER + 1))
  RESULTS+=("  ❌  FAIL  Truth gate: state=complete but trades_analyzed=0 (must not claim optimized)")
else
  PASS=$((PASS + 1))
  RESULTS+=("  ✅  PASS  Truth gate: state='${_state}' with trades_analyzed=${_trades} (truthful)")
fi

# 3. HuggingFace status
echo ""
echo "[3] HuggingFace Status (B)"
check "hf/status exists (200)"       "$BASE_URL/api/hf/status"  "status"
check "hf/status has enabled field"  "$BASE_URL/api/hf/status"  "enabled"

# 4. Wallet
echo ""
echo "[4] Wallet"
check "wallet/status exists (200)"   "$BASE_URL/api/wallet/status" "status" "false"

# 5. Trading mode — paper must be enable-able
echo ""
echo "[5] Trading Mode (C)"
check "system/status has reasons"    "$BASE_URL/api/system/status" "reasons" "false"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------"
echo " RESULTS"
echo "------------------------------------------------------------"
for r in "${RESULTS[@]}"; do
  echo "$r"
done
echo ""
echo "------------------------------------------------------------"
echo "  PASS: $PASS   FAIL: $FAIL   BLOCKERS: $BLOCKER"
echo "------------------------------------------------------------"
echo ""

if [ "$BLOCKER" -gt 0 ]; then
  echo "❌  GO-LIVE BLOCKED: $BLOCKER blocker(s) must be resolved."
  exit 1
elif [ "$FAIL" -gt 0 ]; then
  echo "⚠️   Non-blocking failures: $FAIL. Review before go-live."
  exit 0
else
  echo "✅  ALL CHECKS PASSED — go-live evidence pack complete."
  exit 0
fi
