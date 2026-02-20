# AMARKTAI NETWORK — FULL REPO FORENSIC AUDIT REPORT (v2)

**Audit Role:** Senior Full-Stack Auditor + Release Manager  
**Type:** READ-ONLY — No code changes applied  
**Repo:** `sharetheherbman-debug/Amarktai-Network---Deployment`  
**Branch:** `copilot/full-repo-forensic-audit`  
**Commit SHA:** `3cd5c1a3708ece5ff41dfc206d520797698632e6`  
**Audit Date:** 2026-02-20

---

## SECTION 0 — Evidence Pack

| Item | Value |
|------|-------|
| Frontend API baseURL | `/api` (`frontend/src/lib/apiClient.js`) |
| Frontend WS endpoint | `ws[s]://host/api/ws?token=<jwt>` (`frontend/src/lib/realtime.js`) |
| SSE fallback | `/api/realtime/events?token=<jwt>` (`frontend/src/lib/realtime.js`) |
| Backend API prefix | All routes served under `/api/*` |
| Nginx proxy rule | `location /api/` → `http://127.0.0.1:8000` (`deployment/nginx/amarktai.conf`) |
| CORS default | Wildcard `["*"]` if `CORS_ALLOWED_ORIGINS` unset (`backend/server.py:416`) |
| Feature flags | `ENABLE_REALTIME=true`, `ENABLE_PAPER_TRADING=true`, `ENABLE_LIVE_TRADING=false` |

---

## SECTION 1 — Executive Summary

1. **`routes.admin_endpoints` NOT MOUNTED** — mislabelled "duplicate of admin_enhanced". Kills `/api/admin/unlock`, `/api/admin/users`, `/api/admin/bots`, `/api/admin/runtime/reset`, all emergency-stop override routes, and ~50 others. Admin panel entirely non-functional.
2. **`routes.ai_chat` NOT MOUNTED** — mislabelled "duplicate of chat_enhanced". Kills `/api/ai/chat/greeting` (login greeting) and `/api/ai/chat` (message persistence). Every login falls back to a hardcoded greeting; no server-side chat persistence.
3. **Double `/api` bug — Start Fresh reset** (`useDashboardState.js:2064`): `axios.post(\`${API}/api/admin/start-fresh\`)` with `API=''` and `apiClient.baseURL='/api'` resolves to `/api/api/admin/start-fresh` → 404.
4. **Double `/api` bug — FetchAI section** (`FetchAISection.js:22,31`): `apiClient.get('/api/fetchai/status')` resolves to `/api/api/fetchai/status` → 404.
5. **`POST /api/admin/runtime/reset` not mounted** — Runtime Reset button in SystemModeSection always 404s.
6. **WebSocket event name mismatches** — Frontend listens for `trades`/`balances`/`transfer_updated`; backend emits `trade_executed`/`balance_updated`/(nothing). Live trades and wallet balances never auto-update.
7. **Duplicate `realtimeClient.connect(token)` call** — Both `useDashboardState.js:750` and `useDashboardData.js:257` call `realtimeClient.connect(token)` against the same singleton, risking reconnect storm.
8. **Three overlapping price-poll intervals** — `useDashboardData.js:239` (4s), `useDashboardState.js:691` (5s), `useDashboardState.js:429` (4s) all call `loadLivePrices`, tripling `/api/prices/live` requests.
9. **8 `useLastUpdate` instances each poll every 1s** — 8 simultaneous 1-second `setInterval` callbacks trigger React re-renders constantly across WalletHub, LiveTradesPanel, PlatformPanel, DecisionTrace, WhaleFlowHeatmap, PrometheusMetrics.
10. **10.9 MB of uncompressed media on login/landing pages** — `amarktai-network-final.mp4` (8.2 MB, `autoPlay`) and `thunderstruck.mp3` (4.7 MB, `preload="auto"`) loaded before user can interact with the login form.
11. **CORS defaults to `["*"]`** if `CORS_ALLOWED_ORIGINS` is absent in production `.env` — critical security risk.
12. **`.env.example` feature flag name mismatch** — `.env.example` defines `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED`; backend reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`. Settings have no effect.

---

## SECTION 2 — P0 BLOCKERS

### P0-1: `routes.admin_endpoints` Not Mounted

| Field | Detail |
|-------|--------|
| **Severity** | P0 BLOCKER |
| **File:Line** | `backend/server.py:3061` |
| **Evidence** | `# REMOVED: routes.admin_endpoints - duplicate of admin_enhanced` |
| **Root Cause** | `admin_enhanced.py` has only 4 routes. `admin_endpoints.py` has ~50 routes. NOT duplicates. |
| **Impact** | Admin panel 100% broken. All admin API calls return 404. |
| **Verify** | `curl -X POST http://localhost:8000/api/admin/unlock -H "Authorization: ******" -d '{"password":"x"}'` → must return 200/401, currently 404 |

**Sample of blocked routes:**

| Path | Source:Line |
|------|-------------|
| `POST /api/admin/unlock` | `admin_endpoints.py:156` |
| `POST /api/admin/runtime/reset` | `admin_endpoints.py:336` |
| `GET /api/admin/users` | `admin_endpoints.py:452` |
| `GET /api/admin/bots` | `admin_endpoints.py:1575` |
| `POST /api/admin/bots/{id}/pause` | `admin_endpoints.py:1763` |
| `POST /api/admin/bots/{id}/resume` | `admin_endpoints.py:1810` |
| `POST /api/admin/bots/{id}/restart` | `admin_endpoints.py:1857` |
| `POST /api/admin/bots/{id}/mode` | `admin_endpoints.py:1683` |
| `GET /api/admin/emergency-stop/status` | `admin_endpoints.py:2897` |
| `POST /api/admin/emergency-stop/global` | `admin_endpoints.py:2918` |
| `POST /api/admin/emergency-stop/user` | `admin_endpoints.py:2951` |
| `POST /api/admin/emergency-stop/clear-user` | `admin_endpoints.py:2977` |
| `POST /api/admin/users/{id}/logout` | `admin_endpoints.py:857` |

---

### P0-2: `routes.ai_chat` Not Mounted

| Field | Detail |
|-------|--------|
| **Severity** | P0 BLOCKER |
| **File:Line** | `backend/server.py:3082` |
| **Evidence** | `# REMOVED: routes.ai_chat - duplicate of chat_enhanced` |
| **Root Cause** | `chat_enhanced.py` at `/api/chat/*`. `ai_chat.py` at `/api/ai/chat*`. Different namespaces. |
| **Impact** | Login greeting broken every session. Chat messages not persisted. |
| **Verify** | `curl -X POST http://localhost:8000/api/ai/chat/greeting -H "Authorization: ******"` → currently 404 |

**Blocked routes:**

| Path | Source:Line |
|------|-------------|
| `POST /api/ai/chat/greeting` | `ai_chat.py:2068` |
| `POST /api/ai/chat` | `ai_chat.py:1385` |
| `GET /api/ai/chat/history` | `ai_chat.py:1963` |

---

### P0-3: Double `/api` Bug — Start Fresh Reset

| Field | Detail |
|-------|--------|
| **Severity** | P0 BLOCKER |
| **File:Line** | `useDashboardState.js:2064` |
| **Code** | `axios.post(\`${API}/api/admin/start-fresh\`, {...})` |
| **Resolved URL** | `/api/api/admin/start-fresh` (double `/api`) |
| **Correct URL** | `/api/admin/start-fresh` |
| **Impact** | Paper trading reset always fails silently with 404. |
| **Verify** | DevTools Network → trigger Start Fresh → request URL is `/api/api/admin/start-fresh` |

---

### P0-4: Double `/api` Bug — FetchAI Section

| Field | Detail |
|-------|--------|
| **Severity** | P0 BLOCKER |
| **File:Line** | `FetchAISection.js:22,31` |
| **Code** | `apiClient.get('/api/fetchai/status')` and `apiClient.get(\`/api/fetchai/signals/${pair}\`)` |
| **Resolved URL** | `/api/api/fetchai/status` |
| **Correct URL** | `/api/fetchai/status` |
| **Impact** | FetchAI section always errors; all market signals broken. |
| **Verify** | DevTools Network → FetchAI section → 404 on `/api/api/fetchai/status` |

---

### P0-5: CORS Wildcard Default

| Field | Detail |
|-------|--------|
| **Severity** | P0 SECURITY |
| **File:Line** | `backend/server.py:416` |
| **Evidence** | `if not origins: return ["*"]` — triggered when `CORS_ALLOWED_ORIGINS` is unset |
| **Impact** | Any website can make cross-origin authenticated requests against the API. |
| **Verify** | `curl -H "Origin: https://evil.com" http://localhost:8000/api/health/ping -I | grep -i access-control` |

---

### P0-6: `.env.example` Feature Flag Name Mismatch

| Field | Detail |
|-------|--------|
| **Severity** | P0 (silent misconfiguration) |
| **File:Line** | `.env.example:9,14,19` vs `server.py:87-92` |
| **Evidence** | `.env.example` has `PAPER_TRADING=0`, `LIVE_TRADING=0`, `AUTOPILOT_ENABLED=0`; backend reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT` |
| **Impact** | Operators copying `.env.example` get silently wrong configuration. Paper trading may be ON when operator thinks it's OFF. |
| **Verify** | Set `PAPER_TRADING=0` in `.env` → verify paper trading still active → confirms mismatch |

---

## SECTION 3 — ROUTE MOUNT COVERAGE MATRIX

All Python modules in `backend/routes/`. `api_key_management.py` is a utility module (encryption helpers), not a router.

| Module | Mounted | Removal Reason | Notes |
|--------|---------|----------------|-------|
| `admin_endpoints` | ❌ NO | "duplicate of admin_enhanced" — **INCORRECT** | P0-1 blocker — ~50 unique routes |
| `admin_enhanced` | ✅ YES | | 4 routes only |
| `admin_start_fresh` | ✅ YES | | Route path includes `/api/` (no router prefix) |
| `admin_whitelist` | ✅ YES | | |
| `advanced_trading_endpoints` | ✅ YES | | prefix `/api/advanced` |
| `agents` | ✅ YES | | routes include `/api/` in path |
| `ai_chat` | ❌ NO | "duplicate of chat_enhanced" — **INCORRECT** | P0-2 blocker — different namespace |
| `ai_rl` | ✅ YES | | routes include `/api/` in path |
| `ai_status` | ✅ YES | | routes include `/api/` in path |
| `alerts` | ✅ YES | | |
| `analytics_api` | ✅ YES | | prefix `/api/analytics` — CRITICAL |
| `api_key_management` | N/A | Utility module, not a router | Correctly excluded |
| `auth` | ✅ YES | | Mounted via `api_router.include_router` |
| `autonomy_control` | ✅ YES | | prefix `/api/autonomy` |
| `autopilot_config` | ✅ YES | | routes include `/api/` in path |
| `autopilot_control` | ✅ YES | | prefix `/api` (bare) |
| `autopilot_growth` | ✅ YES | | prefix `/api/autopilot` |
| `backtesting` | ❌ NO | Not in mount list | prefix `/api/backtest` — no frontend calls found |
| `bot_lifecycle` | ✅ YES | | prefix `/api/bots` — CRITICAL |
| `build_info` | ✅ YES | | |
| `capital_tracking_endpoints` | ✅ YES | | |
| `chat_endpoints` | ✅ YES | | prefix `/api/chat` |
| `chat_enhanced` | ✅ YES | | prefix `/api/chat` |
| `compat` | ✅ YES | | prefix `/api` |
| `compatibility_endpoints` | ✅ YES | | |
| `daily_report` | ✅ YES | | |
| `dashboard_aliases` | ✅ YES | | |
| `dashboard_endpoints` | ✅ YES | | |
| `dashboard_overview` | ✅ YES | | routes include `/api/` in path |
| `decision_trace` | ✅ YES | | prefix `/api/decisions` |
| `diagnostics` | ✅ YES | | |
| `emergency_stop_endpoints` | ✅ YES | | prefix `/api/system` |
| `execution_quality` | ✅ YES | | |
| `fetchai` | ✅ YES | | prefix `/api/fetchai` |
| `genetic_algorithm` | ✅ YES | | |
| `health` | ✅ YES | | prefix `/api/health` |
| `huggingface` | ✅ YES | | routes include `/api/` in path |
| `keys` | ✅ YES | | prefix `/api/keys` — CRITICAL |
| `learning_jobs` | ✅ YES | | |
| `ledger_endpoints` | ✅ YES | | prefix `/api` — CRITICAL |
| `limits_management` | ✅ YES | | |
| `live_readiness` | ✅ YES | | |
| `live_trading_gate` | ✅ YES | | |
| `market_api` | ✅ YES | | |
| `metrics_api` | ✅ YES | | prefix `/api/metrics` |
| `notifications` | ✅ YES | | |
| `order_endpoints` | ✅ YES | | prefix `/api` |
| `payment_agent_endpoints` | ✅ YES | | |
| `phase5_endpoints` | ✅ YES | | |
| `phase6_endpoints` | ✅ YES | | |
| `phase8_endpoints` | ✅ YES | | |
| `platforms` | ✅ YES | | |
| `prices` | ✅ YES | | prefix `/api/prices` |
| `quarantine` | ✅ YES | | prefix `/api/quarantine` — CRITICAL |
| `realtime` | ✅ YES | | conditional on `ENABLE_REALTIME=true` (default true) |
| `risk_management` | ✅ YES | | routes include `/api/` in path |
| `system` | ✅ YES | | prefix `/api/system` |
| `system_capabilities` | ✅ YES | | |
| `system_health_endpoints` | ❌ NO | "has duplicate /health/ping" — CORRECT | Would collide with `health.py`. Correctly excluded. |
| `system_limits` | ✅ YES | | |
| `system_mode` | ✅ YES | | prefix `/api/system` — CRITICAL |
| `system_status` | ✅ YES | | prefix `/api/system` |
| `trades` | ✅ YES | | prefix `/api/trades` — CRITICAL |
| `trading` | ❌ NO | Not in mount list | Bare `APIRouter()`, paths would collide with dashboard_overview. No frontend calls. Correctly excluded. |
| `training` | ✅ YES | | prefix `/api/training` — CRITICAL |
| `training_quarantine` | ✅ YES | | |
| `treasury` | ✅ YES | | |
| `two_factor_auth` | ✅ YES | | |
| `user_countdowns` | ✅ YES | | |
| `user_whitelist` | ✅ YES | | |
| `wallet_addresses` | ✅ YES | | |
| `wallet_endpoints` | ❌ NO | "duplicate of wallet_hub" — CORRECT | Same prefix `/api/wallet`. Would collide. Correctly excluded. |
| `wallet_hub` | ✅ YES | | prefix `/api/wallet` |
| `wallet_transfers` | ❌ NO | "collision with wallet_transfers_enhanced" — CORRECT | Correctly excluded. |
| `wallet_transfers_enhanced` | ✅ YES | | |
| `websocket` | ✅ YES | | `@router.websocket("/api/ws")` — CRITICAL |

**Summary:** 76 modules on disk. 65 mounted. 8 not mounted (2 are P0 bugs; 3 correctly excluded; 1 utility; 2 no-frontend-calls).

---

## SECTION 4 — FRONTEND → BACKEND CONTRACT TABLE

Legend: ✅ route exists + matches | ⚠️ mismatch or unverified | ❌ broken/missing

### Auth & Profile

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `Login.js:29` | `/auth/login` | `/api/auth/login` | POST | ✅ |
| `Register.js:8` | `/auth/register` | `/api/auth/register` | POST | ✅ |
| `useDashboardData.js:87` | `/auth/me` | `/api/auth/me` | GET | ✅ |
| `useDashboardState.js:2124` | `/auth/profile` | `/api/auth/profile` | PUT | ✅ |

### Bots

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardData.js:97` | `/bots/status` | `/api/bots/status` | GET | ✅ |
| `useDashboardState.js:2172` | `/bots` | `/api/bots` | POST | ✅ |
| `useDashboardState.js:2247` | `/bots/{id}` | `/api/bots/{id}` | DELETE | ✅ |
| `useDashboardState.js:2257` | `/bots/{id}` | `/api/bots/{id}` | PUT | ✅ |
| `useDashboardState.js:2326` | `/bots/batch-create` | `/api/bots/batch-create` | POST | ✅ |
| `useDashboardState.js:1508` | `/bots/eligible-for-promotion` | `/api/bots/eligible-for-promotion` | GET | ✅ |
| `useDashboardState.js:1520` | `/bots/confirm-live-switch` | `/api/bots/confirm-live-switch` | POST | ✅ |

### Trades & Portfolio

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardData.js:180` | `/trades/recent?limit=50` | `/api/trades/recent` | GET | ✅ |
| `useDashboardState.js:1404` | `/portfolio/summary` | `/api/portfolio/summary` | GET | ✅ |

### System & Mode

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardData.js:128` | `/system/mode` | `/api/system/mode` | GET | ✅ |
| `useDashboardState.js:2016` | `/system/mode` | `/api/system/mode` | PUT | ✅ |
| `useDashboardData.js:142` | `/system/status` | `/api/system/status` | GET | ✅ |
| `useDashboardState.js:2043` | `/system/emergency-stop` | `/api/system/emergency-stop` | POST | ✅ |

### Keys / API Setup

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardData.js:152` | `/keys/status` | `/api/keys/status` | GET | ✅ |
| `useDashboardState.js:2393` | `/keys/save` | `/api/keys/save` | POST | ✅ |
| `useDashboardState.js:2433` | `/keys/test` | `/api/keys/test` | POST | ✅ |
| `useDashboardState.js:2456` | `/keys/{provider}` | `/api/keys/{provider}` | DELETE | ✅ |

### Analytics

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardState.js:1549` | `/analytics/profit-history` | `/api/analytics/profit-history` | GET | ✅ (`server.py:1425`) |
| `useDashboardState.js:1566` | `/analytics/equity` | `/api/analytics/equity` | GET | ✅ |
| `useDashboardState.js:1576` | `/analytics/drawdown` | `/api/analytics/drawdown` | GET | ✅ |
| `useDashboardState.js:1586` | `/analytics/win_rate` | `/api/analytics/win_rate` | GET | ✅ |
| `useDashboardState.js:1443` | `/analytics/countdown-to-million` | `/api/analytics/countdown-to-million` | GET | ✅ (`server.py:1549`) |
| `useDashboardState.js:2767` | `/ai/insights` | `/api/ai/insights` | GET | ❌ — no such route; nearest: `/api/analytics/insights` |

### Overview & Dashboard

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardData.js:108` | `/overview/snapshot` | `/api/overview/snapshot` | GET | ✅ |

### Wallet & Prices

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardState.js:1206` | `/wallet/paper` | `/api/wallet/paper` | GET | ✅ |
| `useDashboardState.js:1537` | `/wallet/balances` | `/api/wallet/balances` | GET | ✅ |
| `useDashboardData.js:200` | `/prices/live` | `/api/prices/live` | GET | ✅ |

### Risk & Autonomy

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardState.js:1258` | `/risk/status` | `/api/risk/status` | GET | ✅ |
| `useDashboardState.js:1330` | `/risk/resume-all` | `/api/risk/resume-all` | POST | ✅ |
| `useDashboardState.js:1349` | `/risk/daily-loss-lock/reset` | `/api/risk/daily-loss-lock/reset` | POST | ✅ |
| `useDashboardState.js:1367` | `/risk/bodyguard/reset` | `/api/risk/bodyguard/reset` | POST | ✅ |
| `useDashboardState.js:1209` | `/autonomy/status` | `/api/autonomy/status` | GET | ✅ |

### Chat

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `AIChatPanel.js:68` | `/ai/chat/greeting` | `/api/ai/chat/greeting` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:1730+` | `/ai/chat` | `/api/ai/chat` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:1881` | `/chat/message` | `/api/chat/message` | POST | ✅ |
| `AIChatPanel.js:175` | `/chat/history` | `/api/chat/history` | GET | ✅ |
| `useDashboardState.js:603` | `/chat/clear` | `/api/chat/clear` | POST | ✅ |

### Admin — Critical Paths

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `useDashboardState.js:1744` | `/admin/unlock` | `/api/admin/unlock` | POST | ❌ NOT MOUNTED |
| `SystemModeSection.js:121` | `/admin/runtime/reset` | `/api/admin/runtime/reset` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:1620` | `/admin/users` | `/api/admin/users` | GET | ❌ NOT MOUNTED |
| `useDashboardState.js:2972` | `/admin/bots` | `/api/admin/bots` | GET | ❌ NOT MOUNTED |
| `useDashboardState.js:2984` | `/admin/emergency-stop/status` | `/api/admin/emergency-stop/status` | GET | ❌ NOT MOUNTED |
| `useDashboardState.js:2994` | `/admin/emergency-stop/global` | `/api/admin/emergency-stop/global` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3004` | `/admin/emergency-stop/user` | `/api/admin/emergency-stop/user` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3012` | `/admin/emergency-stop/clear-user` | `/api/admin/emergency-stop/clear-user` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3135` | `/admin/users/{id}/logout` | `/api/admin/users/{id}/logout` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3081` | `/admin/users/{id}/reset-password` | `/api/admin/users/{id}/reset-password` | POST | ❌ NOT MOUNTED + ⚠️ mounted variant is `PUT /admin/users/{id}/password` |
| `useDashboardState.js:2882` | `/admin/email/broadcast` | `/api/admin/email/broadcast` | POST | ❌ No such route — nearest: `POST /api/admin/email-all-users` |
| `useDashboardState.js:1630` | `/admin/system-stats` | `/api/admin/system-stats` | GET | ✅ (`admin_enhanced.py:219`) |
| `useDashboardState.js:1686` | `/admin/health-check` | `/api/admin/health-check` | GET | ✅ (`server.py:1786`) |
| `useDashboardState.js:3151` | `/admin/bots/{id}/mode` | `/api/admin/bots/{id}/mode` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3171` | `/admin/bots/{id}/{action}` | `/api/admin/bots/{id}/{action}` | POST | ❌ NOT MOUNTED |
| `useDashboardState.js:3188` | `/admin/bots/{id}/exchange` | `/api/admin/bots/{id}/exchange` | POST | ❌ NOT MOUNTED |

### Start Fresh / Reset (Double `/api` Bugs)

| File:Line | Path Called | Resolved URL | Correct URL | Status |
|-----------|-------------|-------------|-------------|--------|
| `useDashboardState.js:2064` | `${API}/api/admin/start-fresh` | `/api/api/admin/start-fresh` | `/api/admin/start-fresh` | ❌ double `/api` |
| `FetchAISection.js:22` | `apiClient.get('/api/fetchai/status')` | `/api/api/fetchai/status` | `/api/fetchai/status` | ❌ double `/api` |
| `FetchAISection.js:31` | `apiClient.get('/api/fetchai/signals/${pair}')` | `/api/api/fetchai/signals/{pair}` | `/api/fetchai/signals/{pair}` | ❌ double `/api` |

### AI Tools

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `AiToolsSection.js:82` | `/ai/rl-status` | `/api/ai/rl-status` | GET | ✅ |
| `AiToolsSection.js:96` | `/agents/status` | `/api/agents/status` | GET | ✅ |
| `AiToolsSection.js:114` | `/agents/create` | `/api/agents/create` | POST | ✅ |
| `AiToolsSection.js:61` | `/huggingface/test-connection` | `/api/huggingface/test-connection` | GET | ✅ |
| `AiToolsSection.js:143` | `/huggingface/analyze-sentiment` | `/api/huggingface/analyze-sentiment` | POST | ✅ |
| `useDashboardState.js:2798` | `/ml/predict` | `/api/ml/predict` | GET | ❌ no route found |
| `useDashboardState.js:2841` | `/profits/reinvest` | `/api/profits/reinvest` | POST | ❌ no route found |

### Whale / Advanced

| File:Line | Path Called | Final URL | Method | Status |
|-----------|-------------|-----------|--------|--------|
| `WhaleFlowHeatmap.js:54` | `/advanced/whale/summary` | `/api/advanced/whale/summary` | GET | ✅ |

---

## SECTION 5 — REALTIME CONTRACT TABLE

### Backend → Frontend Event Names

| Backend Event Type | Frontend Listens | Match? | Impact |
|-------------------|-----------------|--------|--------|
| `trade_executed` | `trade_executed` (useDashboardState wildcard) | ✅ partial | State updates via handleRealTimeUpdate only |
| `trade_opened` | — `LiveTradesPanel` listens `trades` | ❌ MISMATCH | LiveTradesPanel never receives real-time trade data |
| `trade_closed` | — | ❌ MISMATCH | |
| `profit_updated` | not subscribed directly | ❌ no listener | |
| `balance_updated` | `WalletHub.js` listens `balances` | ❌ MISMATCH | WalletHub.js:95 never fires |
| `wallet` | `WalletHub.js:88` listens `wallet` | ✅ | |
| `wallet_updated` | no listener | ❌ dead emitter | |
| `bot_paused` | `BotFleet.js:363` | ✅ | |
| `bot_resumed` | not subscribed directly | ❌ no listener | |
| `key_saved` | `APIKeySettings.js:63` | ✅ | |
| `key_tested` | `APIKeySettings.js:68` | ✅ | |
| `key_deleted` | `APIKeySettings.js:73` | ✅ | |
| `heartbeat` | not subscribed | ✅ (correctly ignored) | |
| `metrics_updated` | not subscribed directly | ❌ dead emitter | |
| `force_refresh` | not subscribed directly | ❌ dead emitter | |

### Frontend → Backend (Dead Listeners)

| Frontend Listens | Backend Emits | Issue |
|-----------------|---------------|-------|
| `trades` | `trade_executed`/`trade_opened`/`trade_closed` | ❌ MISMATCH — `LiveTradesPanel.js:38`, `ComparisonGraphs.js:81` |
| `balances` | `balance_updated` | ❌ MISMATCH — `WalletHub.js:95` |
| `transfer_updated` | (nothing) | ❌ DEAD LISTENER — `TransferHistory.js:41`, `AdminApproval.js:38` |
| `bots_update` | (not emitted) | ❌ DEAD LISTENER — `useDashboardState.js:767` |
| `overview_update` | (not emitted) | ❌ DEAD LISTENER |
| `system_health` | (not emitted) | ❌ DEAD LISTENER |
| `ai_task_update` | (not emitted) | ❌ DEAD LISTENER |
| `decisions` | (not emitted as WS event) | ❌ DEAD LISTENER — `DecisionTrace.js:23` via `useLastUpdate` |
| `whale` | (not emitted as WS event) | ❌ DEAD LISTENER — `WhaleFlowHeatmap.js:40` via `useLastUpdate` |

### High-Frequency WS Emitters (Jank Risk)

| Emitter | Rate | Event | Risk |
|---------|------|-------|------|
| `trading_scheduler.py:572` | 1x / 10s | `heartbeat` | Low |
| `rt_events.trade_executed` + `trade_opened` + `trade_closed` + `profit_updated` | Per trade (potentially rapid burst) | multiple | **HIGH** — with many bots, 4 WS messages per trade × N bots = rapid React render cascade |
| `rt_events.bot_status_changed` | Per status change | `bot_status_changed` | Medium |
| `metrics_updated` | TBD | `metrics_updated` | Medium |

---

## SECTION 6 — PERFORMANCE / JUMPY UI FINDINGS

### 6.1 Large Assets

| Asset | Size | Page Loaded On | Load Behavior | Risk |
|-------|------|----------------|--------------|------|
| `amarktai-network-final.mp4` | **8.2 MB** | Login + Register (`AuthLayout.js:29`) | `autoPlay muted loop` — browser fetches entire video | **HIGH** — blocks LCP; ~7s on 10 Mbps |
| `thunderstruck.mp3` | **4.7 MB** | Landing (`Landing.js:82`) | `preload="auto"` — full audio pre-fetched | **HIGH** — 4.7 MB wasted on users who never click play |
| `final-logo.png` | **964 KB** | Mobile topbar (`Dashboard.js:587`) | Standard `<img>`, no lazy | Medium — should be WebP |
| `background.mp4` | **1.9 MB** | Not referenced in source | Unused | Low |
| `poster.jpg` | **344 KB** | AuthLayout video poster | Shown during video load — acceptable | Low |
| `overview.jpg` | **364 KB** | `OverviewSection.js:278` | Standard `<img>` | Low |

**Combined login page media weight: ~13.5 MB**

### 6.2 Layout Shift Risks

| Component | Asset | Sizing | CLS Risk |
|-----------|-------|--------|---------|
| `AuthLayout.js` | `.mp4` | CSS-only sizing + poster.jpg | Low (poster prevents shift) |
| `Dashboard.js:536` | `final-logo-v2.png` | `style={{ width:'200px', height:'200px' }}` | ✅ None |
| `Dashboard.js:587` | `final-logo.png` (mobile) | CSS class only — no `width`/`height` attributes | **Medium** CLS risk |
| `Login.js:57` | `final-logo-v2.png` | `style={{ width:'200px', height:'200px' }}` | ✅ None |
| `OverviewSection.js:278` | `overview.jpg` | Parent has `minHeight: 400px` | Low |

### 6.3 Polling Loops / Re-render Storms

| Interval | Frequency | Location | API Calls | Re-render Risk |
|----------|-----------|----------|-----------|---------------|
| Price poll A | 4s | `useDashboardData.js:239` | `loadLivePrices` + `loadMetrics` + `loadSystemStatus` | Medium |
| Price poll B | 5s | `useDashboardState.js:691` | `loadLivePrices` | ⚠️ DUPLICATE of A |
| Price poll C | 4s | `useDashboardState.js:429` | `loadLivePrices` | ⚠️ TRIPLE DUPLICATE — 3 intervals for same data |
| Overview + Risk | 10s | `useDashboardState.js:461` | `loadOverviewData` + `loadRiskStatus` | Medium |
| Realtime check | 10s | `useDashboardState.js:489` | `GET /diagnostics/realtime` | Low |
| Projection calc | 60s | `useDashboardState.js:535` | None (local) | Low |
| Bot promotion | 300s | `useDashboardState.js:644` | `GET /bots/eligible-for-promotion` | Low |
| RTT monitor | 5s | `useDashboardState.js:785` | None (local) | Low |
| Countdown tick | 1s | `useDashboardState.js:714` | None (local) | **HIGH** — every second |
| Flokx status | 30s | `useDashboardState.js:714` | `GET /flokx/status` | Low |
| Flokx alerts | 30s | `useDashboardState.js:726` | `GET /flokx/alerts` | Low |
| Admin panel reload | 15s | `useDashboardState.js:3042` | 5 API calls per cycle | Medium (only when admin open) |
| **`useLastUpdate` ×8** | **1s each** | `useRealtime.js:74-79` | None (local) | **HIGH** — 8 `setState` calls/second |
| ConnectionStatus | 1s | `useRealtime.js:37` | None (local) | Medium |

**Combined high-frequency render load:** 9 simultaneous 1-second timers (8 `useLastUpdate` + 1 ConnectionStatus) each triggering `setState` → React reconciler processes ~9 re-render requests per second continuously while the dashboard is open.

### 6.4 Duplicate WebSocket Connect

| Call | File:Line |
|------|-----------|
| `realtimeClient.connect(token)` | `useDashboardData.js:257` — first call, correct |
| `realtimeClient.connect(token)` | `useDashboardState.js:750` — **DUPLICATE** against same singleton |

If the WS is already OPEN, the second call's guard (`if (this.ws?.readyState === WebSocket.OPEN) return`) prevents a second socket. However, `reconnectAttempts` is never reset when `connect(token)` is called again after logout+login, so re-login with failed prior connection will immediately fall to SSE without retrying WS.

---

## SECTION 7 — GO-LIVE READINESS CHECKLIST

### P0 — Must Fix Before Go-Live

| # | Item | Impact | Evidence (File:Line) | Verify Step |
|---|------|--------|---------------------|------------|
| P0-1 | Re-mount `routes.admin_endpoints` (deconflict collisions first) | Admin panel 100% broken | `server.py:3061` | `curl -X POST /api/admin/unlock` returns 200/401, not 404 |
| P0-2 | Re-mount `routes.ai_chat` | Login greeting broken; chat not persisted | `server.py:3082` | `curl -X POST /api/ai/chat/greeting` returns 200, not 404 |
| P0-3 | Fix `${API}/api/admin/start-fresh` → `${API}/admin/start-fresh` | Paper reset always 404 | `useDashboardState.js:2064` | DevTools: Start Fresh request URL is `/api/admin/start-fresh` |
| P0-4 | Fix `apiClient.get('/api/fetchai/...')` → `apiClient.get('/fetchai/...')` | FetchAI section always 404 | `FetchAISection.js:22,31` | DevTools: FetchAI status returns 200 |
| P0-5 | Set `CORS_ALLOWED_ORIGINS=https://amarktai.online` in production `.env` | CORS wildcard = security risk | `server.py:416` | Evil-origin `curl` test returns no `Access-Control-Allow-Origin` |
| P0-6 | Fix `.env.example` flag names to match backend (`ENABLE_PAPER_TRADING` etc.) | Silent misconfiguration | `.env.example:9,14,19` + `server.py:87` | Set `ENABLE_PAPER_TRADING=false` in `.env` → paper trading disabled |
| P0-7 | Fix admin email broadcast path mismatch | Admin broadcast emails fail | `useDashboardState.js:2882` | Admin broadcast → email received |
| P0-8 | Fix admin reset-password method+path | Admin can't reset passwords | `useDashboardState.js:3081` | Admin reset user password → success |
| P0-9 | Deconflict duplicate inline `server.py` admin routes before re-mounting `admin_endpoints` | Boot-time collision or silent shadowing | `server.py:2163,2214,2246` vs `admin_endpoints.py:783,2328,2344` | Server boots without collision warnings in logs |

### P1 — Strongly Recommended

| # | Item | Impact | Evidence | Verify |
|---|------|--------|----------|--------|
| P1-1 | Align WS event: `LiveTradesPanel` listen for `trade_executed`/`trade_opened`/`trade_closed` | Live trades never auto-update | `LiveTradesPanel.js:38`, `realtime_events.py:100` | Execute trade → panel updates without manual refresh |
| P1-2 | Align WS event: `WalletHub` listen for `balance_updated` | Wallet balances never auto-update | `WalletHub.js:95`, `realtime_events.py:226` | Balance change → wallet card updates |
| P1-3 | Implement `transfer_updated` backend emission | Transfer history never auto-updates | `TransferHistory.js:41` | Initiate transfer → history panel updates |
| P1-4 | Remove 2 of 3 duplicate price polling intervals | Triple `/api/prices/live` requests per cycle | `useDashboardState.js:429,691`, `useDashboardData.js:239` | DevTools: prices/live called ≤1x per 4s |
| P1-5 | Remove duplicate `realtimeClient.connect(token)` in `useDashboardState.js:750` | Risk of reconnect storm | `useDashboardState.js:750`, `useDashboardData.js:257` | DevTools WS: exactly 1 open connection |
| P1-6 | Add `reconnectAttempts = 0` reset in `realtimeClient.connect()` | Re-login falls straight to SSE | `realtime.js:connect()` | Logout → re-login → WS connected (not SSE) |
| P1-7 | Change `thunderstruck.mp3` to `preload="none"` | 4.7 MB audio pre-loaded on landing | `Landing.js:82` | Network tab: audio not fetched until play clicked |
| P1-8 | Fix `/ai/insights` path (likely `/analytics/insights`) | AI Insights returns 404 | `useDashboardState.js:2767` | Feature returns data |
| P1-9 | Fix `/profits/reinvest` path | Reinvest feature broken | `useDashboardState.js:2841` | Reinvest button succeeds |

### P2 — Nice-to-Have

| # | Item | Impact | Evidence | Verify |
|---|------|--------|----------|--------|
| P2-1 | Replace 8×1s `useLastUpdate` polling with event-driven updates | ~9 extra re-renders/second | `useRealtime.js:74-79` | React DevTools profiler: no 1s render bursts |
| P2-2 | Add `preload="metadata"` to `<video>` in `AuthLayout.js` | 8.2 MB video pre-fetched on login | `AuthLayout.js:22` | Lighthouse LCP improves |
| P2-3 | Convert `final-logo.png` (964 KB) to WebP | Reduce image payload | `Dashboard.js:587` + `public/assets/` | Image size < 200 KB |
| P2-4 | Add `width`/`height` to mobile logo `<img>` in `Dashboard.js:587` | Prevents layout shift (CLS) | `Dashboard.js:587` | Lighthouse CLS < 0.1 |
| P2-5 | Audit and remove unused assets (`background.mp4`, `background.jpg`, `logo.png`) | Clean repo | `public/assets/` | No 404s from removed assets |

---

## SECTION 8 — GO-LIVE VERIFICATION SCRIPT OUTLINE

> **Commands only — no code changes. Run after P0 fixes are applied.**

```bash
#!/bin/bash
# Amarktai Go-Live Verification Commands
# Usage: BASE=http://localhost:8000 TOKEN=<jwt> ADMIN_PASS=<pass> bash verify.sh

BASE="${BASE:-http://localhost:8000}"
TOKEN="${TOKEN:-REPLACE_ME}"
ADMIN_PASS="${ADMIN_PASS:-REPLACE_ME}"
AUTH="Authorization: Bearer $TOKEN"
JSON="Content-Type: application/json"

# 1. Health
curl -sf "$BASE/api/health/ping" | jq .status
# Expected: "ok"

# 2. Auth login
curl -sf -X POST "$BASE/api/auth/login" -H "$JSON" \
  -d '{"email":"test@test.com","password":"TestPass1!"}' | jq .access_token
# Expected: non-null string

# 3. P0-1: Admin unlock (must not 404 after fix)
curl -sf -X POST "$BASE/api/admin/unlock" -H "$AUTH" -H "$JSON" \
  -d "{\"password\":\"$ADMIN_PASS\"}" | jq .success
# Expected: true or false (NOT 404)

# 4. P0-2: AI chat greeting (must not 404)
curl -sf -X POST "$BASE/api/ai/chat/greeting" -H "$AUTH" | jq .content
# Expected: non-null string

# 5. P0-3: Start Fresh path test
curl -s -o /dev/null -w "double-api: %{http_code}\n" \
  -X POST "$BASE/api/api/admin/start-fresh" -H "$AUTH"
# Expected: 404 (double /api still goes to 404)
curl -s -o /dev/null -w "correct-path: %{http_code}\n" \
  -X POST "$BASE/api/admin/start-fresh" -H "$AUTH" -H "$JSON" \
  -d '{"confirmation_phrase":"WRONG","scope":"paper_only"}'
# Expected: 400 (wrong phrase), not 404

# 6. P0-4: FetchAI path test
curl -s -o /dev/null -w "double-api: %{http_code}\n" \
  "$BASE/api/api/fetchai/status" -H "$AUTH"
# Expected: 404
curl -sf "$BASE/api/fetchai/status" -H "$AUTH" | jq .status
# Expected: "connected" or config message

# 7. Admin users list
curl -sf "$BASE/api/admin/users" -H "$AUTH" | jq length
# Expected: integer >= 0

# 8. Admin bots list
curl -sf "$BASE/api/admin/bots" -H "$AUTH" | jq length
# Expected: integer >= 0

# 9. Admin runtime reset path
curl -s -o /dev/null -w "runtime-reset: %{http_code}\n" \
  -X POST "$BASE/api/admin/runtime/reset" -H "$AUTH" -H "$JSON" \
  -d '{"confirmation":"WRONG"}'
# Expected: 400/422 (wrong confirm), not 404

# 10. Emergency stop status
curl -sf "$BASE/api/admin/emergency-stop/status" -H "$AUTH" | jq .
# Expected: JSON object

# 11. CORS security check
curl -sf -H "Origin: https://evil.com" "$BASE/api/health/ping" -I 2>&1 |   grep -i "access-control-allow-origin"
# Expected: no output OR only "https://amarktai.online"

# 12. Prices live
curl -sf "$BASE/api/prices/live" -H "$AUTH" | jq 'keys'
# Expected: ["BTC-ZAR","ETH-ZAR",...]

# 13. Overview snapshot
curl -sf "$BASE/api/overview/snapshot" -H "$AUTH" | jq .paper_trading
# Expected: true or false

# 14. WebSocket (requires wscat: npm i -g wscat)
# wscat -c "ws://localhost:8000/api/ws?token=$TOKEN" --wait 5
# Expected: receives {"type":"connection","status":"connected"} within 2s

# 15. Double /api detection (must all be 404)
for bad_path in "/api/api/fetchai/status" "/api/api/admin/start-fresh" "/api/api/admin/users"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$bad_path" -H "$AUTH")
  echo "Double-api $bad_path: $STATUS (must be 404)"
done

echo "=== Verification Complete ==="
```

---

## SECTION 9 — DUPLICATE / CONFLICTING ROUTES

### Collisions When `admin_endpoints` Is Re-Mounted (Must Resolve First)

| Path | Currently Mounted Handler | `admin_endpoints` Handler |
|------|--------------------------|--------------------------|
| `GET /api/admin/system-stats` | `admin_enhanced.py:219` | `admin_endpoints.py:915` |
| `DELETE /api/admin/users/{id}` | `server.py:2163` | `admin_endpoints.py:783` |
| `PUT /api/admin/users/{id}/block` | `server.py:2214` | `admin_endpoints.py:2328` |
| `PUT /api/admin/users/{id}/password` | `server.py:2246` | `admin_endpoints.py:2344` |

FastAPI will log these collisions at boot (collision detector at `server.py:3160+`). First-registered handler wins. Remove or deconflict inline `server.py` routes before mounting.

### Chat Namespace Split (Non-Colliding but Confusing)

`chat_enhanced.py` and `chat_endpoints.py` both use `prefix="/api/chat"` but serve different path suffixes. No runtime collision. But split ownership makes future maintenance confusing.

---

## SECTION 10 — ORPHANED BACKEND FEATURES

| Feature | Route | Module | Status |
|---------|-------|--------|--------|
| Backtesting | `POST /api/backtest/run`, `/optimize`, `GET /history` | `backtesting.py` | NOT MOUNTED — no frontend calls |
| AI/ML prediction | No route found | — | Frontend calls `/api/ml/predict` → 404 |
| AI Insights | `GET /api/analytics/insights` | `analytics_api.py:883` | MOUNTED but frontend calls wrong path `/api/ai/insights` |
| Profits reinvest | No `/api/profits/reinvest` | — | Frontend calls this path → 404 |
| 2FA | All 2FA endpoints | `two_factor_auth.py` | No frontend 2FA flow found |
| Treasury | All treasury endpoints | `treasury.py` | No frontend calls found |
| Execution quality | All endpoints | `execution_quality.py` | No frontend calls found |
| Payment agent | All endpoints | `payment_agent_endpoints.py` | No frontend calls found |
| Ledger fills/audit | `/api/ledger/fills`, `/ledger/audit-trail`, `/ledger/reconcile` | `ledger_endpoints.py` | No frontend calls found |
| Admin email-all-users | `POST /api/admin/email-all-users` | `server.py:2105` | Frontend calls wrong path `/admin/email/broadcast` |
| Wallet updated event | `wallet_updated` WS event | `realtime_events.py:455` | No frontend listener |
| Metrics updated event | `metrics_updated` WS event | `realtime_events.py:367` | No frontend listener |
| Force refresh event | `force_refresh` WS event | `realtime_events.py:198` | No frontend listener |

---

*End of Forensic Audit Report v2 — Amarktai Network*  
*Produced: 2026-02-20 | READ-ONLY | No code was changed in producing this report.*
