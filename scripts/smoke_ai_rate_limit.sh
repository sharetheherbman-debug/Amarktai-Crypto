#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
TOKEN=${AUTH_TOKEN:-}
LIMIT=${AI_RATE_LIMIT_PER_HOUR:-60}
echo "=== AI Rate Limit Test: sending $((LIMIT + 1)) requests ==="
HIT429=0
for i in $(seq 1 $((LIMIT + 1))); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"content":"ping","request_action":false}' \
    "$BASE/api/ai/chat")
  if [ "$STATUS" = "429" ]; then
    HIT429=1
    echo "Got 429 on request $i (expected)"
    break
  fi
done
if [ "$HIT429" = "1" ]; then
  echo "PASS: Rate limit correctly returned 429"
else
  echo "FAIL: Never got 429 after $((LIMIT + 1)) requests"
  exit 1
fi
