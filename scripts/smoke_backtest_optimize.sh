#!/bin/bash
BASE=${BASE_URL:-http://127.0.0.1:8000}
TOKEN=${AUTH_TOKEN:-}
echo "=== Backtest Optimize Test ==="
RESULT=$(curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"parameter_ranges":{"risk_mode":["safe","balanced"],"stop_loss":[0.03,0.05],"take_profit":[0.06,0.10]},"start_date":"2024-01-01","end_date":"2024-03-01","initial_capital":1000,"optimization_metric":"total_return"}' \
  "$BASE/api/backtest/optimize")
echo "$RESULT" | python3 -m json.tool
echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('grid_search')==True, 'grid_search must be True'; print('PASS: grid_search=True, tested_combinations='+str(d.get('tested_combinations')))"
