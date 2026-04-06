#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
TOKEN=${AUTH_TOKEN:-}
echo "=== 2FA Live Switch Test ==="
# Without totp_code → expect 403 or 400
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"luno_funded":true,"bot_ids":[]}' \
  "$BASE/api/bots/confirm-live-switch")
echo "Without totp_code: HTTP $STATUS (expect 403/400)"
if [ "$STATUS" = "403" ] || [ "$STATUS" = "400" ]; then
  echo "PASS"
else
  echo "FAIL: expected 403 or 400, got $STATUS"
  exit 1
fi
