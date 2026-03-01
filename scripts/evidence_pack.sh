#!/usr/bin/env bash
# ============================================================================
# Evidence Pack - Automated Go-Live Readiness Data Collector
# ============================================================================
# Queries all key endpoints and saves JSON + human-readable summary
# to docs/evidence/ for phase verification.
#
# Usage:
#   ./scripts/evidence_pack.sh [BASE_URL] [TOKEN]
#
# Defaults:
#   BASE_URL = http://localhost:8000
#   TOKEN    = (reads from AMARKTAI_TOKEN env var or prompts)
# ============================================================================

set -euo pipefail

BASE_URL="${1:-${AMARKTAI_BASE_URL:-http://localhost:8000}}"
TOKEN="${2:-${AMARKTAI_TOKEN:-}}"

EVIDENCE_DIR="$(cd "$(dirname "$0")/.." && pwd)/docs/evidence"
mkdir -p "$EVIDENCE_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_FILE="${EVIDENCE_DIR}/evidence_${TIMESTAMP}.json"
SUMMARY_FILE="${EVIDENCE_DIR}/evidence_${TIMESTAMP}.txt"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================================================
# Auth: get token if not provided
# ============================================================================
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}No token provided. Attempting login...${NC}"
    echo -n "Email: "; read -r EMAIL
    echo -n "Password: "; read -rs PASSWORD; echo

    LOGIN_RESP=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null || echo '{}')

    TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

    if [ -z "$TOKEN" ]; then
        echo -e "${RED}Login failed. Provide token via AMARKTAI_TOKEN env or second argument.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Login successful.${NC}"
fi

AUTH_HEADER="Authorization: Bearer ${TOKEN}"

# ============================================================================
# Helper: query endpoint and capture result
# ============================================================================
query_endpoint() {
    local name="$1"
    local path="$2"
    local url="${BASE_URL}${path}"

    echo -n "  Querying ${name} ... "

    local http_code body
    body=$(curl -s -w "\n%{http_code}" -H "$AUTH_HEADER" "$url" 2>/dev/null || echo -e "\n000")
    http_code=$(echo "$body" | tail -1)
    body=$(echo "$body" | sed '$d')

    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}${http_code} OK${NC}"
    elif [ "$http_code" = "000" ]; then
        echo -e "${RED}UNREACHABLE${NC}"
        body='{"error":"connection_refused"}'
    else
        echo -e "${YELLOW}${http_code}${NC}"
    fi

    # Output JSON fragment
    echo "\"${name}\": {\"status_code\": ${http_code}, \"body\": ${body:-null}}"
}

# ============================================================================
# Collect evidence
# ============================================================================
echo "=============================================="
echo "  Amarktai Evidence Pack Collector"
echo "  Target: ${BASE_URL}"
echo "  Time:   ${TIMESTAMP}"
echo "=============================================="

ENDPOINTS=(
    "system_status|/api/system/status"
    "system_mode|/api/system/mode"
    "bots_status|/api/bots/status"
    "wallet_paper|/api/wallet/paper"
    "diagnostics_data_integrity|/api/diagnostics/data-integrity"
    "diagnostics_paper_status|/api/diagnostics/paper-status"
    "diagnostics_realtime_status|/api/diagnostics/realtime"
    "diagnostics_go_live|/api/diagnostics/go-live"
    "risk_status|/api/risk/status"
    "circuit_breaker_status|/api/circuit-breaker/status"
    "ledger_fills|/api/ledger/fills?limit=20"
    "radar_snapshot|/api/radar/snapshot"
    "overview_snapshot|/api/overview/snapshot"
    "exchanges_status|/api/exchanges/status"
    "user_settings|/api/user/settings"
    "scalper_caps|/api/scalper/caps"
    "scalper_summary|/api/scalper/summary"
    "truth_summary|/api/admin/truth/summary"
)

echo "{" > "$REPORT_FILE"
echo "\"timestamp\": \"${TIMESTAMP}\"," >> "$REPORT_FILE"
echo "\"base_url\": \"${BASE_URL}\"," >> "$REPORT_FILE"
echo "\"endpoints\": {" >> "$REPORT_FILE"

FIRST=true
for ep in "${ENDPOINTS[@]}"; do
    IFS='|' read -r name path <<< "$ep"
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo "," >> "$REPORT_FILE"
    fi
    result=$(query_endpoint "$name" "$path")
    echo "$result" >> "$REPORT_FILE"
done

echo "}" >> "$REPORT_FILE"
echo "}" >> "$REPORT_FILE"

# ============================================================================
# Generate human-readable summary
# ============================================================================
{
    echo "=============================================="
    echo "  Evidence Pack Summary"
    echo "  Generated: ${TIMESTAMP}"
    echo "  Target: ${BASE_URL}"
    echo "=============================================="
    echo ""
    echo "Endpoint Results:"
    echo "-----------------"

    for ep in "${ENDPOINTS[@]}"; do
        IFS='|' read -r name path <<< "$ep"
        # Extract status from report
        status=$(python3 -c "
import json, sys
try:
    with open('${REPORT_FILE}') as f:
        data = json.load(f)
    code = data.get('endpoints',{}).get('${name}',{}).get('status_code', '?')
    print(f'  {code}')
except:
    print('  ?')
" 2>/dev/null || echo "  ?")
        printf "  %-35s %s\n" "$name" "$status"
    done

    echo ""
    echo "Files saved:"
    echo "  JSON: ${REPORT_FILE}"
    echo "  Text: ${SUMMARY_FILE}"
    echo ""
} | tee "$SUMMARY_FILE"

echo -e "${GREEN}Evidence pack complete.${NC}"
echo "Run: cat ${REPORT_FILE} | python3 -m json.tool"
