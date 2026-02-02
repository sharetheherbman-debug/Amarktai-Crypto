# Gap Report: Dashboard Overhaul & Missing Wiring Fixes

**Generated:** 2026-01-13  
**Repository:** Amarktai-Network---Deployment  
**Backend:** FastAPI + MongoDB  
**Frontend:** React + axios

## Executive Summary

This report identifies gaps between frontend API calls and backend endpoints, focusing on:
1. Missing or mismatched routes
2. Authentication issues (ObjectId resolution)
3. Real-time functionality (WS vs SSE)
4. Asset path issues for production builds
5. Navigation/UI issues (duplicate menu items, underscore in labels)

---

## 1. Frontend API Endpoints Analysis

### Endpoints Called by Dashboard.js

Based on analysis of `frontend/src/pages/Dashboard.js`, the following endpoints are called:

#### Auth & User
- ✅ `GET /api/auth/me` - Fetch current user profile
- ✅ `PUT /api/auth/profile` - Update user profile

#### Bots Management
- ✅ `GET /api/bots` - List user's bots
- ✅ `POST /api/bots` - Create single bot
- ✅ `POST /api/bots/batch-create` - Batch create bots
- ✅ `PUT /api/bots/{bot_id}` - Update bot
- ✅ `DELETE /api/bots/{bot_id}` - Delete bot
- ✅ `POST /api/bots/uagent` - Create uAgent bot
- ✅ `POST /api/bots/flokx` - Create Flokx bot
- ✅ `POST /api/bots/evolve` - Trigger bot evolution
- ✅ `GET /api/bots/eligible-for-promotion` - Check promotion eligibility
- ✅ `POST /api/bots/confirm-live-switch` - Confirm live trading switch

#### Trading & Metrics
- ✅ `GET /api/trades/recent?limit=50` - Recent trades
- ✅ `GET /api/portfolio/summary` - Portfolio summary/metrics
- ✅ `GET /api/profits?period={period}` - Profit data by period
- ✅ `GET /api/prices/live` - Live market prices
- ⚠️ `GET /api/metrics` - Prometheus metrics (needs auth check)

#### System & Modes
- ✅ `GET /api/system/mode` - Get system modes
- ✅ `PUT /api/system/mode` - Set system mode
- ✅ `POST /api/system/emergency-stop` - Emergency stop

#### API Keys
- ✅ `GET /api/api-keys` - List user's API keys
- ✅ `POST /api/keys/save` - Save API key
- ✅ `POST /api/keys/test` - Test API key connection
- ✅ `DELETE /api/api-keys/{provider}` - Delete API key

#### Wallet & Financial
- ✅ `GET /api/wallet/balances` - Wallet balances
- ✅ `GET /api/wallet/requirements` - Wallet requirements
- ✅ `GET /api/wallet/funding-plans?status=awaiting_deposit` - Funding plans
- ✅ `POST /api/wallet/funding-plans/{planId}/cancel` - Cancel funding plan
- ✅ `GET /api/wallet/deposit-address` - Get deposit address

#### Analytics & AI
- ✅ `GET /api/analytics/countdown-to-million` - Countdown to R1M
- ✅ `POST /api/chat` - AI chat
- ✅ `GET /api/insights/daily` - Daily insights
- ✅ `GET /api/ml/predict/{pair}?timeframe={tf}` - ML price prediction

#### Admin
- ⚠️ `GET /api/admin/storage` - Admin storage data (403 issue)
- ✅ `GET /api/admin/users` - List all users
- ✅ `GET /api/admin/system-stats` - System statistics
- ✅ `GET /api/admin/health-check` - Health check
- ✅ `POST /api/admin/email-all-users` - Email all users
- ✅ `DELETE /api/admin/users/{userId}` - Delete user
- ✅ `PUT /api/admin/users/{userId}/block` - Block/unblock user
- ✅ `PUT /api/admin/users/{userId}/password` - Change user password

#### Autonomous Systems
- ✅ `POST /api/autonomous/bodyguard/system-check` - Bodyguard check
- ✅ `POST /api/autonomous/learning/trigger` - Trigger learning
- ✅ `POST /api/autonomous/reinvest-profits` - Reinvest profits

#### Advanced Features (Components)
- ⚠️ `GET /api/advanced/whale/summary` - Whale flow data (needs verification)
- ❌ `GET /api/flokx/alerts` - Flokx alerts (may not exist)

### Endpoints Called by Components

#### APIKeySettings.js
- ✅ `GET /api/user/api-keys/{service}` - Get specific service key
- ✅ `POST /api/user/api-keys` - Save user API key
- ✅ `DELETE /api/user/api-keys/{service}` - Delete service key
- ✅ `GET /api/user/payment-config` - Get payment config
- ✅ `POST /api/user/payment-config` - Update payment config
- ✅ `POST /api/user/generate-wallet` - Generate wallet

#### AIChatPanel.js
- ✅ `GET /api/ai/chat/history` - Chat history
- ✅ `POST /api/ai/chat` - Send chat message

#### BotLifecycleControls.js
- ✅ `POST /api/bots/{bot_id}/{action}` - Bot lifecycle actions

---

## 2. Backend Route Verification

### Routes Mounted in server.py

Analyzed `/backend/server.py` (3063 lines):

**Main API Router** (prefix `/api`):
- ✅ Auth routes from `routes/auth.py`
- ✅ Bots endpoints (directly in server.py)
- ✅ All endpoints under `/api` prefix

**Additional Routers** (mounted without prefix, define own `/api/*`):
- ✅ Phase 5, 6, 8 endpoints
- ✅ Capital tracking
- ✅ Emergency stop
- ✅ Wallet endpoints
- ✅ System health
- ✅ Admin endpoints
- ✅ Bot lifecycle
- ✅ System limits
- ✅ Live trading gate
- ✅ Analytics
- ✅ AI chat
- ✅ 2FA
- ✅ Genetic algorithm
- ✅ Dashboard endpoints
- ✅ API key management (legacy `/api/keys/*`)
- ✅ API keys canonical (`/api/api-keys/*`)
- ✅ Dashboard aliases (whale-flow, decision-trace, metrics/summary)
- ✅ Daily report
- ✅ Ledger
- ✅ Orders
- ✅ Limits management
- ✅ Advanced trading
- ✅ Payment agent
- ✅ User API keys (`/api/user/api-keys/*`)
- ✅ Alerts
- ✅ System router (`/api/system/*`)
- ✅ Trades router (`/api/trades/*`)
- ✅ Health router (`/api/health/*`)
- ⚠️ Realtime router (`/api/realtime/events`) - conditional on `ENABLE_REALTIME` env var

### WebSocket Endpoint
- ✅ `WS /api/ws` - WebSocket with token auth (exists)
- ✅ `WS /ws/decisions` - Decision trace WebSocket (exists)

---

## 3. Identified Gaps & Issues

### 🔴 Critical Issues

#### 3.1 Auth Issue: /api/auth/me Returns 404 "User not found"
**Problem:**  
The `/api/auth/me` endpoint in `routes/auth.py` queries by `{"id": user_id}` but MongoDB may store `_id` as ObjectId. When JWT contains string `user_id`, the query fails.

**Current Code** (`routes/auth.py:59-63`):
```python
@router.get("/auth/me")
async def get_current_user_profile(user_id: str = Depends(get_current_user)):
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {k: v for k, v in user.items() if k != 'password_hash'}
```

**Fix Required:**
- Try querying by both `id` field and `_id` (converted to ObjectId)
- Ensure consistent user ID storage during registration

#### 3.2 Admin Endpoint Returns 403
**Problem:**  
`GET /api/admin/storage` returns 403, suggesting admin permission check may be missing or user not flagged as admin.

**Fix Required:**
- Verify admin endpoints properly check user role
- Ensure test user or deployment has admin flag set
- Review `get_current_user` vs `get_admin_user` dependency usage

#### 3.3 Flokx Alerts Endpoint May Not Exist
**Problem:**  
Dashboard calls `GET /api/flokx/alerts` but this endpoint may not be implemented.

**Fix Required:**
- Verify if endpoint exists in any router
- If missing, create stub endpoint returning empty array or "not configured"
- Ensure no 404 errors in production

### ⚠️ Medium Priority Issues

#### 3.4 Whale Flow Endpoint Behind Auth
**Problem:**  
`GET /api/advanced/whale/summary` is called by `WhaleFlowHeatmap.js` component but may not be properly authenticated or may be disabled.

**Fix Required:**
- Verify endpoint exists in `routes/advanced_trading_endpoints.py`
- Ensure proper auth dependency
- If feature disabled, return safe stub response

#### 3.5 Real-time: WS vs SSE Mismatch
**Problem:**  
- Frontend may try to connect to `WS /api/ws` which exists
- Backend has SSE endpoint `/api/realtime/events` (conditional)
- Need consistent real-time strategy

**Current State:**
- WebSocket: `WS /api/ws` exists, handles token auth, sends various events
- SSE: `/api/realtime/events` exists if `ENABLE_REALTIME=true`
- Frontend uses both depending on component

**Recommendation:**
- Enable SSE by default (`ENABLE_REALTIME=true`)
- Frontend should primarily use SSE for dashboard updates
- Keep WS for chat and specific features
- Ensure no 404 spam from missing WS connections

#### 3.6 Metrics Endpoint Access Control
**Problem:**  
`GET /api/metrics` (Prometheus metrics) may not have proper auth or may expose sensitive system data.

**Fix Required:**
- Verify if endpoint should be admin-only or public
- Add auth dependency if needed
- Document access requirements

### 🟡 Low Priority Issues

#### 3.7 Asset Paths for Production Build
**Problem:**  
Assets (logo, background, audio) must load after `npm run build` with correct paths.

**Current Status:**
- Need to verify assets are in `/public` directory
- References should be relative (e.g., `/logo.png` not absolute URLs)

**Fix Required:**
- Audit asset references in Dashboard.js
- Move assets to `/public` if needed
- Test build output

#### 3.8 API_BASE Configuration
**Problem:**  
Frontend uses `API_BASE` from `lib/api.js` which may not be properly configured for production.

**Fix Required:**
- Verify `window.API_BASE` or env var handling
- Ensure fallback to `/api` works
- Document configuration for deployment

---

## 4. Navigation & UI Issues

### 4.1 Duplicate "API Keys" Navigation Entry
**Problem:**  
Dashboard has two API key related menu items:
- Line 3387: `🔑 Exchange Keys` → section 'api'
- Line 3396: `🔐 AI/Service Keys` → section 'api-keys'

**Fix Required:**
- Remove duplicate at line 3396
- Consolidate ALL keys (Exchange + OpenAI + Luno + Binance + KuCoin + Flokx + FetchAI) into single "API Setup" section
- Show all keys with test/connection status in one place

### 4.2 "Best Day_" Underscore Issue
**Problem:**  
Line 2938 shows "Best Day" label but may have underscore in JSON keys or other places.

**Fix Required:**
- Search for `Best Day_` or `best_day_` in frontend and backend
- Remove all underscores from labels and keys
- Ensure consistent "Best Day" formatting

### 4.3 Missing "Metrics" Section with Sub-menu
**Problem:**  
Current navigation has individual items for intelligence features. Need consolidated "Metrics" section with sub-menu:
- 🔔 Flokx Alerts
- 🎬 Decision Trace
- 🐋 Whale Flow
- 📊 Metrics

**Fix Required:**
- Refactor navigation to include expandable "Metrics" section
- Move intelligence-related items under this section
- Ensure each sub-item shows its panel

### 4.4 Platform Comparison Missing
**Problem:**  
No "Platform Comparison" view comparing Luno vs Binance vs KuCoin.

**Fix Required:**
- Build new section showing per-exchange stats:
  - Trades count
  - Profit
  - Fees
  - Best pair
  - Last trade time
  - Status
- Backend may need new aggregation endpoint or frontend can compute from existing data

### 4.5 Performance Panel Enhancement
**Problem:**  
Current graphs section needs enhancement with better information architecture.

**Fix Required:**
- Add dedicated "Performance" panel with:
  - PnL timeseries chart
  - Profit history
  - Drawdown visualization
  - Win rate stats
  - Fees breakdown
  - Daily/Weekly/Monthly view tabs
- Handle empty data gracefully ("No data yet")

---

## 5. Backend Requirements Summary

### 5.1 Must Fix
- [ ] Fix `/api/auth/me` to handle both `id` and `_id` (ObjectId)
- [ ] Add admin permission checks to admin endpoints
- [ ] Implement `/api/flokx/alerts` stub if missing
- [ ] Verify `/api/advanced/whale/summary` works or stub it
- [ ] Enable SSE by default (`ENABLE_REALTIME=true`)

### 5.2 Should Add
- [ ] Automated tests (pytest) for:
  - Auth flow (login + /api/auth/me)
  - Key dashboard endpoints return 200 or proper 403
  - Admin endpoints require admin role
- [ ] Consistent JSON serialization (convert ObjectId to str)

### 5.3 Nice to Have
- [ ] Platform comparison aggregation endpoint
- [ ] Enhanced metrics endpoint with more detailed stats

---

## 6. Frontend Requirements Summary

### 6.1 Must Fix
- [ ] Remove duplicate API Keys nav item (line 3396)
- [ ] Remove "Best Day_" underscores
- [ ] Add SSE connection for real-time updates
- [ ] Handle 404s gracefully (no spam in console)

### 6.2 Should Add
- [ ] Consolidated API Setup section with all keys
- [ ] Metrics section with sub-menu
- [ ] Platform Comparison view
- [ ] Enhanced Performance panel

### 6.3 UI Modernization
- [ ] Better card system with glassmorphism
- [ ] Improved spacing and typography
- [ ] Better color gradients
- [ ] Consistent icon usage

---

## 7. Asset & Build Issues

### 7.1 Production Build
- [ ] Verify `npm run build` succeeds
- [ ] Test assets load from build output
- [ ] Verify no absolute path issues

### 7.2 Assets Checklist
- [ ] Logo file location and reference
- [ ] Background images
- [ ] Audio files (if any)
- [ ] All in `/public` directory

---

## 8. Testing Strategy

### 8.1 Backend Tests
Create `backend/tests/test_dashboard_integration.py`:
```python
# Test auth flow
# Test dashboard endpoints
# Test admin permissions
# Test real-time SSE
```

### 8.2 Manual Testing Checklist
- [ ] Login works
- [ ] `/api/auth/me` returns 200
- [ ] Dashboard loads without errors
- [ ] No 404s in browser console
- [ ] All API keys can be saved
- [ ] Admin can access admin panel
- [ ] Non-admin cannot access admin endpoints
- [ ] Real-time updates work via SSE
- [ ] No duplicate menu items visible

---

## 9. Security Considerations

### 9.1 Admin Access
- Ensure admin endpoints check user role
- Audit sensitive data exposure

### 9.2 API Key Storage
- Keys should be encrypted at rest
- Use existing Fernet pattern if available
- Per-user encryption

### 9.3 Authentication
- Ensure all endpoints require auth where appropriate
- Verify JWT token validation

---

## 10. Deployment Notes

### 10.1 Backend
```bash
# Set environment variables
export ENABLE_REALTIME=true
export ENABLE_TRADING=0  # Safe default for initial deployment

# Start server
uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

### 10.2 Frontend
```bash
# Build
cd frontend
npm run build

# Output in frontend/build/
# Copy to static file server or serve via backend
```

### 10.3 Verification Commands
```bash
# Test health
curl http://localhost:8000/api/health/ping

# Test auth
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'

# Test SSE (requires token)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/realtime/events
```

---

## 11. Next Steps

### Phase 1: Backend Fixes (Priority 1)
1. Fix `/api/auth/me` ObjectId issue
2. Add admin permission checks
3. Create missing endpoint stubs
4. Enable SSE by default
5. Write minimal tests

### Phase 2: Frontend UI (Priority 2)
1. Remove duplicate nav item
2. Fix "Best Day_" labels
3. Add Metrics section with sub-menu
4. Build Platform Comparison view
5. Enhance Performance panel
6. Connect SSE for real-time

### Phase 3: Polish & Deploy (Priority 3)
1. Asset verification
2. Build testing
3. Documentation
4. Final code review
5. Security scan

---

**End of Gap Report**
