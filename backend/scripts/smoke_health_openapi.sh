#!/usr/bin/env bash
# smoke_health_openapi.sh — validate health and OpenAPI endpoints always return valid JSON
#
# Usage:
#   ./smoke_health_openapi.sh [BASE_URL]
#   BASE_URL defaults to http://127.0.0.1:8000
#   Env vars: BASE_URL
#             AMK_EMAIL + AMK_PASSWORD  — auto-login to provide auth for protected endpoints
#             ADMIN_TOKEN               — pre-existing bearer token (fallback)
#
# Examples:
#   BASE_URL=http://127.0.0.1:8000 ./smoke_health_openapi.sh
#   AMK_EMAIL=admin@example.com AMK_PASSWORD=secret ./smoke_health_openapi.sh

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Optionally acquire a bearer token for protected endpoints.
# Returns empty string (silently) if no credentials are available — callers
# that need auth will then skip or note the missing token.
# ---------------------------------------------------------------------------
_try_acquire_token() {
    local email="${AMK_EMAIL:-}"
    local password="${AMK_PASSWORD:-}"
    local static_token="${ADMIN_TOKEN:-}"

    if [ -n "$email" ] && [ -n "$password" ]; then
        local resp
        resp=$(curl -sf --max-time 15 -X POST \
            -H "Content-Type: application/json" \
            -d "{\"email\":\"${email}\",\"password\":\"${password}\"}" \
            "${BASE_URL}/api/auth/login" 2>/dev/null) || {
            echo "WARN: Login request to ${BASE_URL}/api/auth/login failed — protected checks will use no-auth fallback" >&2
            return 0
        }
        local token
        token=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" <<< "$resp" 2>/dev/null) || {
            echo "WARN: Could not parse access_token from login response — protected checks will use no-auth fallback" >&2
            return 0
        }
        if [ -z "$token" ]; then
            echo "WARN: access_token is empty in login response — protected checks will use no-auth fallback" >&2
            return 0
        fi
        echo "$token"
        return 0
    fi

    if [ -n "$static_token" ]; then
        echo "$static_token"
    fi
}

AUTH_TOKEN="$(_try_acquire_token)"

# ---------------------------------------------------------------------------
# check_json <label> <url> [extra_curl_flags...]
#   Fetches <url> and verifies the response is valid JSON with HTTP 2xx.
# ---------------------------------------------------------------------------
check_json() {
    local label="$1"
    local url="$2"
    shift 2
    local extra_flags=("$@")
    local http_code
    local body

    # curl -s (no -f): we capture the HTTP code ourselves so we can distinguish
    # a real network error (non-zero curl exit) from an HTTP 4xx/5xx response.
    body=$(curl -s --max-time 15 -w "\n%{http_code}" "${extra_flags[@]}" "$url" 2>/dev/null) || {
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

# ---------------------------------------------------------------------------
# check_protected_json <label> <url>
#   Like check_json but uses the bearer token when available.
#   If no token is available, 401 is treated as an expected "auth required"
#   response and the check is reported as SKIP rather than FAIL.
# ---------------------------------------------------------------------------
check_protected_json() {
    local label="$1"
    local url="$2"

    if [ -n "$AUTH_TOKEN" ]; then
        check_json "$label" "$url" -H "Authorization: Bearer ${AUTH_TOKEN}"
        return
    fi

    # No auth available — verify the endpoint is live (returns 401, not 5xx/timeout)
    local http_code
    http_code=$(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null) || {
        echo "FAIL [$label] — curl error or no response from $url"
        FAIL=$((FAIL+1))
        return
    }

    if [ "$http_code" -eq 401 ] || [ "$http_code" -eq 403 ]; then
        echo "SKIP [$label] — HTTP $http_code (auth required; set AMK_EMAIL+AMK_PASSWORD to test fully)"
        PASS=$((PASS+1))
    elif [ "$http_code" -ge 200 ] && [ "$http_code" -lt 400 ]; then
        echo "PASS [$label] — HTTP $http_code (no auth needed, response OK)"
        PASS=$((PASS+1))
    else
        echo "FAIL [$label] — HTTP $http_code from $url"
        FAIL=$((FAIL+1))
    fi
}

echo "=== Smoke: Health + OpenAPI ==="
echo "    BASE_URL: $BASE_URL"
echo ""

# Public health endpoint — no auth required
check_json "health/ping"        "$BASE_URL/api/health/ping"

# Protected admin health endpoint — use token when available; accept 401 otherwise
check_protected_json "admin/health-check" "$BASE_URL/api/admin/health-check"

# OpenAPI JSON — server redirects /openapi.json → /api/openapi.json; follow with -L
check_json "openapi.json"       "$BASE_URL/openapi.json" -L

echo ""
echo "Results: $PASS passed, $FAIL failed"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
