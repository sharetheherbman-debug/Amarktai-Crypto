# Frontend Production Go-Live Checklist

This document covers how to build, gate, and manually QA the frontend before every production deployment.

---

## Build Gate (Single Command)

```bash
cd frontend && ./scripts/prod_gate.sh
```

Or from repo root:
```bash
./frontend/scripts/prod_gate.sh
```

**What it does:**

| Step | Action | Failure = |
|------|--------|-----------|
| 1 | `npm ci` — clean, reproducible install from `package-lock.json` | FAIL gate |
| 2 | ESLint — zero-warning lint pass (skipped if no config found) | FAIL gate |
| 3 | `npm run build` — production React build via CRACO | FAIL gate |
| 4 | `verify-build.js` — checks all `index.html` `/static/` refs exist on disk | FAIL gate |

Script exits **0** only when all steps pass.

---

## Running on a VPS

```bash
# Install Node 20+ if needed
node --version  # must be >= 20

# One-shot gate
cd /path/to/repo/frontend
./scripts/prod_gate.sh
```

---

## Manual QA Steps

### 1. Login Flow
- [ ] Navigate to `/login`
- [ ] Enter valid credentials → redirected to `/dashboard`
- [ ] Enter invalid credentials → error toast shown (no console exception)
- [ ] Clear `localStorage.token` → refreshing `/dashboard` redirects to `/login`
- [ ] After token expiry (401) → redirected to `/login` with session-expired message

### 2. API Setup Section
- [ ] Navigate to API Setup section
- [ ] Verify exchange keys show real status from `/api/keys/status`
- [ ] Add/remove an API key and confirm status updates immediately
- [ ] OpenAI key missing → AI Chat section shows "AI Key Not Set" badge, NOT "Connected"

### 3. Bot Status
- [ ] Bots section shows live data from `/api/bots/status`
- [ ] If no bots: empty state displayed (not fake "0 bots active")
- [ ] Bot status badges (active/paused/quarantined) reflect `/api/bots/status` response

### 4. System Mode
- [ ] System Mode section shows PAPER or LIVE based on `/api/system/mode`
- [ ] Topbar badge shows `PAPER MODE` or `LIVE MODE` (never hardcoded)
- [ ] **Risk badge** shows `Checking...` on initial load until `/api/risk/status` responds

### 5. Realtime Events
- [ ] Topbar shows `Connected` badge after WebSocket connects
- [ ] Disconnect network → topbar shows `Reconnecting` badge and red ConnectionStatus banner
- [ ] Reconnect network → banner dismisses and badge returns to `Connected` automatically
- [ ] Live price ticker updates in real-time (BTC/ZAR, ETH/ZAR, XRP/ZAR)
- [ ] Bot status updates in `bots_update` events reflect in the bot list without page refresh

### 6. Trades Table
- [ ] Trades section loads from `/api/trades/recent?limit=50`
- [ ] Empty state shows "No recent trades" (not placeholder rows)
- [ ] New trade events via WebSocket append to the top of the list

### 7. Graphs / Charts
- [ ] Profit history chart loads from `/api/analytics/profit-history`
- [ ] If no data: chart shows empty/zero state (not fake sample data)
- [ ] Drawdown and equity charts render without JS errors in console

### 8. Fetch.ai Section
- [ ] With no Fetch.ai API key: shows "Fetch.ai Not Configured" state (not fake "Active")
- [ ] After configuring key: shows real agent/signal data from `/api/fetchai/status`

### 9. Flokx Section
- [ ] With no Flokx API key: shows "Flokx Not Configured" state (not fake "Active")
- [ ] After configuring key: shows real alerts from `/api/flokx/*`

### 10. Admin Panel
- [ ] Admin panel is **not visible** in the sidebar for regular users
- [ ] Admin panel unlocked only via AI Chat command "show admin"
- [ ] Admin panel re-hidden when chat is closed or user navigates away

---

## Expected Error States (Keys Not Configured)

| Feature | Expected State | Endpoint |
|---------|---------------|----------|
| Fetch.ai | "Fetch.ai Not Configured" banner | `/api/fetchai/status` |
| Flokx | "Flokx Not Configured" banner | `/api/flokx/status` |
| HuggingFace | "HuggingFace Not Configured" banner | `/api/huggingface/test-connection` |
| OpenAI / AI Chat | "AI Key Not Set" badge in topbar | `/api/ai/status` |
| Exchange API | "Not tested" / red dot in API Setup | `/api/keys/status` |
| Live trading | Live trading toggle disabled | `/api/system/mode` |

---

## Pass / Fail Criteria

| Result | Meaning |
|--------|---------|
| **PASS** | Build succeeds, all assets verified, zero lint errors/warnings |
| **FAIL** | `npm ci` fails, ESLint has errors/warnings, build fails, or a referenced asset is missing from `build/` |

---

## Realtime Connection Architecture

```
Browser WebSocket → ws://host/api/ws?token=<JWT>
  │ on connect   → sets topbar badge: Connected (green)
  │ on close     → reconnect with exponential backoff (1s → 2s → 4s → … → 30s max)
  │ on 5 failed  → falls back to SSE at /api/realtime/events
  │ SSE fails    → falls back to HTTP polling (5–30s intervals per endpoint)
  └ circuit breaker (3 × 502/503/504) → pauses all requests + shows red banner
```

The `ConnectionStatus` component (`src/components/ConnectionStatus.jsx`) renders a fixed red banner at the top of the screen whenever the circuit breaker is OPEN (backend unreachable).
