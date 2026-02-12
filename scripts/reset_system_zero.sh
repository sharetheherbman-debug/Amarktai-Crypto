#!/usr/bin/env bash
# Admin reset script - wipes all collections except users + API keys.
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
ADMIN_TOKEN="${2:-${ADMIN_TOKEN:-}}"

if [ -z "$ADMIN_TOKEN" ]; then
  echo "Usage: $0 <BASE_URL> <ADMIN_TOKEN>" >&2
  echo "Example: $0 http://127.0.0.1:8000 <jwt>" >&2
  echo "Or set ADMIN_TOKEN environment variable." >&2
  exit 1
fi

echo "🔁 Resetting system at ${BASE_URL} (users + API keys preserved)..."

curl -sS -X POST "${BASE_URL}/api/admin/reset-system" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}' | jq .
