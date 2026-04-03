# Production Go-Live Fix - Deployment Notes

## Summary of Changes

This deployment fixes three critical production issues:

### 1. API Key Status Persistence ✅ FIXED
**Problem**: After successfully testing an API key, the UI showed "saved (untested)" instead of "test ok". Status would bounce back after page refresh.

**Root Cause**: 
- Backend used `ProviderStatus.TEST_OK.value = "configured_valid"` 
- Frontend expected status value `"test_ok"`
- Race condition where status fetch could overwrite optimistic UI update

**Solution**:
- Changed ProviderStatus enum to use intuitive values: `test_ok`, `saved_untested`, `test_failed`
- Added optimistic UI updates in frontend (immediate status change)
- Added delayed refetch with race condition protection
- Updated tests to match new enum values

**Files Changed**:
- `backend/services/provider_registry.py` - ProviderStatus enum
- `frontend/src/components/APIKeySettings.js` - Optimistic updates
- `tests/test_api_keys_status.py` - Test assertions

### 2. AI Chat Per-User Key Support ✅ FIXED
**Problem**: AI chat always used system OpenAI key from environment variables. User-configured keys in API Settings were ignored.

**Root Cause**:
- `AIProductionHandler` hardcoded: `self.api_key = os.environ.get('OPENAI_API_KEY')`
- `AIModelsRouter` hardcoded: `self.client = AsyncOpenAI(api_key=self.api_key)`
- No logic to check for per-user keys in database

**Solution**:
- Added `get_openai_client(user_id)` method to retrieve per-user keys first
- Updated `AIModelsRouter.get_client_for_user(user_id)` for same logic
- Updated all AI methods to accept user_id parameter
- Falls back to system key if user has no configured key
- Added `/api/diagnostics/chat` endpoint for troubleshooting

**Files Changed**:
- `backend/ai_production.py` - Per-user key retrieval
- `backend/ai_models_router.py` - Client factory with user support
- `backend/server.py` - New diagnostics endpoints

### 3. Dashboard Endpoint Validation ✅ VERIFIED
**Problem**: Potential 404s or broken endpoints in dashboard sections.

**Action Taken**:
- Audited all 80+ API endpoints used by Dashboard.js and subcomponents
- Verified critical routers are mounted: analytics, wallet, system_mode, bot_lifecycle, keys, realtime
- Confirmed no missing or broken endpoints

**Result**: All critical endpoints exist and are properly mounted. No changes required.

## Testing Before Deployment

### 1. Run Smoke Test
```bash
export AMK_EMAIL="test@example.com"
export AMK_PASSWORD="testpass"
export API_BASE="http://localhost:8000"

./scripts/go_live_smoke.sh
```

Expected: All tests PASS (12 tests total including new diagnostics checks)

### 2. Manual Testing Checklist
- [ ] Save OpenAI key → Test → Status shows "Test OK ✅" immediately
- [ ] Refresh page → Status remains "Test OK ✅" (does NOT revert)
- [ ] Open chat → Send message → Receives AI response (not "key not configured")
- [ ] Dashboard overview loads without console errors
- [ ] Delete API key → Status immediately shows "Not configured"

### 3. Backend Unit Tests
```bash
cd backend
python -m pytest tests/test_api_keys_status.py -v
```

All assertions should pass with new enum values.

## Deployment Steps (Quick Reference)

```bash
# 1. Backup database
mongodump --uri="mongodb://localhost:27017/amarktai" --out=/backup/$(date +%Y%m%d-%H%M%S)

# 2. Pull latest code
cd /var/amarktai/app/frontend/build
sudo -u www-data git pull origin copilot/fix-api-key-management-issues

# 3. Fix ownership
sudo chown -R www-data:www-data /var/amarktai/app/frontend/build

# 4. Install dependencies (if needed)
cd backend && sudo -u www-data pip install -r requirements.txt
cd ../frontend && sudo -u www-data npm install

# 5. Build frontend
cd /var/amarktai/app/frontend/build/frontend
sudo -u www-data npm run build

# 6. Restart backend
sudo systemctl restart amarktai-backend

# 7. Reload nginx
sudo nginx -t && sudo systemctl reload nginx

# 8. Verify
./scripts/go_live_smoke.sh
```

## Rollback (If Needed)

```bash
cd /var/amarktai/app/frontend/build
sudo -u www-data git checkout main  # or previous working commit
cd frontend && sudo -u www-data npm run build
sudo systemctl restart amarktai-backend
```

## Post-Deployment Validation

### Critical User Flows to Test
1. **API Key Management**:
   - Save OpenAI key
   - Test key (should show "Test OK ✅")
   - Refresh browser
   - Verify status is still "Test OK ✅" (NOT "Saved (untested)")

2. **AI Chat**:
   - Open chat panel
   - Type: "Show my portfolio status"
   - Verify: Receives AI response (not error about missing key)
   - Check logs: Confirm using user's OpenAI key if configured

3. **Dashboard Overview**:
   - Portfolio metrics load
   - Bot list populates
   - No 404 errors in browser console
   - Analytics charts render

### Monitoring Commands
```bash
# Watch backend logs
sudo tail -f /var/log/amarktai/backend.log | grep -i "openai\|test_ok\|api key"

# Check diagnostics
curl -X GET "https://api.amarktai.com/api/diagnostics/chat" \
  -H "Authorization: Bearer $TOKEN" | jq

# Admin go-live check
curl -X GET "https://api.amarktai.com/api/diagnostics/go-live" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.overall_status'
```

Expected: `"PASS"` or `"PASS_WITH_WARNINGS"`

## New Diagnostic Endpoints

### GET /api/diagnostics/chat
Returns chat availability and OpenAI key status.

Response:
```json
{
  "success": true,
  "openai_key_status": "test_ok",
  "key_source_would_use": "user",
  "chat_available": true,
  "recommendation": "Chat is ready!"
}
```

### GET /api/diagnostics/go-live (Admin Only)
Comprehensive system health check for production readiness.

Response includes:
- Health check status
- Database connectivity
- System modes
- All API keys status (OpenAI + 7 exchanges)
- Chat diagnostics
- Scheduler state
- Realtime connections

## Expected Behavior After Deployment

### API Key Status Flow
1. User clicks "Save API Key" → Status: `saved_untested`
2. User clicks "Test" → **Immediately** shows "Testing..." (optimistic)
3. Test succeeds → **Immediately** shows "Test OK ✅" (optimistic)
4. Backend confirms → Status refetched after 500ms delay
5. User refreshes page → Status **persists** as "Test OK ✅"

### AI Chat Key Selection
1. Check user's OpenAI key in database
2. If status = `test_ok` → Use user's key ✅
3. If not configured → Fall back to system key (from environment)
4. If neither → Show clear error: "Please configure your OpenAI key"

Logs will show:
```
INFO: Using per-user OpenAI key for user abc12345
```
or
```
INFO: Using system OpenAI key for user abc12345 (no user key configured)
```

## Supported Exchanges (Verified)

✅ **Required exchanges** (all present):
- luno
- binance  
- kucoin
- bybit
- kraken
- bitget
- gate

❌ **Excluded exchanges** (correctly removed):
- VALR (South African exchange - not included)
- OVEX (South African exchange - not included)

## Success Criteria

Deployment is successful when:
- ✅ Smoke test passes (12/12 tests)
- ✅ API key status persists after test
- ✅ Status does NOT bounce back to "saved_untested"
- ✅ AI chat responds using user's key (when configured)
- ✅ Dashboard loads without errors
- ✅ No increase in error rates

## Known Limitations

1. **System key fallback**: If user has no OpenAI key, system key is used. This is intentional for backward compatibility.

2. **Key status caching**: Status is fetched on component mount. If updated in another tab, may need manual refresh to see change.

3. **Optimistic updates**: In rare network failure cases, optimistic update may show "test_ok" briefly before reverting to actual status from server.

## Support Contact

For issues:
1. Check `/var/log/amarktai/backend.log`
2. Run: `GET /api/diagnostics/go-live` (admin)
3. Check browser console for frontend errors
4. Review this document for rollback procedure

---

**Deployment Date**: 2026-02-06
**Branch**: copilot/fix-api-key-management-issues  
**Commit**: (will be set during deployment)
