# AMARKTAI NETWORK — FULL REPO FORENSIC AUDIT REPORT

**Role:** Senior Full-Stack Auditor + Release Manager  
**Audit Type:** READ-ONLY — No code changes applied  
**Repo:** `sharetheherbman-debug/Amarktai-Network---Deployment`  
**Branch:** `copilot/full-repo-forensic-audit`  
**Commit SHA:** `735ee4e6aa14d504cb92c43f70078450d7cf81b9`  
**Date:** 2026-02-19

---

## SECTION 0 — Evidence Pack

### Repo Branch + Commit
- Branch: `copilot/full-repo-forensic-audit`
- Commit: `735ee4e6aa14d504cb92c43f70078450d7cf81b9`
- Parent: `28bbccf` (Merge PR #146 — fix-frontend-visual-bugs)

### Frontend Build Assumptions
- **`homepage`**: NOT SET in `frontend/package.json` (defaults to `/`)
- **`proxy`**: NOT SET in `frontend/package.json`
- **API base URL**: Resolved at runtime from `REACT_APP_API_BASE` or `REACT_APP_API_URL` env vars; defaults to `/api` (relative, works with Nginx reverse proxy)
- **Build tool**: `craco` wrapping CRA (Create React App)
- **Asset paths**: `/assets/final-logo-v2.png`, `/assets/*.png` — served from `public/assets/` at build root

### Backend Base Path Assumptions
- **API prefix**: All backend routes are at `/api/*` (either via `prefix="/api/..."` on individual routers, or via `app.include_router(api_router, prefix="/api")` for inline routes in `server.py`)
- **OpenAPI docs**: `/docs` (FastAPI default), `/openapi.json`
- **WebSocket endpoint**: `/api/ws` (defined in `backend/routes/websocket.py:47`)
- **SSE fallback endpoint**: `/api/realtime/events` (defined in `backend/routes/realtime.py`)

### Global Config / Constants Controlling URLs or Flags
| Variable | Default | Source | Impact |
|---|---|---|---|
| `REACT_APP_API_BASE` / `REACT_APP_API_URL` | (unset → `/api`) | Frontend env | All HTTP API calls |
| `ENABLE_REALTIME` | `true` | `.env.example`, `backend/server.py:3123` | WebSocket router mount |
| `ENABLE_TRADING` | `false` | `.env.example` | Legacy master trading switch |
| `PAPER_TRADING` / `ENABLE_PAPER_TRADING` | `0` / `true` | `.env.example` / `server.py:87` | Paper mode gate |
| `LIVE_TRADING` / `ENABLE_LIVE_TRADING` | `0` / `false` | `.env.example` | Live mode gate |
| `AUTOPILOT_ENABLED` / `ENABLE_AUTOPILOT` | `0` / `false` | `.env.example` | Autopilot gate |
| `JWT_SECRET` | (placeholder) | `.env.example:70` | Auth signing |
| `ADMIN_PASSWORD` | (placeholder) | `.env.example:78` | Admin unlock |
| `CORS_ALLOWED_ORIGINS` | (unset → `["*"]`) | `server.py:396` | CORS — defaults to wildcard if not set |
| `MONGO_URL` / `MONGO_URI` | `mongodb://localhost:27017` | `.env.example` | Database |
| `INVITE_CODE` | `AMARKTAI2024` | `.env.example:90` | Registration gate |

---

## SECTION 1 — Executive Summary

1. **`routes.admin_endpoints` is NOT MOUNTED** (deliberately removed as "duplicate"). This kills every admin endpoint: `POST /api/admin/unlock`, `GET /api/admin/users`, `GET /api/admin/bots`, `POST /api/admin/runtime/reset`, all emergency-stop override routes, and dozens more. Admin panel is completely non-functional.
2. **`routes.ai_chat` is NOT MOUNTED** (removed as "duplicate of chat_enhanced"). This kills `POST /api/ai/chat` (used for saving chat messages), `POST /api/ai/chat/greeting` (dashboard greeting on login), and related endpoints. The initial AI chat greeting on every login is broken.
3. **Double `/api` path bug in `useDashboardState.js:2064`**: The start-fresh reset call resolves to `/api/api/admin/start-fresh` instead of `/api/admin/start-fresh`. Reset is silently broken.
4. **Double `/api` path bug in `FetchAISection.js:22,31`**: The FetchAI status and signals calls resolve to `/api/api/fetchai/status` and `/api/api/fetchai/signals/{pair}`. FetchAI section is silently broken.
5. **`POST /admin/email/broadcast` does not exist**: Frontend (`useDashboardState.js:2882`) calls this path, but backend only has `POST /api/admin/email-all-users`. Admin broadcast emails always fail.
6. **Admin emergency-stop override routes missing**: Frontend calls `GET /api/admin/emergency-stop/status`, `POST /api/admin/emergency-stop/global`, `POST /api/admin/emergency-stop/user`, `POST /api/admin/emergency-stop/clear-user` — all in `admin_endpoints.py` which is not mounted.
7. **WebSocket event contract mismatch**: Frontend listens for event type `trades` and `balances`; backend emits `trade_executed`/`trade_opened`/`trade_closed` and `balance_updated`. Live trades panel and wallet balances never update in real-time.
8. **CORS defaults to wildcard `["*"]`** if `CORS_ALLOWED_ORIGINS` is not set in production `.env`. This is a security risk for a financial platform.
9. **Two feature-flag duplicates** (`ENABLE_TRADING` vs `PAPER_TRADING`/`LIVE_TRADING`, `ENABLE_AUTOPILOT` vs `AUTOPILOT_ENABLED`) create confusion about which flags actually gate trading operations.
10. **`autopilot_control.py` and `admin_start_fresh.py`** define routes with `/api/` baked into the path string while using a bare `APIRouter()`. This pattern is inconsistent and error-prone; the frontend's double-/api calls against start-fresh come directly from this pattern being echoed on the client side.
11. **Admin `GET /api/admin/users`** (list all users for admin panel) is only in `admin_endpoints.py` which is NOT mounted. The admin panel's user list loads a 404.
12. **`POST /api/admin/runtime/reset`** (runtime reset in SystemModeSection) is only in `admin_endpoints.py`. The Runtime Reset button in the System Mode section always fails with 404.

---

## SECTION 2 — GO-LIVE BLOCKERS (CRITICAL)

---

### BLOCKER 1: `routes.admin_endpoints` Not Mounted — Admin Panel Non-Functional

**Severity:** CRITICAL  
**Evidence:**
```python
# backend/server.py:3061
# REMOVED: routes.admin_endpoints - duplicate of admin_enhanced (keep enhanced version)
("routes.admin_enhanced", "Admin Enhanced"),  # NEW - User dropdown, bot profit/loss
```
`admin_enhanced.py` only has 4 routes (`/users/list`, `/users/{user_id}/bots`, `/dashboard/stats`, `/system-stats`). `admin_endpoints.py` has ~50 routes and is not mounted.  
**Root cause:** `admin_endpoints.py` was incorrectly labelled as a duplicate of `admin_enhanced.py` and removed from `routers_to_mount`. The two files are NOT duplicates — `admin_enhanced` is a small supplement; `admin_endpoints` is the canonical admin module.  
**User-visible impact:**  
- Typing "show admin" and entering the correct password → POST `/api/admin/unlock` → 404 → "Admin panel unlocked" message appears but `showAdmin` stays false (the `post('/admin/unlock')` promise throws, caught by try/catch at `useDashboardState.js:1744`, displaying "Invalid admin password").
- Admin panel user list, bots list, emergency overrides, runtime reset, user-logout, audit events — all 404.  
**How to verify:**  
```bash
curl -X POST http://localhost:8000/api/admin/unlock \
  -H "Authorization: Bearer <valid_token>" \
  -H "Content-Type: application/json" \
  -d '{"password":"your_admin_password"}'
# Expected: 200 {"success": true}
# Actual:   404 {"detail": "Not Found"}
```

---

### BLOCKER 2: `routes.ai_chat` Not Mounted — Login Greeting & Chat Save Broken

**Severity:** CRITICAL  
**Evidence:**
```python
# backend/server.py:3082
# REMOVED: routes.ai_chat - duplicate of chat_enhanced (keep enhanced version)
("routes.chat_enhanced", "AI Chat Enhanced"),
```
`ai_chat.py` routes (prefix `/api/ai`): `POST /chat` (save message), `POST /chat/greeting`, `GET /chat/history`, `POST /chat/clear`, `DELETE /chat/history`, `POST /chat/greeting`.  
`chat_enhanced.py` routes (prefix `/api/chat`): `POST /clear`, `GET /daily-summary`, `GET /welcome`, `POST /session/end`. These are completely different endpoints.  
**Root cause:** Removed as "duplicate" but the two files serve different URL namespaces — `/api/ai/chat` vs `/api/chat`.  
**User-visible impact:**  
- Every login: `AIChatPanel.js` calls `post('/ai/chat/greeting')` → 404 → falls back to hardcoded "Welcome!" string, no system state, no since-last-login report.
- Every chat message saved via `post('/ai/chat', {role, content, log_only, ...})` → 404 → chat messages not persisted server-side.  
**How to verify:**  
```bash
curl -X POST http://localhost:8000/api/ai/chat/greeting \
  -H "Authorization: Bearer <valid_token>"
# Expected: 200 {"content": "...", "system_state": {...}}
# Actual:   404
```

---

### BLOCKER 3: Double `/api` Path — Start-Fresh Reset Always 404

**Severity:** CRITICAL  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:2064
const response = await axios.post(`${API}/api/admin/start-fresh`, {
  confirmation_phrase: confirmPhrase,
  scope: 'paper_only',
  also_reset_risk_locks: true
}, axiosConfig);
```
`API = ''` (line 25), so path = `/api/admin/start-fresh`.  
`axios = apiClient` which has `baseURL: '/api'`.  
Axios `combineURLs('/api', '/api/admin/start-fresh')` = **`/api/api/admin/start-fresh`**.  
Backend route: `backend/routes/admin_start_fresh.py:30` → `@router.post("/api/admin/start-fresh")` (no router prefix) → final FastAPI path: `/api/admin/start-fresh`.  
**Root cause:** The path literal already includes `/api/` but `API` is empty-string and `apiClient` adds `/api` via baseURL.  
**User-visible impact:** Paper trading reset (Start Fresh modal) always returns 404. `setPaperResetError` shows error, `toast.success` never fires.  
**How to verify:**  
```bash
# DevTools: Network tab, trigger Start Fresh → observe request URL /api/api/admin/start-fresh → 404
curl -X POST http://localhost:8000/api/api/admin/start-fresh  # 404
curl -X POST http://localhost:8000/api/admin/start-fresh -H "Authorization: Bearer <admin_token>" \
  -d '{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}'  # 200
```

---

### BLOCKER 4: Double `/api` Path — FetchAI Section Always 404

**Severity:** CRITICAL  
**Evidence:**
```javascript
// frontend/src/pages/dashboard/sections/FetchAISection.js:22
const statusResponse = await apiClient.get('/api/fetchai/status');
// line 31
const response = await apiClient.get(`/api/fetchai/signals/${pair}`);
```
`apiClient` has `baseURL: '/api'`, so `combineURLs('/api', '/api/fetchai/status')` = **`/api/api/fetchai/status`**.  
Backend route: `backend/routes/fetchai.py:151` → `prefix="/api/fetchai"` + `@router.get("/status")` → final path: `/api/fetchai/status`.  
**Root cause:** Redundant `/api/` prefix in the request path string passed to `apiClient`.  
**User-visible impact:** FetchAI section loads with 404 errors; all FetchAI market signals and status are unavailable.  
**How to verify:**  
```bash
# DevTools: Network tab, navigate to FetchAI section → requests show /api/api/fetchai/status → 404
```

---

### BLOCKER 5: `POST /api/admin/runtime/reset` Not Mounted — Runtime Reset Broken

**Severity:** CRITICAL  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:336
@router.post("/runtime/reset")  # prefix="/api/admin" → /api/admin/runtime/reset
```
```javascript
// frontend/src/pages/dashboard/sections/SystemModeSection.js:121
const response = await apiClient.post('/admin/runtime/reset', {
  confirmation: 'RESET_RUNTIME',
  scope: 'runtime_only'
});
```
`admin_endpoints.py` not mounted → route doesn't exist.  
**Root cause:** Same as Blocker 1 — `admin_endpoints.py` excluded.  
**User-visible impact:** "Runtime Reset" button in System Mode section always returns 404. Users cannot reset runtime state.  
**How to verify:**  
```bash
curl -X POST http://localhost:8000/api/admin/runtime/reset \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"confirmation":"RESET_RUNTIME","scope":"runtime_only"}'
# 404
```

---

## SECTION 3 — HIGH / MED / LOW Findings

---

### HIGH-1: `GET /api/admin/users` Not Mounted — Admin User List Broken

**Severity:** HIGH  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:452
@router.get("/users")  # prefix="/api/admin" → /api/admin/users
```
```javascript
// frontend/src/hooks/useDashboardState.js:1620
const res = await axios.get(`${API}/admin/users`, axiosConfig);
// also line 2958
const res = await axios.get(`${API}/admin/users`, axiosConfig);
```
`admin_endpoints.py` not mounted.  
**User-visible impact:** Admin panel user dropdown/list is always empty (or errors silently).

---

### HIGH-2: `GET /api/admin/bots` Not Mounted — Admin Bot List Broken

**Severity:** HIGH  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:1575
@router.get("/bots")  # prefix="/api/admin" → /api/admin/bots
```
```javascript
// frontend/src/hooks/useDashboardState.js:2972
const res = await axios.get(`${API}/admin/bots`, axiosConfig);
```
`admin_endpoints.py` not mounted.  
**User-visible impact:** Admin bot list always 404 / empty.

---

### HIGH-3: Admin Emergency-Stop Override Routes Not Mounted

**Severity:** HIGH  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:2897,2918,2951,2977
@router.get("/emergency-stop/status")     # → /api/admin/emergency-stop/status
@router.post("/emergency-stop/global")    # → /api/admin/emergency-stop/global
@router.post("/emergency-stop/user")      # → /api/admin/emergency-stop/user
@router.post("/emergency-stop/clear-user")# → /api/admin/emergency-stop/clear-user
```
```javascript
// frontend/src/hooks/useDashboardState.js:2984,2994,3004,3012
const res = await axios.get(`${API}/admin/emergency-stop/status`, axiosConfig);
await axios.post(`${API}/admin/emergency-stop/global`, ...);
await axios.post(`${API}/admin/emergency-stop/user`, ...);
await axios.post(`${API}/admin/emergency-stop/clear-user`, ...);
```
`admin_endpoints.py` not mounted.  
**User-visible impact:** Admin cannot manage per-user or global emergency stop overrides from the UI.

---

### HIGH-4: `POST /api/admin/email/broadcast` Does Not Exist

**Severity:** HIGH  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:2882
const result = await post('/admin/email/broadcast', { subject, message });
```
No route in any file matches `POST /api/admin/email/broadcast`. Backend has `POST /api/admin/email-all-users` (server.py:2105).  
**User-visible impact:** Admin broadcast email function silently fails (404).

---

### HIGH-5: CORS Defaults to Wildcard `["*"]` in Production

**Severity:** HIGH  
**Evidence:**
```python
# backend/server.py:416-417
if not origins:
    logger.warning("⚠️ CORS: No origins configured, defaulting to wildcard ['*'] - INSECURE FOR PRODUCTION")
    return ["*"]
```
If `CORS_ALLOWED_ORIGINS` is not set in the production `.env`, CORS is open to all origins. On a financial platform, this allows cross-site request forgery from any domain.  
**User-visible impact:** Security vulnerability; no direct user functionality impact.

---

### HIGH-6: `POST /api/admin/users/{user_id}/logout` Not Mounted

**Severity:** HIGH  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:857
@router.post("/users/{user_id}/logout")   # → /api/admin/users/{user_id}/logout
```
```javascript
// frontend/src/hooks/useDashboardState.js:3135
await axios.post(`${API}/admin/users/${userId}/logout`, {}, axiosConfig);
```
`admin_endpoints.py` not mounted.  
**User-visible impact:** Admin cannot force-logout individual users.

---

### HIGH-7: Admin Bot Control Routes Not Mounted

**Severity:** HIGH  
**Evidence:**
```python
# backend/routes/admin_endpoints.py:1683,1763,1810,1857,1954
@router.post("/bots/{bot_id}/mode")     # → /api/admin/bots/{bot_id}/mode
@router.post("/bots/{bot_id}/pause")    # → /api/admin/bots/{bot_id}/pause
@router.post("/bots/{bot_id}/resume")   # → /api/admin/bots/{bot_id}/resume
@router.post("/bots/{bot_id}/restart")  # → /api/admin/bots/{bot_id}/restart
@router.post("/bots/{bot_id}/exchange") # → /api/admin/bots/{bot_id}/exchange
```
```javascript
// frontend/src/hooks/useDashboardState.js:3151,3171,3188
await axios.post(`${API}/admin/bots/${botId}/mode`, ...);
await axios.post(`${API}/admin/bots/${botId}/${action}`, ...);
await axios.post(`${API}/admin/bots/${botId}/exchange`, ...);
```
`admin_endpoints.py` not mounted.  
**User-visible impact:** All admin bot control buttons (pause, resume, restart, mode change, exchange reassign) return 404.

---

### MED-1: WebSocket Event Name Mismatch — Live Trades Panel Never Updates

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/components/LiveTradesPanel.js:38
useRealtimeEvent('trades', (newTrade) => { ... });
// frontend/src/components/ComparisonGraphs.js:81
useRealtimeEvent('trades', () => { ... });
```
```python
# backend/realtime_events.py:100,109,118
{"type": "trade_executed", ...}
{"type": "trade_opened", ...}
{"type": "trade_closed", ...}
```
Backend emits `trade_executed`, `trade_opened`, `trade_closed` — never `trades`.  
**User-visible impact:** Live Trades panel does not update in real-time; users must manually refresh.

---

### MED-2: WebSocket Event Name Mismatch — Wallet Balances Never Update

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/components/WalletHub.js:95
useRealtimeEvent('balances', (data) => { ... });
```
```python
# backend/realtime_events.py:226
{"type": "balance_updated", ...}
```
Backend emits `balance_updated`, not `balances`.  
**User-visible impact:** Wallet balance card does not update in real-time.

---

### MED-3: `transfer_updated` Event Never Emitted by Backend

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/components/TransferHistory.js:41
useRealtimeEvent('transfer_updated', (data) => { ... });
// frontend/src/components/AdminApproval.js:38
useRealtimeEvent('transfer_updated', () => { ... });
```
Searching all `.py` files for `"transfer_updated"` returns no backend emission. Backend emits `wallet` and `balance_updated`.  
**User-visible impact:** Transfer history and admin approval panels don't update in real-time after a transfer.

---

### MED-4: `GET /api/analytics/countdown-to-million` vs `/countdown` Mismatch

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:1443
const res = await axios.get(`${API}/analytics/countdown-to-million`, axiosConfig);
```
```python
# backend/routes/analytics_api.py:738
@router.get("/countdown")   # prefix="/api/analytics" → /api/analytics/countdown
# backend/server.py:1549
@api_router.get("/analytics/countdown-to-million")   # → /api/analytics/countdown-to-million ✓
```
The inline server.py route at line 1549 exists and matches, so this is actually functional. However, two routes serve similar purposes — potential confusion.  
**User-visible impact:** Works, but duplicated logic.

---

### MED-5: `GET /api/analytics/profit-history` vs `/analytics/pnl_timeseries`

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:1549
const res = await axios.get(`${API}/analytics/profit-history?period=${graphPeriod}`, axiosConfig);
```
```python
# backend/server.py:1425
@api_router.get("/analytics/profit-history")   # → /api/analytics/profit-history ✓
# backend/routes/analytics_api.py:19
@router.get("/pnl_timeseries")   # → /api/analytics/pnl_timeseries (different name)
```
The server.py inline route exists and matches. Both exist but serve slightly different shapes.

---

### MED-6: `POST /api/admin/users/{user_id}/reset-password` Method Conflict

**Severity:** MEDIUM  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:3081
await axios.post(`${API}/admin/users/${userId}/reset-password`, { new_password }, axiosConfig);
```
```python
# backend/routes/admin_endpoints.py:713
@router.post("/users/{user_id}/reset-password")   # NOT mounted
# backend/server.py:2246
@api_router.put("/admin/users/{target_user_id}/password")   # different method (PUT) and path
```
Frontend sends `POST /api/admin/users/{userId}/reset-password`; the only mounted route is `PUT /api/admin/users/{target_user_id}/password`. Method and path are both different.  
**User-visible impact:** Admin cannot reset individual user passwords from the panel.

---

### MED-7: Two Sets of Feature Flags for the Same Features

**Severity:** MEDIUM  
**Evidence:**
```
# .env.example:9,14,19
PAPER_TRADING=0       # New flag
LIVE_TRADING=0        # New flag
AUTOPILOT_ENABLED=0   # New flag

# .env.example:31,32
ENABLE_TRADING=false      # Legacy flag
ENABLE_AUTOPILOT=false    # Legacy flag
```
```python
# backend/server.py:87-92
paper_trading = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
live_trading = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'
autopilot = os.getenv('ENABLE_AUTOPILOT', 'false').lower() == 'true'
```
The `.env.example` uses `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED` but `server.py` reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`. The new `.env.example` values are silently ignored by the backend.  
**User-visible impact:** Setting `PAPER_TRADING=1` in `.env` does NOT enable paper trading. You must set `ENABLE_PAPER_TRADING=true`.

---

### LOW-1: `POST /api/admin/users/{user_id}/block` — Method Mismatch

**Severity:** LOW  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:2915
await axios.put(`${API}/admin/users/${userId}/block`, { blocked: true }, axiosConfig);
```
```python
# backend/routes/admin_endpoints.py:611 (NOT mounted)
@router.post("/users/{user_id}/block")   # POST, not PUT
# backend/server.py:2214
@api_router.put("/admin/users/{target_user_id}/block")   # PUT ✓ but admin_endpoints not mounted
```
The server.py inline route is `PUT` which matches frontend's `PUT`. However, `admin_endpoints` has `POST` — if ever remounted, could create duplication.  
**User-visible impact:** Low; as long as server.py inline route is the active one, block user works.

---

### LOW-2: `bot_control.py.REMOVED` File Still Present in routes/

**Severity:** LOW  
**Evidence:**
```
backend/routes/bot_control.py.REMOVED
```
A file with `.REMOVED` extension in the routes directory. While it won't be imported, it's confusing for future developers and creates clutter.

---

### LOW-3: `GET /api/ai/insights` and `GET /api/ml/predict` Not Clearly Mapped

**Severity:** LOW  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:2767
const result = await get('/ai/insights');   // → /api/ai/insights
// line 2798
const result = await get('/ml/predict?symbol=BTC-ZAR&platform=luno');   // → /api/ml/predict
```
`/api/ai/insights` — mapped in `analytics_api.py:883` as `@router.get("/insights")` with `prefix="/api/analytics"` → `/api/analytics/insights` (mismatch!). `routes.ai_chat` has no `/insights` route. This may 404.  
`/api/ml/predict` — requires search; let me note as unverified.

---

### LOW-4: `POST /api/profits/reinvest` May Not Exist

**Severity:** LOW  
**Evidence:**
```javascript
// frontend/src/hooks/useDashboardState.js:2841
const result = await post('/profits/reinvest', {});   // → /api/profits/reinvest
```
Searching backend routes for `profits/reinvest` found no matching route. `autopilot_growth.py` has `POST /api/autopilot/growth/trigger`. This may be broken.

---

## SECTION 4 — Backend Route Truth Table (Complete)

Only the most significant routes are listed. Routes are computed as `router.prefix + @router.path`. Inline `api_router` routes are at `app.include_router(api_router, prefix="/api")`.

| Method | Full Path | Handler | Auth | Source File:Line |
|--------|-----------|---------|------|-----------------|
| POST | `/api/auth/register` | `register` | none | `routes/auth.py:16` |
| POST | `/api/auth/login` | `login` | none | `routes/auth.py:108` |
| GET | `/api/auth/me` | `get_me` | user | `routes/auth.py:186` |
| PUT | `/api/auth/profile` | `update_profile` | user | `routes/auth.py:233` |
| GET | `/api/auth/profile` | `get_profile` | user | `routes/auth.py:281` |
| GET | `/api/bots/status` | `get_bots_status` | user | `routes/bot_lifecycle.py` |
| POST | `/api/bots` | (inline) | user | `server.py` |
| DELETE | `/api/bots/{bot_id}` | (inline) | user | `server.py` |
| PUT | `/api/bots/{bot_id}` | (inline) | user | `server.py` |
| POST | `/api/bots/batch-create` | (inline) | user | `server.py` |
| GET | `/api/bots/eligible-for-promotion` | (inline) | user | `server.py` |
| POST | `/api/bots/confirm-live-switch` | (inline) | user | `server.py` |
| GET | `/api/trades/recent` | `get_recent_trades` | user | `routes/trades.py` |
| GET | `/api/portfolio/summary` | `get_portfolio_summary` | user | `routes/ledger_endpoints.py:24` |
| GET | `/api/profits` | `get_profits` | user | `routes/ledger_endpoints.py:88` |
| GET | `/api/system/mode` | `get_mode` | user | `routes/system_mode.py` |
| PUT | `/api/system/mode` | `set_mode` | user | `server.py:2016` (inline) |
| GET | `/api/system/status` | `get_status` | user | `routes/system_status.py:23` |
| GET | `/api/system/since-last-login` | `get_since_last_login` | user | `routes/system_status.py:157` |
| GET | `/api/system/health` | `get_health` | user | `routes/system_status.py:271` |
| POST | `/api/system/emergency-stop` | `emergency_stop` | user | `routes/emergency_stop_endpoints.py:20` |
| POST | `/api/system/emergency-resume` | `emergency_resume` | user | `routes/emergency_stop_endpoints.py:82` |
| GET | `/api/system/emergency-stop/status` | `get_status` | user | `routes/emergency_stop_endpoints.py:135` |
| GET | `/api/keys/status` | `get_key_status` | user | `routes/keys.py:108` |
| POST | `/api/keys/save` | `save_key` | user | `routes/keys.py:262` |
| POST | `/api/keys/test` | `test_key` | user | `routes/keys.py:407` |
| DELETE | `/api/keys/{provider}` | `delete_key` | user | `routes/keys.py` |
| GET | `/api/analytics/profit-history` | (inline) | user | `server.py:1425` |
| GET | `/api/analytics/equity` | `get_equity` | user | `routes/analytics_api.py:291` |
| GET | `/api/analytics/drawdown` | `get_drawdown` | user | `routes/analytics_api.py:385` |
| GET | `/api/analytics/win_rate` | `get_win_rate` | user | `routes/analytics_api.py:507` |
| GET | `/api/analytics/countdown-to-million` | (inline) | user | `server.py:1549` |
| GET | `/api/overview/snapshot` | `get_overview_snapshot` | user | `routes/dashboard_overview.py:193` |
| GET | `/api/dashboard/overview` | `get_dashboard_overview` | user | `routes/dashboard_overview.py:50` |
| GET | `/api/wallet/paper` | `get_paper_wallet` | user | `routes/wallet_hub.py` |
| GET | `/api/wallet/balances` | `get_balances` | user | `routes/wallet_hub.py` |
| GET | `/api/prices/live` | `get_live_prices` | user | `routes/prices.py:19` |
| GET | `/api/risk/status` | `get_risk_status` | user | `routes/risk_management.py:68` |
| POST | `/api/risk/resume-all` | `resume_all` | user | `routes/risk_management.py:467` |
| POST | `/api/risk/daily-loss-lock/reset` | `reset_daily_loss_lock` | user | `routes/risk_management.py:305` |
| POST | `/api/risk/bodyguard/reset` | `reset_bodyguard` | user | `routes/risk_management.py:393` |
| GET | `/api/autonomy/status` | `get_autonomy_status` | user | `routes/autonomy_control.py` |
| GET | `/api/autopilot/status` | `get_autopilot_status` | user | `routes/autopilot_control.py:19` |
| POST | `/api/autopilot/toggle` | `toggle_autopilot` | user | `routes/autopilot_control.py:49` |
| GET | `/api/autopilot/growth/status` | `get_growth_status` | user | `routes/autopilot_growth.py:20` |
| GET | `/api/autopilot/reinvest/status` | `get_reinvest_status` | user | `routes/autopilot_growth.py:80` |
| GET | `/api/autopilot/user-settings` | `get_user_settings` | user | `routes/autopilot_config.py:27` |
| POST | `/api/autopilot/configure` | `configure_autopilot` | user | `routes/autopilot_config.py:65` |
| GET | `/api/ai/status` | `get_ai_status` | user | `routes/ai_status.py:18` |
| GET | `/api/ai/rl-status` | `get_rl_status` | user | `routes/ai_rl.py:17` |
| GET | `/api/ai/rl-recommendations/{bot_id}` | `get_recommendations` | user | `routes/ai_rl.py:84` |
| GET | `/api/agents/status` | `get_agents_status` | user | `routes/agents.py:150` |
| POST | `/api/agents/create` | `create_agent` | user | `routes/agents.py:30` |
| GET | `/api/huggingface/test-connection` | `test_connection` | user | `routes/huggingface.py:32` |
| GET | `/api/huggingface/tasks` | `get_tasks` | user | `routes/huggingface.py:156` |
| POST | `/api/huggingface/analyze-sentiment` | `analyze_sentiment` | user | `routes/huggingface.py:217` |
| POST | `/api/huggingface/summarize` | `summarize` | user | `routes/huggingface.py:278` |
| POST | `/api/huggingface/classify` | `classify` | user | `routes/huggingface.py:346` |
| POST | `/api/huggingface/embeddings` | `get_embeddings` | user | `routes/huggingface.py:420` |
| GET | `/api/fetchai/status` | `get_status` | user | `routes/fetchai.py:151` |
| GET | `/api/fetchai/signals/{pair}` | `get_signals` | user | `routes/fetchai.py:76` |
| GET | `/api/chat/history` | `get_history` | user | `routes/chat_endpoints.py:78` |
| POST | `/api/chat/message` | `send_message` | user | `routes/chat_endpoints.py:21` |
| POST | `/api/chat/clear` | `clear_chat` | user | `routes/chat_enhanced.py:27` |
| GET | `/api/admin/storage` | (inline) | admin | `server.py:1181` |
| GET | `/api/admin/health-check` | (inline) | admin | `server.py:1786` |
| DELETE | `/api/admin/users/{target_user_id}` | (inline) | admin | `server.py:2163` |
| PUT | `/api/admin/users/{target_user_id}/block` | (inline) | admin | `server.py:2214` |
| PUT | `/api/admin/users/{target_user_id}/password` | (inline) | admin | `server.py:2246` |
| POST | `/api/admin/emergency-stop` | (inline) | admin | `server.py:2684` |
| POST | `/api/admin/emergency-resume` | (inline) | admin | `server.py:2763` |
| GET | `/api/admin/users/list` | `get_users_list` | admin | `routes/admin_enhanced.py:22` |
| GET | `/api/admin/users/{user_id}/bots` | `get_user_bots` | admin | `routes/admin_enhanced.py:68` |
| GET | `/api/admin/dashboard/stats` | `get_dashboard_stats` | admin | `routes/admin_enhanced.py:156` |
| GET | `/api/admin/system-stats` | `get_system_stats` | admin | `routes/admin_enhanced.py:219` |
| POST | `/api/admin/start-fresh` | `start_fresh` | admin | `routes/admin_start_fresh.py:30` |
| POST | `/api/admin/reset-user-data` | `reset_user_data` | admin | `routes/admin_start_fresh.py:230` |
| POST | `/api/bots/reset` | `reset_bots` | admin | `routes/admin_start_fresh.py:380` |
| WS | `/api/ws` | `websocket_endpoint` | token (query) | `routes/websocket.py:47` |
| GET | `/api/realtime/events` | SSE endpoint | token (query) | `routes/realtime.py` |
| **MISSING** | `/api/admin/unlock` | `unlock_admin_panel` | user | `routes/admin_endpoints.py:156` — NOT MOUNTED |
| **MISSING** | `/api/admin/users` | `list_users` | admin | `routes/admin_endpoints.py:452` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots` | `list_admin_bots` | admin | `routes/admin_endpoints.py:1575` — NOT MOUNTED |
| **MISSING** | `/api/admin/runtime/reset` | `runtime_reset` | admin | `routes/admin_endpoints.py:336` — NOT MOUNTED |
| **MISSING** | `/api/admin/emergency-stop/status` | `get_emergency_status` | admin | `routes/admin_endpoints.py:2897` — NOT MOUNTED |
| **MISSING** | `/api/admin/emergency-stop/global` | `global_override` | admin | `routes/admin_endpoints.py:2918` — NOT MOUNTED |
| **MISSING** | `/api/admin/emergency-stop/user` | `user_override` | admin | `routes/admin_endpoints.py:2951` — NOT MOUNTED |
| **MISSING** | `/api/admin/emergency-stop/clear-user` | `clear_user_override` | admin | `routes/admin_endpoints.py:2977` — NOT MOUNTED |
| **MISSING** | `/api/admin/users/{user_id}/logout` | `logout_user` | admin | `routes/admin_endpoints.py:857` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots/{bot_id}/mode` | `set_bot_mode` | admin | `routes/admin_endpoints.py:1683` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots/{bot_id}/pause` | `pause_bot` | admin | `routes/admin_endpoints.py:1763` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots/{bot_id}/resume` | `resume_bot` | admin | `routes/admin_endpoints.py:1810` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots/{bot_id}/restart` | `restart_bot` | admin | `routes/admin_endpoints.py:1857` — NOT MOUNTED |
| **MISSING** | `/api/admin/bots/{bot_id}/exchange` | `reassign_exchange` | admin | `routes/admin_endpoints.py:1954` — NOT MOUNTED |
| **MISSING** | `/api/ai/chat` | `chat` (log-only) | user | `routes/ai_chat.py:1385` — NOT MOUNTED |
| **MISSING** | `/api/ai/chat/greeting` | `get_greeting` | user | `routes/ai_chat.py:2068` — NOT MOUNTED |
| **MISSING** | `/api/ai/chat/history` | `get_history` | user | `routes/ai_chat.py:1963` — NOT MOUNTED |

---

## SECTION 5 — Frontend Network Call Table (Complete)

`apiClient` calls use `baseURL: '/api'` → final path = `/api` + path.  
`axios` calls use `axios = apiClient` (same baseURL). `API = ''`.  
`post('/x')` = `apiClient.post('/x')` = `/api/x`. `axios.get(\`${API}/x\`)` = `/api/x`.

| Method | Final URL | Called From | Auth | Expected Response |
|--------|-----------|-------------|------|-------------------|
| POST | `/api/auth/login` | `Login.js:29` | none | `{access_token, user}` |
| POST | `/api/auth/register` | `Register.js:8` | none | `{access_token, user}` |
| GET | `/api/auth/me` | `useDashboardData.js:87`, `useDashboardState.js:1167` | Bearer | `{id, email, first_name, ...}` |
| PUT | `/api/auth/profile` | `useDashboardState.js:2124`, `2511` | Bearer | `{...user}` |
| GET | `/api/bots/status` | `useDashboardData.js:97`, `useDashboardState.js:1179` | Bearer | `{bots: [...]}` |
| POST | `/api/bots` | `useDashboardState.js:2172` | Bearer | `{bot}` |
| DELETE | `/api/bots/{botId}` | `useDashboardState.js:2247` | Bearer | `{ok: true}` |
| PUT | `/api/bots/{botId}` | `useDashboardState.js:2257,2269,2287` | Bearer | `{bot}` |
| POST | `/api/bots/batch-create` | `useDashboardState.js:2326` | Bearer | `{bots}` |
| GET | `/api/bots/eligible-for-promotion` | `useDashboardState.js:1508` | Bearer | `{bots}` |
| POST | `/api/bots/confirm-live-switch` | `useDashboardState.js:1520` | Bearer | `{ok}` |
| POST | `/api/bots/evolve` | `useDashboardState.js:2728` | Bearer | `{evolved}` |
| POST | `/api/bots/uagent` | `useDashboardState.js:2202` | Bearer | `{bot}` |
| POST | `/api/bots/flokx` | `useDashboardState.js:2229` | Bearer | `{bot}` |
| GET | `/api/trades/recent?limit=50` | `useDashboardData.js:180`, `useDashboardState.js:1379` | Bearer | `{trades: [...]}` |
| GET | `/api/portfolio/summary` | `useDashboardState.js:1404` | Bearer | `{total_profit, ...}` |
| GET | `/api/system/mode` | `useDashboardData.js:128`, `useDashboardState.js:1420` | Bearer | `{paper_trading, live_trading, ...}` |
| PUT | `/api/system/mode` | `useDashboardState.js:2016` | Bearer | `{ok}` |
| GET | `/api/system/status` | `useDashboardData.js:142`, `useDashboardState.js:1639` | Bearer | `{status}` |
| POST | `/api/system/emergency-stop` | `useDashboardState.js:2043` | Bearer | `{ok}` |
| GET | `/api/keys/status` | `useDashboardData.js:152`, `useDashboardState.js:1433` | Bearer | `{providers: {...}}` |
| POST | `/api/keys/save` | `useDashboardState.js:2393` | Bearer | `{ok}` |
| POST | `/api/keys/test` | `useDashboardState.js:2433` | Bearer | `{ok, latency_ms}` |
| DELETE | `/api/keys/{provider}` | `useDashboardState.js:2456` | Bearer | `{ok}` |
| GET | `/api/analytics/profit-history?period=...` | `useDashboardState.js:1549` | Bearer | `{data: [...]}` |
| GET | `/api/analytics/equity?range=...` | `useDashboardState.js:1566` | Bearer | `{data: [...]}` |
| GET | `/api/analytics/drawdown?range=...` | `useDashboardState.js:1576` | Bearer | `{data: [...]}` |
| GET | `/api/analytics/win_rate?period=...` | `useDashboardState.js:1586` | Bearer | `{win_rate}` |
| GET | `/api/analytics/countdown-to-million` | `useDashboardState.js:1443` | Bearer | `{days_remaining, ...}` |
| GET | `/api/overview/snapshot` | `useDashboardData.js:108`, `useDashboardState.js:1205` | Bearer | `{snapshot}` |
| GET | `/api/wallet/paper` | `useDashboardState.js:1206` | Bearer | `{balance, ...}` |
| GET | `/api/wallet/balances` | `useDashboardState.js:1537` | Bearer | `{balances}` |
| GET | `/api/wallet/deposit-address` | `useDashboardState.js:1611` | Bearer | `{address}` |
| GET | `/api/wallet/requirements` | `useDashboardState.js:1984` | Bearer | `{requirements}` |
| GET | `/api/prices/live` | `useDashboardData.js:200` | Bearer | `{BTC-ZAR, ETH-ZAR, ...}` |
| GET | `/api/risk/status` | `useDashboardState.js:1258` | Bearer | `{emergency_stop, daily_loss_lock, ...}` |
| POST | `/api/risk/resume-all` | `useDashboardState.js:1330` | Bearer | `{ok}` |
| POST | `/api/risk/daily-loss-lock/reset?confirmation=RESET_RISK_LOCK` | `useDashboardState.js:1349` | Bearer | `{ok}` |
| POST | `/api/risk/bodyguard/reset?confirmation=RESET_BODYGUARD_LOCK` | `useDashboardState.js:1367` | Bearer | `{ok}` |
| GET | `/api/autonomy/status` | `useDashboardState.js:1209`, `SystemModeSection.js:49` | Bearer | `{status}` |
| GET | `/api/ai/status` | `useDashboardState.js:1210` | Bearer | `{openai_configured}` |
| GET | `/api/learning/status` | `useDashboardState.js:1211` | Bearer | `{status}` |
| GET | `/api/autopilot/growth/status` | `useDashboardState.js:1279`, `AutopilotStatusSection.js:30` | Bearer | `{status}` |
| GET | `/api/autopilot/reinvest/status` | `useDashboardState.js:1290`, `AutopilotStatusSection.js:31` | Bearer | `{status}` |
| GET | `/api/autopilot/user-settings` | `AutopilotInsightsPanel.js:48` | Bearer | `{settings}` |
| POST | `/api/autopilot/configure` | `AutopilotInsightsPanel.js:62` | Bearer | `{ok}` |
| GET | `/api/countdowns` | `useDashboardState.js:1452` | Bearer | `{countdowns}` |
| POST | `/api/countdowns` | `useDashboardState.js:1466` | Bearer | `{countdown}` |
| DELETE | `/api/countdowns/{countdownId}` | `useDashboardState.js:1484` | Bearer | `{ok}` |
| GET | `/api/admin/storage` | `useDashboardState.js:1495` | Bearer/Admin | `{storage}` |
| POST | `/api/chat/message` | `useDashboardState.js:1881`, `AIChatPanel.js` | Bearer | `{content, ...}` |
| GET | `/api/chat/history` | `AIChatPanel.js:175,186` | Bearer | `{messages:[...]}` |
| POST | `/api/chat/clear` | `useDashboardState.js:603` | Bearer | `{ok}` |
| GET | `/api/chat/history?days=30&limit=100` | `useDashboardState.js:572` | Bearer | `{messages:[...]}` |
| GET | `/api/ai/rl-status` | `useDashboardState.js:2652`, `AiToolsSection.js:82` | Bearer | `{rl_status}` |
| GET | `/api/ai/rl-recommendations/{botId}` | `useDashboardState.js:2665` | Bearer | `{recommendations}` |
| GET | `/api/agents/status` | `AiToolsSection.js:96` | Bearer | `{agents}` |
| POST | `/api/agents/create` | `AiToolsSection.js:114` | Bearer | `{agent}` |
| GET | `/api/huggingface/test-connection` | `AiToolsSection.js:61` | Bearer | `{ok}` |
| GET | `/api/huggingface/tasks` | `AiToolsSection.js:71` | Bearer | `{tasks}` |
| POST | `/api/huggingface/analyze-sentiment` | `AiToolsSection.js:143` | Bearer | `{sentiment}` |
| POST | `/api/huggingface/summarize` | `AiToolsSection.js:164` | Bearer | `{summary}` |
| POST | `/api/huggingface/classify` | `AiToolsSection.js:185` | Bearer | `{classification}` |
| POST | `/api/huggingface/embeddings` | `AiToolsSection.js:207` | Bearer | `{embeddings}` |
| GET | `/api/api/fetchai/status` ❌ | `FetchAISection.js:22` | Bearer | *DOUBLE /api BUG* |
| GET | `/api/api/fetchai/signals/{pair}` ❌ | `FetchAISection.js:31` | Bearer | *DOUBLE /api BUG* |
| POST | `/api/admin/unlock` ❌ | `useDashboardState.js:1744` | Bearer | *ROUTE MISSING* |
| GET | `/api/admin/users` ❌ | `useDashboardState.js:1620,2958` | Bearer | *ROUTE MISSING* |
| GET | `/api/admin/system-stats` | `useDashboardState.js:1630` | Bearer | `{stats}` |
| GET | `/api/admin/health-check` | `useDashboardState.js:1686` | Bearer | `{health}` |
| GET | `/api/admin/bots` ❌ | `useDashboardState.js:2972` | Bearer | *ROUTE MISSING* |
| GET | `/api/admin/emergency-stop/status` ❌ | `useDashboardState.js:2984` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/emergency-stop/global` ❌ | `useDashboardState.js:2994` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/emergency-stop/user` ❌ | `useDashboardState.js:3004` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/emergency-stop/clear-user` ❌ | `useDashboardState.js:3012` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/users/{userId}/reset-password` ❌ | `useDashboardState.js:3081` | Bearer | *METHOD+PATH MISMATCH* |
| POST | `/api/admin/users/{userId}/block` ⚠️ | `useDashboardState.js:2915` | Bearer | server.py has `PUT` not `POST` |
| POST | `/api/admin/users/{userId}/logout` ❌ | `useDashboardState.js:3135` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/bots/{botId}/mode` ❌ | `useDashboardState.js:3151` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/bots/{botId}/{action}` ❌ | `useDashboardState.js:3171` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/bots/{botId}/exchange` ❌ | `useDashboardState.js:3188` | Bearer | *ROUTE MISSING* |
| POST | `/api/admin/email/broadcast` ❌ | `useDashboardState.js:2882` | Bearer | *ROUTE MISSING (closest: /api/admin/email-all-users)* |
| POST | `/api/api/admin/start-fresh` ❌ | `useDashboardState.js:2064` | Bearer | *DOUBLE /api BUG* |
| POST | `/api/admin/runtime/reset` ❌ | `SystemModeSection.js:121` | Bearer | *ROUTE MISSING* |
| POST | `/api/ai/chat` ❌ | `useDashboardState.js:1730+` | Bearer | *ROUTE MISSING (ai_chat not mounted)* |
| POST | `/api/ai/chat/greeting` ❌ | `AIChatPanel.js:68` | Bearer | *ROUTE MISSING (ai_chat not mounted)* |
| GET | `/api/ai/chat/history` ❌ | `AIChatPanel.js` | Bearer | *Ambiguous — chat_endpoints has /api/chat/history* |
| POST | `/api/admin/runtime/reset` ❌ | `SystemModeSection.js:121` | Bearer | *ROUTE MISSING* |
| GET | `/api/flokx/status` | `useDashboardState.js:1673` | Bearer | `{status}` |
| GET | `/api/flokx/alerts` | `useDashboardState.js:1705` | Bearer | `{alerts}` |
| GET | `/api/diagnostics/realtime` | `useDashboardState.js:479` | Bearer | `{ok}` |
| GET | `/api/diagnostics/auto-spawn` | `useDashboardState.js:1268` | Bearer | `{status}` |
| POST | `/api/ai/insights` ❌ (verify) | `useDashboardState.js:2767` | Bearer | *May not exist at /api/ai/insights* |
| GET | `/api/ml/predict?...` | `useDashboardState.js:2798` | Bearer | unverified |
| POST | `/api/profits/reinvest` ❌ (verify) | `useDashboardState.js:2841` | Bearer | *May not exist* |
| WS | `ws://host/api/ws?token=...` | `realtime.js:connectWebSocket` | query param token | WS messages |
| SSE | `/api/realtime/events?token=...` | `realtime.js:startSSE` | query param token | SSE stream |

---

## SECTION 6 — Mismatch Matrix

| Frontend Call | Backend Route Status | Issue |
|---|---|---|
| `POST /api/auth/login` | ✅ exists + matches | — |
| `POST /api/auth/register` | ✅ exists + matches | — |
| `GET /api/auth/me` | ✅ exists + matches | — |
| `GET /api/bots/status` | ✅ exists + matches | — |
| `GET /api/overview/snapshot` | ✅ exists + matches | — |
| `GET /api/system/mode` | ✅ exists + matches | — |
| `GET /api/system/status` | ✅ exists + matches | — |
| `GET /api/keys/status` | ✅ exists + matches | — |
| `GET /api/trades/recent` | ✅ exists + matches | — |
| `GET /api/prices/live` | ✅ exists + matches | — |
| `GET /api/risk/status` | ✅ exists + matches | — |
| `POST /api/risk/resume-all` | ✅ exists + matches | — |
| `POST /api/risk/daily-loss-lock/reset` | ✅ exists + matches | — |
| `POST /api/risk/bodyguard/reset` | ✅ exists + matches | — |
| `GET /api/autopilot/growth/status` | ✅ exists + matches | — |
| `GET /api/autopilot/user-settings` | ✅ exists + matches | — |
| `GET /api/ai/status` | ✅ exists + matches | `ai_status.py:18` |
| `GET /api/ai/rl-status` | ✅ exists + matches | `ai_rl.py:17` |
| `GET /api/huggingface/test-connection` | ✅ exists + matches | `huggingface.py:32` |
| `GET /api/chat/history` | ✅ exists + matches | `chat_endpoints.py:78` |
| `POST /api/chat/message` | ✅ exists + matches | `chat_endpoints.py:21` |
| `POST /api/chat/clear` | ✅ exists + matches | `chat_enhanced.py:27` |
| `GET /api/admin/system-stats` | ✅ exists + matches | `admin_enhanced.py:219` |
| `GET /api/admin/health-check` | ✅ exists + matches | `server.py:1786` |
| `GET /api/admin/storage` | ✅ exists + matches | `server.py:1181` |
| `DELETE /api/admin/users/{id}` | ✅ exists + matches | `server.py:2163` |
| `POST /api/system/emergency-stop` | ✅ exists + matches | `emergency_stop_endpoints.py:20` |
| `POST /api/admin/start-fresh` | ❌ **BROKEN** | Double `/api` bug → calls `/api/api/admin/start-fresh` → 404 |
| `GET /api/api/fetchai/status` | ❌ **BROKEN** | Double `/api` bug → 404 (correct: `/api/fetchai/status`) |
| `GET /api/api/fetchai/signals/{pair}` | ❌ **BROKEN** | Double `/api` bug → 404 |
| `POST /api/admin/unlock` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `GET /api/admin/users` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `GET /api/admin/bots` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/runtime/reset` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `GET /api/admin/emergency-stop/status` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/emergency-stop/global` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/emergency-stop/user` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/emergency-stop/clear-user` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/users/{id}/logout` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/bots/{id}/mode` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/bots/{id}/pause` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/bots/{id}/resume` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/bots/{id}/restart` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/bots/{id}/exchange` | ❌ **MISSING** | `admin_endpoints.py` not mounted |
| `POST /api/admin/email/broadcast` | ❌ **MISSING** | No such route; closest: `/api/admin/email-all-users` |
| `POST /api/admin/users/{id}/reset-password` | ⚠️ **MISMATCH** | Backend: `PUT /api/admin/users/{id}/password` (different method + path) |
| `PUT /api/admin/users/{id}/block` | ⚠️ **MISMATCH** | Frontend: PUT; `admin_endpoints.py:611` has POST (not mounted); `server.py:2214` has PUT ✓ |
| `POST /api/ai/chat` | ❌ **MISSING** | `ai_chat.py` not mounted |
| `POST /api/ai/chat/greeting` | ❌ **MISSING** | `ai_chat.py` not mounted |
| WS `trades` event | ⚠️ **MISMATCH** | Backend emits `trade_executed`/`trade_opened`/`trade_closed`, not `trades` |
| WS `balances` event | ⚠️ **MISMATCH** | Backend emits `balance_updated`, not `balances` |
| WS `transfer_updated` event | ❌ **ORPHANED** | Backend never emits this event type |

---

## SECTION 7 — Orphaned Features (Backend Exists, UI Not Wired)

| Backend Route | Path | Notes |
|---|---|---|
| `routes/ledger_endpoints.py` | `GET /api/ledger/fills`, `GET /api/ledger/audit-trail`, `GET /api/ledger/reconcile` | No UI wires these endpoints |
| `routes/admin_endpoints.py` | `GET /api/admin/audit/events`, `GET /api/admin/system/resources`, `GET /api/admin/bots/reconcile` | Admin functionality never surfaced |
| `routes/two_factor_auth.py` | All 2FA endpoints | No frontend 2FA flow found |
| `routes/training_quarantine.py` | Unified training/quarantine | No direct UI calls observed |
| `routes/payment_agent_endpoints.py` | All payment agent endpoints | No UI wired |
| `routes/execution_quality.py` | All execution quality endpoints | No UI wired |
| `routes/treasury.py` | All treasury endpoints | No UI wired |
| `routes/genetic_algorithm.py` | All GA endpoints | No direct user-facing UI |
| `routes/analytics_api.py` | `GET /api/analytics/pnl_timeseries`, `/capital_breakdown`, `/performance_summary`, `/exchange-comparison`, `/insights` | Frontend uses `/profit-history` (server.py inline) instead |
| `backend/server.py:2105` | `POST /api/admin/email-all-users` | Frontend calls `/admin/email/broadcast` (different path) |
| `routes/phase5_endpoints.py`, `phase6_endpoints.py`, `phase8_endpoints.py` | All phase endpoints | Internal only, no UI |

---

## SECTION 8 — Broken Features (UI Exists, Backend Missing or Wrong)

| UI Control | Expected Endpoint | Status | Impact |
|---|---|---|---|
| "show admin" in AI chat → password prompt → Admin Panel | `POST /api/admin/unlock` | ❌ NOT MOUNTED | Admin panel entirely inaccessible |
| Start Fresh (Paper Reset Modal) | `POST /api/admin/start-fresh` | ❌ DOUBLE /api BUG | Reset always 404 |
| Runtime Reset button (SystemModeSection) | `POST /api/admin/runtime/reset` | ❌ NOT MOUNTED | Button always fails |
| FetchAI section status card | `GET /api/fetchai/status` | ❌ DOUBLE /api BUG | FetchAI section always errors |
| FetchAI signals chart | `GET /api/fetchai/signals/{pair}` | ❌ DOUBLE /api BUG | FetchAI signals never load |
| Admin user list | `GET /api/admin/users` | ❌ NOT MOUNTED | User list empty/404 |
| Admin bot list | `GET /api/admin/bots` | ❌ NOT MOUNTED | Bot list empty/404 |
| Admin emergency override panel | `GET /api/admin/emergency-stop/status` | ❌ NOT MOUNTED | Emergency overrides panel broken |
| Admin force-logout user | `POST /api/admin/users/{id}/logout` | ❌ NOT MOUNTED | Action silently fails |
| Admin reset user password | `POST /api/admin/users/{id}/reset-password` | ⚠️ MISMATCH | Backend: `PUT /api/admin/users/{id}/password` |
| Admin email broadcast | `POST /api/admin/email/broadcast` | ❌ WRONG PATH | Backend: `POST /api/admin/email-all-users` |
| Admin bot control (pause/resume/restart/mode) | `POST /api/admin/bots/{id}/pause` etc. | ❌ NOT MOUNTED | All bot control buttons fail |
| AI chat greeting on login | `POST /api/ai/chat/greeting` | ❌ NOT MOUNTED | Falls back to hardcoded greeting |
| Chat message persistence | `POST /api/ai/chat` | ❌ NOT MOUNTED | Messages not saved server-side |
| Live trades real-time updates | WS event type `trades` | ⚠️ MISMATCH | Backend sends `trade_executed`; panel never auto-updates |
| Wallet balance real-time updates | WS event type `balances` | ⚠️ MISMATCH | Backend sends `balance_updated`; balances never auto-update |
| Transfer history real-time updates | WS event type `transfer_updated` | ❌ NOT EMITTED | Transfer panel never auto-updates |

---

## SECTION 9 — Duplicate / Conflicting Routes / Shadowing

### Route Collision Risk: `chat_enhanced.py` + `chat_endpoints.py` (Both prefix `/api/chat`)

**Evidence:**
```python
# routes/chat_enhanced.py:20 — prefix="/api/chat"
@router.post("/clear")       # → /api/chat/clear
@router.get("/daily-summary")
@router.get("/welcome")
@router.post("/session/end")

# routes/chat_endpoints.py:18 — prefix="/api/chat"
@router.post("/message")     # → /api/chat/message
@router.get("/history")
```
No path collision in the actual route paths. Both are mounted and together provide the full `/api/chat/*` namespace. However, the split creates confusion about where to look for chat functionality.

### Route Collision Risk: `admin_enhanced.py` + `server.py` inline routes (Both at `/api/admin`)

`admin_enhanced.py` has `GET /api/admin/system-stats`. Server.py note at line 1784 says "Removed duplicate GET /admin/system-stats - canonical in routes/admin_endpoints.py". But `admin_endpoints.py` is not mounted, so `admin_enhanced.py:219` is now the only provider. Currently no runtime collision because `admin_endpoints.py` is not mounted.

**If `admin_endpoints.py` were remounted**, the following pairs would collide:
- `GET /api/admin/system-stats` — `admin_endpoints.py:915` AND `admin_enhanced.py:219`
- `DELETE /api/admin/users/{id}` — `admin_endpoints.py:783` AND `server.py:2163`
- `PUT /api/admin/users/{id}/block` — `admin_endpoints.py:2328` AND `server.py:2214`
- `PUT /api/admin/users/{id}/password` — `admin_endpoints.py:2344` AND `server.py:2246`
- `POST /api/admin/emergency-stop` — `server.py:2684` AND possibly `admin_endpoints.py`

**Recommendation (in Appendix):** Before remounting `admin_endpoints.py`, audit and deconflict these paths.

### Route with Double `/api` Prefix in Path String

```python
# routes/admin_start_fresh.py:30
router = APIRouter()   # no prefix
@router.post("/api/admin/start-fresh")   # → /api/admin/start-fresh ✓
```
This pattern (no router prefix, `/api/...` in route path) works correctly on the backend but is inconsistent with the rest of the codebase and misleads frontend developers into thinking the path needs an `/api/` prefix in API calls (leading to the double-/api client bug at `useDashboardState.js:2064`).

Same pattern in: `autopilot_config.py`, `ai_rl.py`, `huggingface.py`, `risk_management.py`, `agents.py`, `ai_status.py`, `dashboard_overview.py`, `admin_start_fresh.py`.

---

## SECTION 10 — Realtime Contract Check

### WebSocket Connection
- **Frontend connects to**: `ws[s]://host/api/ws?token=<jwt>` (`realtime.js` → `wsUrl()` + `?token=`)
- **Backend route**: `routes/websocket.py:47` → `@router.websocket("/api/ws")` — router has NO prefix → final FastAPI path: `/api/ws` ✅
- **Auth**: Query param `token` accepted, falls back to `Authorization` header — both supported ✅
- **Max reconnect**: 5 attempts with exponential backoff, then falls back to SSE at `/api/realtime/events` ✅

### SSE Fallback
- **Frontend connects to**: `${API_BASE}/realtime/events?token=...` = `/api/realtime/events?token=...`
- **Backend route**: `routes/realtime.py` with `prefix="/api/realtime"` — needs `@router.get("/events")` — assumed to exist based on server mounting log ✅

### Event Name Contract

| Event Type (Backend) | Event Name (Frontend) | Match? |
|---|---|---|
| `bot_created` | not listened | ❌ orphaned |
| `bot_updated` | not listened | ❌ orphaned |
| `bot_paused` | `bot_paused` (BotFleet.js:363) | ✅ |
| `bot_resumed` | not listened | ❌ orphaned |
| `trade_executed` | — | ❌ frontend listens for `trades` |
| `trade_opened` | — | ❌ frontend listens for `trades` |
| `trade_closed` | — | ❌ frontend listens for `trades` |
| `profit_updated` | not listened | ❌ orphaned |
| `system_mode_changed` | not listened directly | ❌ (state reloaded via polling) |
| `api_key_update` | not listened (frontend listens `key_saved`, `key_tested`, `key_deleted`) | ⚠️ partial — `key_saved` etc. are separate types |
| `key_saved` | `key_saved` (APIKeySettings.js:63) | ✅ |
| `key_tested` | `key_tested` (APIKeySettings.js:68) | ✅ |
| `key_deleted` | `key_deleted` (APIKeySettings.js:73) | ✅ |
| `force_refresh` | not explicitly handled | ❌ orphaned |
| `balance_updated` | — | ❌ frontend listens for `balances` |
| `wallet` | `wallet` (WalletHub.js:88) | ✅ |
| `metrics_updated` | not listened | ❌ orphaned |
| `heartbeat` | not listened | ✅ (correctly ignored) |
| `bot_status_changed` | not listened | ❌ orphaned |
| (none emitted) | `transfer_updated` (TransferHistory.js:41, AdminApproval.js:38) | ❌ never fired |
| (none emitted) | `balances` (WalletHub.js:95) | ❌ never fired |

### Summary of WS Contract Issues
1. Frontend listens for `trades` — backend never emits `trades`. Should be `trade_executed` or similar.
2. Frontend listens for `balances` — backend emits `balance_updated`. 
3. Frontend listens for `transfer_updated` — backend never emits this.
4. Many backend events (`bot_resumed`, `profit_updated`, `force_refresh`, `metrics_updated`) are emitted but no frontend listener exists.

---

## SECTION 11 — "UI Jumping / Not Loading" Root Causes

### 1. Admin Unlock Failure → Infinite Error Loop
**Location:** `useDashboardState.js:1741–1820`  
The `post('/admin/unlock', ...)` call fails with 404. The catch block at ~line 1812 sets `awaitingPassword(false)` and shows "Invalid admin password." However, if the user retries, `awaitingPassword` is set back to `true` and the cycle repeats. The `apiClient` retry logic (3 retries × exponential backoff) means each admin unlock attempt generates 3 HTTP requests before showing the error, causing noticeable 5–10 second delays. Users think the password is wrong and retry repeatedly.

### 2. AI Chat Greeting Throws on Every Login
**Location:** `AIChatPanel.js:67–90` (inside `fetchDailyGreeting`)  
`post('/ai/chat/greeting')` throws 404. Caught in the `catch` block, falls back to hardcoded greeting. Then `get('/system/since-last-login')` is attempted. This part succeeds. Net result: the `setLoading(false)` is called twice (once in catch, once in finally), which is safe but wastes a render cycle. **Risk:** if the fallback greeting catch block re-throws (e.g., `notifyError(err)` behavior change), the component can unmount in error state.

### 3. useDashboardState Large Re-render Storm on Token Change
**Location:** `useDashboardState.js:288–291`  
```javascript
const axiosConfig = useMemo(() => ({
  headers: { Authorization: `Bearer ${token}` }
}), [token]);
```
`token` is the source of truth. When `token` changes (login → logout → login), the `useMemo` for `axiosConfig` fires. Since dozens of `useEffect` hooks depend on `axiosConfig` or `token`, every single data-load function re-fires simultaneously. All pending requests from the previous session are in-flight during the rapid state change. Race conditions between stale 401 responses (from old token) and the 401 handler that clears `localStorage.removeItem('token')` can cause a re-render cascade.

### 4. WebSocket Reconnect Storm After 401
**Location:** `realtime.js:scheduleReconnect`, `apiClient.js:401 handler`  
When a 401 occurs, `apiClient.js` dispatches `auth:unauthorized` event and clears the token. `realtime.js` has a max 5 reconnect attempts; if the token is cleared mid-reconnect attempt, each reconnect fires with `this.token = null` → `connectWebSocket` early-returns → `scheduleReconnect` checks `!this.token` and skips. This is safe. However, if `realtimeClient.connect(newToken)` is called again before `maxReconnectAttempts` is reset, reconnect count starts from 5 (not 0), and the client immediately falls through to SSE/polling. The `reconnectAttempts` field is never explicitly reset when `connect(token)` is called with a new token on re-login.

### 5. `useDashboardData` and `useDashboardState` Both Load `GET /api/bots/status`
**Location:** `useDashboardData.js:97`, `useDashboardState.js:1179`  
Both hooks independently fire `GET /api/bots/status` on mount. Depending on which completes first, the state can flip. If one fails and sets error state while the other succeeds, users may see a brief empty bots list before data appears, or stale data persists.

### 6. Emergency Stop → Dashboard State Resets
**Location:** `useDashboardState.js:2043`  
After `POST /api/system/emergency-stop` succeeds, state is not automatically refreshed. The user must wait for the next polling cycle or WebSocket event `system_mode_changed`. But the WS event is emitted from `realtime_events.py:147` with `type: "system_mode_changed"` — which no frontend listener explicitly handles (except for a general `force_refresh` pattern). The dashboard may appear stuck in the old state.

---

## SECTION 12 — TOMORROW FIX PLAN (NO CODE YET)

### Phase 1: Restore Missing Routes (CRITICAL — fixes Blockers 1, 2, 5)

**Task 1.1** — Re-add `routes.admin_endpoints` to `routers_to_mount` in `server.py:3061`  
*Before re-adding, deconflict collisions with server.py inline routes and admin_enhanced (see Section 9):*  
  - Remove or rename the following inline server.py routes to avoid collision:  
    - `server.py:2163` — DELETE `/admin/users/{id}` (duplicate of `admin_endpoints.py:783`)  
    - `server.py:2214` — PUT `/admin/users/{id}/block` (verify method matches)  
    - `server.py:2246` — PUT `/admin/users/{id}/password` (method mismatch with POST in admin_endpoints)  
    - `server.py:2684` — POST `/admin/emergency-stop` (check for collision)  
    - `server.py:2763` — POST `/admin/emergency-resume` (check for collision)  
  - Also check for `GET /api/admin/system-stats` collision between `admin_enhanced.py:219` and `admin_endpoints.py:915`.  
  - Once deconflicted, add: `("routes.admin_endpoints", "Admin Dashboard Endpoints"),` to `routers_to_mount` in `server.py`.  
  - Restart backend and verify with: `curl -X POST http://localhost:8000/api/admin/unlock`

**Task 1.2** — Re-add `routes.ai_chat` to `routers_to_mount` in `server.py:3082`  
  - These routes are at `/api/ai/...` — no collision with `chat_enhanced.py` (`/api/chat/...`).  
  - Add: `("routes.ai_chat", "AI Chat"),` to `routers_to_mount` in `server.py`.  
  - Verify with: `curl -X POST http://localhost:8000/api/ai/chat/greeting`

### Phase 2: Fix Double `/api` Bugs (CRITICAL — fixes Blockers 3, 4)

**Task 2.1** — Fix `useDashboardState.js:2064`  
  - Change: `axios.post(\`${API}/api/admin/start-fresh\`, ...)` → `axios.post(\`${API}/admin/start-fresh\`, ...)`  
  - References: `useDashboardState.js:2064`

**Task 2.2** — Fix `FetchAISection.js:22,31`  
  - Change: `apiClient.get('/api/fetchai/status')` → `apiClient.get('/fetchai/status')`  
  - Change: `apiClient.get(\`/api/fetchai/signals/${pair}\`)` → `apiClient.get(\`/fetchai/signals/${pair}\`)`  
  - References: `FetchAISection.js:22,31`

### Phase 3: Fix Admin Panel Wiring

**Task 3.1** — Fix admin email broadcast path  
  - Change: `post('/admin/email/broadcast', ...)` → `post('/admin/email-all-users', ...)` (or create a backend route at `/api/admin/email/broadcast`)  
  - References: `useDashboardState.js:2882`

**Task 3.2** — Fix admin reset-password method + path mismatch  
  - Frontend calls `POST /api/admin/users/{id}/reset-password`  
  - Backend has `PUT /api/admin/users/{id}/password` (server.py:2246)  
  - Either: change frontend to `PUT /admin/users/${userId}/password` (match server.py inline)  
  - Or: add a `POST /api/admin/users/{id}/reset-password` route (after admin_endpoints is remounted, it exists at line 713)  
  - References: `useDashboardState.js:3081`

**Task 3.3** — Fix admin user block method consistency  
  - Frontend: `PUT /api/admin/users/{id}/block`; both server.py inline (PUT) and admin_endpoints (POST) need to agree.  
  - Ensure after Phase 1 deconflict, exactly one route handles this as PUT.

### Phase 4: Fix Realtime (WebSocket) Event Contract

**Task 4.1** — Align `trades` event name  
  - Option A: Add frontend listener for `trade_executed`, `trade_opened`, `trade_closed` in `LiveTradesPanel.js` and `ComparisonGraphs.js`  
  - Option B: Change backend `realtime_events.py:100` to emit `type: "trades"` (but this has wider impact)  
  - References: `LiveTradesPanel.js:38`, `ComparisonGraphs.js:81`, `realtime_events.py:100,109,118`

**Task 4.2** — Align `balances` event name  
  - Add frontend listener for `balance_updated` OR change backend to emit `balances`  
  - References: `WalletHub.js:95`, `realtime_events.py:226`

**Task 4.3** — Implement `transfer_updated` backend emission  
  - Backend should emit `{"type": "transfer_updated", ...}` after a transfer state change  
  - References: `TransferHistory.js:41`, `AdminApproval.js:38`, `wallet_transfers_enhanced.py`

**Task 4.4** — Reset `reconnectAttempts` on `connect(token)` re-call  
  - In `realtime.js`, add `this.reconnectAttempts = 0;` at the top of `connect(token)` method  
  - References: `realtime.js:scheduleReconnect`

### Phase 5: Fix Feature Flags Confusion

**Task 5.1** — Align `.env.example` with what backend actually reads  
  - Backend reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`  
  - `.env.example` has `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED` (different names)  
  - Update `.env.example` to use the names backend reads, or add dual-read logic in backend  
  - References: `.env.example:9,14,19`, `server.py:87–92`

**Task 5.2** — Lock CORS in production  
  - Ensure `CORS_ALLOWED_ORIGINS=https://amarktai.online` is set in production `.env`  
  - References: `server.py:396–421`

### Phase 6: Smoke Test Checklist (Post-Fix Verification)

Run these in order after fixing:

1. `curl -X POST http://localhost:8000/api/auth/login -d '{"email":"test@test.com","password":"test"}'`  
   → Expect `{access_token, user}`

2. `curl -X POST http://localhost:8000/api/admin/unlock -H "Authorization: Bearer <token>" -d '{"password":"<admin_pass>"}'`  
   → Expect `{"success": true, "message": "Admin panel unlocked"}`

3. `curl http://localhost:8000/api/admin/users -H "Authorization: Bearer <admin_token>"`  
   → Expect list of users (not 404)

4. `curl -X POST http://localhost:8000/api/ai/chat/greeting -H "Authorization: Bearer <token>"`  
   → Expect `{"content": "Hello...", "system_state": {...}}`

5. `curl -X POST http://localhost:8000/api/admin/start-fresh -H "Authorization: Bearer <admin_token>" -d '{"confirmation_phrase":"START FRESH","scope":"paper_only","also_reset_risk_locks":true}'`  
   → Expect `{"ok": true, ...}` (NOT 404)

6. `curl http://localhost:8000/api/fetchai/status -H "Authorization: Bearer <token>"`  
   → Expect `{"status": "connected"|"not_configured"}` (NOT 404)

7. In browser DevTools, connect to dashboard, open Network tab, filter WS:  
   → Confirm WebSocket to `/api/ws?token=...` stays connected  
   → Trigger a trade → confirm `trade_executed` event arrives (update LiveTradesPanel listener)  
   → Confirm no repeated connect/disconnect cycle

8. In browser console: `localStorage.getItem('token')` → should be non-null after login  
   → No `401` errors in the main feed

9. Admin panel: type "show admin" → enter password → confirm admin section appears  
   → User list loads → emergency stop panel loads

10. Paper reset: click Start Fresh → enter "START FRESH" → confirm `{"ok": true}` toast  
    (not "Reset runtime completed" with 404)

---

## Appendix: Possible Fix Ideas (DO NOT APPLY YET)

> **These are observations only. No changes have been applied to the codebase.**

**A. Re-mount `admin_endpoints` with Deconflict Guard**  
Re-add `("routes.admin_endpoints", "Admin Dashboard Endpoints")` to `routers_to_mount` in `server.py`. Before doing so, wrap duplicate routes in server.py inline (admin/users/*, admin/emergency-stop, etc.) with a check that removes them, or simply comment them out.  The existing route-collision detection at `server.py:3160+` will flag any remaining duplicates at boot time, which is a useful safety net.

**B. Fix FetchAISection.js Double /api Calls**  
Remove the `/api/` prefix from the paths passed to `apiClient` in `FetchAISection.js:22` and `:31`.

**C. Fix useDashboardState.js Start-Fresh Double /api**  
Remove the `/api/` prefix at `useDashboardState.js:2064`: change `/api/admin/start-fresh` to `/admin/start-fresh`.

**D. Re-mount `ai_chat`**  
Add `("routes.ai_chat", "AI Chat")` before `routes.chat_enhanced` in `routers_to_mount`. No path collisions expected since `ai_chat` is at `/api/ai/chat/...` and `chat_enhanced` is at `/api/chat/...`.

**E. WS Event Names — Frontend-Side Fix (Minimal Impact)**  
In `LiveTradesPanel.js:38`, add listeners for `trade_executed`, `trade_opened`, `trade_closed` in addition to (or instead of) `trades`. In `WalletHub.js:95`, add a listener for `balance_updated` in addition to `balances`. This avoids changing backend event emission patterns (which could break other listeners).

**F. Admin Email Broadcast Path**  
Change `useDashboardState.js:2882` from `post('/admin/email/broadcast', ...)` to `post('/admin/email-all-users', ...)` to match the existing inline server.py route.

**G. CORS Production Lock**  
In production `.env`: `CORS_ALLOWED_ORIGINS=https://amarktai.online`.

**H. `.env.example` Flag Name Alignment**  
Replace `PAPER_TRADING=0`, `LIVE_TRADING=0`, `AUTOPILOT_ENABLED=0` in `.env.example` with `ENABLE_PAPER_TRADING=false`, `ENABLE_LIVE_TRADING=false`, `ENABLE_AUTOPILOT=false` to match what the backend actually reads.

**I. Reset `reconnectAttempts` on Re-connect**  
In `realtime.js`, inside `connect(token)`, add `this.reconnectAttempts = 0;` and `this.reconnectDelay = 1000;` to ensure fresh reconnect logic on re-login.

---

*End of Forensic Audit Report — Amarktai Network*  
*Produced by: Copilot (Senior Full-Stack Auditor role)*  
*All findings are READ-ONLY. No code was changed in producing this report.*
