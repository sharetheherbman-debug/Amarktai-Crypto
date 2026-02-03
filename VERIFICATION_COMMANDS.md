# Go-Live Blocker Sweep - Verification Commands

This document contains all curl commands to verify the fixes are working correctly.

## Prerequisites

Set your tokens:
```bash
export TOKEN="your_user_jwt_token"
export ADMIN_TOKEN="your_admin_jwt_token"
export API_BASE="http://localhost:8000"
```

## A) System Status - No Callable Error

**Test:** Verify scheduler status doesn't return error field

```bash
# Should return "running"/"stopped"/"unknown" but never error
curl -s "${API_BASE}/api/system/status" \
  -H "Authorization: Bearer $TOKEN" | jq '.scheduler_status.trading_scheduler'

# Expected output:
# {
#   "running": "stopped",  # or "running" or "unknown"
#   "enabled": false
# }
# NO "error" field should be present
```

## B) API Keys Endpoints

**Test 1:** List providers (public endpoint)
```bash
curl -s "${API_BASE}/api/keys/providers" | jq '.total'
# Expected: 10 (openai, flokx, fetchai, luno, binance, kucoin, bybit, kraken, bitget, gate)
```

**Test 2:** List user keys (requires auth)
```bash
curl -s "${API_BASE}/api/keys/list" \
  -H "Authorization: Bearer $TOKEN" | jq '.keys[] | {provider, status}'
# Expected: Array of provider statuses
```

**Test 3:** Save endpoint validation
```bash
# Missing provider - should return 422
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "${API_BASE}/api/keys/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test"}' | tail -1
# Expected: HTTP 422

# Invalid provider - should return 400
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "${API_BASE}/api/keys/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "invalid_xyz", "api_key": "test"}' | tail -1
# Expected: HTTP 400
```

**Test 4:** Test endpoint
```bash
# Invalid provider - should return 400
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "${API_BASE}/api/keys/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "invalid_xyz"}' | tail -1
# Expected: HTTP 400

# Non-existent saved key - should return 404
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "${API_BASE}/api/keys/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai"}' | tail -1
# Expected: HTTP 404 (if no openai key saved) or 200 (if saved)
```

**Test 5:** Delete endpoint
```bash
# Invalid provider - should return 400
curl -s -w "\nHTTP %{http_code}\n" \
  -X DELETE "${API_BASE}/api/keys/invalid_xyz" \
  -H "Authorization: Bearer $TOKEN" | tail -1
# Expected: HTTP 400

# Valid but non-existent - should return 200 (idempotent)
curl -s "${API_BASE}/api/keys/openai" \
  -X DELETE \
  -H "Authorization: Bearer $TOKEN" | jq '.success'
# Expected: true
```

**Run full smoke test:**
```bash
cd /home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment
TEST_TOKEN="$TOKEN" ./scripts/test_api_keys_smoke.sh
```

## C) Frontend Build Version

**Test 1:** Backend build info
```bash
curl -s "${API_BASE}/api/build/info" | jq '{version, env, built_at}'
# Expected: Git SHA, environment, build timestamp
```

**Test 2:** Frontend version (if deployed)
```bash
curl -s "http://localhost/version.json" | jq '.'
# Expected: {version, built_at, frontend: true}
```

**Test 3:** Verify in browser
- Open http://localhost/dashboard
- Scroll to footer
- Check for version badge with git SHA
- Should match backend version from /api/build/info

## D) Chat Bugs

**Test 1:** Verify chat doesn't auto-load
- Login to dashboard
- Navigate to chat section
- Should see greeting only, NOT old messages
- Should see "Load Previous Chat History" button

**Test 2:** Verify chat clears on logout
- Send a chat message
- Logout
- Login again
- Chat should show fresh greeting only

**Test 3:** Verify chat layout (manual)
- Send multiple messages to fill chat
- Input box should stay pinned at bottom
- Chat container should scroll, not the whole page

## E) Admin Panel Readability

**Test:** Manual verification
1. Login as admin
2. Unlock admin panel (enter password when prompted by chat)
3. Check admin section text colors:
   - Headers should be white (#ffffff)
   - Body text should be white or light grey (#cccccc)
   - All text should be readable on dark background

## F) Bots Count Reconciliation

**Test 1:** Check current bot counts
```bash
# User's active bots
curl -s "${API_BASE}/api/system/status" \
  -H "Authorization: Bearer $TOKEN" | jq '.trading_activity.active_bots'

# Should match count from:
curl -s "${API_BASE}/api/bots/lifecycle/status" \
  -H "Authorization: Bearer $TOKEN" | jq '[.bots[] | select(.status == "active")] | length'
```

**Test 2:** Run reconciliation report (admin only)
```bash
# Dry run - just report
curl -s "${API_BASE}/api/admin/bots/reconcile" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{total_bots, issues, message}'

# Expected output:
# {
#   "total_bots": N,
#   "issues": {
#     "missing_user_id": 0,
#     "empty_user_id": 0,
#     "total": 0
#   },
#   "message": "Found 0 orphaned bots..."
# }
```

**Test 3:** Fix orphaned bots (if any found)
```bash
# Apply fixes - quarantines orphaned bots
curl -s "${API_BASE}/api/admin/bots/reconcile?fix=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{total_bots, issues, quarantined, message}'
```

**Test 4:** Run CLI reconciliation script
```bash
cd /home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment
python3 scripts/reconcile_bots.py

# Follow prompts to quarantine orphaned bots
```

## G) Verify Exactly 7 Exchanges

**Test 1:** Count exchange providers
```bash
curl -s "${API_BASE}/api/keys/providers" | \
  jq '[.providers[] | select(.type == "exchange")] | length'
# Expected: 7
```

**Test 2:** List exchange IDs
```bash
curl -s "${API_BASE}/api/keys/providers" | \
  jq -r '.providers[] | select(.type == "exchange") | .id' | sort
# Expected:
# binance
# bitget
# bybit
# gate
# kraken
# kucoin
# luno
```

**Test 3:** Verify no VALR/OVEX
```bash
# Should return empty
grep -ri "valr\|ovex" backend/ frontend/src/ \
  --exclude-dir=_archive \
  --exclude-dir=node_modules \
  --exclude-dir=.git \
  --exclude="*.pyc" | \
  grep -v "# No VALR\|test_\|AddressApproval"
# Expected: No output (or only false positives like AddressApprovalRequest)
```

## Full System Health Check

Run all checks:
```bash
echo "=== A) System Status ==="
curl -s "${API_BASE}/api/system/status" -H "Authorization: Bearer $TOKEN" | \
  jq '.scheduler_status.trading_scheduler | has("error")'
echo "Expected: false"
echo ""

echo "=== B) API Keys ==="
curl -s "${API_BASE}/api/keys/providers" | jq '.total'
echo "Expected: 10"
echo ""

echo "=== C) Build Version ==="
curl -s "${API_BASE}/api/build/info" | jq '.version_short'
echo ""

echo "=== F) Bots Count ==="
curl -s "${API_BASE}/api/system/status" -H "Authorization: Bearer $TOKEN" | \
  jq '.trading_activity.active_bots'
echo ""

echo "=== G) Exchange Count ==="
curl -s "${API_BASE}/api/keys/providers" | \
  jq '[.providers[] | select(.type == "exchange")] | length'
echo "Expected: 7"
echo ""

echo "✅ All checks complete!"
```

## Post-Deployment Verification

After deploying to production:

1. **Test system status endpoint:**
   ```bash
   curl -s "https://your-domain.com/api/system/status" \
     -H "Authorization: Bearer $PROD_TOKEN" | jq '.scheduler_status'
   ```

2. **Verify version badge in UI:**
   - Open https://your-domain.com/dashboard
   - Check footer shows version badge
   - Matches backend version

3. **Clear browser cache:**
   - Force refresh (Ctrl+Shift+R)
   - Verify dashboard is latest version

4. **Test API keys flow:**
   - Navigate to API Keys section
   - Try saving/testing/deleting a key
   - Verify realtime updates work

5. **Test chat:**
   - Logout and login
   - Verify chat shows fresh greeting
   - Verify no auto-load of old messages

6. **Check admin panel:**
   - Unlock admin panel
   - Verify text is readable (white on dark)

## Troubleshooting

### System status still returns error
- Check trading_scheduler module is installed
- Verify safe handling code is deployed
- Check logs: `tail -f /var/log/amarktai/backend.log`

### Version badge not showing
- Check /api/build/info endpoint
- Verify VersionBadge component is imported
- Check browser console for errors

### Old dashboard persists
- Clear browser cache (Ctrl+Shift+R)
- Verify nginx cache headers for index.html
- Restart nginx: `sudo systemctl restart nginx`

### Chat history reappears
- Verify login.js clears localStorage/sessionStorage
- Check browser localStorage is empty after login
- Test in incognito mode

### Admin panel text unreadable
- Verify admin panel CSS changes are deployed
- Check inline styles use #ffffff or #cccccc
- Test in different browsers
