#!/usr/bin/env bash
# =============================================================================
# verify_truth.sh — Prove all bot-count/wallet endpoints agree on a live server
#
# Usage:
#   TOKEN="<your JWT>" ./scripts/verify_truth.sh [BASE_URL]
#
# Default BASE_URL: http://localhost:8000
# =============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
AUTH_HEADER="Authorization: Bearer ${TOKEN:?Please export TOKEN=<jwt>}"

echo "=== Amarktai Truth Consistency Check ==="
echo "    Server : $BASE_URL"
echo ""

echo "→ Fetching /api/bots/status ..."
BOTS_STATUS=$(curl -sf -H "$AUTH_HEADER" "$BASE_URL/api/bots/status")
BOTS_ACTIVE=$(echo "$BOTS_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active_bots',0))")

echo "→ Fetching /api/diagnostics/paper-status ..."
PAPER_STATUS=$(curl -sf -H "$AUTH_HEADER" "$BASE_URL/api/diagnostics/paper-status")
PAPER_ACTIVE=$(echo "$PAPER_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active_bots',0))")

echo "→ Fetching /api/overview/snapshot ..."
SNAPSHOT=$(curl -sf -H "$AUTH_HEADER" "$BASE_URL/api/overview/snapshot")
SNAP_ACTIVE=$(echo "$SNAPSHOT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('activeBots',0))")

echo "→ Fetching /api/wallet/paper ..."
WALLET=$(curl -sf -H "$AUTH_HEADER" "$BASE_URL/api/wallet/paper")
WALLET_FUNDED=$(echo "$WALLET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('funded_status','?'))")
WALLET_STATUS=$(echo "$WALLET"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))")
WALLET_TOTAL=$(echo "$WALLET"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))")

echo ""
echo "=== RESULTS ==="
echo "  /api/bots/status              active_bots  = $BOTS_ACTIVE"
echo "  /api/diagnostics/paper-status active_bots  = $PAPER_ACTIVE"
echo "  /api/overview/snapshot        activeBots   = $SNAP_ACTIVE"
echo ""
echo "  /api/wallet/paper             total        = $WALLET_TOTAL"
echo "                                funded_status= $WALLET_FUNDED"
echo "                                status       = $WALLET_STATUS"
echo ""

PASS=true

if [ "$BOTS_ACTIVE" != "$PAPER_ACTIVE" ]; then
    echo "❌ MISMATCH: bots/status($BOTS_ACTIVE) ≠ paper-status($PAPER_ACTIVE)"
    PASS=false
fi

if [ "$BOTS_ACTIVE" != "$SNAP_ACTIVE" ]; then
    echo "❌ MISMATCH: bots/status($BOTS_ACTIVE) ≠ overview/snapshot($SNAP_ACTIVE)"
    PASS=false
fi

if [ "$WALLET_FUNDED" != "$WALLET_STATUS" ]; then
    echo "❌ WALLET CONTRADICTION: funded_status=$WALLET_FUNDED ≠ status=$WALLET_STATUS"
    PASS=false
fi

if [ "$PASS" = true ]; then
    echo "✅ All counts agree. No wallet contradictions."
else
    echo ""
    echo "Run /api/diagnostics/truth for a full canonical snapshot."
    exit 1
fi
