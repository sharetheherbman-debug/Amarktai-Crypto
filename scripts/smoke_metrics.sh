#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
METRICS_TOKEN=${METRICS_TOKEN:-}
echo "=== Prometheus Metrics Test ==="
if [ -n "$METRICS_TOKEN" ]; then
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $METRICS_TOKEN" \
    "$BASE/api/metrics")
  echo "With METRICS_TOKEN: HTTP $STATUS (expect 200)"
  [ "$STATUS" = "200" ] && echo "PASS" || { echo "FAIL"; exit 1; }
else
  echo "METRICS_TOKEN not set — skipping token test; JWT test only"
fi
