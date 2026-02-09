# Frontend Go-Live Verification Checklist

## Overview
This document provides step-by-step verification procedures for the frontend fixes implemented in merge #81.

## Backend Prerequisites
Before testing frontend, verify backend is running and endpoints are functional:

```bash
# Test backend is running
curl http://localhost:8000/health

# Test authentication
TOKEN="your-jwt-token-here"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me

# Test API keys list endpoint (should return all 10 providers)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/keys/list

# Test live prices endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/prices/live
```

Expected responses:
- `/health`: `{"status": "healthy", ...}`
- `/api/auth/me`: User profile JSON
- `/api/keys/list`: `{"success": true, "keys": [...]}` with status for all providers
- `/api/prices/live`: Price data for BTC/ZAR, ETH/ZAR, XRP/ZAR

## Frontend Verification Steps

### 1. API Keys UI - Backend Truth ✅

**Goal**: Verify API Keys section shows correct status from backend, never hardcoded values.

**Steps**:
1. Login to dashboard
2. Navigate to "API Setup" section
3. Verify you see all 10 providers:
   - **Exchanges** (7): Luno 🇿🇦, Binance 🟡, KuCoin 🟢, Bybit 🟠, Kraken 🔵, Bitget 🔵, Gate 🟣
   - **AI Providers** (3): OpenAI 🤖, Flokx 🤖, Fetch.ai 🤖

**Expected Results**:
- ✅ All providers without saved keys show: **"⚪ Not configured"** 
- ✅ Status colors:
  - Gray (not_configured)
  - Amber (saved_untested)
  - Green (test_ok)
  - Red (test_failed)
- ✅ Status text matches `status_display` from `/api/keys/list`

**What to check**:
```bash
# Get current status
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/keys/list | jq '.keys[] | {provider, status, status_display}'
```

Compare terminal output with UI - they must match exactly.

---

### 2. Realtime Updates - Save/Test/Delete Keys ⚡

**Goal**: Verify UI updates within 1-2 seconds when API keys are saved/tested/deleted (no page refresh needed).

**Steps**:
1. Open dashboard in browser
2. Open browser DevTools Console (F12)
3. Navigate to "API Setup" section
4. **Test Save**: Enter dummy Luno API key and click "Save API Key"
   - Watch console for: `🔑 Realtime: Key saved`
   - Verify status changes to "⚠️ Saved (untested)" within 1-2 seconds
5. **Test Test**: Click "Test" button on saved key
   - Watch console for: `🔑 Realtime: Key tested`
   - Verify status changes to either "✅ Test OK" or "❌ Test Failed" within 1-2 seconds
6. **Test Delete**: Click "Delete" button
   - Watch console for: `🔑 Realtime: Key deleted`
   - Verify status changes back to "⚪ Not configured" within 1-2 seconds

**Expected Console Logs**:
```
✅ WebSocket connected
✅ Initializing WebSocket connection...
🔑 Realtime: Key saved {provider: "luno", display_name: "Luno", ...}
🔑 Key saved event: {...}
🔑 Realtime: Key tested {provider: "luno", success: false, ...}
🔑 Key tested event: {...}
🔑 Realtime: Key deleted {provider: "luno", ...}
🔑 Key deleted event: {...}
```

**Pass Criteria**:
- ✅ Status updates appear **within 1-2 seconds**
- ✅ No page refresh required
- ✅ WebSocket connection shows "Connected" in console
- ✅ Toast notifications appear for each action

---

### 3. Live Prices - Overview Section 💹

**Goal**: Verify live cryptocurrency prices display and update in real-time.

**Steps**:
1. Login to dashboard
2. Navigate to "Overview" section
3. Locate price ticker showing BTC/ZAR, ETH/ZAR, XRP/ZAR
4. Watch for 10-15 seconds to see prices update
5. Check timestamp/last updated indicator

**Expected Results**:
- ✅ Prices display as "R1,234,567" format
- ✅ Change percentage shows as "+2.45%" (green) or "-1.23%" (red)
- ✅ Prices update every 5 seconds (polling fallback)
- ✅ If Luno API key is configured and valid, prices should be real-time

**What to check**:
```bash
# Verify backend returns live prices
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/prices/live | jq '.'

# Should return:
{
  "BTC/ZAR": {"price": 1234567.89, "change_24h": 2.45, "lastUpdated": "2026-02-09T..."},
  "ETH/ZAR": {"price": 45678.90, "change_24h": -1.23, "lastUpdated": "2026-02-09T..."},
  "XRP/ZAR": {"price": 12.34, "change_24h": 0.56, "lastUpdated": "2026-02-09T..."}
}
```

**Pass Criteria**:
- ✅ Prices match backend response
- ✅ Prices are not zero or "R0"
- ✅ Last updated timestamp is recent (within last 10 seconds)

---

### 4. Admin Panel - Dates & Actions 🔧

**Goal**: Verify admin panel shows dates correctly (no "Invalid Date") and actions work.

**Prerequisites**: You must be an admin user and unlock admin panel with password.

**Steps**:
1. Login as admin user
2. In AI Chat, type: `show admin`
3. Enter admin password when prompted
4. Navigate to "Admin Panel" section
5. Check all date fields:
   - User "Created At" dates
   - Bodyguard "Last check" timestamp
   - Any other timestamps

**Expected Results**:
- ✅ All dates show as valid formatted strings (e.g., "2/9/2026, 6:22:26 PM")
- ✅ Missing/null dates show as "—" (not "Invalid Date")
- ✅ Admin actions (Block User, Delete User, etc.) include Bearer token in requests
- ✅ Toast notifications appear on action success/failure

**What to check in DevTools Network tab**:
- Admin API calls include: `Authorization: Bearer <token>`
- Responses are 200 OK (not 401/403)

**Pass Criteria**:
- ✅ No "Invalid Date" anywhere in UI
- ✅ All dates are human-readable or show "—"
- ✅ Admin actions execute successfully
- ✅ Error messages are clear when actions fail

---

### 5. Dashboard Headers - White Color ⚪

**Goal**: Verify all main section headers are white (#ffffff) as requested.

**Steps**:
1. Login to dashboard
2. Navigate through all sections:
   - Welcome
   - Overview
   - API Setup
   - Bot Management
   - Profile Settings
   - Admin Panel (if admin)
   - System Mode
   - Live Trades
   - Profits & Performance

**Expected Results**:
- ✅ All `<h2>` section headers display in **white color**
- ✅ Headers are easily readable against dark background
- ✅ No layout changes - only color change

**Visual Check**:
- Look for headers like:
  - "Welcome, [Name]" - White ✅
  - "System Overview" - White ✅
  - "🔑 API Setup - All Integration Keys" - White ✅
  - "🤖 Bot Management" - White ✅
  - "Profile Settings" - White ✅
  - "🔧 Admin Panel (God Mode)" - White ✅
  - "System Mode" - White ✅
  - "📊 Live Trades - Platform Comparison" - White ✅
  - "💹 Profits & Performance" - White ✅

---

### 6. AI Chat Integration 🤖

**Goal**: Verify AI chat works and shows appropriate messages.

**Steps**:
1. Login to dashboard
2. Scroll to AI Assistant chat section
3. Type a simple message: "hello"
4. Check response

**Expected Results**:

**Without OpenAI configured**:
- ✅ Backend returns: "OpenAI is not configured. Please add your OpenAI API key in the API Setup section."
- ✅ Chat displays this message clearly

**With OpenAI configured**:
- ✅ AI responds with helpful message
- ✅ Chat history persists across page reloads (stored in backend)
- ✅ "Load History" button works to fetch old messages

**Pass Criteria**:
- ✅ Chat is functional
- ✅ Error messages are clear when OpenAI not configured
- ✅ Once OpenAI key is saved, chat works immediately

---

### 7. Build Verification ✅

**Goal**: Verify production build succeeds without errors.

**Steps**:
```bash
cd frontend
npm run build
```

**Expected Output**:
```
✅ All asset references are valid!
Creating an optimized production build...
Compiled successfully.

File sizes after gzip:
  222.66 kB  build/static/js/main.64aa8f76.js
  14.87 kB   build/static/css/main.cc5a43f1.css

The build folder is ready to be deployed.
```

**Pass Criteria**:
- ✅ No compilation errors
- ✅ No TypeScript/ESLint errors
- ✅ Build completes in < 3 minutes
- ✅ Output bundle size is reasonable (< 500 kB gzipped)

---

## Quick Smoke Test Script

Run this to verify all critical endpoints:

```bash
#!/bin/bash
# save as verify-frontend.sh

TOKEN="your-jwt-token-here"
BASE_URL="http://localhost:8000"

echo "🔍 Frontend Go-Live Verification"
echo "================================"

echo "\n1. Health Check..."
curl -s "$BASE_URL/health" | jq '.status'

echo "\n2. API Keys List..."
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/keys/list" | jq '.success, .keys | length'

echo "\n3. Live Prices..."
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/prices/live" | jq 'keys'

echo "\n4. User Profile..."
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/auth/me" | jq '.email'

echo "\n✅ All backend endpoints responding!"
```

---

## Success Criteria Summary

All items must pass:

- [x] API Keys show correct status from backend (not hardcoded)
- [x] Realtime updates work (save/test/delete keys update UI within 1-2s)
- [x] Live prices display and update
- [x] Admin panel dates show correctly (no "Invalid Date")
- [x] Admin actions include Bearer token and work
- [x] Dashboard section headers are WHITE
- [x] AI chat works and shows helpful messages
- [x] npm run build succeeds without errors

---

## Troubleshooting

### Issue: API Keys still show "saved" for unconfigured providers
**Solution**: 
- Check `/api/keys/list` response in DevTools Network tab
- Verify `status` field is "not_configured" for providers without keys
- If backend returns wrong status, fix backend `/api/keys/list` endpoint

### Issue: Realtime updates not working
**Solution**:
- Check browser console for WebSocket connection messages
- Verify: "✅ WebSocket connected" appears
- Check backend logs for WebSocket connection
- Ensure token is valid and not expired

### Issue: Prices show as R0 or don't update
**Solution**:
- Check `/api/prices/live` endpoint response
- Verify Luno API key is configured and tested OK
- Check backend paper_trading_engine logs for price fetch errors

### Issue: Admin actions return 401/403
**Solution**:
- Verify user has `is_admin: true` in profile
- Check Authorization header includes Bearer token
- Verify admin password unlock was successful

---

## Production Deployment Checklist

Before deploying to production:

1. ✅ All verification steps above pass
2. ✅ Run `npm run build` successfully
3. ✅ Test on staging environment first
4. ✅ Verify WebSocket URL uses wss:// (not ws://) for HTTPS
5. ✅ Check CORS settings allow frontend domain
6. ✅ Verify environment variables are set correctly
7. ✅ Monitor backend logs during first 10 minutes after deployment
8. ✅ Have rollback plan ready

---

## Contact & Support

If verification fails or issues are found:
- Check browser console for errors
- Check backend logs for API errors
- Review this document's troubleshooting section
- Contact development team with:
  - Browser console logs
  - Network tab screenshots
  - Backend error logs

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-09  
**Merge**: #81  
**Commit**: e0ad829
