#!/usr/bin/env bash
# smoke_health_openapi.sh — validate health and OpenAPI endpoints always return valid JSON
#
# Usage:
#   ./smoke_health_openapi.sh [BASE_URL]
#   BASE_URL defaults to http://localhost:8000
#
# On VPS:
#   BASE_URL=http://localhost:8000 ./smoke_health_openapi.sh

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
PASS=0
FAIL=0

check_json() {
    local label="$1"
    local url="$2"
    local http_code
    local body

    body=$(curl -sf --max-time 15 -w "\n%{http_code}" "$url" 2>/dev/null) || {
        echo "FAIL [$label] — curl error or no response from $url"
        FAIL=$((FAIL+1))
        return
    }

    http_code=$(echo "$body" | tail -n1)
    body=$(echo "$body" | head -n -1)

    if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 400 ]; then
        echo "FAIL [$label] — HTTP $http_code from $url"
        FAIL=$((FAIL+1))
        return
    fi

    if echo "$body" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo "PASS [$label] — valid JSON (HTTP $http_code)"
        PASS=$((PASS+1))
    else
        echo "FAIL [$label] — response is NOT valid JSON (HTTP $http_code)"
        echo "  Body preview: ${body:0:200}"
        FAIL=$((FAIL+1))
    fi
}

echo "=== Smoke: Health + OpenAPI ==="
echo "    BASE_URL: $BASE_URL"
echo ""

check_json "health/ping"          "$BASE_URL/api/health/ping"
check_json "admin/health-check"   "$BASE_URL/api/admin/health-check"
check_json "openapi.json"         "$BASE_URL/openapi.json"

echo ""
echo "Results: $PASS passed, $FAIL failed"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
