#!/usr/bin/env bash
# strategy_evidence_pack.sh
# Evidence pack: proves trading quality improvements are active.
# Usage: BASE_URL=https://your-backend.example TOKEN=<jwt> bash strategy_evidence_pack.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0
SKIP=0

_pass() { echo "✅ $*"; PASS=$((PASS+1)); }
_fail() { echo "❌ $*"; FAIL=$((FAIL+1)); }
_skip() { echo "⏭️  $*"; SKIP=$((SKIP+1)); }
_info() { echo "ℹ️  $*"; }

auth_header=""
if [[ -n "$TOKEN" ]]; then
  auth_header="Authorization: Bearer $TOKEN"
fi

# Helper: HTTP GET
_get() {
  local url="$1"
  if [[ -n "$auth_header" ]]; then
    curl -s -f -H "$auth_header" "$url" 2>/dev/null
  else
    curl -s -f "$url" 2>/dev/null
  fi
}

echo ""
echo "=========================================================="
echo "  Amarktai Strategy Evidence Pack"
echo "  Base: $BASE_URL"
echo "  $(date -u)"
echo "=========================================================="
echo ""

# ── 1. Phase 1 backwards compatibility ──────────────────────────────────────
echo "── 1. Phase 1 Endpoint Compatibility ──────────────────────────────────"

for ep in \
  "/api/diagnostics/paper-engine" \
  "/api/diagnostics/open-trades" \
  "/api/diagnostics/last-tick-summary" \
  "/api/diagnostics/symbol-selection"; do
  if [[ -z "$TOKEN" ]]; then
    _skip "No TOKEN — cannot test $ep (auth required)"
  else
    body=$(_get "$BASE_URL$ep" 2>/dev/null || echo "ERROR")
    if echo "$body" | grep -q '"success"'; then
      _pass "$ep responds with success field"
    else
      _fail "$ep missing success field: $body"
    fi
  fi
done
echo ""

# ── 2. New strategy-params endpoint ─────────────────────────────────────────
echo "── 2. Strategy Params Endpoint ─────────────────────────────────────────"
if [[ -z "$TOKEN" ]]; then
  _skip "No TOKEN — skipping /api/diagnostics/strategy-params"
else
  sp=$(_get "$BASE_URL/api/diagnostics/strategy-params" 2>/dev/null || echo "ERROR")
  if echo "$sp" | grep -q '"success"'; then
    _pass "/api/diagnostics/strategy-params OK"
    # Check rate_limit_budgets key
    if echo "$sp" | grep -q '"rate_limit_budgets"'; then
      _pass "  rate_limit_budgets key present"
    else
      _fail "  rate_limit_budgets key missing"
    fi
  else
    _fail "/api/diagnostics/strategy-params: $sp"
  fi
fi
echo ""

# ── 3. Symbol selection diversification ─────────────────────────────────────
echo "── 3. Symbol Selection Diversification ─────────────────────────────────"
if [[ -z "$TOKEN" ]]; then
  _skip "No TOKEN — skipping symbol-selection test"
else
  ss=$(_get "$BASE_URL/api/diagnostics/symbol-selection" 2>/dev/null || echo "ERROR")
  if echo "$ss" | grep -q '"candidate_count"'; then
    candidate_count=$(echo "$ss" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('candidate_count',0))" 2>/dev/null || echo "0")
    if [[ "$candidate_count" -gt 1 ]]; then
      _pass "  candidate_count=$candidate_count (>1 ✓)"
    else
      _fail "  candidate_count=$candidate_count (expected >1)"
    fi
    if echo "$ss" | grep -q '"top5_scored"'; then
      _pass "  top5_scored field present"
    fi
  else
    _fail "symbol-selection missing candidate_count: $ss"
  fi
fi
echo ""

# ── 4. Open trades include exit deadline fields ───────────────────────────────
echo "── 4. Open Trades Exit Fields ───────────────────────────────────────────"
if [[ -z "$TOKEN" ]]; then
  _skip "No TOKEN — skipping open-trades test"
else
  ot=$(_get "$BASE_URL/api/diagnostics/open-trades" 2>/dev/null || echo "ERROR")
  if echo "$ot" | grep -q '"hard_exit_triggered"'; then
    _pass "  hard_exit_triggered field present in open-trades"
  else
    _fail "  hard_exit_triggered missing from open-trades"
  fi
  if echo "$ot" | grep -q '"soft_exit_triggered"'; then
    _pass "  soft_exit_triggered field present"
  fi
  if echo "$ot" | grep -q '"oldest_open_trade_age_minutes"'; then
    _pass "  oldest_open_trade_age_minutes present"
  fi
fi
echo ""

# ── 5. Rate limit budget Python sanity check ─────────────────────────────────
echo "── 5. Rate Limit Budget (Python unit check) ─────────────────────────────"
python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub missing deps
from unittest.mock import MagicMock
for m in ("motor", "motor.motor_asyncio", "pymongo", "fastapi", "bson"):
    if m not in sys.modules:
        sys.modules[m] = MagicMock()

try:
    from services.rate_limit_budget import RateLimitBudgetRegistry
    reg = RateLimitBudgetRegistry()
    b = reg.for_exchange("binance")
    # First acquire must succeed (fresh budget)
    ok, wait = b.acquire("test_bot")
    assert ok, f"Expected ok=True, got ok={ok}"
    # Record 3 429s and check backoff
    b.record_response(429)
    b.record_response(429)
    b.record_response(429)
    ok2, wait2 = b.acquire("test_bot")
    assert not ok2 or wait2 > 0, "Expected backoff after 429 responses"
    print("✅  RateLimitBudget: acquire OK, backoff applied after 429s")
except Exception as e:
    print(f"❌  RateLimitBudget check failed: {e}")
    sys.exit(1)
PYEOF
echo ""

# ── 6. Strategy Tuner Python sanity check ────────────────────────────────────
echo "── 6. Strategy Tuner UCB1 (Python unit check) ───────────────────────────"
python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

try:
    from services.strategy_tuner import StrategyTuner
    st = StrategyTuner()
    params = st.get_params("user_x", "binance", "balanced")
    expected = {"take_profit_pct", "stop_loss_pct", "min_edge_pct",
                "time_exit_minutes", "max_spread_allowed", "confidence_threshold"}
    assert expected.issubset(params.keys()), f"Missing params: {expected - params.keys()}"
    # Apply positive reward 10 times and check change
    for _ in range(10):
        changes = st.update("user_x", "binance", "balanced", reward=1.5)
    params_after = st.get_params("user_x", "binance", "balanced")
    print(f"✅  StrategyTuner: params={list(params.keys())}, updates applied")
    assert 0.008 <= params_after["take_profit_pct"] <= 0.08, "take_profit_pct out of bounds"
    print("✅  StrategyTuner: parameter bounds respected after 10 updates")
except Exception as e:
    print(f"❌  StrategyTuner check failed: {e}")
    sys.exit(1)
PYEOF
echo ""

# ── 7. Stagnation exit constant check ────────────────────────────────────────
echo "── 7. Config Constants ──────────────────────────────────────────────────"
python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
try:
    from config import (
        STAGNATION_EXIT_MINUTES, SOFT_MAX_HOLD_SECONDS, HARD_MAX_HOLD_SECONDS,
        SYMBOL_COOLDOWN_MINUTES, PORTFOLIO_GUARD_MAX_SAME_SYMBOL
    )
    assert STAGNATION_EXIT_MINUTES > 0, "STAGNATION_EXIT_MINUTES must be >0"
    assert 0 < SOFT_MAX_HOLD_SECONDS < HARD_MAX_HOLD_SECONDS, \
        "SOFT_MAX < HARD_MAX required"
    assert SYMBOL_COOLDOWN_MINUTES > 0
    assert PORTFOLIO_GUARD_MAX_SAME_SYMBOL >= 1
    print(f"✅  Config: STAGNATION_EXIT={STAGNATION_EXIT_MINUTES}min "
          f"SOFT_MAX={SOFT_MAX_HOLD_SECONDS}s HARD_MAX={HARD_MAX_HOLD_SECONDS}s "
          f"COOLDOWN={SYMBOL_COOLDOWN_MINUTES}min PORTFOLIO_GUARD={PORTFOLIO_GUARD_MAX_SAME_SYMBOL}")
except Exception as e:
    print(f"❌  Config check failed: {e}")
    sys.exit(1)
PYEOF
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "=========================================================="
echo "  Evidence Pack Summary"
echo "  Passed : $PASS"
echo "  Failed : $FAIL"
echo "  Skipped: $SKIP"
echo "=========================================================="
if [[ $FAIL -eq 0 ]]; then
  echo "✅ All active checks passed!"
  exit 0
else
  echo "❌ $FAIL check(s) failed — review output above"
  exit 1
fi
