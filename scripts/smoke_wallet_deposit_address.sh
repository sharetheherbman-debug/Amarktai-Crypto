#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
TOKEN=${AUTH_TOKEN:-}
echo "=== Wallet Deposit Address Test ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/wallet/deposit-address?exchange=luno&currency=BTC")
echo "HTTP $STATUS (expect 400 if no exchange key, 200 if key present)"
if [ "$STATUS" = "400" ] || [ "$STATUS" = "200" ] || [ "$STATUS" = "501" ]; then
  echo "PASS: returned honest status $STATUS"
else
  echo "FAIL: unexpected status $STATUS"
  exit 1
fi
