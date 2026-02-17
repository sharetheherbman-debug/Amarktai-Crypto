#!/bin/bash
# Frontend API Call Inventory Script
# Finds all API calls in frontend code
# Usage: ./frontend/scripts/find_api_calls.sh

echo "=================================="
echo "FRONTEND API CALLS INVENTORY"
echo "=================================="
echo ""

cd "$(dirname "$0")/.." || exit 1

echo "Searching for fetch/axios calls in src/..."
echo ""

# Find all API endpoint patterns
grep -r -h -o -E "(fetch|axios)\(['\"](/api/[^'\"]+)['\"]" src/ 2>/dev/null \
  | sed -E 's/.*(\/api\/[^'"'"'"]+).*/\1/' \
  | sort -u \
  | while read -r endpoint; do
      count=$(grep -r -c "$endpoint" src/ 2>/dev/null | awk -F: '$2>0' | wc -l)
      printf "%-60s (used in %2d files)\n" "$endpoint" "$count"
  done

echo ""
echo "=================================="

# Also check for apiClient calls
echo ""
echo "API Client method calls:"
grep -r -h -o -E "apiClient\.(get|post|put|delete|patch)\(['\"](/api/[^'\"]+)['\"]" src/ 2>/dev/null \
  | sed -E 's/apiClient\.(get|post|put|delete|patch)\(['"'"'"](.+)['"'"'"]\)/\1 \2/' \
  | sort -u

echo ""
echo "=================================="
