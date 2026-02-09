# TESTING CHECKLIST - AMARKTAI GO-LIVE FIX

Use this checklist to verify all fixes are working correctly in your environment.

## Prerequisites

- [ ] Backend service is running
- [ ] You have valid AMK_EMAIL and AMK_PASSWORD credentials
- [ ] Network connectivity to the API server

## Test Commands

### 1. Quick Syntax Verification (Local)

```bash
# Verify Python syntax
python3 -m py_compile backend/routes/keys.py
python3 -m py_compile backend/tests/test_keys_status_regression.py
python3 -m py_compile backend/tests/test_ai_chat_missing_key.py

# Verify Bash syntax
bash -n scripts/go_live_smoke.sh
bash -n scripts/verify_go_live_now.sh
```

**Expected:** All commands exit with code 0 (no errors)

---

### 2. Backend Health Check

```bash
# Check if backend is responding
curl -s http://127.0.0.1:8000/api/system/ping | jq
```

**Expected:** 
```json
{
  "status": "healthy",
  ...
}
```

---

### 3. Critical Fix Verification - /api/keys/status

This is the MOST IMPORTANT test - verifies the crash fix works.

```bash
# Login first
export AMK_EMAIL="your-email@example.com"
export AMK_PASSWORD="your-password"

LOGIN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$AMK_EMAIL\",\"password\":\"$AMK_PASSWORD\"}")

# Extract token
export TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

# Test the fixed endpoint
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/keys/status | jq
```

**Expected:**
```json
{
  "success": true,
  "status_map": {
    "openai": { "status": "not_configured", ... },
    "flokx": { "status": "not_configured", ... },
    "fetchai": { "status": "not_configured", ... },
    "luno": { "status": "not_configured", ... },
    "binance": { "status": "not_configured", ... },
    "kucoin": { "status": "not_configured", ... },
    "bybit": { "status": "not_configured", ... },
    "kraken": { "status": "not_configured", ... },
    "bitget": { "status": "not_configured", ... },
    "gate": { "status": "not_configured", ... }
  }
}
```

**Must have:** Exactly 10 providers, no crash, no errors

---

### 4. Run Verification Script

```bash
# Set credentials
export AMK_EMAIL="your-email@example.com"
export AMK_PASSWORD="your-password"

# Run verification
./scripts/verify_go_live_now.sh
```

**Expected:**
```
🔥 AMARKTAI GO-LIVE VERIFICATION
=================================
Test 1: System Ping
✅ PASS: System ping
Test 2: Login
✅ PASS: Login successful
Test 3: Providers List
✅ PASS: Providers list has 10 providers
Test 4: Keys Status
✅ PASS: Keys status endpoint working
Test 5: Keys List
✅ PASS: Keys list endpoint working
Test 6: AI Chat Greeting
✅ PASS: AI chat greeting working
Test 7: AI Chat History
✅ PASS: AI chat history working

SUMMARY: 7 passed, 0 failed
✅ ALL TESTS PASSED - READY FOR GO-LIVE
```

**Exit code:** 0

---

### 5. Run Smoke Tests

```bash
# Run full smoke test suite
./scripts/go_live_smoke.sh
```

**Expected:**
- All tests pass (or at most, non-critical warnings)
- Script completes without hanging
- Exit code: 0

---

### 6. Run Regression Tests (Optional - requires full environment)

```bash
cd backend
pytest tests/test_keys_status_regression.py tests/test_ai_chat_missing_key.py -v
```

**Expected:** All tests pass

---

## Success Criteria

✅ All tests above pass  
✅ No backend crashes when accessing /api/keys/status  
✅ Scripts complete without hanging  
✅ All 10 providers are returned in status checks  

If all criteria are met: **SYSTEM IS READY FOR GO-LIVE** 🚀

---

## Troubleshooting

### If /api/keys/status still crashes:

1. Check backend logs: `sudo journalctl -u amarktai-api -f`
2. Verify fix was applied: `grep "p\['id'\]" backend/routes/keys.py`
3. Restart backend: `sudo systemctl restart amarktai-api`

### If scripts hang:

1. Check TIMEOUT variable: `echo $TIMEOUT` (should be 10 or your custom value)
2. Verify network connectivity to API
3. Check if backend is responding: `curl http://127.0.0.1:8000/api/system/ping`

### If wrong number of providers:

1. Check providers endpoint: `curl http://127.0.0.1:8000/api/keys/providers | jq`
2. Should return exactly 10 providers (3 AI + 7 exchanges)

---

## Support

If issues persist after following this checklist:
1. Check GO_LIVE_FIX_SUMMARY.md for detailed implementation notes
2. Review backend logs for errors
3. Verify all files were updated correctly using git diff
