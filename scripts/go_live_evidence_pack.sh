#!/usr/bin/env bash
# =============================================================================
# GO-LIVE EVIDENCE PACK — Amarktai Network
# Validates all critical go-live endpoints and exits nonzero if any blocker remains.
# Usage: BASE_URL=http://localhost:8000 TOKEN=<jwt> bash scripts/go_live_evidence_pack.sh
#   OR:  BASE_URL=http://localhost:8000 AMK_EMAIL=admin@example.com AMK_PASSWORD=secret bash scripts/go_live_evidence_pack.sh
# If TOKEN is not set, the script will attempt to login with AMK_EMAIL + AMK_PASSWORD.
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"
AMK_EMAIL="${AMK_EMAIL:-}"
AMK_PASSWORD="${AMK_PASSWORD:-}"

PASS=0
FAIL=0
BLOCKER=0
RESULTS=()

_TMPFILE=$(mktemp /tmp/go_live_evidence_pack.XXXXXX)
trap 'rm -f "$_TMPFILE"' EXIT

# ---------------------------------------------------------------------------
# Auto-login: obtain TOKEN from AMK_EMAIL + AMK_PASSWORD if TOKEN is missing
# ---------------------------------------------------------------------------
if [ -z "$TOKEN" ] && [ -n "$AMK_EMAIL" ] && [ -n "$AMK_PASSWORD" ]; then
  echo ""
  echo "[0] Auto-login (TOKEN not set; using AMK_EMAIL + AMK_PASSWORD)"
  _LOGIN_BODY=$(printf '{"email":"%s","password":"%s"}' "$AMK_EMAIL" "$AMK_PASSWORD")
  _LOGIN_CODE=$(curl -s -o "$_TMPFILE" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$_LOGIN_BODY" \
    "$BASE_URL/api/auth/login")
  _LOGIN_RESP=$(cat "$_TMPFILE" 2>/dev/null)
  if [ "$_LOGIN_CODE" -ge 200 ] && [ "$_LOGIN_CODE" -lt 300 ]; then
    TOKEN=$(echo "$_LOGIN_RESP" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('access_token',''))
except Exception: print('')
" 2>/dev/null)
    if [ -n "$TOKEN" ]; then
      echo "  ✅  Login successful — TOKEN obtained"
    else
      echo "  ❌  Login returned 2xx but no access_token in response"
    fi
  else
    echo "  ❌  Login failed (HTTP $_LOGIN_CODE): $(echo "$_LOGIN_RESP" | head -c 200)"
  fi
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

auth_header() {
  if [ -n "$TOKEN" ]; then
    echo "-H" "Authorization: Bearer $TOKEN"
  fi
}

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

http_post() {
  local url="$1"
  local body="${2:-{}}"
  if [ -n "$TOKEN" ]; then
    curl -s -o "$_TMPFILE" -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "$url"
  else
    curl -s -o "$_TMPFILE" -w "%{http_code}" \
      -X POST \
      -H "Content-Type: application/json" \
      -d "$body" \
      "$url"
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
    if echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    # Navigate nested keys e.g. trading_mode_flags.paper_trading
    keys = '${field}'.split('.')
    v = d
    for k in keys:
        v = v[k]
    expected = '${expected_value}'
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
      actual=$(echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    keys = '${field}'.split('.')
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

check_not_value() {
  # check that field != bad_value
  local label="$1"
  local url="$2"
  local field="$3"
  local bad_value="$4"
  local is_blocker="${5:-true}"

  local http_code resp
  http_code=$(http_get "$url")
  resp=$(cat "$_TMPFILE" 2>/dev/null)

  if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    actual=$(echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    keys = '${field}'.split('.')
    v = d
    for k in keys:
        v = v.get(k, '<missing>') if isinstance(v, dict) else '<missing>'
    print(v)
except: print('<parse error>')
" 2>/dev/null)
    if [ "$actual" != "${bad_value}" ]; then
      PASS=$((PASS + 1))
      RESULTS+=("  ✅  PASS  $label  (${field}='${actual}' != '${bad_value}')")
    else
      FAIL=$((FAIL + 1))
      [ "$is_blocker" = "true" ] && BLOCKER=$((BLOCKER + 1))
      RESULTS+=("  ❌  FAIL  $label  (${field}='${actual}' must not equal '${bad_value}')")
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
echo " Token:  $([ -n "$TOKEN" ] && echo 'SET' || echo 'NOT SET — protected endpoints will 401')"
echo " Time:   $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
echo ""

# 1. Health / system
echo "[1] Health & System"
check "system health"       "$BASE_URL/api/health"         "status"
check "system status"       "$BASE_URL/api/system/status"  "feature_flags"
check "system status has trading_mode_flags" "$BASE_URL/api/system/status" "trading_mode_flags"

# 2. Learning status — BLOCKER if missing or returns non-truthy state
echo ""
echo "[2] Learning Status (A)"
check "learning/status exists (200)" "$BASE_URL/api/learning/status" "state"
check "learning/status has trades_analyzed" "$BASE_URL/api/learning/status" "trades_analyzed"
# Compound truth check (state=complete with 0 trades) is done in Test 6 below

# 3. HuggingFace status
echo ""
echo "[3] HuggingFace Status (B)"
check "hf/status exists (200)"       "$BASE_URL/api/hf/status"  "status"
check "hf/status has enabled field"  "$BASE_URL/api/hf/status"  "enabled"
check_not_value "hf/status must not return null status" "$BASE_URL/api/hf/status" "status" "null" "true"

# 4. Wallet — explicit Bearer-token checks (same auth as /api/risk/status)
echo ""
echo "[4] Wallet"
check "wallet/status (200 with Bearer)"   "$BASE_URL/api/wallet/status" "mode"  "true"
check "wallet/status has paper field"     "$BASE_URL/api/wallet/status" "paper" "true"
check "wallet/paper (200 with Bearer)"    "$BASE_URL/api/wallet/paper"  "mode"  "false"

# 5. Trading mode — paper must be enabled; uses same /api/system/mode endpoint the dashboard calls
echo ""
echo "[5] Trading Mode (C)"
# The env layer should now default paper to allowed (True at env level)
check "system/status has reasons"         "$BASE_URL/api/system/status" "reasons"      "false"
# Check paper mode is active via the real mode endpoint the dashboard uses
_mode_code=$(http_get "$BASE_URL/api/system/mode")
_mode_body=$(cat "$_TMPFILE" 2>/dev/null)
_paper_trading=$(echo "$_mode_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('paperTrading', '')).lower())
except Exception: print('')
" 2>/dev/null)
if [ "$_paper_trading" = "true" ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  ✅  PASS  system/mode: paperTrading=true (paper mode is enabled)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  system/mode: paperTrading='${_paper_trading}' (expected true for go-live paper run)")
fi

# 6. Check learning status does not claim 'optimized' with zero trades
echo ""
echo "[6] Truth Gate — no fake 'optimized' state"
_learning_resp=$(http_get "$BASE_URL/api/learning/status")
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

# 7. Enable paper+autonomous mode via canonical POST /api/system/mode
echo ""
echo "[7] Enable Paper+Autonomous Mode"
if [ -n "$TOKEN" ]; then
  _mode_set_code=$(http_post "$BASE_URL/api/system/mode" '{"paper_trading":true,"live_trading":false,"autonomous":true}')
  _mode_set_body=$(cat "$_TMPFILE" 2>/dev/null)
  _mode_set_ok=$(echo "$_mode_set_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('true' if d.get('success') and d.get('paperTrading') else 'false')
except Exception: print('false')
" 2>/dev/null)
  if [ "$_mode_set_code" -ge 200 ] && [ "$_mode_set_code" -lt 300 ] && [ "$_mode_set_ok" = "true" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  POST system/mode: paper+autonomous enabled (HTTP $_mode_set_code)")
  else
    FAIL=$((FAIL + 1))
    BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  POST system/mode: HTTP $_mode_set_code body=$(echo "$_mode_set_body" | head -c 120)")
  fi

  # Verify GET /api/system/status reflects paper mode
  _verify_code=$(http_get "$BASE_URL/api/system/status")
  _verify_body=$(cat "$_TMPFILE" 2>/dev/null)
  _paper_flag=$(echo "$_verify_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('system_modes',{}).get('paper_trading','')).lower())
except Exception: print('')
" 2>/dev/null)
  if [ "$_paper_flag" = "true" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  system/status confirms paper_trading=true after mode switch")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ⚠️  WARN  system/status paper_trading='${_paper_flag}' after POST /system/mode")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [7] Skipped mode enable — no TOKEN available")
fi

# 8. Fund paper wallet to 30000 ZAR via POST /api/wallet/paper/set-balance
echo ""
echo "[8] Fund Paper Wallet (30000 ZAR)"
if [ -n "$TOKEN" ]; then
  _fund_code=$(http_post "$BASE_URL/api/wallet/paper/set-balance" '{"balance_zar":30000}')
  _fund_body=$(cat "$_TMPFILE" 2>/dev/null)
  _fund_ok=$(echo "$_fund_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('true' if d.get('success') and float(d.get('set_to', 0)) >= 30000 else 'false')
except Exception: print('false')
" 2>/dev/null)
  if [ "$_fund_code" -ge 200 ] && [ "$_fund_code" -lt 300 ] && [ "$_fund_ok" = "true" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  POST wallet/paper/set-balance: 30000 ZAR funded (HTTP $_fund_code)")
  else
    FAIL=$((FAIL + 1))
    BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  POST wallet/paper/set-balance: HTTP $_fund_code body=$(echo "$_fund_body" | head -c 120)")
  fi

  # Verify GET /api/wallet/paper shows available >= 30000
  _wp_code=$(http_get "$BASE_URL/api/wallet/paper")
  _wp_body=$(cat "$_TMPFILE" 2>/dev/null)
  _wp_avail=$(echo "$_wp_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    v = d.get('available_wallet_zar') or d.get('total', 0)
    print(str(float(v)))
except Exception: print('0')
" 2>/dev/null)
  if python3 -c "import sys; sys.exit(0 if float('${_wp_avail:-0}') >= 30000 else 1)" 2>/dev/null; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  wallet/paper available=${_wp_avail} >= 30000 ZAR")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ⚠️  WARN  wallet/paper available=${_wp_avail} (expected >= 30000)")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [8] Skipped wallet fund — no TOKEN available")
fi

# 9. Seed 5 Luno paper bots
echo ""
echo "[9] Seed Luno Paper Bots"
if [ -n "$TOKEN" ]; then
  _seed_code=$(http_post "$BASE_URL/api/bots/seed-luno-paper" '{}')
  _seed_body=$(cat "$_TMPFILE" 2>/dev/null)
  _seed_total=$(echo "$_seed_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(int(d.get('created', 0)) + int(d.get('existing', 0)))
except Exception: print(0)
" 2>/dev/null)
  if [ "$_seed_code" -ge 200 ] && [ "$_seed_code" -lt 300 ] && [ "${_seed_total:-0}" = "5" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  POST bots/seed-luno-paper: total=${_seed_total} bots (HTTP $_seed_code)")
  else
    FAIL=$((FAIL + 1))
    BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  POST bots/seed-luno-paper: total=${_seed_total:-unknown} (HTTP $_seed_code) body=$(echo "$_seed_body" | head -c 120)")
  fi

  # Verify /api/bots/status shows 5+ luno paper bots
  _bs_code=$(http_get "$BASE_URL/api/bots/status")
  _bs_body=$(cat "$_TMPFILE" 2>/dev/null)
  _bs_count=$(echo "$_bs_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    bots = d.get('bots') or []
    paper_luno = [b for b in bots if b.get('exchange','').lower()=='luno' and b.get('trading_mode','')=='paper']
    print(len(paper_luno))
except Exception: print(0)
" 2>/dev/null)
  if python3 -c "import sys; sys.exit(0 if int('${_bs_count:-0}') >= 5 else 1)" 2>/dev/null; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  bots/status shows ${_bs_count} luno paper bots (>= 5)")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ⚠️  WARN  bots/status shows ${_bs_count} luno paper bots (expected >= 5)")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [9] Skipped seeding — no TOKEN available")
fi

# ---------------------------------------------------------------------------
# 10. FLOKx status
# ---------------------------------------------------------------------------
echo ""
echo "[10] FLOKx Status"
if [ -n "$TOKEN" ]; then
  _flokx_code=$(http_get "$BASE_URL/api/flokx/status")
  _flokx_body=$(cat "$_TMPFILE" 2>/dev/null)
  _flokx_configured=$(echo "$_flokx_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('configured', '')).lower())
except Exception: print('')
" 2>/dev/null)
  if [ "$_flokx_code" -eq 200 ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  GET flokx/status: HTTP $_flokx_code configured=${_flokx_configured}")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ❌  FAIL  GET flokx/status: HTTP $_flokx_code body=$(echo "$_flokx_body" | head -c 120)")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [10] Skipped flokx/status — no TOKEN available")
fi

# ---------------------------------------------------------------------------
# 11. HuggingFace status
# ---------------------------------------------------------------------------
echo ""
echo "[11] HuggingFace Status"
if [ -n "$TOKEN" ]; then
  _hf_code=$(http_get "$BASE_URL/api/hf/status")
  _hf_body=$(cat "$_TMPFILE" 2>/dev/null)
  _hf_enabled=$(echo "$_hf_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('enabled', '')).lower())
except Exception: print('')
" 2>/dev/null)
  if [ "$_hf_code" -eq 200 ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  GET hf/status: HTTP $_hf_code enabled=${_hf_enabled}")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ❌  FAIL  GET hf/status: HTTP $_hf_code body=$(echo "$_hf_body" | head -c 120)")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [11] Skipped hf/status — no TOKEN available")
fi

# ---------------------------------------------------------------------------
# 12. User paper-start-fresh
# ---------------------------------------------------------------------------
echo ""
echo "[12] User Paper Start Fresh"
if [ -n "$TOKEN" ]; then
  _psf_code=$(http_post "$BASE_URL/api/user/paper-start-fresh" \
    '{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}')
  _psf_body=$(cat "$_TMPFILE" 2>/dev/null)
  _psf_ok=$(echo "$_psf_body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('ok', False)).lower())
except Exception: print('false')
" 2>/dev/null)
  if [ "$_psf_code" -ge 200 ] && [ "$_psf_code" -lt 300 ] && [ "$_psf_ok" = "true" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✅  PASS  POST user/paper-start-fresh: ok=true (HTTP $_psf_code)")
  else
    FAIL=$((FAIL + 1))
    BLOCKER=$((BLOCKER + 1))
    RESULTS+=("  ❌  FAIL  POST user/paper-start-fresh: ok=${_psf_ok} (HTTP $_psf_code) body=$(echo "$_psf_body" | head -c 120)")
  fi
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ⚠️  WARN  [12] Skipped user/paper-start-fresh — no TOKEN available")
fi
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
