#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
TOKEN=${AUTH_TOKEN:-}
echo "=== Sentiment News Diagnostics ==="
curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/sentiment-news" | python3 -m json.tool
