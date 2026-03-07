# FORENSIC GO-LIVE AUDIT REPORT
## Amarktai Network — Full Repository Inspection
**Date:** 2026-03-07  
**Auditor:** Copilot Coding Agent  
**Branch:** copilot/full-forensic-audit  
**Scope:** Complete codebase — frontend, backend, scripts, deployment, docs, tests

---

## 1. Executive Summary

The Amarktai Network repository is a large, iteratively built trading platform that has accumulated significant technical debt across multiple dimensions. The codebase is structurally functional at its core but contains **numerous duplicate systems, dead code layers, contradictory configurations, and architectural inconsistencies** that create serious go-live risk.

**Most Critical Blockers:**
1. **CI YAML indentation bug** — `env:` block for `Build frontend` step had `CI: true` / `NODE_ENV: production` at incorrect indentation, meaning build env vars were never passed. **THIS HAS BEEN FIXED in this PR.**
2. **bot_control.py routes missing `/api` prefix** — `POST /bots/{bot_id}/pause|resume|start` are mounted without `/api` prefix and are unreachable from the frontend via the standard API path.
3. **Three separate platform/exchange truth sources** in the frontend that can diverge.
4. **Env variable naming contradictions** across two `.env.example` files vs what `config.py` actually reads.
5. **Multiple email service files** (7 total across root and services/).
6. **Two conflicting systemd service definitions** pointing to different paths, users, and configurations.
7. **Duplicate paper-reset routes** in two different router families.
8. **14 of 27 dashboard section files** not imported in Dashboard.js (dead dead UI code).
9. **92 docs** in `docs/` with overlapping, stale, and contradictory deployment instructions.
10. **Phase 5/6/8 legacy endpoints** still mounted in production.

---

## 2. Repo Structure Overview

```
/ (root)
├── .github/workflows/ci.yml       — CI pipeline (BUG FIXED: env indentation)
├── .env.example                   — Root env template (CONFLICTS with backend/.env.example)
├── AUDIT_REPORT.md                — Stale partial audit from previous session
├── GO_LIVE_TRUTH_AUDIT.md         — Another partial audit document
├── VERIFICATION.md, DEPLOY.md, ACCEPTANCE_TESTS.md, etc.  — Multiple root-level docs
├── audit_report.json              — JSON audit snapshot from automated script
├── backend/                       — FastAPI Python backend (3180-line server.py)
│   ├── server.py                  — Main entry; mounts 70+ routers; route collision detector
│   ├── routes/ (70 files)         — Over-proliferated route modules
│   ├── services/ (50+ files)      — Service layer, many duplicated
│   ├── engines/ (30+ files)       — Trading engines, several duplicated
│   ├── config.py                  — PRIMARY config (reads ENABLE_* vars)
│   ├── config/settings.py         — SECONDARY config module (separate path)
│   ├── core/settings.py           — TERTIARY settings (claims to be "ONE TRUTH")
│   ├── _archive/                  — Still has OVEX/VALR platform_constants.py
│   └── migrations/                — 6 one-off migration scripts still present
├── frontend/                      — React 18 / Craco / Tailwind
│   ├── src/pages/Dashboard.js     — 867-line single-page dashboard
│   ├── src/hooks/useDashboardState.js  — 3246-line mega-hook (68 API calls)
│   ├── src/pages/dashboard/sections/  — 27 section files; 14 UNUSED
│   ├── src/components/Dashboard/  — 7 components; 6 UNUSED
│   └── src/constants/platforms.js — One of THREE platform config sources
├── docs/ (92 files)               — Massive docs; 55 archived; many stale
├── scripts/ (80+ files)           — Extreme proliferation of smoke/verify scripts
├── tests/ (26 test files)         — Reasonable coverage but 2 ignored
├── ops/                           — Canonical deploy scripts and systemd
└── tools/                         — Misc helper tools
```

---

## 3. Frontend Audit

### 3.1 Dead Pages — MEDIUM

**Files:** `frontend/src/pages/Features.js`, `Privacy.js`, `Terms.js`, `About.js`  
**Issue:** These four page files exist but are **not registered in `App.js` routes**. They use `PublicPageLayout`/`PublicNav` components. They are completely unreachable at runtime.  
**Domain:** UI routing truth  
**Severity:** MEDIUM — not a crash risk but confuses future developers and wastes bundle space

### 3.2 Three Platform/Exchange Config Sources — HIGH

**Files:**
- `frontend/src/constants/platforms.js` → `SUPPORTED_PLATFORMS`, `PLATFORM_CONFIG`
- `frontend/src/lib/platforms.js` → `PLATFORMS`
- `frontend/src/config/exchanges.js` → `EXCHANGES`

**Issue:** All three define the same 7 exchanges with different object structures and different field names (`maxBots` vs `max_bots`, `requiresPassphrase` vs `requiresPassphrase`). `useDashboardState.js` imports from **both** `constants/platforms.js` and `config/exchanges.js`. This creates multiple sources of truth for exchange configuration.  
**Domain:** Exchange/platform truth  
**Severity:** HIGH — if one file is updated and others are not, exchange behavior diverges

### 3.3 Dead Dashboard Sections (14 of 27) — HIGH

**Files in `frontend/src/pages/dashboard/sections/` NOT imported in `Dashboard.js`:**
- `AiChatSection.js` — imported only by WelcomeSection and AiCommandSection (both also unused from Dashboard)
- `AiCommandSection.js` — wraps AiChatSection, not imported in Dashboard
- `BotOperationsSection.js` — thin wrapper over BotManagementSection
- `BotRadarSection.js` — standalone bot radar UI
- `CoinStatsPanel.js` — CoinStats integration panel
- `ExchangeStatusSection.js` — exchange health UI
- `HomeSection.js` — home/welcome landing UI
- `HuggingFacePanel.js` — HuggingFace AI panel
- `ProfileControlsSection.js` — wraps ProfileSection
- `ScalperBotsPanel.js` — scalper bot management UI
- `TradingMonitorSection.js` — trade monitoring UI
- `TruthConsoleSection.js` — truth console UI
- `WalletTreasurySection.js` — treasury UI
(Note: `ProfitsSection` is imported but used inside MetricsWithTabsSection, not as a named nav entry)

**Issue:** 14 fully-built sections exist in the repo but are **never mounted in Dashboard.js**. Dashboard only uses 13 of the 27 section files.  
**Domain:** UI truth, dashboard functionality  
**Severity:** HIGH — BotRadar, ScalperBots, TruthConsole, ExchangeStatus, CoinStats, HuggingFace are potentially important feature sections that users cannot see

### 3.4 Wrapper Section Anti-Pattern — MEDIUM

**Files:**
- `BotOperationsSection.js` wraps `BotManagementSection` (adds no logic)
- `AiCommandSection.js` wraps `AiChatSection` (adds minor structure)
- `ProfileControlsSection.js` wraps `ProfileSection` (adds minor structure)

**Issue:** These wrapper files create naming confusion. `BotManagementSection` is what's used; `BotOperationsSection` with the near-identical name is dead weight. Future developers may import the wrong one.  
**Domain:** Dashboard architecture  
**Severity:** MEDIUM

### 3.5 Dead Components in `components/Dashboard/` — HIGH

**Files (all in `frontend/src/components/Dashboard/`):**
- `BotQuarantineSection.js` — NOT imported anywhere
- `BotTrainingSection.js` — NOT imported anywhere
- `CreateBotSection.js` — NOT imported anywhere
- `LivePricesTicker.js` — NOT imported anywhere
- `MetricsOverview.js` — NOT imported anywhere
- `SystemModesSection.js` — NOT imported anywhere
- `TrainingQuarantineSection.js` — IS imported by `BotManagementSection.js` (only survivor)

**Issue:** The `components/Dashboard/` subdirectory is an older generation of dashboard components. Six of seven files are completely unused. They duplicate functionality now in `pages/dashboard/sections/`.  
**Domain:** Dashboard UI truth — two generations of component architecture coexisting  
**Severity:** HIGH — creates confusion about which component to use when updating bot/quarantine UI

### 3.6 Dead Top-Level Components — MEDIUM

**Files in `frontend/src/components/`:**
- `AIChatPanel.js` — NOT used anywhere
- `AdminApproval.js` — NOT used anywhere
- `BotLifecycleControls.js` — NOT used anywhere
- `ComparisonGraphs.js` — NOT used anywhere
- `LiveTradesPanel.js` — NOT used anywhere (LiveTradesSection in sections/ IS used)
- `PlatformPanel.js` — NOT used anywhere
- `TransferCreate.js` — NOT used anywhere
- `TransferHistory.js` — NOT used anywhere
- `VersionBadge.js` — NOT used anywhere
- `WalletOverview.js` — NOT used anywhere

**Issue:** 10 components exist and compile into the bundle but are never rendered.  
**Domain:** Frontend bloat  
**Severity:** MEDIUM

### 3.7 Dead Render Functions in Dashboard.js — LOW

**File:** `frontend/src/pages/Dashboard.js` lines 293, 437, 444, 450

**Issue:** Functions `renderProfile()`, `renderWalletHub()`, `renderAPIKeys()`, `renderBots()` are defined but **never called** in the JSX. The sections are rendered directly inline in the conditional blocks. These dead helper functions add confusion without value.  
**Domain:** Dashboard architecture  
**Severity:** LOW

### 3.8 Oversized useDashboardState Hook — HIGH

**File:** `frontend/src/hooks/useDashboardState.js` — **3,246 lines**, **68 API calls**

**Issue:** This single hook manages ALL dashboard state, ALL API polling, ALL event handling, ALL bot management actions. It imports from `config/exchanges`, `constants/platforms`, `lib/realtime`, `hooks/useRealtime`, and contains hardcoded exchange lists in addition to what's in the platform constants. This god-hook is a maintenance liability and creates multiple implicit source-of-truth issues within a single file.  
**Domain:** State management truth  
**Severity:** HIGH — any regression here can break the entire dashboard

### 3.9 Hardcoded Exchange List Inside State Hook — MEDIUM

**File:** `frontend/src/hooks/useDashboardState.js` line 18
```js
const EXCHANGES_NEEDING_SECRET = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];
const EXCHANGES_NEEDING_PASSPHRASE = ['kucoin', 'bitget'];
```
**Issue:** These hardcoded arrays duplicate what's already defined in `constants/platforms.js` (`requiredKeyFields`, `requiresPassphrase`). If an exchange is added or changed, it must be updated in BOTH places.  
**Domain:** Exchange truth  
**Severity:** MEDIUM

### 3.10 Dual API Client Pattern — LOW

**Files:** `frontend/src/lib/api.js` (URL builder + wsUrl) and `frontend/src/lib/apiClient.js` (axios instance)

**Issue:** These two files are both imported across the codebase. `apiClient.js` imports `API_BASE` from `api.js`. They serve different but related purposes. The dual-file pattern can confuse developers about which to import for simple vs complex requests.  
**Domain:** Frontend API contract  
**Severity:** LOW — functional but architecturally messy

---

## 4. Backend Audit

### 4.1 bot_control.py Routes Missing `/api` Prefix — CRITICAL

**File:** `backend/routes/bot_control.py`
```python
router = APIRouter()  # NO PREFIX

@router.post("/bots/{bot_id}/pause")
@router.post("/bots/{bot_id}/resume")
@router.post("/bots/{bot_id}/start")
@router.get("/bots/{bot_id}/status")
```

**Issue:** When `app.include_router(router_obj)` is called without an additional prefix, these routes mount at `/bots/{bot_id}/*` — NOT `/api/bots/{bot_id}/*`. Meanwhile, `bot_lifecycle.py` has `prefix="/api/bots"` and provides `POST /{bot_id}/pause`, `POST /{bot_id}/resume`, `POST /{bot_id}/start`, `GET /{bot_id}/status` at the correct `/api/bots/{bot_id}/*` paths.

The frontend (`useDashboardState.js`) calls `post('/bots/${botId}/resume')` via apiClient with `baseURL: /api`, which resolves to `/api/bots/{bot_id}/resume`. This hits `bot_lifecycle.py`, **never bot_control.py**.

`bot_control.py` routes are effectively **dead/unreachable**.  
**Domain:** Bot control truth — pause/resume/start are silently served by bot_lifecycle.py  
**Severity:** CRITICAL — dead routes create confusion; any attempt to use bot_control routes will fail with 404

### 4.2 Three Config Modules — HIGH

**Files:**
- `backend/config.py` — reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`, etc.
- `backend/config/settings.py` — different settings module, different `env_bool()` implementations
- `backend/core/settings.py` — claims to be "ONE TRUTH Configuration Module"

**Issue:** THREE Python config modules. `core/settings.py` is designated canonical but `config.py` is what most modules actually import. `server.py` uses `import config` (the root config.py). If `config.py` and `core/settings.py` diverge on defaults or variable names, behavior will differ across modules.  
**Domain:** Configuration truth  
**Severity:** HIGH

### 4.3 Env Variable Naming Contradiction — CRITICAL

**Root `.env.example` uses:**
```
PAPER_TRADING=0       # int 0/1
LIVE_TRADING=0        # int 0/1
AUTOPILOT_ENABLED=0   # int 0/1
```

**Backend `config.py` reads:**
```python
ENABLE_PAPER_TRADING = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'  # string true/false
ENABLE_LIVE_TRADING = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'
ENABLE_AUTOPILOT = os.getenv('ENABLE_AUTOPILOT', 'true').lower() == 'true'
```

**Issue:** The root `.env.example` (the file most users will copy first) sets `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED` — variables that `config.py` does NOT read. `config.py` reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`. A user who copies root `.env.example` will have NO effect on the backend's trading modes.

Additionally, `backend/.env.example` uses BOTH naming schemes — `PAPER_TRADING=1` (old) AND `ENABLE_PAPER_TRADING` (new) — creating further confusion.  
**Domain:** Trading mode gate truth  
**Severity:** CRITICAL — new deployment using root `.env.example` will have trading modes at their DEFAULT values (`ENABLE_PAPER_TRADING=true`, `ENABLE_LIVE_TRADING=false`) regardless of what's in .env

### 4.4 Seven Email Service Files — HIGH

**Backend root:**
- `backend/email_alerts.py`
- `backend/email_scheduler.py`
- `backend/email_service.py`

**Services:**
- `backend/services/email_alerts.py`
- `backend/services/email_service.py`
- `backend/services/email_service_enhanced.py`
- `backend/services/enhanced_email_service.py`

**Issue:** Seven files providing email functionality with overlapping names. It is unclear which is canonical. Some modules may import from the root versions, others from services/. Changes to one won't propagate to others. The `enhanced_email_service.py` vs `email_service_enhanced.py` naming is especially confusing.  
**Domain:** Email service truth  
**Severity:** HIGH

### 4.5 Duplicate Admin Routers — HIGH

**Files:**
- `backend/routes/admin_endpoints.py` → `prefix="/api/admin"`, tags `["Admin Dashboard"]`
- `backend/routes/admin_enhanced.py` → `prefix="/api/admin"`, tags `["Enhanced Admin"]`

**Issue:** Two routers share the `/api/admin` prefix. `admin_enhanced.py` adds endpoints like `GET /api/admin/users/list`, `GET /api/admin/users/{user_id}/bots`, `GET /api/admin/dashboard/stats`. `admin_endpoints.py` has `GET /api/admin/users`, `GET /api/admin/users/{user_id}`. These don't literally collide (FastAPI's route collision detector would catch exact path+method duplicates), but having two admin routers under the same prefix is architecturally fragile.  
**Domain:** Admin truth  
**Severity:** HIGH

### 4.6 Duplicate Chat Routers — HIGH

**Files:**
- `backend/routes/chat_endpoints.py` → `prefix="/api/chat"`, has `POST /message`, `GET /history`
- `backend/routes/chat_enhanced.py` → `prefix="/api/chat"`, has `POST /clear`, `GET /daily-summary`, `GET /welcome`, `POST /session/end`
- `backend/routes/ai_chat.py` → `prefix="/api/ai"`, has `POST /chat`, `GET /chat/history`, `POST /chat/clear`, `DELETE /chat/history`, etc.

**Issue:** Chat history is accessible via `/api/chat/history` (chat_endpoints) AND `/api/ai/chat/history` (ai_chat). Chat clear is at `/api/chat/clear` (chat_enhanced) AND `/api/ai/chat/clear` (ai_chat). Depending on which the frontend calls, they may hit different underlying implementations.  
**Domain:** AI chat truth, session history  
**Severity:** HIGH

### 4.7 Five Wallet Routers — HIGH

**Files (all prefix `/api/wallet`):**
- `backend/routes/wallet_endpoints.py` — required-capital, balances-legacy, requirements, funding-plans
- `backend/routes/wallet_hub.py` — health, paper, paper/deposit, paper/topup, paper/reset, live, transfer, balances, transactions, admin endpoints
- `backend/routes/wallet_transfers_enhanced.py` — transfers/create, transfers, transfers/{id}, transfers/{id}/cancel, admin/transfers/pending, etc.
- `backend/routes/wallet_addresses.py` — address management
- (routes/wallet_transfers.py noted as REMOVED in server.py comment)

**Issue:** `GET /api/wallet/balances` is in wallet_hub.py. `GET /api/wallet/balances-legacy` is in wallet_endpoints.py. Having five routers under `/api/wallet` makes it nearly impossible to understand the full wallet API surface without reading all five files. Admin transfer approval is in wallet_transfers_enhanced.py AND wallet_hub.py.  
**Domain:** Wallet truth  
**Severity:** HIGH

### 4.8 Six System Routers — HIGH

**Files (all prefix `/api/system` or routing system functionality):**
- `backend/routes/system.py` → `/api/system/ping`, `/api/system/platforms`, `/api/system/gates`
- `backend/routes/system_mode.py` → `/api/system/mode`, `/api/system/paper-reset`, `/api/system/reset-paper`, `/api/system/mode/switch`, `/api/system/mode/readiness`
- `backend/routes/system_limits.py` → `/api/system` limits
- `backend/routes/system_status.py` → `/api/system` status
- `backend/routes/emergency_stop_endpoints.py` → `/api/system/emergency-stop`, `/api/system/emergency-gates`
- `backend/routes/live_trading_gate.py` → `/api/system/request-live`, `/api/system/live-eligibility`

**Issue:** SIX routers under `/api/system`. The paper-reset endpoint appears in BOTH `system_mode.py` and `wallet_hub.py` under different paths (see §10).  
**Domain:** System control truth  
**Severity:** HIGH

### 4.9 Phase Endpoints Still Mounted — MEDIUM

**Files:**
- `backend/routes/phase5_endpoints.py` → `prefix="/api/phase5"` — Capital/risk endpoints, circuit breaker
- `backend/routes/phase6_endpoints.py` → `prefix="/api/phase6"` — AI/learning endpoints
- `backend/routes/phase8_endpoints.py` → `prefix="/api/phase8"` — Audit/email endpoints

**Issue:** These "phase" endpoints are development-era routes that should have been absorbed into canonical endpoint families. They remain mounted in production under `/api/phase5/*`, `/api/phase6/*`, `/api/phase8/*`. The functionality they expose (capital allocation, AI analysis, audit trail) overlaps with canonical routes.  
**Domain:** Endpoint cleanliness  
**Severity:** MEDIUM — low risk of functional conflict but adds confusion and potential duplication

### 4.10 Two Capital Allocator Implementations — HIGH

**Files:**
- `backend/capital_allocator.py` — root-level module
- `backend/engines/capital_allocator.py` — engines/ module

**Issue:** Two files named `capital_allocator.py` in different locations. Imports could resolve to either depending on `sys.path` order. Whichever is not canonical will diverge.  
**Domain:** Capital allocation truth  
**Severity:** HIGH

### 4.11 Two Autopilot Engine Implementations — HIGH

**Files:**
- `backend/autopilot_engine.py` — root-level
- `backend/engines/autopilot_production.py` — engines/ module

**Issue:** Two autopilot engine files. `server.py` imports from `autopilot_engine.py` (root). The `engines/autopilot_production.py` may have diverged features.  
**Domain:** Autopilot execution truth  
**Severity:** HIGH

### 4.12 Two Trading Engine Live Files — HIGH

**Files:**
- `backend/engines/trading_engine_live.py`
- `backend/engines/trading_engine_production.py`

**Issue:** `trading_scheduler.py` imports `from engines.trading_engine_live import live_trading_engine`. The `trading_engine_production.py` may be the newer version that was never wired in. Any fixes to live execution may have been applied to the wrong file.  
**Domain:** Live trading execution truth  
**Severity:** HIGH

### 4.13 AI Command Router — Three Versions — HIGH

**Files:**
- `backend/services/ai_command_router.py`
- `backend/services/ai_command_router_enhanced.py`
- `backend/services/ai_command_router_legacy.py`

**Issue:** Three AI command router service files. Which is canonical? If `ai_command_router_legacy.py` is still imported anywhere, it could serve stale AI command logic.  
**Domain:** AI command truth  
**Severity:** HIGH

### 4.14 dashboard_overview.py Has Hardcoded `/api` in Routes — MEDIUM

**File:** `backend/routes/dashboard_overview.py`
```python
router = APIRouter()  # No prefix

@router.get("/api/dashboard/overview")
@router.get("/api/overview/snapshot")
```

**Issue:** This router defines `/api` in the path directly rather than via `prefix=". Other routers use `prefix="/api/..."`. When `app.include_router(router_obj)` is called, these routes mount correctly at `/api/dashboard/overview` and `/api/overview/snapshot`, but the pattern is inconsistent and brittle.  
**Domain:** Endpoint architecture  
**Severity:** MEDIUM

### 4.15 admin_start_fresh.py Has Hardcoded `/api` in Routes — MEDIUM

**File:** `backend/routes/admin_start_fresh.py`
```python
router = APIRouter()  # No prefix

@router.post("/api/admin/start-fresh")
@router.post("/api/admin/reset-user-data")
@router.post("/api/bots/reset")
```

Same issue as dashboard_overview.py — `/api` is hardcoded in path instead of using prefix.  
**Domain:** Endpoint architecture  
**Severity:** MEDIUM

### 4.16 _archive Module Contains Old Platform List — HIGH

**File:** `backend/_archive/platform_constants.py`
```python
SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'ovex', 'valr']
```

**Issue:** The archived file still lists OVEX and VALR as supported platforms. While the CI correctly checks `if grep -r "from _archive\|import _archive"` (and finds none), the file's existence in the repo creates confusion. Any developer who accidentally imports from it gets a list with forbidden exchanges.  
**Domain:** Exchange platform truth  
**Severity:** HIGH — FLOKx has a regression test; OVEX/VALR in _archive do not

### 4.17 Four Scheduler Modules — HIGH

**Files:**
- `backend/trading_scheduler.py` — main trading loop, CRITICAL
- `backend/autonomous_scheduler.py` — autonomous bot management
- `backend/ai_scheduler.py` — AI learning cycles
- `backend/email_scheduler.py` — email report timing

**Issue:** Four separate schedulers. `trading_scheduler.py` imports from `engines/trading_engine_live.py`. `autonomous_scheduler.py` may overlap with autopilot functionality. Scheduler start/stop state is not coordinated through a single interface, meaning emergency stops may not halt all schedulers simultaneously.  
**Domain:** Scheduler execution truth  
**Severity:** HIGH

### 4.18 Three Realtime/WebSocket Managers — HIGH

**Files:**
- `backend/realtime_events.py` — `RealTimeEventBus`, `RealTimeEvents`
- `backend/websocket_manager.py` — WebSocket connection manager
- `backend/services/realtime_broadcaster.py` — broadcaster service
- `backend/services/realtime_service.py` — realtime service layer

**Issue:** Four separate files handling real-time event propagation. Which is the canonical event bus? If different modules use different event buses, events can be broadcast to some clients but not others. Any disconnection from the canonical bus means missed state updates.  
**Domain:** Realtime event truth  
**Severity:** HIGH

### 4.19 Paper Reset in Multiple Routes — HIGH

**Endpoints:**
- `POST /api/system/paper-reset` (system_mode.py)
- `POST /api/system/reset-paper` (system_mode.py — duplicate function!)
- `POST /api/system/paper-reset/validate` (system_mode.py)
- `POST /api/wallet/paper/reset` (wallet_hub.py)

**Issue:** Paper reset has FOUR endpoints across two router families. Two of them in `system_mode.py` (`paper-reset` and `reset-paper`) appear to do the same thing. `wallet_hub.py` provides a third paper reset at a completely different path. These may have different implementation details (different collections cleared, different reset scope).  
**Domain:** Paper reset truth, wallet truth  
**Severity:** HIGH — if the wrong reset endpoint is called, paper wallet state may be partially reset

---

## 5. Realtime / Scheduler / Execution Audit

### 5.1 Trading Mode Resolution — CRITICAL

**Issue:** The system resolves trading mode (paper vs live) from multiple sources:
1. `system_modes_collection` in MongoDB (per-user, set via `/api/system/mode`)
2. `ENABLE_PAPER_TRADING` / `ENABLE_LIVE_TRADING` environment variables read by `config.py`
3. `core/settings.py` `FeatureFlags` class (separate env reads)
4. Individual bot `trading_mode` field

**Trading scheduler code:**
```python
modes = await db.system_modes_collection.find_one({"user_id": user_id}, ...)
is_live_trading = modes.get('liveTrading', False)
is_paper_trading = not is_live_trading  # Paper by default
```

The scheduler uses DB mode (per-user) but `config.py` uses env vars. These can contradict each other.  
**Domain:** Paper/live trading mode truth  
**Severity:** CRITICAL

### 5.2 Bot Count Sources — HIGH

**Issue:** Bot counts are computed in multiple places:
- `routes/bot_lifecycle.py` — `GET /api/bots/status` queries `bots_collection` directly
- `routes/scalper.py` — `GET /api/scalper/summary` counts `bot_type="scalper"` separately
- `services/truth_kernel.py` — independent count from DB
- `routes/dashboard_overview.py` — `GET /api/dashboard/overview` counts bots independently
- `useDashboardData.js` (frontend hook) — counts from API response
- `useDashboardState.js` (frontend hook) — also counts from overview response

**Domain:** Bot count truth  
**Severity:** HIGH — different counts displayed in different panels

### 5.3 Risk Lock Service — MEDIUM

**Canonical:** `backend/services/risk_lock_service.py` (verified canonical per memory)  
**Issue:** Multiple paths write risk lock state. The trading scheduler, AI bodyguard, and risk management route all interact with daily loss lock. The truth kernel evaluates risk state independently of the risk lock service.  
**Domain:** Risk lock truth  
**Severity:** MEDIUM — canonical service exists but multiple writers increase race condition risk

### 5.4 Paper Trading Engine vs Paper Wallet Service — HIGH

**Files:**
- `backend/paper_trading_engine.py` — legacy paper trading engine
- `backend/services/paper_wallet_service.py` — newer paper wallet service
- `backend/services/paper_wallet_ledger.py` — paper wallet ledger

**Issue:** The `trading_scheduler.py` imports `from paper_trading_engine import paper_engine`. The services/ directory has a separate `paper_wallet_service.py`. Trade fills may be written to different data stores depending on which path is executed.  
**Domain:** Paper trade execution truth  
**Severity:** HIGH

---

## 6. Dashboard Architecture Audit

### 6.1 Two Dashboard UI Generations Coexisting — HIGH

The dashboard has **two generations** of components:

**Generation 1 (OLD):** `frontend/src/components/Dashboard/`
- Components: BotQuarantineSection, BotTrainingSection, CreateBotSection, LivePricesTicker, MetricsOverview, SystemModesSection, TrainingQuarantineSection
- Only `TrainingQuarantineSection` is still used (from BotManagementSection)
- These appear to be self-contained, API-fetching components (no prop drilling)

**Generation 2 (CURRENT):** `frontend/src/pages/dashboard/sections/`
- 27 sections orchestrated by Dashboard.js
- Receive props from the mega-state hook

**Impact:** `BotManagementSection.js` imports the old `TrainingQuarantineSection` from Generation 1. This creates a mixed-generation dependency that will cause issues when either generation changes its API call patterns.  
**Domain:** Dashboard UI architecture  
**Severity:** HIGH

### 6.2 Dashboard.js Double Render Helper Functions — LOW

As noted in §3.7, dead render helper functions `renderProfile()`, `renderWalletHub()`, `renderBots()`, `renderAPIKeys()` are defined but never called in the JSX. The sections are rendered directly in the conditional `{activeSection === NAV.X && ...}` blocks.  
**Domain:** Code quality  
**Severity:** LOW

### 6.3 Dashboard Only Has 11 Nav Items But Sections Provide 27 — HIGH

The `NAV` constant in `dashboardNav.js` defines 11 navigation items. The sections/ directory has 27 files. Even among sections that ARE imported in Dashboard.js, some (like AdminPanelSection, AdminTruthSection) are not listed in NAV — they're conditionally shown. This means:
- `AdminPanelSection` is rendered but not in the public nav (admin-only)
- Sections like BotRadar, ScalperBots, TruthConsole, ExchangeStatus are built but completely inaccessible

**Domain:** Dashboard navigation truth  
**Severity:** HIGH

---

## 7. Duplicate Systems Audit

### 7.1 Email Services (7 files)
See §4.4. **Severity: HIGH**

### 7.2 Platform Configuration (3 frontend files + 1 backend file)
- Frontend: `constants/platforms.js`, `lib/platforms.js`, `config/exchanges.js`
- Backend: `backend/platforms.py` + `backend/core/settings.py` SUPPORTED_EXCHANGES + `backend/exchange_limits.py`
**Severity: HIGH**

### 7.3 Config Modules (3 backend files)
See §4.2. **Severity: HIGH**

### 7.4 Realtime/Event Bus (4 files)
See §4.18. **Severity: HIGH**

### 7.5 Trading Schedulers (4 files)
See §4.17. **Severity: HIGH**

### 7.6 Capital Allocator (2 files)
See §4.10. **Severity: HIGH**

### 7.7 Autopilot Engine (2 files)
See §4.11. **Severity: HIGH**

### 7.8 Live Trading Engine (2 files)
See §4.12. **Severity: HIGH**

### 7.9 AI Command Router (3 files)
See §4.13. **Severity: HIGH**

### 7.10 Bot Pause/Resume/Start Routes (2 router files)
`bot_lifecycle.py` + `bot_control.py` both define pause/resume/start but one is unreachable (see §4.1). **Severity: CRITICAL**

### 7.11 Smoke Test Scripts (20+ files)
```
scripts/smoke.sh, smoke_admin.sh, smoke_ai_chat.sh, smoke_api.sh, 
smoke_api_contract.sh, smoke_backend.sh, smoke_check.py,
smoke_dashboard.sh, smoke_frontend_backend.sh, smoke_full.sh,
smoke_local.sh, smoke_old.sh, smoke_paper_trading.sh, smoke_prod.sh,
smoke_realtime.sh, smoke_sections.sh, smoke_test.py, smoke_test.sh,
smoke_test_comprehensive.py, smoke_user.sh
```
20+ smoke test scripts with no clear canonical one. `smoke_old.sh` is explicitly labeled old but still present.  
**Severity: MEDIUM**

### 7.12 Verify Scripts (20+ files)
```
scripts/verify.sh, verify_ai_chat_enhancement.py, verify_auth_contract.py,
verify_changes.py, verify_clean_deploy.sh, verify_dashboard_endpoints.py,
verify_dashboard_restructure.sh, verify_deployment.py, verify_endpoints.py,
verify_enhancements.py, verify_fix.py, verify_go_live.py, verify_go_live.sh,
verify_go_live_now.sh, verify_go_live_runtime.py, verify_live.sh,
verify_live_ready.sh, verify_no_route_collisions.sh, verify_openapi.sh,
verify_parity.py, verify_platforms.py, verify_production_ready.py,
verify_repo.sh, verify_route_parity.sh, verify_system.py,
verify_trading_mode_gating.py, verify_truth.sh, verify_ui_and_paper_trading.sh
```
28+ verification scripts with significant overlap.  
**Severity: MEDIUM**

### 7.13 Deploy Scripts (5 files)
```
scripts/deploy.sh, deploy_clean.sh, deploy_frontend.sh, deploy_vps.sh
ops/deploy.sh
```
Five deploy scripts. `ops/deploy.sh` is the most polished (idempotent, BUILD_SHA injection, health-check before reload). `scripts/deploy.sh` is a simpler older version. `deploy_vps.sh` and `deploy_clean.sh` may have diverged.  
**Severity: HIGH**

---

## 8. Legacy / Dead Code Audit

### 8.1 backend/_archive/ Still in Repo
**File:** `backend/_archive/platform_constants.py`  
Contains `SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'ovex', 'valr']` — the pre-removal platform list. No production code imports from `_archive`, but the file persists.  
**Severity: HIGH**

### 8.2 Phase Endpoints (5, 6, 8) — Legacy Migration Artifacts
**Files:** `routes/phase5_endpoints.py`, `routes/phase6_endpoints.py`, `routes/phase8_endpoints.py`  
These were "phase" development endpoints that were never cleaned up. They remain mounted in production.  
**Severity: MEDIUM**

### 8.3 compatibility_endpoints.py + compat.py — Both Mounted
**Files:** `routes/compat.py` AND `routes/compatibility_endpoints.py`  
Both provide backward-compatible API shims under `/api`. Comments in `compat.py` call it "DEPRECATED". Both are mounted in server.py. This doubles the surface area of legacy-compat endpoints.  
**Severity: MEDIUM**

### 8.4 Migrations Still in Repo (6 one-shot scripts)
**Files:** `backend/migrations/*.py` (6 files)  
One-shot migration scripts remain in the active codebase. The `fix_user_id_field.py` migration is actually called at startup (`run_startup_migrations`), which runs it on EVERY startup even after the migration has been applied.  
**Severity: HIGH** — running migration logic on every startup adds startup latency and risk

### 8.5 api_key_management.py — Explicitly Removed but File Exists
Server.py comment: `# REMOVED: routes.api_key_management - duplicate of keys`  
The file `backend/routes/api_key_management.py` still exists on disk.  
**Severity: LOW** — not mounted, but confusing

### 8.6 system_health_endpoints.py — Explicitly Removed but File Exists
Server.py comment: `# REMOVED: routes.system_health_endpoints - has duplicate /health/ping`  
The file `backend/routes/system_health_endpoints.py` still exists.  
**Severity: LOW**

### 8.7 Frontend Features.js, Privacy.js, Terms.js, About.js — Dead Pages
See §3.1. These page files are never rendered.  
**Severity: MEDIUM**

### 8.8 docs/archive/ — 55 Stale Documents
**Path:** `docs/archive/` — 55 markdown files  
These are development-era summaries, PR reports, and implementation notes. They describe old architecture and completed tasks. They should not be in the active repo tree.  
**Severity: LOW**

---

## 9. Frontend/Backend Contract Audit

### 9.1 Frontend Calls `/bots/{id}/resume` and `/bots/{id}/start` — Unresolved
**File:** `frontend/src/hooks/useDashboardState.js` line 1281:
```js
await post(`/bots/${botId}/resume`, {});
await post(`/bots/${botId}/start`, {});
```
With `apiClient.baseURL = /api`, these resolve to `/api/bots/{id}/resume` and `/api/bots/{id}/start`.  
`bot_lifecycle.py` has `POST /{bot_id}/resume` under prefix `/api/bots` — this DOES match.  
`bot_control.py` has the same paths but mounted WITHOUT `/api` prefix — so it's at `/bots/{id}/resume` (no `/api`).  
The frontend correctly hits `bot_lifecycle.py`. `bot_control.py` is dead.  
**Domain:** Bot control API contract  
**Severity:** CRITICAL (dead code risk)

### 9.2 Frontend Analytics Calls — MEDIUM
`compat.py` re-exports `GET /api/analytics/performance` as a legacy compat alias for `GET /api/analytics/performance_summary`. If the frontend is still calling `/analytics/performance` (old), it hits the compat layer. New code should call `/analytics/performance_summary` directly.  
**Domain:** Analytics API contract  
**Severity:** MEDIUM

### 9.3 Dashboard Overview — Dual Endpoints
`GET /api/dashboard/overview` and `GET /api/overview/snapshot` are in `dashboard_overview.py`.  
`useDashboardState.js` calls both in different contexts.  
These are separate snapshots but serve overlapping data — bot counts, system mode, profit. Redundant polling of overlapping data.  
**Domain:** Dashboard data contract  
**Severity:** MEDIUM

### 9.4 SSE vs WebSocket — Both Active
**Frontend:** `frontend/src/lib/realtime.js` (SSE client) and `frontend/src/hooks/useRealtime.js` (WebSocket hook) — both are imported in `useDashboardState.js`.  
**Backend:** `routes/realtime.py` (SSE at `/api/realtime/events`) and `routes/websocket.py` (WebSocket at `/api/ws`).  
**Issue:** Two real-time channels simultaneously. State received via SSE and state received via WebSocket may arrive out of order. If a bot state update comes via WebSocket and a price update via SSE, the frontend has two event-reconciliation paths.  
**Domain:** Realtime data truth  
**Severity:** MEDIUM

---

## 10. Reset / Wallet / Performance Truth Audit

### 10.1 Paper Reset Endpoints Across Two Families
**Endpoints:**
- `POST /api/system/paper-reset` — `system_mode.py` — full paper reset
- `POST /api/system/reset-paper` — `system_mode.py` — appears to be the same endpoint with a different path
- `POST /api/system/paper-reset/validate` — validates the reset password before reset
- `POST /api/wallet/paper/reset` — `wallet_hub.py` — resets paper wallet balance

**Issue:** `system/paper-reset` resets trades/analytics. `wallet/paper/reset` resets wallet balance. If only one is called, state will be partially reset. Neither endpoint appears to call the other. A complete paper reset requires hitting at least two different endpoints.  
**Domain:** Reset truth  
**Severity:** HIGH — partial resets leave phantom paper balances or phantom trade history

### 10.2 Analytics Cache After Reset — HIGH
**Issue:** The `analytics_api.py` may serve cached analytics data from before a paper reset. If analytics results are computed from `trades_collection` but a reset only clears trades and not cached summaries, stale performance graphs could persist post-reset.  
**Domain:** Analytics truth after reset  
**Severity:** HIGH

### 10.3 Admin Start Fresh vs User Paper Reset — MEDIUM
**Endpoints:**
- `POST /api/admin/start-fresh` — `admin_start_fresh.py` — admin-level full wipe
- `POST /api/admin/reset-user-data` — `admin_start_fresh.py` — admin resets specific user
- `POST /api/bots/reset` — `admin_start_fresh.py` — admin resets all bots

Three admin reset paths exist for different scopes. The relationship between these and the user-facing paper-reset is undocumented.  
**Domain:** Reset scope truth  
**Severity:** MEDIUM

---

## 11. API Key / Bot / Scalper Truth Audit

### 11.1 API Key Routes — Unified But Partially Shadowed
**Canonical:** `routes/keys.py` with `prefix="/api/keys"`  
**Removed (file exists):** `routes/api_key_management.py`  
**Issue:** `api_key_management.py` file persists even though it was REMOVED from mounting. If someone accidentally re-mounts it, it would conflict with `keys.py`. Provider registry is in `services/provider_registry.py` (11 providers: 7 exchanges + 4 AI).  
**Domain:** API key truth  
**Severity:** LOW (currently)

### 11.2 Scalper Classification — Written One Place, Read Another
**Write path:** `POST /api/scalper` (or bot creation with `bot_type="scalper"`) sets `bot_type: "scalper"` in MongoDB
**Read paths:**
- `routes/scalper.py` queries `{"bot_type": "scalper"}` for scalper-specific metrics
- `routes/bot_lifecycle.py` `GET /api/bots/status` returns ALL bots, callers must filter by `bot_type`
- `routes/dashboard_overview.py` counts bots without distinguishing scalper vs regular
- Frontend `useDashboardState.js` has bot arrays that mix scalper and regular bots

**Issue:** Multiple read paths for scalper vs regular bot classification. The overview count (`activeBots`) may include both scalper and regular bots, while scalper-specific panels expect them separated.  
**Domain:** Bot/scalper truth  
**Severity:** MEDIUM

### 11.3 Bot Status Normalization — Multiple Sources
**File:** `utils/bot_state.py` — `normalize_bot_state()` — canonical  
**Issue:** Multiple call sites normalize bot state differently. `bot_lifecycle.py` uses `normalize_bot_state`, but `autonomous_scheduler.py` and `ai_scheduler.py` may have their own status resolution logic.  
**Domain:** Bot status truth  
**Severity:** MEDIUM

---

## 12. Docs / Readmes / Deployment File Audit

### 12.1 92 Documents in docs/ — CRITICAL (Operational Risk)
The `docs/` directory contains 92 files, 55 of which are in `docs/archive/`. The non-archived 37 docs include:

**Multiple overlapping deploy guides:**
- `DEPLOY.md` (root)
- `docs/DEPLOY.md`
- `docs/DEPLOY_NOTES.md`
- `docs/DEPLOYMENT.md`
- `docs/DEPLOYMENT_GUIDE.md`
- `docs/DEPLOYMENT_CHECKLIST.md`
- `docs/DEPLOY_CHECKLIST.md`
- `docs/CLEAN_DEPLOYMENT.md`
- `docs/GO_LIVE_GUIDE.md`
- `docs/GO_LIVE_DEPLOYMENT.md`
- `docs/VPS_DEPLOYMENT_CHECKLIST.md`
- `docs/deploy/PRODUCTION_DEPLOY.md`

A new engineer faces 12+ deployment documents. Only `ops/deploy.sh` is the actual canonical deployment script.  
**Domain:** Deployment process truth  
**Severity:** CRITICAL

### 12.2 Two Systemd Service Files — CRITICAL

**File 1:** `ops/systemd/amarktai-api.service`
- User: `www-data`
- WorkingDir: `/var/amarktai/app/backend`
- EnvFile: `/etc/amarktai/backend.env` (external, never committed)
- Start: `uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1`
- Restart: `on-failure`

**File 2:** `docs/examples/amarktai.service`
- User: `amarktai`
- WorkingDir: `/opt/amarktai`
- EnvFile: `/opt/amarktai/.env` (inside repo directory!)
- Start: `uvicorn backend.server:app --host 0.0.0.0 --port 8000 --workers 4`
- Restart: `always`

**Critical contradictions:**
1. **Different module path**: `server:app` vs `backend.server:app` — one will fail to start depending on working directory
2. **Binding address**: `127.0.0.1` (correct, behind Nginx) vs `0.0.0.0` (exposed directly)
3. **Workers**: 1 (correct for single-threaded async) vs 4 (creates WebSocket/SSE race conditions)
4. **EnvFile path**: External `/etc/amarktai/backend.env` (secure) vs `/opt/amarktai/.env` (in repo dir)
5. **User**: `www-data` vs `amarktai` — different filesystem permissions

**Domain:** Deployment/systemd truth  
**Severity:** CRITICAL — using the wrong service file can expose the API directly, run wrong module, or crash on start

### 12.3 Root .env.example vs Backend .env.example — Contradictions
See §4.3. The root file uses wrong variable names. The backend file uses both old and new names.  
**Severity: CRITICAL**

### 12.4 README Companion Docs Reference
`README.md` references `DEPLOY.md`, `VERIFICATION.md`, `ACCEPTANCE_TESTS.md` at root. These are real files. But the `docs/` directory has more complete versions. A new user following the README will read the root DEPLOY.md, which may differ from `docs/DEPLOYMENT_GUIDE.md`.  
**Domain:** Documentation truth  
**Severity:** MEDIUM

### 12.5 AUDIT_REPORT.md at Root — Stale
**File:** `AUDIT_REPORT.md` at repo root  
This appears to be from a previous audit pass. It will be superseded by this report.  
**Severity: LOW**

### 12.6 GO_LIVE_TRUTH_AUDIT.md at Root — Stale
**File:** `GO_LIVE_TRUTH_AUDIT.md` at repo root  
Another stale go-live check document.  
**Severity: LOW**

### 12.7 docs/examples/nginx.conf vs ops/nginx/ — Two Nginx Configs
**Files:**
- `docs/examples/nginx.conf` — single server block, no WebSocket upgrade
- `ops/nginx/amarktai.conf` — production nginx config
- `ops/nginx/amarktai-websocket.conf` — WebSocket-specific config

**Issue:** The docs/examples nginx.conf may not include WebSocket proxy headers that are required for `/api/ws`. A deployer using docs/examples/ will get a broken WebSocket.  
**Domain:** Deployment nginx truth  
**Severity:** HIGH

---

## 13. Tests / Coverage / Observability Audit

### 13.1 Two Tests Permanently Ignored — MEDIUM
**pytest.ini** indicates running with:
```
--ignore=tests/test_paper_trade_scenario.py
--ignore=tests/test_canonical_truth.py
```
These tests have pre-existing issues (async plugin requirements) and are permanently excluded from CI. `test_canonical_truth.py` specifically tests canonical truth — the most critical contract to verify.  
**Domain:** Test coverage truth  
**Severity:** MEDIUM

### 13.2 Route Collision Test — exists and passes
**File:** `tests/test_route_collisions.py`  
This test imports `server.py` and checks for duplicate routes. It provides real protection. The server.py also has a startup-time route collision detector. This is double-verified.  
**Domain:** Route truth  
**Severity:** (positive finding)

### 13.3 No Frontend Tests for Critical Hooks — HIGH
`useDashboardState.js` (3,246 lines, 68 API calls) has **zero tests**. `useDashboardData.js` has zero tests. A 3,246-line state management hook with no test coverage is a critical risk.  
**Domain:** Frontend state test coverage  
**Severity:** HIGH

### 13.4 FLOKx Regression Test — Positive Finding
`tests/test_flokx_removal.py` prevents FLOKx re-introduction. Verified working.  
**Severity:** (positive finding)

### 13.5 test_truth_kernel.py — Does It Actually Run? — MEDIUM
**File:** `tests/test_truth_kernel.py`  
If this test runs against a real DB, it could fail in CI since MongoDB won't be available. Need to verify it mocks DB correctly.  
**Domain:** Truth kernel test validity  
**Severity:** MEDIUM

---

## 14. Final Go-Live Blocker List

### CRITICAL BLOCKERS

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| C1 | **CI YAML env indentation bug** *(FIXED in this PR)* | `.github/workflows/ci.yml` | CI env vars not passed to build |
| C2 | **bot_control.py routes at wrong path** — unreachable | `routes/bot_control.py` | Bot control API surface is dead |
| C3 | **Env variable naming contradiction** — root .env.example sets wrong var names | `.env.example`, `backend/config.py` | New deployments have wrong trading defaults |
| C4 | **Two conflicting systemd service files** | `ops/systemd/amarktai-api.service`, `docs/examples/amarktai.service` | Wrong file used = API exposed on 0.0.0.0 with 4 workers |
| C5 | **Trading mode has dual truth** — DB modes vs env vars can contradict | `trading_scheduler.py`, `config.py`, `system_mode.py` | Live trading may run when it should be paper |
| C6 | **Paper reset is split across 4 endpoints** — no single complete reset | `system_mode.py`, `wallet_hub.py` | Partial reset leaves phantom state |

### HIGH SEVERITY RISKS

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| H1 | Three config modules (`config.py`, `config/settings.py`, `core/settings.py`) | Multiple | Configuration divergence |
| H2 | Seven email service files | `email_*.py`, `services/email_*.py` | Email delivery failures silently routed wrong |
| H3 | Two capital allocator implementations | `capital_allocator.py`, `engines/capital_allocator.py` | Wrong capital allocation logic used |
| H4 | Two autopilot engines | `autopilot_engine.py`, `engines/autopilot_production.py` | Autopilot behavior unpredictable |
| H5 | Two live trading engines | `engines/trading_engine_live.py`, `engines/trading_engine_production.py` | Fixes applied to wrong file |
| H6 | Three AI command routers (including `_legacy`) | `services/ai_command_router*.py` | Stale AI logic may be active |
| H7 | 14 dashboard section files completely unused | `pages/dashboard/sections/` | BotRadar, ScalperBots, TruthConsole invisible |
| H8 | Startup migration runs on every boot | `migrations/fix_user_id_field.py` | Startup latency risk |
| H9 | `_archive/platform_constants.py` has OVEX/VALR | `backend/_archive/` | Accidental import gives banned exchanges |
| H10 | Two nginx configs (only one has WebSocket headers) | `docs/examples/nginx.conf`, `ops/nginx/` | WebSocket broken if wrong config used |
| H11 | Three frontend platform sources of truth | `constants/platforms.js`, `lib/platforms.js`, `config/exchanges.js` | Exchange list divergence |
| H12 | 12+ deployment documentation files | `docs/`, root | Deployer confusion, wrong instructions followed |
| H13 | SSE + WebSocket both active simultaneously | `lib/realtime.js`, `hooks/useRealtime.js` | Out-of-order state updates |
| H14 | Analytics stale after paper reset | `analytics_api.py` | Graphs show pre-reset data post-reset |

### MEDIUM SEVERITY (Cleanup)

- Phase 5/6/8 endpoints still mounted (legacy development artifacts)
- `compat.py` AND `compatibility_endpoints.py` both mounted
- Dead frontend pages (Features, Privacy, Terms, About)
- 20+ smoke test scripts with no canonical one
- `bot_control.py` dead (confuses future developers)
- `system_health_endpoints.py` and `api_key_management.py` files exist but unmounted
- Dashboard dead section files (14 of 27)
- Dead components (10 in components/, 6 in components/Dashboard/)
- `dashboard_overview.py` and `admin_start_fresh.py` use hardcoded `/api` in paths

---

## 15. Recommended Go-Live Phase Breakdown

### Phase 0: Immediate Fixes (Pre-Deploy Blockers)
1. ✅ Fix CI YAML indentation (DONE in this PR)
2. Fix `bot_control.py` — either give it correct `/api/bots` prefix, or remove it (routes are dead)
3. Fix root `.env.example` — change `PAPER_TRADING` → `ENABLE_PAPER_TRADING` (with `true/false` values)
4. Choose ONE systemd service file — use `ops/systemd/amarktai-api.service` as canonical, delete `docs/examples/amarktai.service`
5. Consolidate paper reset into one clear complete reset path

### Phase 1: Configuration Truth
1. Consolidate `config.py` + `config/settings.py` + `core/settings.py` into one module
2. Align `backend/.env.example` to match exactly what `config.py` reads
3. Update root `.env.example` or remove it (backend/.env.example is the real one)
4. Choose one `capital_allocator.py` (engines/ or root)
5. Choose one `autopilot_engine.py` (root or engines/autopilot_production.py)
6. Choose one live trading engine (`trading_engine_live.py` or `trading_engine_production.py`)

### Phase 2: Email & Service Deduplication
1. Choose ONE canonical email service file — suggest `services/email_service.py`
2. Archive/delete the other 6 email files
3. Consolidate AI command router — choose one (suggest `ai_command_router_enhanced.py`, delete `_legacy`)
4. Consolidate realtime/WebSocket managers

### Phase 3: Route Cleanup
1. Remove `phase5_endpoints.py`, `phase6_endpoints.py`, `phase8_endpoints.py` from mount list (migrate functionality to canonical routes)
2. Merge `compat.py` + `compatibility_endpoints.py` into single file
3. Unmount and delete `api_key_management.py` and `system_health_endpoints.py`
4. Fix `dashboard_overview.py` and `admin_start_fresh.py` to use `prefix=` instead of hardcoded `/api`
5. Decide on `bot_control.py` fate (fix prefix or delete)

### Phase 4: Frontend Cleanup
1. Add unused sections to Dashboard nav (BotRadar, ScalperBots, TruthConsole, ExchangeStatus) OR delete them
2. Remove dead components (AIChatPanel, AdminApproval, BotLifecycleControls, ComparisonGraphs, LiveTradesPanel, PlatformPanel, TransferCreate, TransferHistory, VersionBadge, WalletOverview)
3. Remove dead pages (Features, Privacy, Terms, About) OR register them in App.js routes
4. Consolidate platform config into `constants/platforms.js` as single source; remove `lib/platforms.js` and `config/exchanges.js`
5. Remove dead components from `components/Dashboard/` (keep only TrainingQuarantineSection)
6. Remove dead render functions from `Dashboard.js`

### Phase 5: Documentation Cleanup
1. Delete or archive all but ONE deploy document (canonical: `ops/deploy.sh` + `docs/INSTALL.md`)
2. Merge all go-live guides into single `GO_LIVE.md`
3. Delete `docs/archive/` from active repo tree (move to GitHub releases or gist)
4. Update README to reference only canonical docs
5. Remove root-level `AUDIT_REPORT.md`, `GO_LIVE_TRUTH_AUDIT.md` (superseded by this report)

### Phase 6: Test Coverage
1. Write tests for `useDashboardState.js` critical paths
2. Restore or rewrite `test_canonical_truth.py` to run without async plugin issues
3. Verify `test_truth_kernel.py` runs correctly in CI without real DB

### Phase 7: Architecture Rationalization (Post Go-Live)
1. Break up `useDashboardState.js` (3,246 lines) into domain-specific hooks
2. Migrate paper_trading_engine.py to use paper_wallet_service.py as the sole engine
3. Establish one realtime channel (either SSE or WebSocket) for each event type
4. Move startup migration (`fix_user_id_field.py`) to a one-time run guard

---

*End of Forensic Audit Report.*  
*This report may be handed directly to an LLM planning session for go-live recovery plan generation.*
