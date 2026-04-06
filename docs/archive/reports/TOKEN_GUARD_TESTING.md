# Token Guard Testing Guide

## Purpose
Verify that dashboard hooks and realtime connections do NOT run on public pages without authentication.

## Test Cases

### Test 1: Landing Page (No Authentication)
**Expected Behavior:** NO API calls or WebSocket attempts

1. Clear browser localStorage and cookies
2. Navigate to `/` (landing page)
3. Open browser DevTools → Network tab
4. Clear network log
5. Wait 30 seconds on landing page

**Success Criteria:**
- ✅ No requests to `/api/*` endpoints
- ✅ No WebSocket connection attempts to `/api/ws`
- ✅ Console shows NO "Connecting to WebSocket" messages
- ✅ Console shows NO 403 Forbidden errors
- ✅ Only static asset loads (HTML, CSS, JS, images, videos)

**Expected Console Messages:**
- None related to API or WebSocket (should be silent)

### Test 2: Login Page (No Authentication)
**Expected Behavior:** NO API calls except login submission

1. Clear browser localStorage and cookies
2. Navigate to `/login`
3. Open browser DevTools → Network tab
4. Clear network log
5. Wait 30 seconds without logging in

**Success Criteria:**
- ✅ No background polling or WebSocket attempts
- ✅ No 403 errors in console
- ✅ Only API calls should be from explicit user actions (login button click)

### Test 3: Dashboard (Authenticated)
**Expected Behavior:** Normal operation with API calls and WebSocket

1. Log in with valid credentials
2. Navigate to `/dashboard`
3. Open browser DevTools → Network and Console tabs

**Success Criteria:**
- ✅ WebSocket connection established successfully
- ✅ See "✅ WebSocket connected" in console
- ✅ See "✅ Connecting to WebSocket:" in console
- ✅ Polling intervals running for live prices, metrics, etc.
- ✅ Real-time updates working
- ✅ No 403 Forbidden errors
- ✅ Connection status shows "Connected"

**Expected Console Messages:**
```
✅ Initializing WebSocket connection...
🔌 Connecting to WebSocket: wss://[domain]/api/ws?token=***
✅ WebSocket connected
```

### Test 4: Logout Flow
**Expected Behavior:** Connections stop after logout

1. While logged in and on dashboard, note active connections
2. Click logout
3. Observe network activity stops

**Success Criteria:**
- ✅ WebSocket disconnects
- ✅ Polling intervals stop
- ✅ Redirected to login page
- ✅ No further API calls on login page

### Test 5: Token Expiry
**Expected Behavior:** Connections stop when token becomes invalid

1. Log in and stay on dashboard
2. Manually delete token from localStorage: `localStorage.removeItem('token')`
3. Wait for next polling interval (up to 30 seconds)

**Success Criteria:**
- ✅ Polling intervals detect missing token and stop
- ✅ Console shows "⏸️  No token available - skipping..." messages
- ✅ No new API calls attempted
- ✅ User redirected to login page

## Implementation Details

### Token Guard Pattern
All hooks use this pattern:

```javascript
const getToken = () => {
  try {
    return localStorage.getItem('token') || null;
  } catch (error) {
    console.error('Error reading token:', error);
    return null;
  }
};

// In useEffect
useEffect(() => {
  const currentToken = getToken();
  if (!currentToken) {
    return undefined; // Early return - no setup
  }
  
  // Setup connections/polling
  const interval = setInterval(() => {
    if (getToken()) { // Double-check before each action
      fetchData();
    }
  }, intervalMs);
  
  return () => clearInterval(interval); // Always cleanup
}, [dependencies]);
```

### Files Protected

1. **`frontend/src/lib/realtime.js`**
   - `scheduleReconnect()` - Guards reconnection
   - `startSSE()` - Guards SSE fallback
   - `startPolling()` - Guards polling fallback

2. **`frontend/src/hooks/useDashboardData.js`**
   - Polling useEffect (line ~227)
   - Realtime connection useEffect (line ~243)

3. **`frontend/src/hooks/useDashboardState.js`**
   - Flokx status polling
   - Flokx alerts polling
   - `setupRealTimeConnections()` function
   - RL metrics polling
   - Admin data polling

### Components That Don't Import Dashboard Hooks

✅ **Public Pages (Safe):**
- `frontend/src/pages/Landing.js` - Uses AuthLayout only
- `frontend/src/pages/Login.js` - No dashboard imports
- `frontend/src/pages/Register.js` - No dashboard imports
- `frontend/src/components/AuthLayout.js` - Layout only
- `frontend/src/components/PublicPageLayout.js` - Layout only

✅ **Dashboard-Only (Protected by PrivateRoute):**
- `frontend/src/pages/Dashboard.js` - Only loads after auth
- `frontend/src/components/APIKeySettings.js` - Only used in dashboard sections

## Manual Verification Steps

1. **Start Fresh:**
   ```bash
   # Clear all browser data
   # Open incognito window
   ```

2. **Test Public Pages:**
   ```
   Visit: http://localhost:5173/
   - Check Network tab: Should be empty of API calls
   - Check Console: Should be clean
   ```

3. **Test Dashboard:**
   ```
   Visit: http://localhost:5173/login
   Login with credentials
   - Check Network: Should see API calls and WebSocket
   - Check Console: Should see connection messages
   ```

4. **Verify Token Guards:**
   ```javascript
   // In browser console while on landing page
   localStorage.getItem('token') // Should be null
   
   // In browser console while on dashboard
   localStorage.getItem('token') // Should be JWT string
   ```

## Success Metrics

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| API calls on landing page | 10-20 (403s) | 0 |
| WebSocket attempts without auth | Yes | No |
| Console errors on public pages | Multiple 403s | None |
| Dashboard functionality | Working | Working |
| Memory leaks | Possible | None (proper cleanup) |

## Related Files

- Implementation: `frontend/src/hooks/useDashboardState.js`
- Implementation: `frontend/src/hooks/useDashboardData.js`
- Implementation: `frontend/src/lib/realtime.js`
- Router: `frontend/src/App.js`
- Auth Guard: `PrivateRoute` in App.js
